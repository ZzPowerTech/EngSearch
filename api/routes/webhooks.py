"""Twilio WhatsApp webhook route.

POST /webhooks/whatsapp is called by Twilio every time a message is received
on the Neomot WhatsApp number. The route:

1. Identifies the lead by the sender's WhatsApp number.
2. Loads the conversation history from the ``interacoes`` table.
3. Saves the incoming message.
4. Calls the WhatsApp bot to generate a reply.
5. Persists the reply and sends it via Twilio.
6. Applies side-effects based on the new conversation state:
   - EMAIL_SOLICITADO → triggers email dispatch task (Celery) + notifies manager
   - COLETANDO_CONTATO → updates lead record with any extracted contact info
   - AGENDANDO → saves meeting + notifies manager
   - ENCERRADO → marks lead as ``lost`` if still in early stages
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Form, HTTPException

from agents.whatsapp_bot import WhatsappBot
from db.client import get_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

# Singleton — reused across requests (stateless; heavy only because of file reads)
_bot: WhatsappBot | None = None


def _get_bot() -> WhatsappBot:
    global _bot
    if _bot is None:
        _bot = WhatsappBot()
    return _bot


# ────────────────────────────────────────────────────────────────────────────
# State → lead status mapping
# ────────────────────────────────────────────────────────────────────────────
_STATE_TO_STATUS: dict[str, str] = {
    "INTRO": "reception_contacted",
    "AGUARDANDO_INTERESSE": "reception_contacted",
    "EMAIL_SOLICITADO": "email_requested",
    "COLETANDO_CONTATO": "email_sent",
    "AGENDANDO": "contact_requested",
    "ENCERRADO": None,  # handled separately
}


@router.post("/whatsapp")
async def receive_whatsapp(
    From: str = Form(...),
    Body: str = Form(...),
):
    """Handle an incoming WhatsApp message from Twilio."""
    # Twilio sends From as "whatsapp:+5547999999999"
    raw_number = From.replace("whatsapp:", "").lstrip("+")

    db = get_client()

    # ── 1. Identify lead ─────────────────────────────────────────────────
    lead_result = (
        db.table("leads")
        .select("*")
        .eq("whatsapp_recepcao", raw_number)
        .limit(1)
        .execute()
    )
    if not lead_result.data:
        logger.warning("Received WhatsApp from unknown number: %s", raw_number)
        # Return 200 so Twilio doesn't retry
        return {"status": "lead_not_found"}

    lead = lead_result.data[0]
    lead_id = lead["id"]

    # ── 2. Load conversation history ─────────────────────────────────────
    history_result = (
        db.table("interacoes")
        .select("direcao, conteudo")
        .eq("lead_id", lead_id)
        .eq("canal", "whatsapp")
        .order("criado_em")
        .execute()
    )
    history = [
        {
            "role": "assistant" if row["direcao"] == "enviado" else "user",
            "content": row["conteudo"],
        }
        for row in history_result.data
    ]

    # ── 3. Determine current conversation state ──────────────────────────
    current_state = _resolve_state(lead["status"])

    # ── 4. Persist incoming message ──────────────────────────────────────
    db.table("interacoes").insert(
        {
            "lead_id": lead_id,
            "canal": "whatsapp",
            "direcao": "recebido",
            "conteudo": Body,
        }
    ).execute()

    # ── 5. Generate bot reply ────────────────────────────────────────────
    bot = _get_bot()
    try:
        reply = bot.respond(lead, history, Body, current_state)
    except Exception:
        logger.exception("Bot failed to generate reply for lead %s", lead_id)
        raise HTTPException(status_code=500, detail="Bot error")

    bot_message: str = reply["mensagem"]
    new_state: str = reply["novo_estado"]
    extracted: dict = reply.get("dados_extraidos", {})

    # ── 6. Persist bot reply ─────────────────────────────────────────────
    db.table("interacoes").insert(
        {
            "lead_id": lead_id,
            "canal": "whatsapp",
            "direcao": "enviado",
            "conteudo": bot_message,
        }
    ).execute()

    # ── 7. Send via Twilio ───────────────────────────────────────────────
    bot.send_message(raw_number, bot_message)

    # ── 8. Apply state side-effects ──────────────────────────────────────
    _apply_state_effects(db, bot, lead, new_state, extracted)

    return {"status": "ok", "novo_estado": new_state}


# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────

def _resolve_state(lead_status: str) -> str:
    """Map a lead's pipeline status back to a conversation state string."""
    mapping = {
        "discovered": "INTRO",
        "reception_contacted": "AGUARDANDO_INTERESSE",
        "email_requested": "EMAIL_SOLICITADO",
        "email_sent": "COLETANDO_CONTATO",
        "followup_sent": "COLETANDO_CONTATO",
        "contact_requested": "AGENDANDO",
        "meeting_scheduled": "ENCERRADO",
        "lost": "ENCERRADO",
    }
    return mapping.get(lead_status, "INTRO")


def _apply_state_effects(
    db,
    bot: WhatsappBot,
    lead: dict,
    new_state: str,
    extracted: dict,
) -> None:
    """Trigger database updates and notifications based on the new conversation state."""
    lead_id = lead["id"]

    # Update lead status
    new_status = _STATE_TO_STATUS.get(new_state)

    # Merge any extracted contact data into the lead record
    update_payload: dict = {}
    if extracted.get("email_destino"):
        update_payload["email_corporativo"] = extracted["email_destino"]
    if extracted.get("contato_tecnico"):
        update_payload["contato_tecnico"] = extracted["contato_tecnico"]
    if extracted.get("cargo_contato_tecnico"):
        update_payload["cargo_contato_tecnico"] = extracted["cargo_contato_tecnico"]

    if new_state == "ENCERRADO":
        # Only mark as lost if still in early stages
        if lead["status"] in ("discovered", "reception_contacted"):
            update_payload["status"] = "lost"
        # else keep current status (meeting_scheduled stays as-is)
    elif new_status:
        update_payload["status"] = new_status

    if update_payload:
        db.table("leads").update(update_payload).eq("id", lead_id).execute()
        lead.update(update_payload)  # keep local copy fresh

    # EMAIL_SOLICITADO: dispatch email task + notify manager
    if new_state == "EMAIL_SOLICITADO" and extracted.get("email_solicitado"):
        _trigger_email_task(lead_id)
        bot.notify_manager(lead, "📧 E-mail solicitado pela recepção")

    # AGENDANDO with complete meeting data: save meeting + notify manager
    if new_state == "AGENDANDO":
        meeting_data = {
            k: extracted.get(k)
            for k in ("reuniao_data", "reuniao_horario", "reuniao_formato")
        }
        if all(meeting_data.values()):
            bot.schedule_meeting(lead_id, meeting_data)
            bot.notify_manager(lead, "📅 Reunião agendada pelo bot")


def _trigger_email_task(lead_id: str) -> None:
    """Enqueue the email dispatch Celery task (import here to avoid circular deps)."""
    try:
        from tasks.email_task import send_email_task  # noqa: PLC0415
        send_email_task.delay(lead_id)
    except Exception:
        logger.exception("Failed to enqueue email task for lead %s", lead_id)

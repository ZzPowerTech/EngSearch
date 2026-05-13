"""Celery task: 24-hour follow-up for leads that haven't responded.

This task is scheduled 24 hours after the bot sends the initial reception message.
If the lead still hasn't advanced past ``reception_contacted``, the bot sends a
polite follow-up and the manager is notified.
"""
from __future__ import annotations

import logging

from tasks.celery_app import app

logger = logging.getLogger(__name__)

# Message sent if the lead has not responded after 24 hours
FOLLOWUP_MESSAGE = (
    "Olá! 😊 Passando para verificar se recebeu nossa mensagem anterior "
    "sobre soluções em elevadores para a {empresa}. "
    "Caso tenha interesse em mais informações, é só me avisar!"
)


@app.task(bind=True, max_retries=2, default_retry_delay=300)
def send_followup_task(self, lead_id: str) -> dict:
    """Send a 24-hour follow-up WhatsApp message to a lead that hasn't responded.

    Only fires if the lead is still in ``reception_contacted`` status (meaning
    the reception received the intro message but hasn't replied yet).

    Args:
        lead_id: UUID of the lead to follow up with.

    Returns:
        Dict with ``status``: ``"sent"``, ``"skipped"``, or ``"no_whatsapp"``.
    """
    from agents.whatsapp_bot import WhatsappBot  # noqa: PLC0415
    from db.client import get_client  # noqa: PLC0415

    db = get_client()
    bot = WhatsappBot()

    try:
        result = db.table("leads").select("*").eq("id", lead_id).maybe_single().execute()
        if not result.data:
            logger.warning("Followup task: lead %s not found", lead_id)
            return {"status": "lead_not_found"}

        lead = result.data

        # Skip if lead has already advanced — they replied and the pipeline moved on
        if lead["status"] != "reception_contacted":
            logger.info("Lead %s already past reception_contacted (%s); skipping followup", lead_id, lead["status"])
            return {"status": "skipped", "current_status": lead["status"]}

        whatsapp = lead.get("whatsapp_recepcao")
        if not whatsapp:
            logger.warning("Lead %s has no whatsapp_recepcao; skipping followup", lead_id)
            return {"status": "no_whatsapp"}

        message = FOLLOWUP_MESSAGE.format(empresa=lead.get("empresa", "sua empresa"))
        sent = bot.send_message(whatsapp, message)

        if sent:
            # Persist the interaction
            db.table("interacoes").insert(
                {
                    "lead_id": lead_id,
                    "canal": "whatsapp",
                    "direcao": "enviado",
                    "conteudo": message,
                }
            ).execute()

            # Update lead status
            db.table("leads").update({"status": "followup_sent"}).eq("id", lead_id).execute()

            # Notify manager
            bot.notify_manager(lead, "🔔 Follow-up 24h enviado automaticamente")

        return {"status": "sent" if sent else "failed"}

    except Exception as exc:
        logger.exception("Followup task failed for lead %s", lead_id)
        raise self.retry(exc=exc)


def schedule_followup(lead_id: str, delay_seconds: int = 86_400) -> None:
    """Convenience wrapper: enqueue ``send_followup_task`` with a 24-hour delay.

    Called by the webhook after the initial intro message is sent to reception.

    Args:
        lead_id: UUID of the lead.
        delay_seconds: Seconds to wait before firing. Default = 86400 (24 h).
    """
    send_followup_task.apply_async(args=[lead_id], countdown=delay_seconds)
    logger.info("Scheduled 24h follow-up for lead %s (in %ds)", lead_id, delay_seconds)

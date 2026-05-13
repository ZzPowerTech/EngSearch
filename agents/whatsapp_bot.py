"""WhatsApp bot agent — Neo.

Manages the full reception conversation flow:
  INTRO → AGUARDANDO_INTERESSE → EMAIL_SOLICITADO → COLETANDO_CONTATO → AGENDANDO → ENCERRADO

Each call to `respond()` receives the conversation history, the incoming message,
and the current lead record. It returns a structured dict with the bot reply,
the new state, and any data extracted from the conversation.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import anthropic
from twilio.rest import Client as TwilioClient

from db.client import get_client

logger = logging.getLogger(__name__)

BOT_STATES = {
    "INTRO",
    "AGUARDANDO_INTERESSE",
    "EMAIL_SOLICITADO",
    "COLETANDO_CONTATO",
    "AGENDANDO",
    "ENCERRADO",
}


class WhatsappBot:
    """Conversational agent that handles WhatsApp reception flow for EngSearch."""

    def __init__(self) -> None:
        self.claude = anthropic.Anthropic()
        self._persona_template = Path("prompts/whatsapp_persona.md").read_text(encoding="utf-8")
        self._intro_prompt = Path("prompts/reception_intro.md").read_text(encoding="utf-8")
        self.twilio = TwilioClient(
            os.environ["TWILIO_ACCOUNT_SID"],
            os.environ["TWILIO_AUTH_TOKEN"],
        )
        self.whatsapp_from = os.environ["WHATSAPP_FROM"]

    # ------------------------------------------------------------------ #
    # Public interface                                                      #
    # ------------------------------------------------------------------ #

    def build_intro_message(self, empresa: str) -> str:
        """Generate the very first message sent to the reception WhatsApp."""
        prompt = self._intro_prompt.replace("{{empresa}}", empresa)
        response = self.claude.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=256,
            messages=[{"role": "user", "content": f"Empresa: {empresa}"}],
            system=prompt,
        )
        raw = response.content[0].text.strip()
        try:
            data = json.loads(raw)
            return data.get("mensagem", raw)
        except json.JSONDecodeError:
            return raw

    def respond(
        self,
        lead: dict[str, Any],
        history: list[dict],
        incoming: str,
        current_state: str = "INTRO",
    ) -> dict[str, Any]:
        """Generate the next bot reply given conversation context.

        Args:
            lead: Full lead record from the database.
            history: List of ``{"role": ..., "content": ...}`` messages so far.
            incoming: Text of the most recent message received from the lead.
            current_state: Current pipeline state of the conversation.

        Returns:
            Dict with keys ``mensagem``, ``novo_estado``, ``dados_extraidos``.
        """
        system = self._build_system_prompt(lead, current_state)
        messages = history + [{"role": "user", "content": incoming}]

        response = self.claude.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=512,
            system=system,
            messages=messages,
        )

        raw = response.content[0].text.strip()
        return self._parse_response(raw)

    def send_message(self, whatsapp_number: str, text: str) -> bool:
        """Send a WhatsApp message via Twilio.

        Args:
            whatsapp_number: Destination number in E.164 format (e.g. ``5547999999999``).
            text: Message body.

        Returns:
            True if Twilio accepted the request, False on error.
        """
        try:
            self.twilio.messages.create(
                from_=f"whatsapp:{self.whatsapp_from}",
                to=f"whatsapp:+{whatsapp_number}",
                body=text,
            )
            return True
        except Exception:
            logger.exception("Failed to send WhatsApp message to %s", whatsapp_number)
            return False

    def schedule_meeting(self, lead_id: str, dados: dict[str, Any]) -> bool:
        """Persist a meeting to the ``reunioes`` table and update the lead status.

        Args:
            lead_id: UUID of the lead.
            dados: Dict with keys ``reuniao_data``, ``reuniao_horario``, ``reuniao_formato``.

        Returns:
            True if saved successfully.
        """
        db = get_client()
        data_hora = f"{dados['reuniao_data']}T{dados['reuniao_horario']}:00"
        result = db.table("reunioes").insert(
            {
                "lead_id": lead_id,
                "data_hora": data_hora,
                "local": dados.get("reuniao_formato", "vídeo"),
            }
        ).execute()
        if result.data:
            db.table("leads").update({"status": "meeting_scheduled"}).eq("id", lead_id).execute()
            return True
        return False

    def notify_manager(self, lead: dict[str, Any], event: str) -> bool:
        """Send a notification to the Neomot manager's WhatsApp.

        Args:
            lead: Lead record (used to build a summary message).
            event: Short description of what happened (e.g. ``"email solicitado"``).

        Returns:
            True if sent successfully.
        """
        manager_number = os.environ.get("WHATSAPP_GESTOR", "")
        if not manager_number:
            logger.warning("WHATSAPP_GESTOR not set — skipping manager notification")
            return False

        # Normalize number: strip leading +
        manager_number = manager_number.lstrip("+")

        empresa = lead.get("empresa", "empresa desconhecida")
        msg = (
            f"🤖 *EngSearch*: {event}\n"
            f"Empresa: *{empresa}*\n"
            f"WhatsApp recepção: {lead.get('whatsapp_recepcao', 'n/d')}"
        )
        return self.send_message(manager_number, msg)

    # ------------------------------------------------------------------ #
    # Private helpers                                                       #
    # ------------------------------------------------------------------ #

    def _build_system_prompt(self, lead: dict[str, Any], estado: str) -> str:
        dados_coletados = {
            k: lead.get(k)
            for k in ("email_corporativo", "contato_tecnico", "cargo_contato_tecnico")
        }
        return (
            self._persona_template
            .replace("{{estado}}", estado)
            .replace("{{empresa}}", lead.get("empresa", ""))
            .replace("{{dados_coletados}}", json.dumps(dados_coletados, ensure_ascii=False))
        )

    def _parse_response(self, raw: str) -> dict[str, Any]:
        """Parse Claude's JSON response, with fallback for malformed output."""
        # Claude sometimes wraps JSON in markdown code fences
        if raw.startswith("```"):
            lines = raw.splitlines()
            raw = "\n".join(
                line for line in lines if not line.startswith("```")
            ).strip()

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Could not parse bot response as JSON; using raw text")
            data = {
                "mensagem": raw,
                "novo_estado": "AGUARDANDO_INTERESSE",
                "dados_extraidos": {},
            }

        # Validate state
        if data.get("novo_estado") not in BOT_STATES:
            data["novo_estado"] = "AGUARDANDO_INTERESSE"

        # Ensure dados_extraidos always exists
        data.setdefault("dados_extraidos", {})
        return data

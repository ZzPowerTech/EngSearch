"""Email writer agent.

Generates personalised B2B introduction emails using Claude and dispatches
them via SendGrid. Only fires when explicitly requested by the lead's reception
during the WhatsApp conversation.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import anthropic
import sendgrid
from sendgrid.helpers.mail import Mail

from db.client import get_client

logger = logging.getLogger(__name__)


class EmailWriter:
    """Generates and sends personalised presentation emails for EngSearch leads."""

    def __init__(self) -> None:
        self.claude = anthropic.Anthropic()
        self.sg = sendgrid.SendGridAPIClient(os.environ["SENDGRID_API_KEY"])
        self.sender = os.environ["EMAIL_REMETENTE"]
        self._template = Path("prompts/email_template.md").read_text(encoding="utf-8")

    # ------------------------------------------------------------------ #
    # Public interface                                                      #
    # ------------------------------------------------------------------ #

    def can_send(self, lead: dict[str, Any]) -> bool:
        """Return True only if the lead has a corporate email address."""
        return bool(lead.get("email_corporativo"))

    def generate(self, lead: dict[str, Any]) -> dict[str, str]:
        """Generate a personalised email for the given lead using Claude.

        Args:
            lead: Lead record dict (needs ``empresa``, ``segmento``,
                  optionally ``contato_tecnico`` and ``cargo_contato_tecnico``).

        Returns:
            Dict with ``assunto`` and ``corpo`` keys.

        Raises:
            ValueError: If Claude returns malformed JSON.
        """
        system = self._build_system_prompt(lead)
        response = self.claude.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1024,
            system=system,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Empresa: {lead.get('empresa', '')}\n"
                        f"Segmento: {lead.get('segmento', '')}\n"
                        f"Contato técnico: {lead.get('contato_tecnico', 'não informado')}\n"
                        f"Cargo: {lead.get('cargo_contato_tecnico', 'não informado')}"
                    ),
                }
            ],
        )

        raw = response.content[0].text.strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = "\n".join(
                line for line in raw.splitlines() if not line.startswith("```")
            ).strip()

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.error("Failed to parse email JSON from Claude: %s", raw)
            raise ValueError("Claude returned malformed JSON for email generation") from exc

        return {"assunto": data["assunto"], "corpo": data["corpo"]}

    def send(self, lead: dict[str, Any]) -> bool:
        """Generate and dispatch the email for a lead.

        Side effects:
        - Updates the lead's ``status`` to ``email_sent`` in Supabase.
        - Inserts an entry in the ``interacoes`` table.

        Returns:
            True if SendGrid accepted the message (HTTP 202).
        """
        if not self.can_send(lead):
            logger.warning("Lead %s has no email — skipping send", lead.get("id"))
            return False

        email_data = self.generate(lead)
        message = Mail(
            from_email=self.sender,
            to_emails=lead["email_corporativo"],
            subject=email_data["assunto"],
            plain_text_content=email_data["corpo"],
        )

        response = self.sg.send(message)
        success = response.status_code == 202

        if success:
            self._record_interaction(lead, email_data)

        return success

    # ------------------------------------------------------------------ #
    # Private helpers                                                       #
    # ------------------------------------------------------------------ #

    def _build_system_prompt(self, lead: dict[str, Any]) -> str:
        return (
            self._template
            .replace("{{empresa}}", lead.get("empresa", ""))
            .replace("{{segmento}}", lead.get("segmento", ""))
            .replace("{{contato_tecnico}}", lead.get("contato_tecnico") or "não informado")
            .replace(
                "{{cargo_contato_tecnico}}",
                lead.get("cargo_contato_tecnico") or "não informado",
            )
        )

    def _record_interaction(self, lead: dict[str, Any], email_data: dict[str, str]) -> None:
        """Persist the sent email in the ``interacoes`` table and update lead status."""
        db = get_client()
        lead_id = lead["id"]

        db.table("interacoes").insert(
            {
                "lead_id": lead_id,
                "canal": "email",
                "direcao": "enviado",
                "conteudo": f"[{email_data['assunto']}]\n\n{email_data['corpo']}",
            }
        ).execute()

        db.table("leads").update({"status": "email_sent"}).eq("id", lead_id).execute()

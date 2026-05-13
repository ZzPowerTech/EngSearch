"""Tests for the EmailWriter agent."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


SAMPLE_LEAD = {
    "id": "lead-uuid-002",
    "empresa": "Incorporadora Lima",
    "segmento": "incorporadora",
    "email_corporativo": "contato@lima.com.br",
    "contato_tecnico": "Ana Lima",
    "cargo_contato_tecnico": "Diretora de Projetos",
    "status": "email_requested",
}

LEAD_NO_EMAIL = {**SAMPLE_LEAD, "email_corporativo": None}


def _make_writer():
    with (
        patch("agents.email_writer.anthropic.Anthropic"),
        patch("agents.email_writer.sendgrid.SendGridAPIClient"),
        patch("agents.email_writer.get_client"),
        patch("agents.email_writer.Path.read_text", return_value="template prompt"),
        patch.dict("os.environ", {"SENDGRID_API_KEY": "fake", "EMAIL_REMETENTE": "neo@neomot.com.br"}),
    ):
        from agents.email_writer import EmailWriter
        return EmailWriter()


class TestCanSend:
    def test_true_when_email_present(self):
        writer = _make_writer()
        assert writer.can_send(SAMPLE_LEAD) is True

    def test_false_when_email_missing(self):
        writer = _make_writer()
        assert writer.can_send(LEAD_NO_EMAIL) is False

    def test_false_when_email_empty_string(self):
        writer = _make_writer()
        assert writer.can_send({**SAMPLE_LEAD, "email_corporativo": ""}) is False


class TestGenerate:
    def test_returns_assunto_and_corpo(self):
        writer = _make_writer()
        email_payload = {"assunto": "Elevadores para a Lima", "corpo": "Olá Ana, tudo bem?"}
        writer.claude.messages.create.return_value = MagicMock(
            content=[MagicMock(text=json.dumps(email_payload))]
        )

        result = writer.generate(SAMPLE_LEAD)

        assert result["assunto"] == "Elevadores para a Lima"
        assert "corpo" in result

    def test_raises_on_malformed_json(self):
        writer = _make_writer()
        writer.claude.messages.create.return_value = MagicMock(
            content=[MagicMock(text="isso não é json")]
        )

        with pytest.raises(ValueError, match="malformed JSON"):
            writer.generate(SAMPLE_LEAD)

    def test_handles_fenced_json(self):
        writer = _make_writer()
        fenced = "```json\n" + json.dumps({"assunto": "Oi", "corpo": "Corpo aqui"}) + "\n```"
        writer.claude.messages.create.return_value = MagicMock(
            content=[MagicMock(text=fenced)]
        )

        result = writer.generate(SAMPLE_LEAD)
        assert result["assunto"] == "Oi"


class TestSend:
    def test_returns_true_on_sendgrid_202(self):
        writer = _make_writer()
        writer.claude.messages.create.return_value = MagicMock(
            content=[MagicMock(text=json.dumps({"assunto": "Oi", "corpo": "Corpo"}))]
        )
        writer.sg.send.return_value = MagicMock(status_code=202)

        with patch("agents.email_writer.get_client") as mock_db:
            mock_db.return_value.table.return_value.insert.return_value.execute.return_value = MagicMock()
            mock_db.return_value.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()
            result = writer.send(SAMPLE_LEAD)

        assert result is True

    def test_returns_false_when_no_email(self):
        writer = _make_writer()
        result = writer.send(LEAD_NO_EMAIL)
        assert result is False

    def test_returns_false_on_sendgrid_non_202(self):
        writer = _make_writer()
        writer.claude.messages.create.return_value = MagicMock(
            content=[MagicMock(text=json.dumps({"assunto": "Oi", "corpo": "Corpo"}))]
        )
        writer.sg.send.return_value = MagicMock(status_code=400)

        with patch("agents.email_writer.get_client"):
            result = writer.send(SAMPLE_LEAD)

        assert result is False

"""Tests for the WhatsApp bot agent (WhatsappBot)."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

# ── Fixtures ─────────────────────────────────────────────────────────────────

SAMPLE_LEAD = {
    "id": "lead-uuid-001",
    "empresa": "Construtora Silva",
    "segmento": "construtora",
    "whatsapp_recepcao": "5547992731177",
    "email_corporativo": None,
    "contato_tecnico": None,
    "cargo_contato_tecnico": None,
    "status": "reception_contacted",
}


_FAKE_ENV = {
    "TWILIO_ACCOUNT_SID": "AC-fake",
    "TWILIO_AUTH_TOKEN": "fake-token",
    "WHATSAPP_FROM": "+14155238886",
    "WHATSAPP_GESTOR": "+5547992731177",
    "ANTHROPIC_API_KEY": "sk-ant-fake",
}


def _make_bot():
    """Create a WhatsappBot with all external dependencies mocked."""
    with (
        patch.dict("os.environ", _FAKE_ENV),
        patch("agents.whatsapp_bot.anthropic.Anthropic"),
        patch("agents.whatsapp_bot.TwilioClient"),
        patch("agents.whatsapp_bot.get_client"),
        patch("agents.whatsapp_bot.Path.read_text", return_value="system prompt"),
    ):
        from agents.whatsapp_bot import WhatsappBot
        bot = WhatsappBot()
    return bot


# ── Tests: respond() ──────────────────────────────────────────────────────────

class TestRespond:
    def test_returns_valid_structure(self):
        """respond() should always return mensagem, novo_estado, dados_extraidos."""
        bot = _make_bot()
        valid_json = json.dumps({
            "mensagem": "Olá! Como posso ajudar?",
            "novo_estado": "AGUARDANDO_INTERESSE",
            "dados_extraidos": {"email_solicitado": False},
        })
        bot.claude.messages.create.return_value = MagicMock(
            content=[MagicMock(text=valid_json)]
        )

        result = bot.respond(SAMPLE_LEAD, [], "Oi, quem é?")

        assert "mensagem" in result
        assert "novo_estado" in result
        assert "dados_extraidos" in result

    def test_valid_state_is_preserved(self):
        """novo_estado from Claude must be accepted if it is a valid state."""
        bot = _make_bot()
        bot.claude.messages.create.return_value = MagicMock(
            content=[MagicMock(text=json.dumps({
                "mensagem": "Certo!",
                "novo_estado": "EMAIL_SOLICITADO",
                "dados_extraidos": {"email_solicitado": True},
            }))]
        )

        result = bot.respond(SAMPLE_LEAD, [], "Pode me mandar um e-mail?")
        assert result["novo_estado"] == "EMAIL_SOLICITADO"

    def test_invalid_state_falls_back_to_default(self):
        """If Claude returns an unknown state, fall back to AGUARDANDO_INTERESSE."""
        bot = _make_bot()
        bot.claude.messages.create.return_value = MagicMock(
            content=[MagicMock(text=json.dumps({
                "mensagem": "...",
                "novo_estado": "ESTADO_INVALIDO",
                "dados_extraidos": {},
            }))]
        )

        result = bot.respond(SAMPLE_LEAD, [], "algo")
        assert result["novo_estado"] == "AGUARDANDO_INTERESSE"

    def test_malformed_json_falls_back_gracefully(self):
        """If Claude returns non-JSON, use raw text as mensagem and don't crash."""
        bot = _make_bot()
        bot.claude.messages.create.return_value = MagicMock(
            content=[MagicMock(text="Olá! Posso ajudar?")]
        )

        result = bot.respond(SAMPLE_LEAD, [], "oi")
        assert result["mensagem"] == "Olá! Posso ajudar?"
        assert result["novo_estado"] == "AGUARDANDO_INTERESSE"

    def test_markdown_fenced_json_is_parsed(self):
        """Claude sometimes wraps JSON in ```json ... ``` — must be handled."""
        bot = _make_bot()
        fenced = "```json\n" + json.dumps({
            "mensagem": "Ótimo!",
            "novo_estado": "COLETANDO_CONTATO",
            "dados_extraidos": {},
        }) + "\n```"
        bot.claude.messages.create.return_value = MagicMock(
            content=[MagicMock(text=fenced)]
        )

        result = bot.respond(SAMPLE_LEAD, [], "tenho interesse")
        assert result["novo_estado"] == "COLETANDO_CONTATO"


# ── Tests: send_message() ─────────────────────────────────────────────────────

class TestSendMessage:
    def test_returns_true_on_success(self):
        bot = _make_bot()
        bot.twilio.messages.create.return_value = MagicMock()

        result = bot.send_message("5547999999999", "Olá!")
        assert result is True

    def test_returns_false_on_twilio_error(self):
        bot = _make_bot()
        bot.twilio.messages.create.side_effect = Exception("Twilio error")

        result = bot.send_message("5547999999999", "Olá!")
        assert result is False


# ── Tests: schedule_meeting() ─────────────────────────────────────────────────

class TestScheduleMeeting:
    def test_saves_meeting_and_updates_lead(self):
        bot = _make_bot()
        mock_db = MagicMock()
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[{"id": "reuniao-1"}])
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()

        with patch("agents.whatsapp_bot.get_client", return_value=mock_db):
            result = bot.schedule_meeting(
                "lead-uuid-001",
                {"reuniao_data": "2026-06-01", "reuniao_horario": "14:00", "reuniao_formato": "vídeo"},
            )

        assert result is True

    def test_returns_false_when_insert_fails(self):
        bot = _make_bot()
        mock_db = MagicMock()
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[])

        with patch("agents.whatsapp_bot.get_client", return_value=mock_db):
            result = bot.schedule_meeting(
                "lead-uuid-001",
                {"reuniao_data": "2026-06-01", "reuniao_horario": "14:00", "reuniao_formato": "vídeo"},
            )

        assert result is False

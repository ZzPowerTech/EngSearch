"""Tests for the Twilio WhatsApp webhook route."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_db(lead: dict | None = None, history: list | None = None):
    """Build a mock Supabase client that returns the given lead and history."""
    mock_db = MagicMock()

    # leads.select().eq().maybe_single().execute() → lead
    mock_db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
        data=lead
    )

    # interacoes select (history)
    mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
        data=history or []
    )

    # insert / update → always succeed
    mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[{}])
    mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()

    return mock_db


SAMPLE_LEAD = {
    "id": "lead-uuid-003",
    "empresa": "Construtora Horizonte",
    "segmento": "construtora",
    "whatsapp_recepcao": "5547992731177",
    "email_corporativo": None,
    "contato_tecnico": None,
    "cargo_contato_tecnico": None,
    "status": "reception_contacted",
}

BOT_REPLY_INTEREST = json.dumps({
    "mensagem": "Que ótimo! Posso enviar mais informações por e-mail?",
    "novo_estado": "AGUARDANDO_INTERESSE",
    "dados_extraidos": {"email_solicitado": False},
})

BOT_REPLY_EMAIL_REQUEST = json.dumps({
    "mensagem": "Perfeito! Qual o melhor e-mail para enviar?",
    "novo_estado": "EMAIL_SOLICITADO",
    "dados_extraidos": {"email_solicitado": True, "email_destino": None},
})


def _make_app():
    """Return a FastAPI TestClient with all external dependencies mocked."""
    env = {
        "SUPABASE_URL": "http://fake",
        "SUPABASE_SERVICE_KEY": "fake-key",
        "TWILIO_ACCOUNT_SID": "AC-fake",
        "TWILIO_AUTH_TOKEN": "fake-token",
        "WHATSAPP_FROM": "+14155238886",
        "WHATSAPP_GESTOR": "+5547992731177",
        "ANTHROPIC_API_KEY": "sk-ant-fake",
        "SENDGRID_API_KEY": "SG.fake",
        "EMAIL_REMETENTE": "neo@neomot.com.br",
        "REDIS_URL": "redis://localhost:6379/0",
    }
    with patch.dict("os.environ", env):
        with (
            patch("agents.whatsapp_bot.anthropic.Anthropic"),
            patch("agents.whatsapp_bot.TwilioClient"),
            patch("agents.whatsapp_bot.Path.read_text", return_value="prompt"),
            patch("db.client.create_client"),
        ):
            from api.main import app
            return TestClient(app)


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestWebhookWhatsapp:
    def test_unknown_number_returns_lead_not_found(self):
        client = _make_app()
        mock_db = _make_db(lead=None)

        with (
            patch("api.routes.webhooks.get_client", return_value=mock_db),
            patch("api.routes.webhooks._get_bot") as mock_get_bot,
        ):
            mock_get_bot.return_value = MagicMock()
            response = client.post(
                "/webhooks/whatsapp",
                data={"From": "whatsapp:+5511999999999", "Body": "oi"},
            )

        assert response.status_code == 200
        assert response.json()["status"] == "lead_not_found"

    def test_known_number_returns_ok(self):
        client = _make_app()
        mock_db = _make_db(lead=SAMPLE_LEAD, history=[])

        bot_mock = MagicMock()
        bot_mock.respond.return_value = json.loads(BOT_REPLY_INTEREST)
        bot_mock.send_message.return_value = True

        with (
            patch("api.routes.webhooks.get_client", return_value=mock_db),
            patch("api.routes.webhooks._get_bot", return_value=bot_mock),
        ):
            response = client.post(
                "/webhooks/whatsapp",
                data={"From": "whatsapp:+5547992731177", "Body": "Olá, quem é?"},
            )

        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_email_requested_state_triggers_email_task(self):
        """When bot returns EMAIL_SOLICITADO, the email Celery task must be enqueued."""
        client = _make_app()
        mock_db = _make_db(lead=SAMPLE_LEAD, history=[])

        bot_mock = MagicMock()
        bot_mock.respond.return_value = json.loads(BOT_REPLY_EMAIL_REQUEST)
        bot_mock.send_message.return_value = True
        bot_mock.notify_manager.return_value = True

        with (
            patch("api.routes.webhooks.get_client", return_value=mock_db),
            patch("api.routes.webhooks._get_bot", return_value=bot_mock),
            patch("api.routes.webhooks._trigger_email_task") as mock_trigger,
        ):
            response = client.post(
                "/webhooks/whatsapp",
                data={"From": "whatsapp:+5547992731177", "Body": "Pode mandar por e-mail?"},
            )

        assert response.status_code == 200
        mock_trigger.assert_called_once_with(SAMPLE_LEAD["id"])

    def test_conversation_history_is_passed_to_bot(self):
        """History from DB should be converted and passed to bot.respond()."""
        client = _make_app()
        mock_db = _make_db(
            lead=SAMPLE_LEAD,
            history=[
                {"direcao": "enviado", "conteudo": "Olá da Neomot!"},
                {"direcao": "recebido", "conteudo": "Oi, pode explicar?"},
            ],
        )

        bot_mock = MagicMock()
        bot_mock.respond.return_value = json.loads(BOT_REPLY_INTEREST)
        bot_mock.send_message.return_value = True

        with (
            patch("api.routes.webhooks.get_client", return_value=mock_db),
            patch("api.routes.webhooks._get_bot", return_value=bot_mock),
        ):
            client.post(
                "/webhooks/whatsapp",
                data={"From": "whatsapp:+5547992731177", "Body": "Sim, me conta mais"},
            )

        call_args = bot_mock.respond.call_args
        history_passed = call_args[0][1]  # positional arg: history
        assert len(history_passed) == 2
        assert history_passed[0]["role"] == "assistant"
        assert history_passed[1]["role"] == "user"

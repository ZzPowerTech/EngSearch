import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from api.main import app

client = TestClient(app)

MOCK_LEAD = {
    "id": "00000000-0000-0000-0000-000000000001",
    "empresa": "Construtora Silva",
    "segmento": "construtora",
    "whatsapp_recepcao": "5547992731177",
    "email_corporativo": None,
    "contato_tecnico": None,
    "cargo_contato_tecnico": None,
    "instagram_url": "https://instagram.com/construtorasilva",
    "linkedin_url": None,
    "status": "discovered",
    "notas": None,
    "criado_em": "2026-05-13T10:00:00+00:00",
    "atualizado_em": "2026-05-13T10:00:00+00:00",
}


def _mock_db(return_data):
    """Helper: patches get_client so Supabase is never called in tests."""
    mock_client = MagicMock()
    mock_client.table.return_value.insert.return_value.execute.return_value.data = return_data
    mock_client.table.return_value.select.return_value.order.return_value.range.return_value.execute.return_value.data = return_data
    mock_client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = (
        return_data[0] if return_data else None
    )
    mock_client.table.return_value.update.return_value.eq.return_value.execute.return_value.data = return_data
    return mock_client


# ── POST /leads ─────────────────────────────────────────────────────────────

def test_create_lead_returns_201():
    with patch("api.routes.leads.get_client", return_value=_mock_db([MOCK_LEAD])):
        res = client.post("/leads", json={
            "empresa": "Construtora Silva",
            "segmento": "construtora",
            "whatsapp_recepcao": "47 99273-1177",
            "instagram_url": "https://instagram.com/construtorasilva",
        })
    assert res.status_code == 201
    assert res.json()["empresa"] == "Construtora Silva"


def test_whatsapp_normalization():
    """Input '47 99273-1177' should be stored as '5547992731177'."""
    from api.models import LeadCreate
    lead = LeadCreate(empresa="X", whatsapp_recepcao="47 99273-1177")
    assert lead.whatsapp_recepcao == "5547992731177"


def test_whatsapp_already_with_country_code():
    from api.models import LeadCreate
    lead = LeadCreate(empresa="X", whatsapp_recepcao="5547992731177")
    assert lead.whatsapp_recepcao == "5547992731177"


# ── GET /leads ───────────────────────────────────────────────────────────────

def test_list_leads_returns_200():
    with patch("api.routes.leads.get_client", return_value=_mock_db([MOCK_LEAD])):
        res = client.get("/leads")
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_list_leads_filter_by_status():
    with patch("api.routes.leads.get_client") as mock_get:
        mock_client = MagicMock()
        mock_client.table.return_value.select.return_value.eq.return_value.order.return_value.range.return_value.execute.return_value.data = [MOCK_LEAD]
        mock_get.return_value = mock_client
        res = client.get("/leads?status=discovered")
    assert res.status_code == 200


# ── GET /leads/{id} ──────────────────────────────────────────────────────────

def test_get_lead_found():
    with patch("api.routes.leads.get_client", return_value=_mock_db([MOCK_LEAD])):
        res = client.get(f"/leads/{MOCK_LEAD['id']}")
    assert res.status_code == 200
    assert res.json()["id"] == MOCK_LEAD["id"]


def test_get_lead_not_found():
    with patch("api.routes.leads.get_client") as mock_get:
        mock_client = MagicMock()
        mock_client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = None
        mock_get.return_value = mock_client
        res = client.get("/leads/nonexistent-id")
    assert res.status_code == 404


# ── PATCH /leads/{id} ────────────────────────────────────────────────────────

def test_update_lead_status():
    updated = {**MOCK_LEAD, "status": "reception_contacted"}
    with patch("api.routes.leads.get_client", return_value=_mock_db([updated])):
        res = client.patch(f"/leads/{MOCK_LEAD['id']}", json={"status": "reception_contacted"})
    assert res.status_code == 200
    assert res.json()["status"] == "reception_contacted"


def test_update_lead_no_fields_returns_400():
    res = client.patch(f"/leads/{MOCK_LEAD['id']}", json={})
    assert res.status_code == 400


# ── Health ───────────────────────────────────────────────────────────────────

def test_health_endpoint():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"

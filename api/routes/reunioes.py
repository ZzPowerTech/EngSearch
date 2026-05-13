from fastapi import APIRouter, HTTPException
from api.models import ReuniaoCreate, ReuniaoResponse
from db.client import get_client

router = APIRouter(prefix="/reunioes", tags=["reunioes"])


@router.post("", response_model=ReuniaoResponse, status_code=201)
async def create_reuniao(reuniao: ReuniaoCreate):
    """Schedule a meeting and update the lead status to meeting_scheduled."""
    client = get_client()
    payload = reuniao.model_dump(exclude_none=True)
    payload["lead_id"] = str(payload["lead_id"])
    if payload.get("data_hora"):
        payload["data_hora"] = payload["data_hora"].isoformat()

    result = client.table("reunioes").insert(payload).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to schedule meeting")

    # Update lead status
    client.table("leads").update({"status": "meeting_scheduled"}).eq(
        "id", str(reuniao.lead_id)
    ).execute()

    return result.data[0]


@router.get("/lead/{lead_id}", response_model=list[ReuniaoResponse])
async def list_reunioes_by_lead(lead_id: str):
    """List all meetings for a given lead."""
    client = get_client()
    result = (
        client.table("reunioes")
        .select("*")
        .eq("lead_id", lead_id)
        .order("criado_em", desc=True)
        .execute()
    )
    return result.data

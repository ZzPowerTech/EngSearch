from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from api.models import LeadCreate, LeadUpdate, LeadResponse, LeadStatus
from db.client import get_client

router = APIRouter(prefix="/leads", tags=["leads"])


@router.post("", response_model=LeadResponse, status_code=201)
async def create_lead(lead: LeadCreate):
    """Create a new lead. Deduplicates by instagram_url if provided."""
    client = get_client()
    payload = lead.model_dump(exclude_none=True)

    result = client.table("leads").insert(payload).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create lead")
    return result.data[0]


@router.get("", response_model=list[LeadResponse])
async def list_leads(
    status: Optional[LeadStatus] = Query(None, description="Filter by pipeline status"),
    segmento: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """List leads with optional filters."""
    client = get_client()
    query = client.table("leads").select("*")

    if status:
        query = query.eq("status", status)
    if segmento:
        query = query.eq("segmento", segmento)

    result = (
        query.order("criado_em", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    )
    return result.data


@router.get("/{lead_id}", response_model=LeadResponse)
async def get_lead(lead_id: str):
    """Fetch a single lead by ID."""
    client = get_client()
    result = client.table("leads").select("*").eq("id", lead_id).limit(1).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Lead not found")
    return result.data[0]


@router.patch("/{lead_id}", response_model=LeadResponse)
async def update_lead(lead_id: str, update: LeadUpdate):
    """Partially update a lead (status, contact info, notes, etc.)."""
    payload = update.model_dump(exclude_none=True)
    if not payload:
        raise HTTPException(status_code=400, detail="No fields to update")
    client = get_client()

    result = (
        client.table("leads")
        .update(payload)
        .eq("id", lead_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Lead not found")
    return result.data[0]


@router.delete("/{lead_id}", status_code=204)
async def delete_lead(lead_id: str):
    """Delete a lead and all its interactions (cascade)."""
    client = get_client()
    client.table("leads").delete().eq("id", lead_id).execute()

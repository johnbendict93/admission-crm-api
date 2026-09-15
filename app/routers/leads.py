from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from postgrest.exceptions import APIError
from supabase import Client

from app.core.database import get_supabase_client
from app.core.security import verify_api_key
from app.models.leads import LeadCreate, LeadResponse, LeadUpdate
from app.services import leads_service

router = APIRouter(prefix="/leads", tags=["Leads"], dependencies=[Depends(verify_api_key)])


@router.get("/", response_model=List[LeadResponse])
def list_leads(
    limit: int = Query(50, ge=1, le=200, description="Rows per page (max 200)"),
    offset: int = Query(0, ge=0),
    supabase: Client = Depends(get_supabase_client),
):
    try:
        return leads_service.get_all_leads(supabase, limit=limit, offset=offset)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")


@router.get("/{lead_id}", response_model=LeadResponse)
def get_lead(lead_id: str, supabase: Client = Depends(get_supabase_client)):
    try:
        lead = leads_service.get_lead_by_id(supabase, lead_id)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


@router.post("/", response_model=LeadResponse, status_code=201)
def create_lead(lead: LeadCreate, supabase: Client = Depends(get_supabase_client)):
    try:
        created = leads_service.create_lead(supabase, lead)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not created:
        raise HTTPException(status_code=500, detail="Insert succeeded but no data was returned")
    return created


@router.patch("/{lead_id}", response_model=LeadResponse)
def update_lead(lead_id: str, lead: LeadUpdate, supabase: Client = Depends(get_supabase_client)):
    payload = lead.model_dump(exclude_unset=True)
    if not payload:
        raise HTTPException(status_code=400, detail="No fields provided to update")
    try:
        updated = leads_service.update_lead(supabase, lead_id, payload)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not updated:
        raise HTTPException(status_code=404, detail="Lead not found")
    return updated


@router.delete("/{lead_id}", status_code=204)
def delete_lead(lead_id: str, supabase: Client = Depends(get_supabase_client)):
    try:
        deleted = leads_service.delete_lead(supabase, lead_id)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not deleted:
        raise HTTPException(status_code=404, detail="Lead not found")
    return None

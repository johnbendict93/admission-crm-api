from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from postgrest.exceptions import APIError
from supabase import Client

from app.core.database import get_supabase_client
from app.core.security import verify_api_key
from app.models.applicants import ApplicantCreate, ApplicantResponse, ApplicantUpdate
from app.services import applicants_service

router = APIRouter(prefix="/applicants", tags=["Applicants"], dependencies=[Depends(verify_api_key)])


@router.get("/", response_model=List[ApplicantResponse])
def list_applicants(
    limit: int = Query(50, ge=1, le=200, description="Rows per page (max 200)"),
    offset: int = Query(0, ge=0),
    supabase: Client = Depends(get_supabase_client),
):
    try:
        return applicants_service.get_all_applicants(supabase, limit=limit, offset=offset)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")


@router.get("/{applicant_id}", response_model=ApplicantResponse)
def get_applicant(applicant_id: str, supabase: Client = Depends(get_supabase_client)):
    try:
        applicant = applicants_service.get_applicant_by_id(supabase, applicant_id)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not applicant:
        raise HTTPException(status_code=404, detail="Applicant not found")
    return applicant


@router.post("/", response_model=ApplicantResponse, status_code=201)
def create_applicant(applicant: ApplicantCreate, supabase: Client = Depends(get_supabase_client)):
    try:
        created = applicants_service.create_applicant(supabase, applicant)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not created:
        raise HTTPException(status_code=500, detail="Insert succeeded but no data was returned")
    return created


@router.patch("/{applicant_id}", response_model=ApplicantResponse)
def update_applicant(applicant_id: str, applicant: ApplicantUpdate, supabase: Client = Depends(get_supabase_client)):
    payload = applicant.model_dump(exclude_unset=True, mode="json")
    if not payload:
        raise HTTPException(status_code=400, detail="No fields provided to update")
    try:
        updated = applicants_service.update_applicant(supabase, applicant_id, payload)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not updated:
        raise HTTPException(status_code=404, detail="Applicant not found")
    return updated


@router.delete("/{applicant_id}", status_code=204)
def delete_applicant(applicant_id: str, supabase: Client = Depends(get_supabase_client)):
    try:
        deleted = applicants_service.delete_applicant(supabase, applicant_id)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not deleted:
        raise HTTPException(status_code=404, detail="Applicant not found")
    return None

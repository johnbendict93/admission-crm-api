from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from postgrest.exceptions import APIError
from supabase import Client

from app.core.database import get_supabase_client
from app.core.jwt_auth import get_current_user, require_deleter, require_writer
from app.models.scholarships import ScholarshipCreate, ScholarshipResponse, ScholarshipUpdate
from app.services import scholarships_service

router = APIRouter(prefix="/scholarships", tags=["Scholarships"])


@router.get("/", response_model=List[ScholarshipResponse])
def list_scholarships(
    limit: int = Query(50, ge=1, le=200, description="Rows per page (max 200)"),
    offset: int = Query(0, ge=0),
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(get_current_user),
):
    try:
        return scholarships_service.get_all_scholarships(supabase, limit=limit, offset=offset)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")


@router.get("/{scholarship_id}", response_model=ScholarshipResponse)
def get_scholarship(
    scholarship_id: str,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(get_current_user),
):
    try:
        scholarship = scholarships_service.get_scholarship_by_id(supabase, scholarship_id)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not scholarship:
        raise HTTPException(status_code=404, detail="Scholarship not found")
    return scholarship


@router.post("/", response_model=ScholarshipResponse, status_code=201)
def create_scholarship(
    scholarship: ScholarshipCreate,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(require_writer),
):
    try:
        created = scholarships_service.create_scholarship(supabase, scholarship)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not created:
        raise HTTPException(status_code=500, detail="Insert succeeded but no data was returned")
    return created


@router.patch("/{scholarship_id}", response_model=ScholarshipResponse)
def update_scholarship(
    scholarship_id: str,
    scholarship: ScholarshipUpdate,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(require_writer),
):
    payload = scholarship.model_dump(exclude_unset=True, mode="json")
    if not payload:
        raise HTTPException(status_code=400, detail="No fields provided to update")
    try:
        updated = scholarships_service.update_scholarship(supabase, scholarship_id, payload)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not updated:
        raise HTTPException(status_code=404, detail="Scholarship not found")
    return updated


@router.delete("/{scholarship_id}", status_code=204)
def delete_scholarship(
    scholarship_id: str,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(require_deleter),
):
    try:
        deleted = scholarships_service.delete_scholarship(supabase, scholarship_id, deleted_by=current_user["id"])
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not deleted:
        raise HTTPException(status_code=404, detail="Scholarship not found")
    return None

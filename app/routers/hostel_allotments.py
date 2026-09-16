from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from postgrest.exceptions import APIError
from supabase import Client

from app.core.database import get_supabase_client
from app.core.jwt_auth import get_current_user, require_deleter, require_writer
from app.models.hostel_allotments import (
    HostelAllotmentCreate,
    HostelAllotmentResponse,
    HostelAllotmentUpdate,
)
from app.services import hostel_allotments_service

router = APIRouter(prefix="/hostel-allotments", tags=["Hostel Allotments"])


@router.get("/", response_model=List[HostelAllotmentResponse])
def list_hostel_allotments(
    limit: int = Query(50, ge=1, le=200, description="Rows per page (max 200)"),
    offset: int = Query(0, ge=0),
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(get_current_user),
):
    try:
        return hostel_allotments_service.get_all_hostel_allotments(supabase, limit=limit, offset=offset)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")


@router.get("/{hostel_allotment_id}", response_model=HostelAllotmentResponse)
def get_hostel_allotment(
    hostel_allotment_id: str,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(get_current_user),
):
    try:
        hostel_allotment = hostel_allotments_service.get_hostel_allotment_by_id(supabase, hostel_allotment_id)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not hostel_allotment:
        raise HTTPException(status_code=404, detail="Hostel allotment not found")
    return hostel_allotment


@router.post("/", response_model=HostelAllotmentResponse, status_code=201)
def create_hostel_allotment(
    hostel_allotment: HostelAllotmentCreate,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(require_writer),
):
    try:
        created = hostel_allotments_service.create_hostel_allotment(supabase, hostel_allotment)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not created:
        raise HTTPException(status_code=500, detail="Insert succeeded but no data was returned")
    return created


@router.patch("/{hostel_allotment_id}", response_model=HostelAllotmentResponse)
def update_hostel_allotment(
    hostel_allotment_id: str,
    hostel_allotment: HostelAllotmentUpdate,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(require_writer),
):
    payload = hostel_allotment.model_dump(exclude_unset=True, mode="json")
    if not payload:
        raise HTTPException(status_code=400, detail="No fields provided to update")
    try:
        updated = hostel_allotments_service.update_hostel_allotment(supabase, hostel_allotment_id, payload)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not updated:
        raise HTTPException(status_code=404, detail="Hostel allotment not found")
    return updated


@router.delete("/{hostel_allotment_id}", status_code=204)
def delete_hostel_allotment(
    hostel_allotment_id: str,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(require_deleter),
):
    try:
        deleted = hostel_allotments_service.delete_hostel_allotment(
            supabase, hostel_allotment_id, deleted_by=current_user["id"]
        )
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not deleted:
        raise HTTPException(status_code=404, detail="Hostel allotment not found")
    return None

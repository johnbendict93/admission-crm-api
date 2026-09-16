from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from postgrest.exceptions import APIError
from supabase import Client

from app.core.database import get_supabase_client
from app.core.jwt_auth import get_current_user, require_deleter, require_writer
from app.models.telecallers import TelecallerCreate, TelecallerResponse, TelecallerUpdate
from app.services import telecallers_service

router = APIRouter(prefix="/telecallers", tags=["Telecallers"])


@router.get("/", response_model=List[TelecallerResponse])
def list_telecallers(
    limit: int = Query(50, ge=1, le=200, description="Rows per page (max 200)"),
    offset: int = Query(0, ge=0),
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(get_current_user),
):
    try:
        return telecallers_service.get_all_telecallers(supabase, limit=limit, offset=offset)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")


@router.get("/{telecaller_id}", response_model=TelecallerResponse)
def get_telecaller(
    telecaller_id: str,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(get_current_user),
):
    try:
        telecaller = telecallers_service.get_telecaller_by_id(supabase, telecaller_id)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not telecaller:
        raise HTTPException(status_code=404, detail="Telecaller not found")
    return telecaller


@router.post("/", response_model=TelecallerResponse, status_code=201)
def create_telecaller(
    telecaller: TelecallerCreate,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(require_writer),
):
    try:
        created = telecallers_service.create_telecaller(supabase, telecaller)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not created:
        raise HTTPException(status_code=500, detail="Insert succeeded but no data was returned")
    return created


@router.patch("/{telecaller_id}", response_model=TelecallerResponse)
def update_telecaller(
    telecaller_id: str,
    telecaller: TelecallerUpdate,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(require_writer),
):
    payload = telecaller.model_dump(exclude_unset=True, mode="json")
    if not payload:
        raise HTTPException(status_code=400, detail="No fields provided to update")
    try:
        updated = telecallers_service.update_telecaller(supabase, telecaller_id, payload)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not updated:
        raise HTTPException(status_code=404, detail="Telecaller not found")
    return updated


@router.delete("/{telecaller_id}", status_code=204)
def delete_telecaller(
    telecaller_id: str,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(require_deleter),
):
    try:
        deleted = telecallers_service.delete_telecaller(supabase, telecaller_id, deleted_by=current_user["id"])
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not deleted:
        raise HTTPException(status_code=404, detail="Telecaller not found")
    return None

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from postgrest.exceptions import APIError
from supabase import Client

from app.core.database import get_supabase_client
from app.core.jwt_auth import get_current_user, require_deleter, require_writer
from app.models.lookup_values import LookupValueCreate, LookupValueResponse, LookupValueUpdate
from app.services import lookup_values_service

router = APIRouter(prefix="/lookup-values", tags=["Lookup Values"])


@router.get("/", response_model=List[LookupValueResponse])
def list_lookup_values(
    limit: int = Query(50, ge=1, le=200, description="Rows per page (max 200)"),
    offset: int = Query(0, ge=0),
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(get_current_user),
):
    try:
        return lookup_values_service.get_all_lookup_values(supabase, limit=limit, offset=offset)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")


@router.get("/{lookup_value_id}", response_model=LookupValueResponse)
def get_lookup_value(
    lookup_value_id: str,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(get_current_user),
):
    try:
        lookup_value = lookup_values_service.get_lookup_value_by_id(supabase, lookup_value_id)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not lookup_value:
        raise HTTPException(status_code=404, detail="Lookup value not found")
    return lookup_value


@router.post("/", response_model=LookupValueResponse, status_code=201)
def create_lookup_value(
    lookup_value: LookupValueCreate,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(require_writer),
):
    try:
        created = lookup_values_service.create_lookup_value(supabase, lookup_value)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not created:
        raise HTTPException(status_code=500, detail="Insert succeeded but no data was returned")
    return created


@router.patch("/{lookup_value_id}", response_model=LookupValueResponse)
def update_lookup_value(
    lookup_value_id: str,
    lookup_value: LookupValueUpdate,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(require_writer),
):
    payload = lookup_value.model_dump(exclude_unset=True, mode="json")
    if not payload:
        raise HTTPException(status_code=400, detail="No fields provided to update")
    try:
        updated = lookup_values_service.update_lookup_value(supabase, lookup_value_id, payload)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not updated:
        raise HTTPException(status_code=404, detail="Lookup value not found")
    return updated


@router.delete("/{lookup_value_id}", status_code=204)
def delete_lookup_value(
    lookup_value_id: str,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(require_deleter),
):
    try:
        deleted = lookup_values_service.delete_lookup_value(supabase, lookup_value_id)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not deleted:
        raise HTTPException(status_code=404, detail="Lookup value not found")
    return None

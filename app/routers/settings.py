from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from postgrest.exceptions import APIError
from supabase import Client

from app.core.database import get_supabase_client
from app.core.jwt_auth import get_current_user, require_deleter, require_writer
from app.models.settings import SettingCreate, SettingResponse, SettingUpdate
from app.models.pagination import PaginatedResponse
from app.services import settings_service

router = APIRouter(prefix="/settings", tags=["Settings"])


@router.get("/", response_model=PaginatedResponse[SettingResponse])
def list_settings(
    limit: int = Query(50, ge=1, le=200, description="Rows per page (max 200)"),
    offset: int = Query(0, ge=0),
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(get_current_user),
):
    """List settings, most recently created first, excluding inactive rows."""
    try:
        items, total = settings_service.get_all_settings(supabase, limit=limit, offset=offset)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    return PaginatedResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        has_more=offset + len(items) < total,
    )


@router.get("/{setting_id}", response_model=SettingResponse)
def get_setting(
    setting_id: str,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(get_current_user),
):
    """Get a single setting by id."""
    try:
        setting = settings_service.get_setting_by_id(supabase, setting_id)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not setting:
        raise HTTPException(status_code=404, detail="Setting not found")
    return setting


@router.post("/", response_model=SettingResponse, status_code=201)
def create_setting(
    setting: SettingCreate,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(require_writer),
):
    """Create a new setting."""
    try:
        created = settings_service.create_setting(supabase, setting)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not created:
        raise HTTPException(status_code=500, detail="Insert succeeded but no data was returned")
    return created


@router.patch("/{setting_id}", response_model=SettingResponse)
def update_setting(
    setting_id: str,
    setting: SettingUpdate,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(require_writer),
):
    """Partially update a setting by id - only the fields provided are changed."""
    payload = setting.model_dump(exclude_unset=True, mode="json")
    if not payload:
        raise HTTPException(status_code=400, detail="No fields provided to update")
    try:
        updated = settings_service.update_setting(supabase, setting_id, payload)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not updated:
        raise HTTPException(status_code=404, detail="Setting not found")
    return updated


@router.delete("/{setting_id}", status_code=204)
def delete_setting(
    setting_id: str,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(require_deleter),
):
    """Deactivate a setting by id (sets is_active to false; the row is preserved)."""
    try:
        deleted = settings_service.delete_setting(supabase, setting_id)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not deleted:
        raise HTTPException(status_code=404, detail="Setting not found")
    return None

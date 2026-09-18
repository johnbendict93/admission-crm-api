from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from postgrest.exceptions import APIError
from supabase import Client

from app.core.database import get_supabase_client
from app.core.jwt_auth import get_current_user, require_deleter, require_writer
from app.models.followups import FollowupCreate, FollowupResponse, FollowupUpdate
from app.models.pagination import PaginatedResponse
from app.services import followups_service

router = APIRouter(prefix="/followups", tags=["Followups"])


@router.get("/", response_model=PaginatedResponse[FollowupResponse])
def list_followups(
    limit: int = Query(50, ge=1, le=200, description="Rows per page (max 200)"),
    offset: int = Query(0, ge=0),
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(get_current_user),
):
    """List follow-ups, most recently created first, excluding soft-deleted rows."""
    try:
        items, total = followups_service.get_all_followups(supabase, limit=limit, offset=offset)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    return PaginatedResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        has_more=offset + len(items) < total,
    )


@router.get("/{followup_id}", response_model=FollowupResponse)
def get_followup(
    followup_id: str,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(get_current_user),
):
    """Get a single follow-up by id."""
    try:
        followup = followups_service.get_followup_by_id(supabase, followup_id)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not followup:
        raise HTTPException(status_code=404, detail="Followup not found")
    return followup


@router.post("/", response_model=FollowupResponse, status_code=201)
def create_followup(
    followup: FollowupCreate,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(require_writer),
):
    """Create a new follow-up."""
    try:
        created = followups_service.create_followup(supabase, followup)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not created:
        raise HTTPException(status_code=500, detail="Insert succeeded but no data was returned")
    return created


@router.patch("/{followup_id}", response_model=FollowupResponse)
def update_followup(
    followup_id: str,
    followup: FollowupUpdate,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(require_writer),
):
    """Partially update a follow-up by id - only the fields provided are changed."""
    payload = followup.model_dump(exclude_unset=True, mode="json")
    if not payload:
        raise HTTPException(status_code=400, detail="No fields provided to update")
    try:
        updated = followups_service.update_followup(supabase, followup_id, payload)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not updated:
        raise HTTPException(status_code=404, detail="Followup not found")
    return updated


@router.delete("/{followup_id}", status_code=204)
def delete_followup(
    followup_id: str,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(require_deleter),
):
    """Soft-delete a follow-up by id (sets deleted_at/deleted_by; the row is preserved)."""
    try:
        deleted = followups_service.delete_followup(supabase, followup_id, deleted_by=current_user["id"])
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not deleted:
        raise HTTPException(status_code=404, detail="Followup not found")
    return None

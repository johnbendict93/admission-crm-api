from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from postgrest.exceptions import APIError
from supabase import Client

from app.core.database import get_supabase_client
from app.core.jwt_auth import get_current_user, require_deleter, require_writer
from app.models.counseling_sessions import (
    CounselingSessionCreate,
    CounselingSessionResponse,
    CounselingSessionUpdate,
)
from app.models.pagination import PaginatedResponse
from app.services import counseling_sessions_service

router = APIRouter(prefix="/counseling-sessions", tags=["Counseling Sessions"])


@router.get("/", response_model=PaginatedResponse[CounselingSessionResponse])
def list_counseling_sessions(
    limit: int = Query(50, ge=1, le=200, description="Rows per page (max 200)"),
    offset: int = Query(0, ge=0),
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(get_current_user),
):
    """List counseling sessions, most recently created first, excluding soft-deleted rows."""
    try:
        items, total = counseling_sessions_service.get_all_counseling_sessions(supabase, limit=limit, offset=offset)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    return PaginatedResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        has_more=offset + len(items) < total,
    )


@router.get("/{counseling_session_id}", response_model=CounselingSessionResponse)
def get_counseling_session(
    counseling_session_id: str,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(get_current_user),
):
    """Get a single counseling session by id."""
    try:
        counseling_session = counseling_sessions_service.get_counseling_session_by_id(
            supabase, counseling_session_id
        )
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not counseling_session:
        raise HTTPException(status_code=404, detail="Counseling session not found")
    return counseling_session


@router.post("/", response_model=CounselingSessionResponse, status_code=201)
def create_counseling_session(
    counseling_session: CounselingSessionCreate,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(require_writer),
):
    """Create a new counseling session."""
    try:
        created = counseling_sessions_service.create_counseling_session(supabase, counseling_session)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not created:
        raise HTTPException(status_code=500, detail="Insert succeeded but no data was returned")
    return created


@router.patch("/{counseling_session_id}", response_model=CounselingSessionResponse)
def update_counseling_session(
    counseling_session_id: str,
    counseling_session: CounselingSessionUpdate,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(require_writer),
):
    """Partially update a counseling session by id - only the fields provided are changed."""
    payload = counseling_session.model_dump(exclude_unset=True, mode="json")
    if not payload:
        raise HTTPException(status_code=400, detail="No fields provided to update")
    try:
        updated = counseling_sessions_service.update_counseling_session(
            supabase, counseling_session_id, payload
        )
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not updated:
        raise HTTPException(status_code=404, detail="Counseling session not found")
    return updated


@router.delete("/{counseling_session_id}", status_code=204)
def delete_counseling_session(
    counseling_session_id: str,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(require_deleter),
):
    """Soft-delete a counseling session by id (sets deleted_at/deleted_by; the row is preserved)."""
    try:
        deleted = counseling_sessions_service.delete_counseling_session(
            supabase, counseling_session_id, deleted_by=current_user["id"]
        )
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not deleted:
        raise HTTPException(status_code=404, detail="Counseling session not found")
    return None

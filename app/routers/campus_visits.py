from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from postgrest.exceptions import APIError
from supabase import Client

from app.core.database import get_supabase_client
from app.core.jwt_auth import get_current_user, require_deleter, require_writer
from app.models.campus_visits import CampusVisitCreate, CampusVisitResponse, CampusVisitUpdate
from app.models.pagination import PaginatedResponse
from app.services import campus_visits_service

router = APIRouter(prefix="/campus-visits", tags=["Campus Visits"])


@router.get("/", response_model=PaginatedResponse[CampusVisitResponse])
def list_campus_visits(
    limit: int = Query(50, ge=1, le=200, description="Rows per page (max 200)"),
    offset: int = Query(0, ge=0),
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(get_current_user),
):
    """List campus visits, most recently created first, excluding soft-deleted rows."""
    try:
        items, total = campus_visits_service.get_all_campus_visits(supabase, limit=limit, offset=offset)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    return PaginatedResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        has_more=offset + len(items) < total,
    )


@router.get("/{campus_visit_id}", response_model=CampusVisitResponse)
def get_campus_visit(
    campus_visit_id: str,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(get_current_user),
):
    """Get a single campus visit by id."""
    try:
        campus_visit = campus_visits_service.get_campus_visit_by_id(supabase, campus_visit_id)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not campus_visit:
        raise HTTPException(status_code=404, detail="Campus visit not found")
    return campus_visit


@router.post("/", response_model=CampusVisitResponse, status_code=201)
def create_campus_visit(
    campus_visit: CampusVisitCreate,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(require_writer),
):
    """Create a new campus visit."""
    try:
        created = campus_visits_service.create_campus_visit(supabase, campus_visit)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not created:
        raise HTTPException(status_code=500, detail="Insert succeeded but no data was returned")
    return created


@router.patch("/{campus_visit_id}", response_model=CampusVisitResponse)
def update_campus_visit(
    campus_visit_id: str,
    campus_visit: CampusVisitUpdate,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(require_writer),
):
    """Partially update a campus visit by id - only the fields provided are changed."""
    payload = campus_visit.model_dump(exclude_unset=True, mode="json")
    if not payload:
        raise HTTPException(status_code=400, detail="No fields provided to update")
    try:
        updated = campus_visits_service.update_campus_visit(supabase, campus_visit_id, payload)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not updated:
        raise HTTPException(status_code=404, detail="Campus visit not found")
    return updated


@router.delete("/{campus_visit_id}", status_code=204)
def delete_campus_visit(
    campus_visit_id: str,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(require_deleter),
):
    """Soft-delete a campus visit by id (sets deleted_at/deleted_by; the row is preserved)."""
    try:
        deleted = campus_visits_service.delete_campus_visit(
            supabase, campus_visit_id, deleted_by=current_user["id"]
        )
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not deleted:
        raise HTTPException(status_code=404, detail="Campus visit not found")
    return None

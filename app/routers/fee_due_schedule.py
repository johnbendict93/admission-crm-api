from fastapi import APIRouter, Depends, HTTPException, Query
from postgrest.exceptions import APIError
from supabase import Client

from app.core.database import get_supabase_client
from app.core.jwt_auth import get_current_user, require_deleter, require_writer
from app.models.fee_due_schedule import FeeDueScheduleCreate, FeeDueScheduleResponse, FeeDueScheduleUpdate
from app.models.pagination import PaginatedResponse
from app.services import fee_due_schedule_service

router = APIRouter(prefix="/fee-due-schedule", tags=["Fee Due Schedule"])


@router.get("/", response_model=PaginatedResponse[FeeDueScheduleResponse])
def list_fee_due_schedules(
    limit: int = Query(50, ge=1, le=200, description="Rows per page (max 200)"),
    offset: int = Query(0, ge=0),
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(get_current_user),
):
    """List fee due-schedule rows, earliest due date first, excluding soft-deleted rows."""
    try:
        items, total = fee_due_schedule_service.get_all_fee_due_schedules(supabase, limit=limit, offset=offset)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    return PaginatedResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        has_more=offset + len(items) < total,
    )


@router.get("/{fee_due_schedule_id}", response_model=FeeDueScheduleResponse)
def get_fee_due_schedule(
    fee_due_schedule_id: str,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(get_current_user),
):
    """Get a single fee due-schedule row by id."""
    try:
        row = fee_due_schedule_service.get_fee_due_schedule_by_id(supabase, fee_due_schedule_id)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not row:
        raise HTTPException(status_code=404, detail="Fee due-schedule row not found")
    return row


@router.post("/", response_model=FeeDueScheduleResponse, status_code=201)
def create_fee_due_schedule(
    fee_due_schedule: FeeDueScheduleCreate,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(require_writer),
):
    """Create a new fee due-schedule row (what an applicant owes, and by when)."""
    try:
        created = fee_due_schedule_service.create_fee_due_schedule(supabase, fee_due_schedule)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not created:
        raise HTTPException(status_code=500, detail="Insert succeeded but no data was returned")
    return created


@router.patch("/{fee_due_schedule_id}", response_model=FeeDueScheduleResponse)
def update_fee_due_schedule(
    fee_due_schedule_id: str,
    fee_due_schedule: FeeDueScheduleUpdate,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(require_writer),
):
    """Partially update a fee due-schedule row by id - only the fields provided are changed."""
    payload = fee_due_schedule.model_dump(exclude_unset=True, mode="json")
    if not payload:
        raise HTTPException(status_code=400, detail="No fields provided to update")
    try:
        updated = fee_due_schedule_service.update_fee_due_schedule(supabase, fee_due_schedule_id, payload)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not updated:
        raise HTTPException(status_code=404, detail="Fee due-schedule row not found")
    return updated


@router.delete("/{fee_due_schedule_id}", status_code=204)
def delete_fee_due_schedule(
    fee_due_schedule_id: str,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(require_deleter),
):
    """Soft-delete a fee due-schedule row by id (sets deleted_at/deleted_by; the row is preserved)."""
    try:
        deleted = fee_due_schedule_service.delete_fee_due_schedule(supabase, fee_due_schedule_id, deleted_by=current_user["id"])
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not deleted:
        raise HTTPException(status_code=404, detail="Fee due-schedule row not found")
    return None

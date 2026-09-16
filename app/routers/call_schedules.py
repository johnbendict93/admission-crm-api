from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from postgrest.exceptions import APIError
from supabase import Client

from app.core.database import get_supabase_client
from app.core.jwt_auth import get_current_user, require_deleter, require_writer
from app.models.call_schedules import CallScheduleCreate, CallScheduleResponse, CallScheduleUpdate
from app.services import call_schedules_service

router = APIRouter(prefix="/call-schedules", tags=["Call Schedules"])


@router.get("/", response_model=List[CallScheduleResponse])
def list_call_schedules(
    limit: int = Query(50, ge=1, le=200, description="Rows per page (max 200)"),
    offset: int = Query(0, ge=0),
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(get_current_user),
):
    try:
        return call_schedules_service.get_all_call_schedules(supabase, limit=limit, offset=offset)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")


@router.get("/{call_schedule_id}", response_model=CallScheduleResponse)
def get_call_schedule(
    call_schedule_id: str,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(get_current_user),
):
    try:
        call_schedule = call_schedules_service.get_call_schedule_by_id(supabase, call_schedule_id)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not call_schedule:
        raise HTTPException(status_code=404, detail="Call schedule not found")
    return call_schedule


@router.post("/", response_model=CallScheduleResponse, status_code=201)
def create_call_schedule(
    call_schedule: CallScheduleCreate,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(require_writer),
):
    try:
        created = call_schedules_service.create_call_schedule(supabase, call_schedule)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not created:
        raise HTTPException(status_code=500, detail="Insert succeeded but no data was returned")
    return created


@router.patch("/{call_schedule_id}", response_model=CallScheduleResponse)
def update_call_schedule(
    call_schedule_id: str,
    call_schedule: CallScheduleUpdate,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(require_writer),
):
    payload = call_schedule.model_dump(exclude_unset=True, mode="json")
    if not payload:
        raise HTTPException(status_code=400, detail="No fields provided to update")
    try:
        updated = call_schedules_service.update_call_schedule(supabase, call_schedule_id, payload)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not updated:
        raise HTTPException(status_code=404, detail="Call schedule not found")
    return updated


@router.delete("/{call_schedule_id}", status_code=204)
def delete_call_schedule(
    call_schedule_id: str,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(require_deleter),
):
    try:
        deleted = call_schedules_service.delete_call_schedule(
            supabase, call_schedule_id, deleted_by=current_user["id"]
        )
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not deleted:
        raise HTTPException(status_code=404, detail="Call schedule not found")
    return None

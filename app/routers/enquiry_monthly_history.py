from fastapi import APIRouter, Depends, HTTPException, Query
from postgrest.exceptions import APIError
from supabase import Client

from app.core.database import get_supabase_client
from app.core.jwt_auth import get_current_user, require_deleter, require_writer
from app.models.enquiry_monthly_history import (
    EnquiryMonthlyHistoryCreate,
    EnquiryMonthlyHistoryResponse,
    EnquiryMonthlyHistoryUpdate,
)
from app.models.pagination import PaginatedResponse
from app.services import enquiry_monthly_history_service

router = APIRouter(prefix="/enquiry-monthly-history", tags=["Enquiry Monthly History"])


@router.get("/", response_model=PaginatedResponse[EnquiryMonthlyHistoryResponse])
def list_enquiry_monthly_history(
    limit: int = Query(50, ge=1, le=200, description="Rows per page (max 200)"),
    offset: int = Query(0, ge=0),
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(get_current_user),
):
    """List monthly enquiry history, oldest first, excluding soft-deleted rows."""
    try:
        items, total = enquiry_monthly_history_service.get_all_enquiry_monthly_history(supabase, limit=limit, offset=offset)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    return PaginatedResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        has_more=offset + len(items) < total,
    )


@router.get("/{row_id}", response_model=EnquiryMonthlyHistoryResponse)
def get_enquiry_monthly_history(
    row_id: str,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(get_current_user),
):
    """Get a single monthly enquiry history row by id."""
    try:
        row = enquiry_monthly_history_service.get_enquiry_monthly_history_by_id(supabase, row_id)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not row:
        raise HTTPException(status_code=404, detail="Enquiry monthly history row not found")
    return row


@router.post("/", response_model=EnquiryMonthlyHistoryResponse, status_code=201)
def create_enquiry_monthly_history(
    row: EnquiryMonthlyHistoryCreate,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(require_writer),
):
    """Create a new monthly enquiry history row."""
    try:
        created = enquiry_monthly_history_service.create_enquiry_monthly_history(supabase, row)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not created:
        raise HTTPException(status_code=500, detail="Insert succeeded but no data was returned")
    return created


@router.patch("/{row_id}", response_model=EnquiryMonthlyHistoryResponse)
def update_enquiry_monthly_history(
    row_id: str,
    row: EnquiryMonthlyHistoryUpdate,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(require_writer),
):
    """Partially update a monthly enquiry history row by id - only the fields provided are changed."""
    payload = row.model_dump(exclude_unset=True, mode="json")
    if not payload:
        raise HTTPException(status_code=400, detail="No fields provided to update")
    try:
        updated = enquiry_monthly_history_service.update_enquiry_monthly_history(supabase, row_id, payload)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not updated:
        raise HTTPException(status_code=404, detail="Enquiry monthly history row not found")
    return updated


@router.delete("/{row_id}", status_code=204)
def delete_enquiry_monthly_history(
    row_id: str,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(require_deleter),
):
    """Soft-delete a monthly enquiry history row by id (sets deleted_at/deleted_by; the row is preserved)."""
    try:
        deleted = enquiry_monthly_history_service.delete_enquiry_monthly_history(supabase, row_id, deleted_by=current_user["id"])
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not deleted:
        raise HTTPException(status_code=404, detail="Enquiry monthly history row not found")
    return None

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from postgrest.exceptions import APIError
from supabase import Client

from app.core.database import get_supabase_client
from app.core.jwt_auth import get_current_user, require_deleter, require_writer
from app.models.fee_payments import FeePaymentCreate, FeePaymentResponse, FeePaymentUpdate
from app.models.pagination import PaginatedResponse
from app.services import fee_payments_service

router = APIRouter(prefix="/fee-payments", tags=["Fee Payments"])


@router.get("/", response_model=PaginatedResponse[FeePaymentResponse])
def list_fee_payments(
    limit: int = Query(50, ge=1, le=200, description="Rows per page (max 200)"),
    offset: int = Query(0, ge=0),
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(get_current_user),
):
    """List fee payments, most recently created first, excluding soft-deleted rows."""
    try:
        items, total = fee_payments_service.get_all_fee_payments(supabase, limit=limit, offset=offset)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    return PaginatedResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        has_more=offset + len(items) < total,
    )


@router.get("/{fee_payment_id}", response_model=FeePaymentResponse)
def get_fee_payment(
    fee_payment_id: str,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(get_current_user),
):
    """Get a single fee payment by id."""
    try:
        fee_payment = fee_payments_service.get_fee_payment_by_id(supabase, fee_payment_id)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not fee_payment:
        raise HTTPException(status_code=404, detail="Fee payment not found")
    return fee_payment


@router.post("/", response_model=FeePaymentResponse, status_code=201)
def create_fee_payment(
    fee_payment: FeePaymentCreate,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(require_writer),
):
    """Create a new fee payment."""
    try:
        created = fee_payments_service.create_fee_payment(supabase, fee_payment)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not created:
        raise HTTPException(status_code=500, detail="Insert succeeded but no data was returned")
    return created


@router.patch("/{fee_payment_id}", response_model=FeePaymentResponse)
def update_fee_payment(
    fee_payment_id: str,
    fee_payment: FeePaymentUpdate,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(require_writer),
):
    """Partially update a fee payment by id - only the fields provided are changed."""
    payload = fee_payment.model_dump(exclude_unset=True, mode="json")
    if not payload:
        raise HTTPException(status_code=400, detail="No fields provided to update")
    try:
        updated = fee_payments_service.update_fee_payment(supabase, fee_payment_id, payload)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not updated:
        raise HTTPException(status_code=404, detail="Fee payment not found")
    return updated


@router.delete("/{fee_payment_id}", status_code=204)
def delete_fee_payment(
    fee_payment_id: str,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(require_deleter),
):
    """Soft-delete a fee payment by id (sets deleted_at/deleted_by; the row is preserved)."""
    try:
        deleted = fee_payments_service.delete_fee_payment(supabase, fee_payment_id, deleted_by=current_user["id"])
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not deleted:
        raise HTTPException(status_code=404, detail="Fee payment not found")
    return None

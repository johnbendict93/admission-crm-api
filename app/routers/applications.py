from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from postgrest.exceptions import APIError
from supabase import Client

from app.core.database import get_supabase_client
from app.core.jwt_auth import get_current_user, require_deleter, require_writer
from app.models.applications import ApplicationCreate, ApplicationResponse, ApplicationUpdate
from app.models.pagination import PaginatedResponse
from app.services import applications_service

router = APIRouter(prefix="/applications", tags=["Applications"])


@router.get("/", response_model=PaginatedResponse[ApplicationResponse])
def list_applications(
    limit: int = Query(50, ge=1, le=200, description="Rows per page (max 200)"),
    offset: int = Query(0, ge=0),
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(get_current_user),
):
    """List applications, most recently created first, excluding soft-deleted rows."""
    try:
        items, total = applications_service.get_all_applications(supabase, limit=limit, offset=offset)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    return PaginatedResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        has_more=offset + len(items) < total,
    )


@router.get("/{application_id}", response_model=ApplicationResponse)
def get_application(
    application_id: str,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(get_current_user),
):
    """Get a single application by id."""
    try:
        application = applications_service.get_application_by_id(supabase, application_id)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    return application


@router.post("/", response_model=ApplicationResponse, status_code=201)
def create_application(
    application: ApplicationCreate,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(require_writer),
):
    """Create a new application."""
    try:
        created = applications_service.create_application(supabase, application)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not created:
        raise HTTPException(status_code=500, detail="Insert succeeded but no data was returned")
    return created


@router.patch("/{application_id}", response_model=ApplicationResponse)
def update_application(
    application_id: str,
    application: ApplicationUpdate,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(require_writer),
):
    """Partially update a application by id - only the fields provided are changed."""
    payload = application.model_dump(exclude_unset=True, mode="json")
    if not payload:
        raise HTTPException(status_code=400, detail="No fields provided to update")
    try:
        updated = applications_service.update_application(supabase, application_id, payload)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not updated:
        raise HTTPException(status_code=404, detail="Application not found")
    return updated


@router.delete("/{application_id}", status_code=204)
def delete_application(
    application_id: str,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(require_deleter),
):
    """Soft-delete a application by id (sets deleted_at/deleted_by; the row is preserved)."""
    try:
        deleted = applications_service.delete_application(supabase, application_id, deleted_by=current_user["id"])
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not deleted:
        raise HTTPException(status_code=404, detail="Application not found")
    return None

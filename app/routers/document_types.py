from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from postgrest.exceptions import APIError
from supabase import Client

from app.core.database import get_supabase_client
from app.core.jwt_auth import get_current_user, require_deleter, require_writer
from app.models.document_types import DocumentTypeCreate, DocumentTypeResponse, DocumentTypeUpdate
from app.models.pagination import PaginatedResponse
from app.services import document_types_service

router = APIRouter(prefix="/document-types", tags=["Document Types"])


@router.get("/", response_model=PaginatedResponse[DocumentTypeResponse])
def list_document_types(
    limit: int = Query(50, ge=1, le=200, description="Rows per page (max 200)"),
    offset: int = Query(0, ge=0),
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(get_current_user),
):
    """List document types, most recently created first, excluding inactive rows."""
    try:
        items, total = document_types_service.get_all_document_types(supabase, limit=limit, offset=offset)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    return PaginatedResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        has_more=offset + len(items) < total,
    )


@router.get("/{document_type_id}", response_model=DocumentTypeResponse)
def get_document_type(
    document_type_id: str,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(get_current_user),
):
    """Get a single document type by id."""
    try:
        document_type = document_types_service.get_document_type_by_id(supabase, document_type_id)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not document_type:
        raise HTTPException(status_code=404, detail="Document type not found")
    return document_type


@router.post("/", response_model=DocumentTypeResponse, status_code=201)
def create_document_type(
    document_type: DocumentTypeCreate,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(require_writer),
):
    """Create a new document type."""
    try:
        created = document_types_service.create_document_type(supabase, document_type)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not created:
        raise HTTPException(status_code=500, detail="Insert succeeded but no data was returned")
    return created


@router.patch("/{document_type_id}", response_model=DocumentTypeResponse)
def update_document_type(
    document_type_id: str,
    document_type: DocumentTypeUpdate,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(require_writer),
):
    """Partially update a document type by id - only the fields provided are changed."""
    payload = document_type.model_dump(exclude_unset=True, mode="json")
    if not payload:
        raise HTTPException(status_code=400, detail="No fields provided to update")
    try:
        updated = document_types_service.update_document_type(supabase, document_type_id, payload)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not updated:
        raise HTTPException(status_code=404, detail="Document type not found")
    return updated


@router.delete("/{document_type_id}", status_code=204)
def delete_document_type(
    document_type_id: str,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(require_deleter),
):
    """Deactivate a document type by id (sets is_active to false; the row is preserved)."""
    try:
        deleted = document_types_service.delete_document_type(supabase, document_type_id)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not deleted:
        raise HTTPException(status_code=404, detail="Document type not found")
    return None

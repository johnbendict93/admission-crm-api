from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from postgrest.exceptions import APIError
from supabase import Client

from app.core.database import get_supabase_client
from app.core.jwt_auth import get_current_user
from app.models.pagination import PaginatedResponse
from app.models.users import UserResponse
from app.services import users_service

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/", response_model=PaginatedResponse[UserResponse])
def list_users(
    role: Optional[List[str]] = Query(
        None,
        description=(
            "Only return users whose role is one of these. Repeat the parameter "
            "(?role=admin&role=staff) or comma-separate it (?role=admin,staff). "
            "Omit to return every role. Allowed values are whatever the database's "
            "users_role_check constraint permits; an unknown role simply matches no rows."
        ),
    ),
    limit: int = Query(50, ge=1, le=200, description="Rows per page (max 200)"),
    offset: int = Query(0, ge=0),
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(get_current_user),
):
    """List active staff users, ordered by name. Read-only; email and phone are never returned."""
    try:
        items, total = users_service.get_all_users(
            supabase,
            roles=users_service.normalize_roles(role),
            limit=limit,
            offset=offset,
        )
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    return PaginatedResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        has_more=offset + len(items) < total,
    )


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: str,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(get_current_user),
):
    """Get a single active user by id. Email and phone are never returned."""
    try:
        user = users_service.get_user_by_id(supabase, user_id)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

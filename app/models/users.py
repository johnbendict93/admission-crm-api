from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

# Roles an admin may hand out through POST /users. 'admin' is deliberately
# NOT here: new admins are made directly in Supabase, so a stolen admin
# token cannot mint more admins. The DB's users_role_check constraint
# still owns the full list of valid roles.
CREATABLE_ROLES = ("counselor", "staff", "viewer")


class UserResponse(BaseModel):
    """Read-only, deliberately slim view of public.users for pickers and
    display (e.g. counseling_sessions.counselor_id). Only these five
    columns are ever selected from the database (see users_service.py's
    USER_COLUMNS) - email, phone and avatar_url are never fetched, so they
    cannot leak through this API even by accident.

    Matches the real public.users table (confirmed live on dev AND prod,
    Sept 2026, via information_schema.columns): id uuid NOT NULL,
    full_name text NOT NULL, role text NOT NULL (DB CHECK: admin /
    counselor / staff / viewer - kept as free text here, not a Literal, so
    the DB stays the single source of truth for the allowed values),
    department text NULL, is_active boolean NULL (DB default true).
    """

    id: UUID
    full_name: str
    role: str
    department: Optional[str] = None
    is_active: Optional[bool] = None

    class Config:
        from_attributes = True


class UserCreate(BaseModel):
    """Body of POST /users (admin only). The admin sets a temporary
    password and tells the person; they should change it after first login.
    The password is never returned or logged."""

    email: EmailStr
    full_name: str = Field(min_length=1, max_length=100)
    role: str
    department: Optional[str] = Field(default=None, max_length=100)
    temporary_password: str = Field(min_length=8, max_length=72)

    @field_validator("full_name")
    @classmethod
    def _name_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("full_name must not be blank")
        return v

    @field_validator("department")
    @classmethod
    def _blank_department_is_none(cls, v: Optional[str]) -> Optional[str]:
        v = v.strip() if v else v
        return v or None

    @field_validator("role")
    @classmethod
    def _role_allowed(cls, v: str) -> str:
        if v not in CREATABLE_ROLES:
            raise ValueError(f"role must be one of: {', '.join(CREATABLE_ROLES)}")
        return v

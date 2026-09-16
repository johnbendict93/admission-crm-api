from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class DocumentTypeBase(BaseModel):
    # Matches the real Supabase "document_types" table (confirmed live via
    # information_schema.columns + pg_constraint, Sept 2026, immediately
    # before writing this module - dev had zero existing rows, no drift
    # found against the prod_schema.sql dump). No FKs point at this table
    # from anywhere else (checked prod_schema.sql), and none point out of
    # it either. UNIQUE constraint on name - not modeled here since
    # uniqueness violations surface as a normal APIError, same as every
    # other module's DB-level constraints.
    name: str
    # DB default true
    is_required: Optional[bool] = None
    # DB default 0
    sort_order: Optional[int] = None
    # DB default true. Doubles as this module's delete mechanism instead
    # of deleted_at/deleted_by - see document_types_service.py for why.
    is_active: Optional[bool] = None


class DocumentTypeCreate(DocumentTypeBase):
    pass


class DocumentTypeResponse(DocumentTypeBase):
    id: UUID
    # No created_at column exists on this table - not modeled here.

    class Config:
        from_attributes = True


class DocumentTypeUpdate(BaseModel):
    """PATCH model - every field optional. Nothing needs excluding here:
    nothing on document_types is trigger-generated, and there's no
    created_by column to protect."""
    name: Optional[str] = None
    is_required: Optional[bool] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None

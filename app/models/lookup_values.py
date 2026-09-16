from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class LookupValueBase(BaseModel):
    # Matches the real Supabase "lookup_values" table (confirmed live via
    # information_schema.columns + pg_constraint, Sept 2026, immediately
    # before writing this module - dev had zero existing rows, no drift
    # found against the prod_schema.sql dump). No FKs point at this table
    # from anywhere else (checked prod_schema.sql), and none point out of
    # it either. UNIQUE constraint on (type, value) - not modeled here
    # since uniqueness violations surface as a normal APIError, same as
    # every other module's DB-level constraints.
    type: str
    value: str
    # DB default 0
    sort_order: Optional[int] = None
    # DB default true. Doubles as this module's delete mechanism instead
    # of deleted_at/deleted_by - see lookup_values_service.py for why.
    is_active: Optional[bool] = None


class LookupValueCreate(LookupValueBase):
    pass


class LookupValueResponse(LookupValueBase):
    id: UUID
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class LookupValueUpdate(BaseModel):
    """PATCH model - every field optional. Nothing needs excluding here:
    nothing on lookup_values is trigger-generated, and there's no
    created_by column to protect."""
    type: Optional[str] = None
    value: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None

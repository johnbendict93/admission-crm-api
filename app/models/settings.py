from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class SettingBase(BaseModel):
    # Matches the real Supabase "settings" table (confirmed live via
    # information_schema.columns + pg_constraint, Sept 2026, immediately
    # before writing this module - dev had zero existing rows, no drift
    # found against the prod_schema.sql dump). No FKs point at this table
    # from anywhere else (checked prod_schema.sql), and none point out of
    # it either. UNIQUE constraint on (category, key) - not modeled here
    # since uniqueness violations surface as a normal APIError, same as
    # every other module's DB-level constraints (same situation as
    # document_types' UNIQUE(name) and lookup_values' UNIQUE(type,value)).
    category: str
    key: str
    value: str
    # DB default true. Doubles as this module's delete mechanism instead
    # of deleted_at/deleted_by - see settings_service.py for why.
    is_active: Optional[bool] = None


class SettingCreate(SettingBase):
    pass


class SettingResponse(SettingBase):
    id: UUID
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SettingUpdate(BaseModel):
    """PATCH model - every field optional. updated_at is deliberately
    excluded - it's trigger-maintained (migration 0011 attaches the
    same shared public.update_updated_at() function used by
    fee_payments/hostel_allotments/scholarships/applicants/applications),
    not client-settable. Nothing else needs excluding: nothing on
    settings is otherwise trigger-generated, and there's no created_by
    column to protect."""
    category: Optional[str] = None
    key: Optional[str] = None
    value: Optional[str] = None
    is_active: Optional[bool] = None

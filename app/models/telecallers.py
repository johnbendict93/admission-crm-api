from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr


class TelecallerBase(BaseModel):
    # Matches the real Supabase "telecallers" table (confirmed live via
    # information_schema.columns + pg_constraint, Sept 2026, immediately
    # before writing this module - dev had zero existing rows, no drift
    # found against the prod_schema.sql dump). No FKs, no CHECK
    # constraints, no created_by column (same situation as
    # applications/fee_payments/scholarships/hostel_allotments) - and
    # unlike all six prior modules, this table has no updated_at column
    # or trigger either, so none is modeled here.
    name: str
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    department: Optional[str] = None
    # DB default true
    active: Optional[bool] = None


class TelecallerCreate(TelecallerBase):
    pass


class TelecallerResponse(TelecallerBase):
    id: UUID
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class TelecallerUpdate(BaseModel):
    """PATCH model - every field optional. Nothing needs excluding here:
    nothing on telecallers is trigger-generated, and there's no
    created_by column to protect (see TelecallerBase's audit note)."""
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    department: Optional[str] = None
    active: Optional[bool] = None

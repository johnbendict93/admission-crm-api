from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class HostelAllotmentBase(BaseModel):
    # Matches the real Supabase "hostel_allotments" table (confirmed live
    # via information_schema.columns + pg_constraint, Sept 2026,
    # immediately before writing this module - dev had zero existing
    # rows, no drift found against the prod_schema.sql dump). FK:
    # applicant_id -> applicants(id) ON DELETE CASCADE. No CHECK
    # constraints exist on this table - block_name/room_type/status are
    # plain text, not restricted to a fixed set at the DB level. No
    # created_by column exists here, the same situation
    # applications/fee_payments/scholarships are already in.
    applicant_id: UUID
    block_name: str
    room_number: str
    # DB default 'Double'
    room_type: Optional[str] = None
    # DB default CURRENT_DATE
    allotment_date: Optional[date] = None
    # DB default '2026-27'
    academic_year: Optional[str] = None
    # DB default 'Active'
    status: Optional[str] = None
    remarks: Optional[str] = None


class HostelAllotmentCreate(HostelAllotmentBase):
    pass


class HostelAllotmentResponse(HostelAllotmentBase):
    id: UUID
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class HostelAllotmentUpdate(BaseModel):
    """PATCH model - every field optional. Nothing needs excluding here:
    nothing on hostel_allotments is trigger-generated, and there's no
    created_by column to protect (see HostelAllotmentBase's audit note)."""
    applicant_id: Optional[UUID] = None
    block_name: Optional[str] = None
    room_number: Optional[str] = None
    room_type: Optional[str] = None
    allotment_date: Optional[date] = None
    academic_year: Optional[str] = None
    status: Optional[str] = None
    remarks: Optional[str] = None

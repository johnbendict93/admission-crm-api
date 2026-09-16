from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class ScholarshipBase(BaseModel):
    # Matches the real Supabase "scholarships" table (confirmed live via
    # information_schema.columns + pg_constraint, Sept 2026, immediately
    # before writing this module - dev had zero existing rows, no drift
    # found against the prod_schema.sql dump). FK: applicant_id ->
    # applicants(id) ON DELETE CASCADE. No CHECK constraints exist on this
    # table - scholarship_type/status are plain text, not restricted to a
    # fixed set at the DB level. No created_by column exists here, the
    # same situation "applications" and "fee_payments" are already in.
    applicant_id: UUID
    scholarship_type: str
    # DB default 0
    amount: Optional[float] = None
    # DB default '2026-27'
    academic_year: Optional[str] = None
    # DB default 'Applied'
    status: Optional[str] = None
    reference_no: Optional[str] = None
    remarks: Optional[str] = None


class ScholarshipCreate(ScholarshipBase):
    pass


class ScholarshipResponse(ScholarshipBase):
    id: UUID
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ScholarshipUpdate(BaseModel):
    """PATCH model - every field optional. Nothing needs excluding here:
    nothing on scholarships is trigger-generated, and there's no
    created_by column to protect (see ScholarshipBase's audit note)."""
    applicant_id: Optional[UUID] = None
    scholarship_type: Optional[str] = None
    amount: Optional[float] = None
    academic_year: Optional[str] = None
    status: Optional[str] = None
    reference_no: Optional[str] = None
    remarks: Optional[str] = None

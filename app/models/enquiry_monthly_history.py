from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class EnquiryMonthlyHistoryBase(BaseModel):
    # Matches the "enquiry_monthly_history" table added by migration 0020
    # (module 20 prep). One row per (year, month) - UNIQUE constraint in
    # the DB, so a duplicate insert 400s rather than silently overwriting.
    # No CHECK constraint violations are reshaped here (month/enquiry_count
    # CHECKs) - a bad value surfaces as a clear 400 from Supabase, same
    # convention as every other module in this repo.
    year: int
    month: int  # 1-12
    enquiry_count: int
    # DB default 'synthetic'; left optional so create() can omit it and
    # let the database default apply. Distinguishes seeded illustrative
    # history from a real monthly aggregate once a customer has actual
    # usage - see migration 0020's WHY section.
    source: Optional[str] = None


class EnquiryMonthlyHistoryCreate(EnquiryMonthlyHistoryBase):
    pass


class EnquiryMonthlyHistoryResponse(EnquiryMonthlyHistoryBase):
    id: UUID
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class EnquiryMonthlyHistoryUpdate(BaseModel):
    """PATCH model - every field optional. Nothing trigger-generated here
    and no created_by column to protect, same as FeeDueScheduleUpdate."""
    year: Optional[int] = None
    month: Optional[int] = None
    enquiry_count: Optional[int] = None
    source: Optional[str] = None

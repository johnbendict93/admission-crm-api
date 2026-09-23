from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class FeeDueScheduleBase(BaseModel):
    # Matches the "fee_due_schedule" table added by migration 0019 (module
    # 18 prep). FK: applicant_id -> applicants(id) ON DELETE CASCADE. No
    # CHECK constraints - fee_component is plain text, same as
    # fee_payments.fee_component, not restricted to a fixed set at the DB
    # level. No created_by column, matching fee_payments (see that
    # module's audit note - this is the same "money on an applicant"
    # domain).
    applicant_id: UUID
    fee_component: str
    # DB default '2026-27'; left optional so create() can omit it and let
    # the database default apply.
    academic_year: Optional[str] = None
    amount_due: float
    due_date: date


class FeeDueScheduleCreate(FeeDueScheduleBase):
    pass


class FeeDueScheduleResponse(FeeDueScheduleBase):
    id: UUID
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class FeeDueScheduleUpdate(BaseModel):
    """PATCH model - every field optional. Nothing trigger-generated here
    and no created_by column to protect, same as FeePaymentUpdate."""
    applicant_id: Optional[UUID] = None
    fee_component: Optional[str] = None
    academic_year: Optional[str] = None
    amount_due: Optional[float] = None
    due_date: Optional[date] = None

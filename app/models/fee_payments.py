from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class FeePaymentBase(BaseModel):
    # Matches the real Supabase "fee_payments" table (confirmed live via
    # information_schema.columns + pg_constraint, Sept 2026, immediately
    # before writing this module - dev had zero existing rows, no drift
    # found against the prod_schema.sql dump). FK: applicant_id ->
    # applicants(id) ON DELETE CASCADE. No CHECK constraints exist on this
    # table (unlike applications.programme/allotted_seat_type) -
    # fee_component/payment_mode are plain text, not restricted to a fixed
    # set at the DB level. No created_by column exists here, the same
    # situation "applications" is already in.
    applicant_id: UUID
    fee_component: str
    amount: float
    payment_mode: str
    # DB default CURRENT_DATE; left optional so create() can omit it and
    # let the database default apply.
    payment_date: Optional[date] = None
    receipt_no: Optional[str] = None
    # DB default '2026-27'
    academic_year: Optional[str] = None
    remarks: Optional[str] = None


class FeePaymentCreate(FeePaymentBase):
    pass


class FeePaymentResponse(FeePaymentBase):
    id: UUID
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class FeePaymentUpdate(BaseModel):
    """PATCH model - every field optional. Nothing needs excluding here
    the way applicants.reg_number or applications.application_no are:
    nothing on fee_payments is trigger-generated, and there's no
    created_by column to protect (see FeePaymentBase's audit note)."""
    applicant_id: Optional[UUID] = None
    fee_component: Optional[str] = None
    amount: Optional[float] = None
    payment_mode: Optional[str] = None
    payment_date: Optional[date] = None
    receipt_no: Optional[str] = None
    academic_year: Optional[str] = None
    remarks: Optional[str] = None

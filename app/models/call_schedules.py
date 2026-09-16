from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class CallScheduleBase(BaseModel):
    # Matches the real Supabase "call_schedules" table (confirmed live via
    # information_schema.columns + pg_constraint, Sept 2026, immediately
    # before writing this module - dev had zero existing rows, no drift
    # found against the prod_schema.sql dump). FK'd to leads(id); no
    # created_by column, no CHECK constraints, no triggers, no
    # updated_at column (same situation as telecallers).
    #
    # scheduled_by is a plain text field on this table, not a FK to
    # users - matching the live schema exactly, so it's modeled as a
    # free-text string rather than a UUID.
    lead_id: UUID
    scheduled_by: Optional[str] = None
    scheduled_time: Optional[datetime] = None
    # DB default false
    reminder_sent: Optional[bool] = None
    # DB default 'Pending'
    status: Optional[str] = None


class CallScheduleCreate(CallScheduleBase):
    pass


class CallScheduleResponse(CallScheduleBase):
    id: UUID
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CallScheduleUpdate(BaseModel):
    """PATCH model - every field optional. Nothing needs excluding here:
    nothing on call_schedules is trigger-generated, and there's no
    created_by column to protect (see CallScheduleBase's audit note)."""
    lead_id: Optional[UUID] = None
    scheduled_by: Optional[str] = None
    scheduled_time: Optional[datetime] = None
    reminder_sent: Optional[bool] = None
    status: Optional[str] = None

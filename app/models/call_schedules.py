from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, field_validator


def _require_tz_aware_scheduled_time(v):
    """scheduled_time must carry an explicit UTC offset (e.g. '+05:30').

    Rejecting naive datetimes here, rather than silently assuming IST,
    closes the exact bug the Tier-2 timezone fix exists to prevent: a
    naive value like "2026-09-19T10:15:00" is ambiguous the instant it
    reaches Postgres - once scheduled_time is timestamptz, Postgres would
    interpret it using the session timezone (UTC), not the sender's
    intended local time, silently storing it 5.5 hours off. Both writers
    (this API and the Streamlit app's insert_schedule call site) now
    attach the offset explicitly before sending; this validator is the
    permanent guard against either one regressing.

    A fixed +05:30 offset (rather than a named zone) is expected on the
    wire, matching the writer-side fix - India has never observed DST,
    so this is exact, not an approximation.
    """
    if v is not None and v.tzinfo is None:
        raise ValueError(
            "scheduled_time must include a UTC offset (e.g. '+05:30'); "
            "naive datetimes are rejected to avoid silent timezone misinterpretation"
        )
    return v


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
    # Validator lives here, not on CallScheduleBase: CallScheduleResponse
    # also inherits from CallScheduleBase and must NOT reject existing
    # rows whose scheduled_time is still naive (the column is still
    # `timestamp without time zone` until the Tier-2 data migration
    # runs) - this only guards new writes, never reads.
    _validate_scheduled_time = field_validator("scheduled_time")(_require_tz_aware_scheduled_time)


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

    _validate_scheduled_time = field_validator("scheduled_time")(_require_tz_aware_scheduled_time)

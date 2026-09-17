from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class FollowupBase(BaseModel):
    # Matches the real Supabase "followups" table (confirmed live via
    # information_schema.columns + pg_constraint, Sept 2026, immediately
    # before writing this module - dev had zero existing rows, no drift
    # found against the prod_schema.sql dump). FK'd to leads(id); no
    # created_by column, no CHECK constraints, no triggers, no
    # updated_at column (same situation as telecallers/call_schedules/
    # campus_visits).
    #
    # called_by is a plain text field on this table, not a FK to users -
    # matching the live schema exactly. call_time is also text (not a
    # native time type), matching the live column type exactly rather
    # than assuming.
    #
    # This is the table the old Streamlit app (dce_crm) actively reads
    # from and writes to today - see migrations/0010 for the prod-safety
    # analysis on adding deleted_at/deleted_by alongside it.
    lead_id: UUID
    called_by: Optional[str] = None
    call_date: Optional[date] = None
    call_time: Optional[str] = None
    response: Optional[str] = None
    notes: Optional[str] = None
    next_followup_date: Optional[date] = None


class FollowupCreate(FollowupBase):
    pass


class FollowupResponse(FollowupBase):
    id: UUID
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class FollowupUpdate(BaseModel):
    """PATCH model - every field optional. Nothing needs excluding here:
    nothing on followups is trigger-generated, and there's no
    created_by column to protect (see FollowupBase's audit note)."""
    lead_id: Optional[UUID] = None
    called_by: Optional[str] = None
    call_date: Optional[date] = None
    call_time: Optional[str] = None
    response: Optional[str] = None
    notes: Optional[str] = None
    next_followup_date: Optional[date] = None

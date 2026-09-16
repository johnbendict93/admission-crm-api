from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class CampusVisitBase(BaseModel):
    # Matches the real Supabase "campus_visits" table (confirmed live via
    # information_schema.columns + pg_constraint, Sept 2026, immediately
    # before writing this module - dev had zero existing rows, no drift
    # found against the prod_schema.sql dump). FK'd to leads(id); no
    # created_by column, no CHECK constraints, no triggers, no
    # updated_at column (same situation as telecallers/call_schedules).
    #
    # visited_by is a plain text field on this table, not a FK to users -
    # matching the live schema exactly, so it's modeled as a free-text
    # string rather than a UUID.
    lead_id: UUID
    visit_date: Optional[date] = None
    visited_by: Optional[str] = None
    departments_seen: Optional[str] = None
    outcome: Optional[str] = None
    notes: Optional[str] = None


class CampusVisitCreate(CampusVisitBase):
    pass


class CampusVisitResponse(CampusVisitBase):
    id: UUID
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CampusVisitUpdate(BaseModel):
    """PATCH model - every field optional. Nothing needs excluding here:
    nothing on campus_visits is trigger-generated, and there's no
    created_by column to protect (see CampusVisitBase's audit note)."""
    lead_id: Optional[UUID] = None
    visit_date: Optional[date] = None
    visited_by: Optional[str] = None
    departments_seen: Optional[str] = None
    outcome: Optional[str] = None
    notes: Optional[str] = None

from datetime import date, datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel


class CounselingSessionBase(BaseModel):
    # Matches the real Supabase "counseling_sessions" table (confirmed
    # live via information_schema.columns + pg_constraint + pg_trigger,
    # Sept 2026, immediately before writing this module - dev had zero
    # existing rows, no drift found against the prod_schema.sql dump).
    #
    # FKs: applicant_id -> applicants(id) ON DELETE CASCADE (required),
    # application_id -> applications(id) (nullable, no cascade),
    # counselor_id -> users(id) (required, no cascade). Three CHECK
    # constraints, confirmed live:
    #   mode: In-Person / Remote (DB default 'In-Person')
    #   outcome: Interested / Not Interested / Need More Time /
    #     Documents Requested / Fee Discussed / Confirmed / Dropped /
    #     Callback Scheduled / Other
    #   session_type: Walk-in / Phone Call / Video Call / WhatsApp /
    #     Email / Home Visit / School Visit / Camp / Follow-up
    # All three left as free text below (not Literal/Enum) so a
    # constraint violation surfaces as a clear 400 from Supabase rather
    # than being silently reshaped by the API - same convention as
    # applicants.priority and applications.programme/allotted_seat_type.
    #
    # topics_discussed is a native Postgres text[] (udt_name "_text") -
    # the first array column in this project. Modeled as
    # Optional[List[str]]; pydantic's model_dump(mode="json") produces a
    # plain JSON array, which PostgREST/postgrest-py accepts directly
    # for an array-typed column - verified explicitly in
    # tests/test_counseling_sessions.py (round-tripped, not assumed).
    applicant_id: UUID
    application_id: Optional[UUID] = None
    counselor_id: UUID
    session_type: str
    # DB default now()
    session_date: Optional[datetime] = None
    duration_mins: Optional[int] = None
    topics_discussed: Optional[List[str]] = None
    outcome: Optional[str] = None
    next_action: Optional[str] = None
    next_action_date: Optional[date] = None
    notes: Optional[str] = None
    # DB default 'In-Person'
    mode: Optional[str] = None


class CounselingSessionCreate(CounselingSessionBase):
    pass


class CounselingSessionResponse(CounselingSessionBase):
    id: UUID
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CounselingSessionUpdate(BaseModel):
    """PATCH model - every field optional. updated_at needs no exclusion
    here: it's trigger-maintained (trg_sessions_updated_at, already
    present before this module was built - see migration 0012's
    comment), and there's no created_by column to protect (see
    CounselingSessionBase's audit note)."""
    applicant_id: Optional[UUID] = None
    application_id: Optional[UUID] = None
    counselor_id: Optional[UUID] = None
    session_type: Optional[str] = None
    session_date: Optional[datetime] = None
    duration_mins: Optional[int] = None
    topics_discussed: Optional[List[str]] = None
    outcome: Optional[str] = None
    next_action: Optional[str] = None
    next_action_date: Optional[date] = None
    notes: Optional[str] = None
    mode: Optional[str] = None

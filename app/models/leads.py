from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, field_validator


class LeadBase(BaseModel):
    # Matches the real Supabase "leads" table (confirmed via Table Editor).
    name: str
    phone: str
    email: Optional[EmailStr] = None
    school: Optional[str] = None
    district: Optional[str] = None
    marks: Optional[float] = None
    course_interest: Optional[str] = None
    parent_name: Optional[str] = None
    parent_occupation: Optional[str] = None
    source: Optional[str] = None           # e.g. Walk-in, Referral
    status: Optional[str] = "New"          # matches existing data convention
    score: Optional[int] = 0
    assigned_to: Optional[str] = None


class LeadCreate(LeadBase):
    pass


class LeadResponse(LeadBase):
    id: str
    created_at: Optional[datetime] = None

    @field_validator("email", mode="before")
    @classmethod
    def blank_email_to_none(cls, v):
        """Old rows may hold email = ''; treat as no email so one bad row
        does not 500 the whole list. Create/update models stay strict."""
        if isinstance(v, str) and not v.strip():
            return None
        return v

    class Config:
        from_attributes = True

class LeadUpdate(BaseModel):
    """PATCH model — every field optional. Uses exclude_unset (not
    exclude_none) at the call site so a client can explicitly null out an
    optional field without every omitted field being treated the same way."""
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    school: Optional[str] = None
    district: Optional[str] = None
    marks: Optional[float] = None
    course_interest: Optional[str] = None
    parent_name: Optional[str] = None
    parent_occupation: Optional[str] = None
    source: Optional[str] = None
    status: Optional[str] = None
    score: Optional[int] = None
    assigned_to: Optional[str] = None

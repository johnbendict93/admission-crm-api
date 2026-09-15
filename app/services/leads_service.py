import logging

from postgrest.exceptions import APIError
from supabase import Client

from app.core.config import settings
from app.models.leads import LeadCreate

logger = logging.getLogger(__name__)

TABLE_NAME = settings.LEADS_TABLE

# Explicit columns instead of select("*") — only pull what the API actually
# returns, and any accidental extra column added later doesn't silently leak.
LEAD_COLUMNS = (
    "id,name,phone,email,school,district,marks,course_interest,"
    "parent_name,parent_occupation,source,status,score,assigned_to,created_at"
)


def get_all_leads(supabase: Client, limit: int = 50, offset: int = 0):
    try:
        response = (
            supabase.table(TABLE_NAME)
            .select(LEAD_COLUMNS)
            .order("created_at", desc=True)
            .order("id")  # tiebreaker: seeded rows share identical created_at,
            # so pagination needs a secondary key for stable, deterministic order
            .range(offset, offset + limit - 1)
            .execute()
        )
    except APIError as e:
        logger.error("Supabase error in get_all_leads: %s", e)
        raise
    return response.data


def get_lead_by_id(supabase: Client, lead_id: str):
    try:
        response = (
            supabase.table(TABLE_NAME)
            .select(LEAD_COLUMNS)
            .eq("id", lead_id)
            .maybe_single()
            .execute()
        )
    except APIError as e:
        logger.error("Supabase error in get_lead_by_id: %s", e)
        raise
    return response.data if response else None


def create_lead(supabase: Client, lead: LeadCreate):
    payload = lead.model_dump(exclude_none=True)
    try:
        response = supabase.table(TABLE_NAME).insert(payload).execute()
    except APIError as e:
        logger.error("Supabase error in create_lead: %s", e)
        raise
    return response.data[0] if response.data else None


def update_lead(supabase: Client, lead_id: str, payload: dict):
    try:
        response = (
            supabase.table(TABLE_NAME)
            .update(payload)
            .eq("id", lead_id)
            .execute()
        )
    except APIError as e:
        logger.error("Supabase error in update_lead: %s", e)
        raise
    return response.data[0] if response.data else None


def delete_lead(supabase: Client, lead_id: str) -> bool:
    try:
        response = supabase.table(TABLE_NAME).delete().eq("id", lead_id).execute()
    except APIError as e:
        logger.error("Supabase error in delete_lead: %s", e)
        raise
    return bool(response.data)

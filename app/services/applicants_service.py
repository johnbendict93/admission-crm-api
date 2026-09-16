import logging
from datetime import datetime, timezone

from postgrest.exceptions import APIError
from supabase import Client

from app.core.config import settings
from app.models.applicants import ApplicantCreate

logger = logging.getLogger(__name__)

TABLE_NAME = settings.APPLICANTS_TABLE

# Explicit columns instead of select("*") — matches the real applicants table
# exactly, column-by-column (audited via Supabase Table Editor, Sept 2026).
APPLICANT_COLUMNS = (
    "id,reg_number,first_name,last_name,date_of_birth,gender,phone,"
    "alternate_phone,email,address_line1,address_line2,city,state,pincode,"
    "aadhaar_number,category,community_cert_no,twelfth_school,twelfth_board,"
    "twelfth_year,twelfth_percentage,twelfth_group,pcm_marks,cutoff_marks,"
    "entrance_exam,entrance_rank,entrance_score,parent_name,parent_phone,"
    "parent_occupation,annual_income,lead_source,referred_by,"
    "assigned_counselor,status,priority,notes,created_by,created_at,"
    "updated_at,blood_group,father_name,mother_name,father_mobile,address,"
    "school_name,hsc_percentage,reference_name,programme_interested,"
    "department_interested,doc_status,full_name,mobile,dob"
)


def get_all_applicants(supabase: Client, limit: int = 50, offset: int = 0):
    try:
        response = (
            supabase.table(TABLE_NAME)
            .select(APPLICANT_COLUMNS)
            .is_("deleted_at", "null")  # soft-deleted rows excluded by default
            .order("created_at", desc=True)
            .order("id")  # tiebreaker: seeded rows share identical created_at,
            # so pagination needs a secondary key for stable, deterministic order
            .range(offset, offset + limit - 1)
            .execute()
        )
    except APIError as e:
        logger.error("Supabase error in get_all_applicants: %s", e)
        raise
    return response.data


def get_applicant_by_id(supabase: Client, applicant_id: str):
    try:
        response = (
            supabase.table(TABLE_NAME)
            .select(APPLICANT_COLUMNS)
            .eq("id", applicant_id)
            .is_("deleted_at", "null")  # soft-deleted rows excluded by default
            .maybe_single()
            .execute()
        )
    except APIError as e:
        logger.error("Supabase error in get_applicant_by_id: %s", e)
        raise
    return response.data if response else None


def create_applicant(supabase: Client, applicant: ApplicantCreate, created_by: str):
    """created_by is always set from the authenticated caller (see
    require_writer in the router), never trusted from the request body -
    otherwise a client could attribute a record to any user id it likes,
    which defeats the point of an audit trail."""
    payload = applicant.model_dump(exclude_none=True, mode="json")
    payload["created_by"] = created_by
    try:
        response = supabase.table(TABLE_NAME).insert(payload).execute()
    except APIError as e:
        logger.error("Supabase error in create_applicant: %s", e)
        raise
    return response.data[0] if response.data else None


def update_applicant(supabase: Client, applicant_id: str, payload: dict):
    try:
        response = (
            supabase.table(TABLE_NAME)
            .update(payload)
            .eq("id", applicant_id)
            .execute()
        )
    except APIError as e:
        logger.error("Supabase error in update_applicant: %s", e)
        raise
    return response.data[0] if response.data else None


def delete_applicant(supabase: Client, applicant_id: str, deleted_by: str) -> bool:
    """Soft delete - see leads_service.delete_lead for the full rationale.
    Same double-delete guard: already-deleted or nonexistent both come
    back as zero affected rows, which the router reports as 404."""
    try:
        response = (
            supabase.table(TABLE_NAME)
            .update({"deleted_at": datetime.now(timezone.utc).isoformat(), "deleted_by": deleted_by})
            .eq("id", applicant_id)
            .is_("deleted_at", "null")
            .execute()
        )
    except APIError as e:
        logger.error("Supabase error in delete_applicant: %s", e)
        raise
    return bool(response.data)

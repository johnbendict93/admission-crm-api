import logging

from postgrest.exceptions import APIError
from supabase import Client

from app.core.config import settings
from app.services.ml_conversion_service import ModelNotAvailableError, get_conversion_model
from ml.features import OPEN_STATUSES, rows_to_frame

logger = logging.getLogger(__name__)

# Re-exported so the router can catch one exception type imported from
# either ML service without caring which model actually raised it - same
# convention as ml_telecaller_match_service.
__all__ = ["ModelNotAvailableError", "get_open_leads_for_telecaller", "rank_leads_for_telecaller"]

# Explicit columns - enough for the model's features (ml/features.py) plus
# what the response needs to display (id/name/phone/status). Excludes
# other PII (email, parent details) the response has no use for.
LEAD_RANKING_COLUMNS = (
    "id,name,phone,school,district,marks,course_interest,parent_occupation,source,status,score,assigned_to"
)


def get_open_leads_for_telecaller(supabase: Client, telecaller_name: str) -> list[dict]:
    """Leads currently assigned to this telecaller that are still being
    worked (status in OPEN_STATUSES - see ml/features.py) - Enrolled/Lost
    leads are resolved, nothing left to rank them for. assigned_to is free
    text matched by name (no real FK from leads to telecallers - same
    situation as ml_telecaller_match_service/followups.called_by), so this
    takes the telecaller's name directly rather than an id."""
    try:
        response = (
            supabase.table(settings.LEADS_TABLE)
            .select(LEAD_RANKING_COLUMNS)
            .eq("assigned_to", telecaller_name)
            .in_("status", sorted(OPEN_STATUSES))
            .is_("deleted_at", "null")
            .execute()
        )
    except APIError as e:
        logger.error("Supabase error in get_open_leads_for_telecaller: %s", e)
        raise
    return response.data


def rank_leads_for_telecaller(leads: list[dict]) -> list[tuple[dict, float]]:
    """Reuses module 13's already-trained conversion model (roadmap module
    21 - "Lead Ranking System" - is module 13's same prediction, reframed:
    instead of asking "will THIS lead convert", rank ALL of a telecaller's
    open leads by that same probability so the most promising ones get
    called first). Scores every lead in one batch predict_proba call and
    returns them sorted best-first; the router turns this into
    RankedLead rows."""
    if not leads:
        return []
    model = get_conversion_model()
    frame = rows_to_frame(leads)
    probabilities = model.predict_proba(frame)[:, 1]
    ranked = sorted(zip(leads, probabilities), key=lambda pair: -pair[1])
    return [(lead, float(p)) for lead, p in ranked]

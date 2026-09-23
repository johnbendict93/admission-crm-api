import logging

from postgrest.exceptions import APIError
from supabase import Client

from app.core.config import settings
from app.services.ml_conversion_service import ModelNotAvailableError, get_conversion_model
from ml.features import rows_to_frame

logger = logging.getLogger(__name__)

# Re-exported so the router can catch one exception type imported from
# either ML service without caring which model actually raised it.
__all__ = ["ModelNotAvailableError", "get_active_telecaller_names", "predict_best_telecaller"]


def get_active_telecaller_names(supabase: Client) -> list[str]:
    """Direct minimal query - not telecallers_service.get_all_telecallers,
    which is paginated for the CRUD UI and would silently drop names past
    its page size. This module needs every active telecaller, not a page
    of them."""
    try:
        response = (
            supabase.table(settings.TELECALLERS_TABLE)
            .select("name")
            .eq("active", True)
            .is_("deleted_at", "null")
            .execute()
        )
    except APIError as e:
        logger.error("Supabase error in get_active_telecaller_names: %s", e)
        raise
    return [row["name"] for row in response.data]


def predict_best_telecaller(lead: dict, telecaller_names: list[str]) -> tuple[str, float, list[tuple[str, float]]]:
    """Reuses module 13's already-trained conversion model rather than
    training a separate one - assigned_to is already one of its features
    (ml/features.py), and this module's whole job (roadmap item 17 -
    "matches best telecaller to lead") is exactly "score this lead against
    each telecaller", which module 13's pipeline already does the moment
    assigned_to is swapped. Holds every other lead field fixed and only
    varies assigned_to.

    lead: a raw lead dict (leads_service.get_lead_by_id) - extra keys like
    name/phone/status are ignored by rows_to_frame, same as
    ml_conversion_service.predict_conversion."""
    model = get_conversion_model()
    rows = [{**lead, "assigned_to": name} for name in telecaller_names]
    frame = rows_to_frame(rows)
    probabilities = model.predict_proba(frame)[:, 1]
    ranked = sorted(zip(telecaller_names, probabilities), key=lambda pair: -pair[1])
    best_name, best_probability = ranked[0]
    return best_name, float(best_probability), [(name, float(p)) for name, p in ranked]

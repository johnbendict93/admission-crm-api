from fastapi import APIRouter, Depends, HTTPException
from postgrest.exceptions import APIError
from supabase import Client

from app.core.config import settings
from app.core.database import get_supabase_client
from app.core.jwt_auth import get_current_user
from app.models.ml_telecaller_match import BestTelecallerResponse, TelecallerMatch
from app.services import leads_service
from app.services.ml_telecaller_match_service import (
    ModelNotAvailableError,
    get_active_telecaller_names,
    predict_best_telecaller,
)

router = APIRouter(prefix="/ml", tags=["ML - Telecaller Matching"])


@router.get("/leads/{lead_id}/best-telecaller", response_model=BestTelecallerResponse)
def get_best_telecaller(
    lead_id: str,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(get_current_user),
):
    """Ranks active telecallers by this lead's predicted conversion
    probability if assigned to each one (roadmap module 17 - "matches best
    telecaller to lead"). Reuses module 13's trained conversion model
    rather than a separate one - see ml_telecaller_match_service.py.
    Read-only: never writes anything back to the lead or reassigns it."""
    try:
        lead = leads_service.get_lead_by_id(supabase, lead_id)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    try:
        telecaller_names = get_active_telecaller_names(supabase)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not telecaller_names:
        raise HTTPException(status_code=404, detail="No active telecallers found")

    try:
        best_name, best_probability, ranked = predict_best_telecaller(lead, telecaller_names)
    except ModelNotAvailableError as e:
        raise HTTPException(status_code=503, detail=str(e))

    return BestTelecallerResponse(
        lead_id=lead_id,
        current_assigned_to=lead.get("assigned_to"),
        best_telecaller=best_name,
        best_telecaller_probability=round(best_probability, 4),
        ranked_telecallers=[
            TelecallerMatch(telecaller=name, predicted_conversion_probability=round(p, 4)) for name, p in ranked
        ],
        model_version=settings.CONVERSION_MODEL_PATH,
    )

from fastapi import APIRouter, Depends, HTTPException
from postgrest.exceptions import APIError
from supabase import Client

from app.core.config import settings
from app.core.database import get_supabase_client
from app.core.jwt_auth import get_current_user
from app.models.ml_followup_timing import BestFollowupTimeResponse, FollowupTimeSlot
from app.services import leads_service
from app.services.ml_followup_timing_service import ModelNotAvailableError, predict_best_followup_time

router = APIRouter(prefix="/ml", tags=["ML - Follow-up Timing"])


@router.get("/leads/{lead_id}/best-followup-time", response_model=BestFollowupTimeResponse)
def get_best_followup_time(
    lead_id: str,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(get_current_user),
):
    """Ranks candidate calling hours (9am-8pm) for this lead's assigned
    telecaller by predicted probability of a positive response (roadmap
    module 14 - see ml/train_followup_timing_model.py for the model
    itself). Read-only: never writes anything back to the lead."""
    try:
        lead = leads_service.get_lead_by_id(supabase, lead_id)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    try:
        best_hour, best_probability, ranked = predict_best_followup_time(lead.get("assigned_to"))
    except ModelNotAvailableError as e:
        raise HTTPException(status_code=503, detail=str(e))

    return BestFollowupTimeResponse(
        lead_id=lead_id,
        assigned_to=lead.get("assigned_to"),
        best_hour=best_hour,
        best_hour_probability=round(best_probability, 4),
        ranked_hours=[FollowupTimeSlot(hour=h, predicted_positive_probability=round(p, 4)) for h, p in ranked],
        model_version=settings.FOLLOWUP_TIMING_MODEL_PATH,
    )

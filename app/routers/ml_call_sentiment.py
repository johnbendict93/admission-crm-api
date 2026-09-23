from fastapi import APIRouter, Depends, HTTPException
from postgrest.exceptions import APIError
from supabase import Client

from app.core.config import settings
from app.core.database import get_supabase_client
from app.core.jwt_auth import get_current_user
from app.models.ml_call_sentiment import CallSentimentResponse, SentimentScore
from app.services import followups_service
from app.services.ml_call_sentiment_service import ModelNotAvailableError, predict_call_sentiment

router = APIRouter(prefix="/ml", tags=["ML - Call Sentiment"])


@router.get("/followups/{followup_id}/sentiment", response_model=CallSentimentResponse)
def get_call_sentiment(
    followup_id: str,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(get_current_user),
):
    """Predicts the sentiment (positive/neutral/negative) of a followup's
    free-text notes (roadmap module 19). Read-only: never writes anything
    back to the followup."""
    try:
        followup = followups_service.get_followup_by_id(supabase, followup_id)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not followup:
        raise HTTPException(status_code=404, detail="Followup not found")

    notes = followup.get("notes") or ""
    try:
        predicted_label, scores = predict_call_sentiment(notes)
    except ModelNotAvailableError as e:
        raise HTTPException(status_code=503, detail=str(e))

    return CallSentimentResponse(
        followup_id=followup_id,
        notes=notes,
        predicted_sentiment=predicted_label,
        scores=[SentimentScore(label=label, probability=round(p, 4)) for label, p in scores],
        model_version=settings.CALL_SENTIMENT_MODEL_PATH,
    )

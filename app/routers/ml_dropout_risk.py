from fastapi import APIRouter, Depends, HTTPException
from postgrest.exceptions import APIError
from supabase import Client

from app.core.config import settings
from app.core.database import get_supabase_client
from app.core.jwt_auth import get_current_user
from app.models.ml_dropout_risk import DropoutRiskResponse
from app.services import applicants_service, applications_service
from app.services.ml_dropout_risk_service import ModelNotAvailableError, predict_dropout_risk

router = APIRouter(prefix="/ml", tags=["ML - Dropout Risk"])


@router.get("/applications/{application_id}/dropout-risk", response_model=DropoutRiskResponse)
def get_dropout_risk(
    application_id: str,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(get_current_user),
):
    """Predicts the probability that this application will NOT end in
    application_stage == "Admitted" (roadmap module 16 - see
    ml/train_dropout_risk_model.py for the model itself). Read-only: never
    writes anything back to the application."""
    try:
        application = applications_service.get_application_by_id(supabase, application_id)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    try:
        applicant = applicants_service.get_applicant_by_id(supabase, application["applicant_id"])
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not applicant:
        raise HTTPException(status_code=404, detail="Linked applicant not found")

    try:
        probability, label = predict_dropout_risk(application, applicant)
    except ModelNotAvailableError as e:
        raise HTTPException(status_code=503, detail=str(e))

    return DropoutRiskResponse(
        application_id=application_id,
        applicant_id=str(application["applicant_id"]),
        application_stage=application.get("application_stage"),
        dropout_probability=round(probability, 4),
        predicted_label=label,
        model_version=settings.DROPOUT_RISK_MODEL_PATH,
    )

from fastapi import APIRouter, Depends, HTTPException
from postgrest.exceptions import APIError
from supabase import Client

from app.core.config import settings
from app.core.database import get_supabase_client
from app.core.jwt_auth import get_current_user
from app.models.ml_fee_default_risk import FeeDefaultRiskResponse
from app.services import applicants_service, fee_due_schedule_service
from app.services.ml_fee_default_risk_service import ModelNotAvailableError, predict_fee_default_risk

router = APIRouter(prefix="/ml", tags=["ML - Fee Default Risk"])


@router.get("/fee-due-schedule/{fee_due_schedule_id}/default-risk", response_model=FeeDefaultRiskResponse)
def get_fee_default_risk(
    fee_due_schedule_id: str,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(get_current_user),
):
    """Predicts the probability that this fee_due_schedule row will go
    unpaid (roadmap module 18 - see ml/train_fee_default_risk_model.py for
    the model itself). Read-only: never writes anything back to the
    schedule row or to fee_payments."""
    try:
        due_row = fee_due_schedule_service.get_fee_due_schedule_by_id(supabase, fee_due_schedule_id)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not due_row:
        raise HTTPException(status_code=404, detail="Fee due-schedule row not found")

    try:
        applicant = applicants_service.get_applicant_by_id(supabase, due_row["applicant_id"])
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not applicant:
        raise HTTPException(status_code=404, detail="Linked applicant not found")

    try:
        probability, label = predict_fee_default_risk(applicant)
    except ModelNotAvailableError as e:
        raise HTTPException(status_code=503, detail=str(e))

    return FeeDefaultRiskResponse(
        fee_due_schedule_id=fee_due_schedule_id,
        applicant_id=str(due_row["applicant_id"]),
        fee_component=due_row["fee_component"],
        academic_year=due_row.get("academic_year"),
        amount_due=due_row["amount_due"],
        due_date=due_row["due_date"],
        default_probability=round(probability, 4),
        predicted_label=label,
        model_version=settings.FEE_DEFAULT_RISK_MODEL_PATH,
    )

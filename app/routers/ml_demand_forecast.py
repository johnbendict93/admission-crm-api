from fastapi import APIRouter, Depends, HTTPException
from fastapi import Path as PathParam

from app.core.config import settings
from app.core.jwt_auth import get_current_user
from ml.features_demand_forecast import BASE_YEAR
from app.models.ml_demand_forecast import DemandForecastResponse
from app.services.ml_demand_forecast_service import ModelNotAvailableError, predict_demand

router = APIRouter(prefix="/ml", tags=["ML - Demand Forecast"])


@router.get("/demand-forecast/{year}/{month}", response_model=DemandForecastResponse)
def get_demand_forecast(
    year: int = PathParam(..., ge=BASE_YEAR, description="Calendar year to forecast"),
    month: int = PathParam(..., ge=1, le=12, description="Calendar month (1-12) to forecast"),
    current_user: dict = Depends(get_current_user),
):
    """Predicts the number of enquiries (leads) expected in a given
    calendar month (roadmap module 20 - see ml/train_demand_forecast_model.py
    for the model itself). A genuine forecast, not a lookup: works for any
    future month, not only ones the model was trained on. No database
    lookup here - the prediction is a pure function of (year, month).

    Honest limitation: this is a linear trend + seasonal fit on ~40-50
    monthly data points (mostly illustrative synthetic history - see
    scripts/seed_dev_enquiry_monthly_history.py). Treat forecasts for the
    next few months as a reasonable planning signal; treat forecasts more
    than a year or two past the model's training data as illustrative, not
    precise. Re-train periodically as more real months of leads data
    accumulate (ml/train_demand_forecast_model.py always prefers real data
    over synthetic where they overlap)."""
    try:
        predicted = predict_demand(year, month)
    except ModelNotAvailableError as e:
        raise HTTPException(status_code=503, detail=str(e))

    return DemandForecastResponse(
        year=year,
        month=month,
        predicted_enquiry_count=round(predicted, 1),
        model_version=settings.DEMAND_FORECAST_MODEL_PATH,
    )

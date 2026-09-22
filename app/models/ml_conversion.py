from pydantic import BaseModel


class ConversionPredictionResponse(BaseModel):
    """Output of the module-13 conversion predictor. Not tied to a Supabase
    table - this model has no *_TABLE setting, it just shapes what the
    endpoint returns."""
    lead_id: str
    probability: float          # 0-1: P(this lead eventually resolves to status "Enrolled")
    predicted_label: str        # human-readable, threshold 0.5 on probability
    model_version: str          # artifact path - a stand-in for real versioning until one exists

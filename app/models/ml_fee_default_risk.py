from datetime import date
from typing import Optional

from pydantic import BaseModel


class FeeDefaultRiskResponse(BaseModel):
    """Output of the module-18 fee default risk predictor. Not tied to a
    Supabase table itself - this model has no *_TABLE setting, it just
    shapes what the endpoint returns."""
    fee_due_schedule_id: str
    applicant_id: str
    fee_component: str
    academic_year: Optional[str]
    amount_due: float
    due_date: date
    default_probability: float   # 0-1: P(no matching payment found by/after due_date)
    predicted_label: str         # human-readable, threshold 0.5 on default_probability
    model_version: str           # artifact path - same stand-in convention as other ML modules

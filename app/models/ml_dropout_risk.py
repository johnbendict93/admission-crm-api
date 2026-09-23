from pydantic import BaseModel


class DropoutRiskResponse(BaseModel):
    """Output of the module-16 dropout risk predictor. Not tied to a
    Supabase table - this model has no *_TABLE setting, it just shapes
    what the endpoint returns."""
    application_id: str
    applicant_id: str
    application_stage: str | None    # the application's CURRENT stage, for context
    dropout_probability: float       # 0-1: P(this application does NOT end in application_stage == "Admitted")
    predicted_label: str             # human-readable, threshold 0.5 on dropout_probability
    model_version: str               # artifact path - same stand-in convention as modules 13/14

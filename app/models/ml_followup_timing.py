from pydantic import BaseModel


class FollowupTimeSlot(BaseModel):
    """One candidate hour and this lead's predicted probability of a
    positive response if called then."""
    hour: int                              # 24-hour clock, e.g. 18 = 6pm
    predicted_positive_probability: float  # 0-1


class BestFollowupTimeResponse(BaseModel):
    """Output of the module-14 optimal follow-up time predictor. Not tied
    to a Supabase table - this model has no *_TABLE setting, it just
    shapes what the endpoint returns."""
    lead_id: str
    assigned_to: str | None       # telecaller this prediction is scoped to (leads.assigned_to)
    best_hour: int
    best_hour_probability: float
    ranked_hours: list[FollowupTimeSlot]   # all candidate hours, best first
    model_version: str            # artifact path - same stand-in convention as module 13

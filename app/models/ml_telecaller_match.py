from pydantic import BaseModel


class TelecallerMatch(BaseModel):
    """One candidate telecaller and this lead's predicted conversion
    probability if assigned to them."""
    telecaller: str
    predicted_conversion_probability: float  # 0-1


class BestTelecallerResponse(BaseModel):
    """Output of the module-17 telecaller matcher. Not tied to a Supabase
    table - this model has no *_TABLE setting, it just shapes what the
    endpoint returns."""
    lead_id: str
    current_assigned_to: str | None
    best_telecaller: str
    best_telecaller_probability: float
    ranked_telecallers: list[TelecallerMatch]  # every active telecaller, best first
    model_version: str  # module 13's artifact path - this module reuses that model, see the service

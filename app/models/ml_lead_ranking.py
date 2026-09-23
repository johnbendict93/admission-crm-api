from pydantic import BaseModel


class RankedLead(BaseModel):
    """One lead in a telecaller's ranked call queue."""
    lead_id: str
    name: str
    phone: str
    status: str | None
    predicted_conversion_probability: float  # 0-1, from module 13's model


class LeadRankingResponse(BaseModel):
    """Output of the module-21 lead ranker. Not tied to a Supabase table -
    this model has no *_TABLE setting, it just shapes what the endpoint
    returns."""
    telecaller: str
    lead_count: int
    ranked_leads: list[RankedLead]  # this telecaller's open (New/Contacted/Visited) leads, best-first
    model_version: str  # module 13's artifact path - this module reuses that model, see the service

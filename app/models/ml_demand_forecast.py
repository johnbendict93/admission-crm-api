from pydantic import BaseModel


class DemandForecastResponse(BaseModel):
    """Output of the module-20 demand forecaster. Not tied to a single
    Supabase row - year/month are the request itself (a calendar month to
    forecast), not a linked entity id."""
    year: int
    month: int
    predicted_enquiry_count: float  # never negative - clipped at 0, see the service
    model_version: str              # artifact path - same stand-in convention as other ML modules

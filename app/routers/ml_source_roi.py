from fastapi import APIRouter, Depends, HTTPException
from postgrest.exceptions import APIError
from supabase import Client

from app.core.database import get_supabase_client
from app.core.jwt_auth import get_current_user
from app.models.ml_source_roi import SourceROIResponse
from app.services.ml_source_roi_service import get_source_performance

router = APIRouter(prefix="/ml", tags=["ML - Source ROI"])

_NOTE = (
    "overall_conversion_rate = Enrolled / all leads from this source. "
    "resolved_conversion_rate = Enrolled / (Enrolled + Lost) - excludes leads "
    "still New/Contacted/Visited, so a source that ramped up recently isn't "
    "unfairly penalized for having more open leads. Sort order uses "
    "resolved_conversion_rate. True cost-per-rupee ROI is NOT computed - "
    "there is no marketing spend/cost data anywhere in the schema yet."
)


@router.get("/source-performance", response_model=SourceROIResponse)
def get_source_roi(
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(get_current_user),
):
    """Roadmap module 15 (Enquiry Source ROI Analyzer) - conversion
    performance by lead source, computed live from the leads table (not a
    trained model - see `note` in the response for exactly what this does
    and doesn't measure)."""
    try:
        sources = get_source_performance(supabase)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    return SourceROIResponse(sources=sources, note=_NOTE)

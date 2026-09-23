from fastapi import APIRouter, Depends, HTTPException
from postgrest.exceptions import APIError
from supabase import Client

from app.core.config import settings
from app.core.database import get_supabase_client
from app.core.jwt_auth import get_current_user
from app.models.ml_lead_ranking import LeadRankingResponse, RankedLead
from app.services.ml_lead_ranking_service import (
    ModelNotAvailableError,
    get_open_leads_for_telecaller,
    rank_leads_for_telecaller,
)

router = APIRouter(prefix="/ml", tags=["ML - Lead Ranking"])


@router.get("/telecallers/{telecaller_name}/ranked-leads", response_model=LeadRankingResponse)
def get_ranked_leads(
    telecaller_name: str,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(get_current_user),
):
    """Ranks a telecaller's open leads (New/Contacted/Visited) by module
    13's predicted conversion probability, best-first (roadmap module 21 -
    same model as module 13, reframed as "which of my leads should I call
    next"). Read-only: never writes anything back to any lead. An unknown
    or currently-empty telecaller_name simply returns zero ranked leads,
    not a 404 - assigned_to is free text, not a real FK to telecallers."""
    try:
        leads = get_open_leads_for_telecaller(supabase, telecaller_name)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")

    try:
        ranked = rank_leads_for_telecaller(leads)
    except ModelNotAvailableError as e:
        raise HTTPException(status_code=503, detail=str(e))

    return LeadRankingResponse(
        telecaller=telecaller_name,
        lead_count=len(ranked),
        ranked_leads=[
            RankedLead(
                lead_id=lead["id"],
                name=lead["name"],
                phone=lead["phone"],
                status=lead.get("status"),
                predicted_conversion_probability=round(p, 4),
            )
            for lead, p in ranked
        ],
        model_version=settings.CONVERSION_MODEL_PATH,
    )

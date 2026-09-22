import logging

from postgrest.exceptions import APIError
from supabase import Client

from app.core.config import settings

logger = logging.getLogger(__name__)

TABLE_NAME = settings.LEADS_TABLE

# Below this many leads from a source, the conversion rate is noisy enough
# not to trust - flagged via low_sample rather than hidden.
LOW_SAMPLE_THRESHOLD = 20


def get_source_performance(supabase: Client) -> list[dict]:
    """Pulls source+status for every non-deleted lead and aggregates in
    Python. PostgREST (what supabase-py talks to) doesn't do GROUP BY, and
    the leads table is small enough (currently ~500 rows) that this is
    simpler than a raw SQL aggregate and just as fast."""
    try:
        response = (
            supabase.table(TABLE_NAME)
            .select("source,status")
            .is_("deleted_at", "null")
            .execute()
        )
    except APIError as e:
        logger.error("Supabase error in get_source_performance: %s", e)
        raise

    counts: dict[str, dict[str, int]] = {}
    for row in response.data:
        source = row.get("source") or "Unknown"
        bucket = counts.setdefault(source, {"total": 0, "enrolled": 0, "lost": 0, "unresolved": 0})
        bucket["total"] += 1
        status = row.get("status")
        if status == "Enrolled":
            bucket["enrolled"] += 1
        elif status == "Lost":
            bucket["lost"] += 1
        else:
            bucket["unresolved"] += 1

    results = []
    for source, c in counts.items():
        resolved = c["enrolled"] + c["lost"]
        results.append({
            "source": source,
            "total_leads": c["total"],
            "enrolled_count": c["enrolled"],
            "lost_count": c["lost"],
            "unresolved_count": c["unresolved"],
            "overall_conversion_rate": round(c["enrolled"] / c["total"], 4) if c["total"] else 0.0,
            "resolved_conversion_rate": round(c["enrolled"] / resolved, 4) if resolved else None,
            "low_sample": c["total"] < LOW_SAMPLE_THRESHOLD,
        })

    # Best resolved_conversion_rate first; sources with no resolved leads yet go last.
    results.sort(key=lambda r: (r["resolved_conversion_rate"] is None, -(r["resolved_conversion_rate"] or 0)))
    return results

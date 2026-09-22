from typing import List, Optional

from pydantic import BaseModel


class SourcePerformance(BaseModel):
    source: str
    total_leads: int
    enrolled_count: int
    lost_count: int
    unresolved_count: int              # New/Contacted/Visited - outcome not yet known
    overall_conversion_rate: float     # enrolled / total_leads
    resolved_conversion_rate: Optional[float] = None  # enrolled / (enrolled + lost); None if no resolved leads yet
    low_sample: bool                   # total_leads below LOW_SAMPLE_THRESHOLD - rate isn't reliable yet


class SourceROIResponse(BaseModel):
    """Roadmap module 15 - not tied to a Supabase table, no *_TABLE
    setting. Aggregated live from the leads table on every request, not a
    trained/saved model like module 13 - there's nothing to train here."""
    sources: List[SourcePerformance]   # sorted by resolved_conversion_rate desc, unresolved-only sources last
    note: str

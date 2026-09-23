from pydantic import BaseModel


class SentimentScore(BaseModel):
    label: str          # "positive" / "neutral" / "negative"
    probability: float  # 0-1, this class's predicted probability


class CallSentimentResponse(BaseModel):
    """Output of the module-19 call sentiment analyzer. Not tied to a
    Supabase table - this model has no *_TABLE setting, it just shapes
    what the endpoint returns."""
    followup_id: str
    notes: str
    predicted_sentiment: str      # the highest-probability label
    scores: list[SentimentScore]  # all 3 classes, for transparency
    model_version: str            # artifact path - same stand-in convention as other ML modules

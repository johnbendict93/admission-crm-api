from typing import Generic, List, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Standard envelope returned by every list endpoint across all 14
    modules (added Sept 2026 so a frontend never has to guess how many
    total rows exist behind a page, or reimplement the has-more-pages
    arithmetic itself).

    `total` is the count of ALL rows matching the endpoint's default
    filter (deleted_at IS NULL, or is_active = true for the three
    config-style modules) - independent of `limit`/`offset`, i.e. how
    many rows exist in total, not how many are in `items`.

    `has_more` is precomputed server-side: `offset + len(items) < total`.
    """

    items: List[T]
    total: int
    limit: int
    offset: int
    has_more: bool

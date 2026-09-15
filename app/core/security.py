import secrets
from typing import Optional

from fastapi import Header, HTTPException, status

from app.core.config import settings


def verify_api_key(x_api_key: Optional[str] = Header(None, alias="X-API-Key")) -> None:
    """Shared-secret auth dependency for all business routers.

    The expected key comes from Settings/.env (zero hardcoding, same
    pattern as every other config value in this project) and the
    comparison is constant-time (secrets.compare_digest) to avoid leaking
    timing information about a partially-correct key. Missing and wrong
    keys both return the same 401 — no distinction that would help an
    attacker narrow things down.
    """
    if not x_api_key or not secrets.compare_digest(x_api_key, settings.API_KEY):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )

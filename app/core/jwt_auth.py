"""Per-user JWT authentication, replacing the old shared API-key dependency
(app/core/security.py::verify_api_key - that file has been deleted).

How verification works: Supabase migrated this project's auth server from a
single shared HS256 secret to asymmetric JWT Signing Keys (confirmed live on
both dev and prod — see Settings -> API -> JWT Keys in each project's
dashboard: current key is ECC P-256 on both). That means there is no shared
secret to store in Settings/.env for verifying tokens — instead, each
project publishes its current public key(s) at a JWKS endpoint, and a
token's signature is verified locally against whichever key matches its
`kid` header. PyJWKClient handles fetching + caching that endpoint (10
minutes, matching Supabase's own edge-cache duration for it, per
https://supabase.com/docs/guides/auth/jwts).

supabase-py has no built-in verify/get_claims() helper for this yet (see
https://github.com/supabase/supabase-py/issues/1183), so this is hand-rolled
with PyJWT - the standard pattern recommended in Supabase's own docs for
non-JS backends.

Auth extraction uses FastAPI's HTTPBearer security scheme (not a raw Header
param) so /docs gets a real "Authorize" button and the OpenAPI spec carries
a proper securityScheme - added Sept 2026 after a consistency review found
every protected endpoint required manually pasting "Bearer <token>" into a
plain header field on every single request in Swagger UI. auto_error=False
so a missing/malformed header still reaches our own error handling below (a
consistent 401 with our own detail message) instead of HTTPBearer's default.
"""
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from supabase import Client

from app.core.config import settings
from app.core.database import get_supabase_client

# One PyJWKClient per distinct SUPABASE_URL seen so far, cached for the
# process lifetime. In practice there's only ever one active URL per
# running process (dev or prod, per ENVIRONMENT) but this avoids assuming
# that and re-creating clients pointlessly if it's ever imported oddly
# (e.g. by tooling/tests that touch both).
_jwks_clients: dict[str, PyJWKClient] = {}

# See module docstring: this is what registers the OpenAPI securityScheme
# and adds the /docs "Authorize" button. auto_error=False keeps a missing
# or malformed header (or wrong scheme, e.g. "Basic ...") from short-
# circuiting with FastAPI's own generic error - it comes back as None and
# falls through to get_current_user's own check below instead, so the
# 401 detail message stays exactly what it was before this change.
_bearer_scheme = HTTPBearer(auto_error=False)


def _get_jwks_client(supabase_url: str) -> PyJWKClient:
    if supabase_url not in _jwks_clients:
        _jwks_clients[supabase_url] = PyJWKClient(
            f"{supabase_url}/auth/v1/.well-known/jwks.json",
            cache_keys=True,
            lifespan=600,  # seconds; matches Supabase's own edge-cache TTL for this endpoint
        )
    return _jwks_clients[supabase_url]


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """Decodes and verifies a Supabase-issued access token, then looks up
    the matching row in public.users to get the app-level role (Supabase
    Auth itself knows nothing about admin/counselor/staff/viewer - that's
    our own users table). Returns that row as a dict; raises 401 on any
    failure (missing header, malformed header/scheme, bad/expired
    signature, or the user id from the token not existing in public.users).
    """
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header (expected 'Bearer <token>')",
        )
    token = credentials.credentials.strip()

    try:
        signing_key = _get_jwks_client(settings.SUPABASE_URL).get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256", "RS256"],
            audience="authenticated",
            leeway=10,
        )
    except jwt.PyJWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {e}",
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token missing 'sub' claim")

    response = (
        supabase.table(settings.USERS_TABLE)
        .select("id, email, full_name, role, is_active")
        .eq("id", user_id)
        .limit(1)
        .execute()
    )
    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authenticated user has no matching row in the users table",
        )

    user = response.data[0]
    if not user.get("is_active", True):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User account is inactive")
    return user


def require_writer(current_user: dict = Depends(get_current_user)) -> dict:
    """Blocks the 'viewer' role from write operations (POST/PATCH).
    admin/counselor/staff may all write - only viewer is read-only."""
    if current_user["role"] == "viewer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Viewer role is read-only",
        )
    return current_user


def require_deleter(current_user: dict = Depends(get_current_user)) -> dict:
    """Only admin/staff may delete records - stricter than require_writer,
    per the task's explicit role matrix."""
    if current_user["role"] not in ("admin", "staff"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin or staff roles may delete records",
        )
    return current_user


def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """Only the admin role may manage user accounts (create/edit/deactivate).
    Stricter than require_deleter, which also lets staff through."""
    if current_user["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the admin role may manage users",
        )
    return current_user

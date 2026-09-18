from functools import lru_cache

import httpx
from postgrest.constants import DEFAULT_POSTGREST_CLIENT_TIMEOUT
from supabase import Client, ClientOptions, create_client

from app.core.config import settings

# Root cause of the recurring "transient" pytest network flakes (Sept
# 2026): get_supabase_client() below is @lru_cache'd - ONE process-wide
# httpx client/connection reused for the entire process lifetime. In
# the test suite that means a single HTTP/2 connection carries ~5,000+
# requests over a 20+ minute run (tests/conftest.py's verify_db_untouched
# fixture alone does a full 14-table row-count sweep before AND after
# every single test - ~4,800 of the suite's requests). Across three
# separate sessions this has surfaced as a connection-level read
# failure (RemoteProtocolError, WinError 10054, an SSL protocol-version
# alert) on three different, unrelated tests (test_leads/test_applicants,
# test_auth, test_fee_payments) - never the same test twice. That rules
# out anything specific to any one module's code: it's the shared
# long-lived HTTP/2 connection occasionally getting recycled somewhere
# on the network path to Supabase's edge, and whichever request happens
# to be reading a response on it at that instant eats a connection
# error. httpx's own `retries=` transport option only covers failures
# during connection *establishment*, not a previously-good pooled
# connection going stale between requests, so it does not help here.
#
# This also isn't just a test-suite problem: the same singleton client
# serves the running FastAPI app in production, where a long-uptime
# process would eventually hit the identical failure on a real request
# - and nothing currently catches it, since the `except APIError`
# blocks in every router only catch PostgREST-level errors (4xx/5xx
# responses), not transport-level ones like httpx.ReadError. A real
# request could currently 500 on a purely transient, retryable blip.
#
# Fix: give the client a transport that retries exactly once, but only
# for idempotent methods (GET/HEAD/OPTIONS - never POST/PATCH/DELETE,
# so a write is never silently double-applied). This is the standard
# pattern for long-lived pooled-connection clients; it fixes both the
# test flake and the latent production gap without changing HTTP/2 or
# any other behavior.
_IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class _RetryOnceTransport(httpx.HTTPTransport):
    """httpx.HTTPTransport that retries a request exactly once if it
    fails with a connection-level error (ConnectError, ReadError,
    RemoteProtocolError, etc. - anything under httpx.TransportError),
    provided the method is safe to retry. See module docstring above
    for why this is needed."""

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        try:
            return super().handle_request(request)
        except httpx.TransportError:
            if request.method not in _IDEMPOTENT_METHODS:
                raise
            return super().handle_request(request)


def _build_httpx_client() -> httpx.Client:
    # Mirrors postgrest's own default Client construction (timeout,
    # http2, follow_redirects) - see postgrest/_sync/client.py - except
    # for the transport, which is swapped for _RetryOnceTransport above.
    # base_url/headers are deliberately not set here: postgrest passes
    # the full absolute path and explicit headers (auth, apikey, etc.)
    # on every single request regardless of the client's own defaults
    # (see postgrest/base_request_builder.py RequestConfig.send), so a
    # bare client is safe to hand it.
    return httpx.Client(
        timeout=DEFAULT_POSTGREST_CLIENT_TIMEOUT,
        follow_redirects=True,
        transport=_RetryOnceTransport(http2=True),
    )


@lru_cache
def get_supabase_client() -> Client:
    """FastAPI dependency — one cached client per process, injected per-request
    instead of a module-level global. Makes services testable with a mock client.

    Uses the service_role key: full CRUD access, bypasses RLS. This is the
    client every business router and service uses."""
    return create_client(
        settings.SUPABASE_URL,
        settings.SUPABASE_KEY,
        options=ClientOptions(httpx_client=_build_httpx_client()),
    )


@lru_cache
def get_supabase_auth_client() -> Client:
    """A separate client instantiated with the anon (public) key, used only
    for the login endpoint's sign_in_with_password() call (app/routers/auth.py).
    The anon key is the correct, minimal-privilege credential for a
    client-facing auth operation — the service_role key above must never be
    used to authenticate an end user."""
    return create_client(
        settings.SUPABASE_URL,
        settings.SUPABASE_ANON_KEY,
        options=ClientOptions(httpx_client=_build_httpx_client()),
    )

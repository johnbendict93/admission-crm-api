"""Tests for the shared API-key auth dependency (app/core/security.py),
applied to every business router (leads, applicants, applications).
The /health endpoint is intentionally left open and is not covered here.
"""


class TestApiKeyAuth:
    def test_request_without_api_key_returns_401(self, client):
        response = client.get("/leads/", headers={"X-API-Key": ""})
        assert response.status_code == 401
        assert response.status_code != 500

    def test_request_with_wrong_api_key_returns_401(self, client):
        response = client.get(
            "/applicants/", headers={"X-API-Key": "definitely-not-the-real-key"}
        )
        assert response.status_code == 401
        assert response.status_code != 500

    def test_request_with_correct_api_key_succeeds(self, client):
        # The shared `client` fixture already sends the real key by
        # default (see conftest.py) — this just confirms that path works
        # for all three protected routers, not only the ones exercised
        # elsewhere in the suite.
        assert client.get("/leads/").status_code == 200
        assert client.get("/applicants/").status_code == 200
        assert client.get("/applications/").status_code == 200

    def test_health_check_does_not_require_api_key(self, client):
        response = client.get("/health", headers={"X-API-Key": ""})
        assert response.status_code == 200

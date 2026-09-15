"""HTTP contract.

Only the rejection paths and the two read-only routes are exercised: a valid
request would run the full agent pipeline, which needs an API key and several
model calls. Validation happens before the orchestrator is touched, so these stay
fast and offline.
"""

import pytest

from src.api.app import app


@pytest.fixture
def client():
    app.config.update(TESTING=True)
    return app.test_client()


def test_health_is_ok(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"


def test_root_lists_the_endpoints(client):
    body = client.get("/").get_json()
    assert body["service"] == "reguard-ai"
    assert "audit" in body["endpoints"]


def test_audit_rejects_a_missing_clause(client):
    response = client.post("/api/audit", json={})
    assert response.status_code == 400
    assert "required" in response.get_json()["error"]


def test_audit_rejects_a_short_clause(client):
    response = client.post("/api/audit", json={"clause_text": "too short"})
    assert response.status_code == 400
    assert "at least" in response.get_json()["error"]


def test_audit_rejects_an_overlong_clause(client):
    response = client.post("/api/audit", json={"clause_text": "x" * 10001})
    assert response.status_code == 400
    assert "at most" in response.get_json()["error"]


@pytest.mark.parametrize("value", [123, ["a", "list"], {"nested": "object"}, True])
def test_audit_rejects_a_non_string_clause_as_json(client, value):
    """A wrong type used to reach .strip() and return an HTML 500."""
    response = client.post("/api/audit", json={"clause_text": value})

    assert response.status_code == 400
    assert response.is_json
    assert "string" in response.get_json()["error"]


def test_audit_rejects_a_non_object_body(client):
    response = client.post("/api/audit", json=["not", "an", "object"])

    assert response.status_code == 400
    assert response.get_json()["error"] == "Request body must be a JSON object."


def test_audit_rejects_a_body_that_is_not_json(client):
    response = client.post("/api/audit", data="clause_text=hello", content_type="text/plain")

    assert response.status_code == 400
    assert response.is_json


def test_wrong_method_is_method_not_allowed(client):
    assert client.get("/api/audit").status_code == 405


def test_errors_are_json_not_html(client):
    """The frontend parses JSON, so an HTML error page breaks it confusingly."""
    response = client.post("/api/audit", json={"clause_text": 1})
    assert response.content_type.startswith("application/json")

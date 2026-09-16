"""HTTP contract.

Only the rejection paths and the read-only routes are exercised: a valid request
would run the full agent pipeline, which needs an API key and several model
calls. Validation happens before the orchestrator is touched, so these stay fast
and offline.
"""

import pytest

from src.api import app as api


@pytest.fixture
def client():
    api.app.config.update(TESTING=True)
    return api.app.test_client()


@pytest.fixture(autouse=True)
def clear_rate_limit_state():
    """The window counters are module state, so they must not leak between tests."""
    api._rate_windows.clear()
    yield
    api._rate_windows.clear()


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


def test_every_response_carries_a_request_id(client):
    """A reported failure has to be findable in the log."""
    response = client.post("/api/audit", json={})

    request_id = response.headers["X-Request-Id"]
    assert request_id
    assert response.get_json()["request_id"] == request_id


def test_a_caller_supplied_request_id_is_reused(client):
    response = client.get("/api/health", headers={"X-Request-Id": "trace-123"})
    assert response.headers["X-Request-Id"] == "trace-123"


def test_errors_carry_a_machine_readable_code(client):
    """The frontend prints `error`; the code is what a caller can branch on."""
    body = client.post("/api/audit", json={}).get_json()

    assert body["code"] == "invalid_request"
    assert isinstance(body["error"], str)


@pytest.mark.parametrize("path", ["/api/nope", "/api/audit/details"])
def test_unknown_routes_answer_with_json_not_the_default_html(client, path):
    """Flask's default 404 page is HTML, which the frontend cannot parse."""
    response = client.get(path)

    assert response.status_code == 404
    assert response.is_json
    assert response.get_json()["code"] == "not_found"


def test_wrong_method_answers_with_json_and_says_which_method_is_allowed(client):
    response = client.get("/api/audit")

    assert response.status_code == 405
    assert response.is_json
    assert response.get_json()["code"] == "method_not_allowed"


def test_an_oversized_body_is_rejected_rather_than_buffered(client):
    """A clause is a paragraph; anything at the body cap is not one."""
    payload = {"clause_text": "x" * (api.MAX_BODY_BYTES + 1)}
    response = client.post("/api/audit", json=payload)

    assert response.status_code == 413
    assert response.get_json()["code"] == "body_too_large"


def test_rate_limit_blocks_a_caller_that_exceeds_its_window():
    """One audit is several model calls, so a loop must not be free."""
    allowed = [
        api.rate_limit("10.0.0.1", now=1000.0)[0]
        for _ in range(api.RATE_LIMIT_REQUESTS + 1)
    ]

    assert allowed[: api.RATE_LIMIT_REQUESTS] == [True] * api.RATE_LIMIT_REQUESTS
    assert allowed[-1] is False


def test_rate_limit_forgets_a_caller_once_the_window_passes():
    for _ in range(api.RATE_LIMIT_REQUESTS + 1):
        api.rate_limit("10.0.0.2", now=1000.0)

    allowed, _remaining, _retry = api.rate_limit(
        "10.0.0.2", now=1000.0 + api.RATE_LIMIT_WINDOW_SECONDS
    )
    assert allowed is True


def test_rate_limit_counts_each_caller_separately():
    """One noisy client must not lock everyone else out."""
    for _ in range(api.RATE_LIMIT_REQUESTS + 1):
        api.rate_limit("10.0.0.3", now=1000.0)

    assert api.rate_limit("10.0.0.4", now=1000.0)[0] is True


def test_the_rate_limit_reports_when_to_retry():
    for _ in range(api.RATE_LIMIT_REQUESTS + 1):
        api.rate_limit("10.0.0.5", now=1000.0)

    _allowed, _remaining, retry_after = api.rate_limit("10.0.0.5", now=1000.0)
    assert 0 < retry_after <= api.RATE_LIMIT_WINDOW_SECONDS


def test_readiness_reports_the_parts_retrieval_depends_on(client):
    """The deployment failure this guards against had no corpus at all."""
    response = client.get("/api/ready")
    body = response.get_json()

    assert body["retrieval"]["corpus_file"] is True
    assert body["retrieval"]["onnx_model"] is True
    assert body["retrieval"]["regulatory_chunks"] > 0
    assert body["retrieval"]["retrieval_ready"] is True
    assert response.status_code == 200


def test_metrics_serves_the_measured_results(client):
    """The dashboard reads the same artefact the report quotes."""
    body = client.get("/api/metrics").get_json()

    assert "hybrid" in body["retrieval"]["strategies"]
    assert body["retrieval"]["strategies"]["hybrid"]["macro"]["recall@4"] is not None
    assert body["retrieval"]["verdict"]["best_ndcg@8"]
    assert body["ml"]["shipped_model"]["name"]
    assert body["benchmark"]["total_clauses"] == 24


def test_metrics_drops_the_per_clause_arrays(client):
    """96 rows of per-clause scores are noise on a dashboard."""
    body = client.get("/api/metrics").get_json()

    for entry in body["retrieval"]["strategies"].values():
        assert "per_clause" not in entry



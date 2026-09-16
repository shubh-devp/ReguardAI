# """Flask API for Reguard AI.

# One endpoint does the work: POST /api/audit runs the whole agent pipeline for a
# single policy clause and returns the result as JSON.

# Three routes back it up: GET / (a human checking the URL sees something real),
# GET /api/health (cheap, for uptime monitoring) and GET /api/ready (checks the
# corpus, the encoder and the index, for diagnosing a deployment).
# """

# import logging
# import os
# import sys
# import threading
# import time
# import uuid
# from pathlib import Path

# # Cap every numerical library's thread pool at one thread.
# #
# # This is not a tuning preference, it decides whether the process fits in the
# # instance at all. numpy defaults to one worker per core, and importing it then
# # calling into BLAS allocates a thread pool plus per-thread scratch buffers. That
# # measured +235 MB of resident memory on an 8-core box here, against +10 MB when
# # capped, and scikit-learn inherits the same cost on top.
# #
# # Each library reads a different variable, so all of them are set. OpenBLAS is the
# # one that matters on Linux: the pip wheels for numpy and scipy link against it, and
# # it ignores OMP_NUM_THREADS unless it was built with OpenMP. Setting only the
# # OpenMP and MKL variables therefore looked correct on a development machine and did
# # nothing in the container, which is what made the deployed process exceed its
# # memory limit during warm-up.
# #
# # These have to be in the environment before numpy is first imported, which is why
# # they sit at the top of the module rather than inside main().
# os.environ.setdefault("OMP_NUM_THREADS", "1")
# os.environ.setdefault("MKL_NUM_THREADS", "1")
# os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
# os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")
# os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
# os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

# # The project root has to be importable for `from src....` to work. Render starts
# # the app as `python app.py`, which puts src/api/ on sys.path instead of the root.
# PROJECT_ROOT = Path(__file__).resolve().parents[2]
# if str(PROJECT_ROOT) not in sys.path:
#     sys.path.insert(0, str(PROJECT_ROOT))

# # data/corpus, data/chroma_db, data/database and data/processed are all resolved
# # relative to the working directory, so pin it to the project root.
# os.chdir(PROJECT_ROOT)

# from flask import Flask, jsonify, request
# from flask_cors import CORS

# logging.basicConfig(
#     level=logging.WARNING,
#     format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
# )

# # Only our own modules and the HTTP access log talk at INFO. Third-party
# # libraries are left at WARNING, otherwise httpx prints a line for every
# # request it makes while downloading the embedding model.
# for logger_name in ("reguard", "src", "werkzeug"):
#     logging.getLogger(logger_name).setLevel(logging.INFO)

# logger = logging.getLogger("reguard.api")

# app = Flask(__name__)

# # Comma-separated list of allowed origins. Defaults to "*" so local development
# # and preview URLs keep working; set ALLOWED_ORIGINS in production.
# ALLOWED_ORIGINS = [origin.strip() for origin in os.environ.get("ALLOWED_ORIGINS", "*").split(",") if origin.strip()]
# CORS(app, origins=ALLOWED_ORIGINS or ["*"], expose_headers=["X-Request-Id"])

# MIN_CLAUSE_CHARS = 10
# MAX_CLAUSE_CHARS = 10000

# # A clause is a paragraph, not a document, so the body is capped well below the
# # 10 KB text limit to leave room for the JSON envelope.
# MAX_BODY_BYTES = 64 * 1024
# app.config["MAX_CONTENT_LENGTH"] = MAX_BODY_BYTES

# # Fixed-window rate limit per caller. One audit is several model calls, so this
# # is mostly here to stop a loop from burning the API quota and the instance's
# # memory. Raise or disable it through the environment.
# RATE_LIMIT_REQUESTS = int(os.environ.get("RATE_LIMIT_REQUESTS", "30"))
# RATE_LIMIT_WINDOW_SECONDS = int(os.environ.get("RATE_LIMIT_WINDOW_SECONDS", "60"))

# # The agents are imported inside get_orchestrator() on purpose. Importing them
# # pulls in onnxruntime and ChromaDB, which takes tens of seconds and hundreds of
# # megabytes. Doing that at module level kept the port closed for too long, so
# # Render's port scan reported "No open ports detected".
# _orchestrator = None
# _orchestrator_lock = threading.Lock()

# # Fixed-window counters, keyed by caller. Small and in-process on purpose: on one
# # instance behind one Render service this is enough, and a shared store would be
# # a lot of machinery for a demo deployment.
# _rate_windows = {}
# _rate_lock = threading.Lock()


# def get_orchestrator():
#     """Build the orchestrator once, on first use, and reuse it afterwards."""
#     global _orchestrator
#     if _orchestrator is None:
#         with _orchestrator_lock:
#             if _orchestrator is None:
#                 from src.agents.orchestrator import ReguardOrchestrator

#                 logger.info("Loading agents, corpus and vector store (first run only)")
#                 _orchestrator = ReguardOrchestrator()
#                 logger.info("Orchestrator ready")
#     return _orchestrator


# def warm_up():
#     """Load the agents in the background so the first audit does not have to."""
#     try:
#         get_orchestrator()
#     except Exception:
#         logger.exception("Warm-up failed; the first audit will try again")


# def error_response(code, message, status, request_id):
#     """One error shape everywhere.

#     ``error`` stays a plain string because that is what the frontend prints; the
#     machine-readable code and the request id are added alongside it so a report
#     can be traced back to a log line.
#     """
#     return jsonify({"error": message, "code": code, "request_id": request_id}), status


# def validate(body):
#     """Returns (clause_text, error_message). One of the two is always None."""
#     if not isinstance(body, dict):
#         return None, "Request body must be a JSON object."

#     clause_text = body.get("clause_text")
#     if clause_text is None or (isinstance(clause_text, str) and not clause_text.strip()):
#         return None, "clause_text is required."
#     if not isinstance(clause_text, str):
#         # Without this, a number or list would reach .strip() and raise, turning a
#         # bad request into a 500 with an HTML body instead of a JSON error.
#         return None, "clause_text must be a string."

#     clause_text = clause_text.strip()
#     if len(clause_text) < MIN_CLAUSE_CHARS:
#         return None, f"clause_text must be at least {MIN_CLAUSE_CHARS} characters."
#     if len(clause_text) > MAX_CLAUSE_CHARS:
#         return None, f"clause_text must be at most {MAX_CLAUSE_CHARS} characters."

#     return clause_text, None


# def _optional_string(body, key, fallback):
#     """Read an optional string field, ignoring a wrong-typed value."""
#     value = body.get(key)
#     if isinstance(value, str) and value.strip():
#         return value.strip()
#     return fallback


# def rate_limit(caller, now=None):
#     """Count one request against a caller's window.

#     Returns ``(allowed, remaining, retry_after_seconds)``. Disabled when
#     RATE_LIMIT_REQUESTS is 0, which is what tests and local development use.
#     """
#     if RATE_LIMIT_REQUESTS <= 0:
#         return True, RATE_LIMIT_REQUESTS, 0

#     now = now if now is not None else time.time()
#     with _rate_lock:
#         window_start, count = _rate_windows.get(caller, (now, 0))
#         if now - window_start >= RATE_LIMIT_WINDOW_SECONDS:
#             window_start, count = now, 0
#         count += 1
#         _rate_windows[caller] = (window_start, count)

#         if len(_rate_windows) > 1024:
#             # Without this the table grows with every distinct caller, which on a
#             # 512 MB instance is a slow leak an attacker controls.
#             cutoff = now - RATE_LIMIT_WINDOW_SECONDS
#             for key in [key for key, (start, _) in _rate_windows.items() if start < cutoff]:
#                 del _rate_windows[key]

#     retry_after = max(0, int(window_start + RATE_LIMIT_WINDOW_SECONDS - now))
#     return count <= RATE_LIMIT_REQUESTS, max(0, RATE_LIMIT_REQUESTS - count), retry_after


# @app.before_request
# def assign_request_id():
#     """Give every request an id, so a report can be traced to its log lines."""
#     request.request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex[:12]


# @app.after_request
# def tag_response(response):
#     response.headers["X-Request-Id"] = getattr(request, "request_id", "-")
#     return response


# @app.errorhandler(404)
# def handle_not_found(_error):
#     return error_response(
#         "not_found",
#         f"{request.method} {request.path} is not a route. Use POST /api/audit.",
#         404,
#         getattr(request, "request_id", "-"),
#     )


# @app.errorhandler(405)
# def handle_method_not_allowed(_error):
#     return error_response(
#         "method_not_allowed",
#         f"{request.method} is not allowed on {request.path}.",
#         405,
#         getattr(request, "request_id", "-"),
#     )


# @app.errorhandler(413)
# def handle_too_large(_error):
#     return error_response(
#         "body_too_large",
#         f"Request body must be at most {MAX_BODY_BYTES} bytes.",
#         413,
#         getattr(request, "request_id", "-"),
#     )


# @app.errorhandler(500)
# def handle_server_error(_error):
#     """A crash must still answer with JSON, because the frontend parses JSON."""
#     return error_response(
#         "internal_error",
#         "The audit pipeline failed. Check the server log for the traceback.",
#         500,
#         getattr(request, "request_id", "-"),
#     )


# @app.route("/", methods=["GET"])
# def index():
#     """Opening the base URL should not look like a broken deployment."""
#     return jsonify(
#         {
#             "service": "reguard-ai",
#             "status": "ok",
#             "endpoints": {
#                 "health": "GET /api/health",
#                 "ready": "GET /api/ready",
#                 "metrics": "GET /api/metrics",
#                 "audit": "POST /api/audit",
#             },
#         }
#     ), 200


# @app.route("/api/health", methods=["GET"])
# def health():
#     """Cheap liveness check. Does not touch the models, so it cannot be slow."""
#     return jsonify({"status": "ok", "service": "reguard-ai"}), 200


# @app.route("/api/ready", methods=["GET"])
# def ready():
#     """Dependency-aware check: can an audit actually retrieve evidence?

#     The port being open says nothing about whether retrieval works, and the
#     deployment failure this project hit was exactly that gap.

#     Imported from src.retrieval.health, which touches only the filesystem. Pulling
#     in the retriever module here would drag ChromaDB, onnxruntime and LangChain into
#     a request thread - tens of seconds on a cold container, which is long enough to
#     be marked unhealthy and restarted if this endpoint is used as a health check.
#     """
#     from src.retrieval.health import corpus_status

#     status = corpus_status()
#     return jsonify(
#         {
#             "status": "ready" if status["retrieval_ready"] else "degraded",
#             "service": "reguard-ai",
#             "orchestrator_loaded": _orchestrator is not None,
#             "retrieval": status,
#         }
#     ), (200 if status["retrieval_ready"] else 503)


# @app.route("/api/metrics", methods=["GET"])
# def metrics():
#     """The measured evaluation results, so the dashboard shows real numbers.

#     Served from the files the evaluation scripts write. Nothing here is typed in
#     by hand, and the dashboard reads the same artefact the README quotes.
#     """
#     from src.evaluation import results

#     return jsonify(results.headline()), 200


# @app.route("/api/audit", methods=["POST"])
# def run_audit():
#     started = time.time()
#     request_id = request.request_id

#     # Render sits behind a proxy, so the first X-Forwarded-For entry is the
#     # caller. It is only used to group requests, never for access control.
#     forwarded = request.headers.get("X-Forwarded-For", "")
#     caller = forwarded.split(",")[0].strip() or request.remote_addr or "unknown"

#     allowed, remaining, retry_after = rate_limit(caller)
#     if not allowed:
#         logger.warning("Rate limit hit by %s (request %s)", caller, request_id)
#         response, status = error_response(
#             "rate_limited",
#             f"Too many audits. Try again in {retry_after} seconds.",
#             429,
#             request_id,
#         )
#         response.headers["Retry-After"] = str(retry_after)
#         return response, status

#     if request.content_length and request.content_length > MAX_BODY_BYTES:
#         # Answered before the body is parsed, so a huge upload is not buffered.
#         return error_response(
#             "body_too_large",
#             f"Request body must be at most {MAX_BODY_BYTES} bytes.",
#             413,
#             request_id,
#         )

#     body = request.get_json(silent=True)
#     clause_text, error = validate(body)
#     if error:
#         logger.warning("Rejected audit request %s: %s", request_id, error)
#         return error_response("invalid_request", error, 400, request_id)

#     policy_name = _optional_string(body, "policy_name", "policy.txt")
#     full_text = _optional_string(body, "full_text", clause_text)

#     try:
#         result = get_orchestrator().run(policy_name, full_text, clause_text)
#     except Exception:
#         # The traceback goes to the log, not to the caller: it can name internal
#         # paths and model details that are not useful to whoever submitted the
#         # clause.
#         logger.exception("Audit failed (request %s)", request_id)
#         return error_response(
#             "audit_failed",
#             "The audit pipeline failed. Check the server log for the traceback.",
#             500,
#             request_id,
#         )

#     logger.info(
#         "Audit %s finished in %.1fs with status=%s (rate limit remaining %d)",
#         request_id, time.time() - started, result.get("status"), remaining,
#     )
#     result["request_id"] = request_id
#     return jsonify(result), 200


# if __name__ == "__main__":
#     # Render routes traffic to the port given in $PORT; it is only 5000 locally.
#     port = int(os.environ.get("PORT", 5000))
#     debug = os.environ.get("FLASK_DEBUG", "0") == "1"

#     # Warm-up pre-loads the retrieval stack so the first audit is fast. It is a pure
#     # optimisation and it has no effect on correctness, but it costs a couple of
#     # hundred megabytes of resident memory at startup - memory a 512 MB instance
#     # cannot spare alongside the running service. On the deployed instance the
#     # process was being killed while warming up, which took the whole service down
#     # and produced a 502 on every route, including the ones that import nothing.
#     #
#     # It is therefore off by default. The port opens with almost no memory in use,
#     # every read-only route answers, and the first audit pays the load instead. Set
#     # WARMUP=1 in the environment to restore the old behaviour on a larger instance.
#     if os.environ.get("WARMUP", "0") == "1":
#         threading.Thread(target=warm_up, daemon=True).start()
#         logger.info("Warm-up started in the background")
#     else:
#         logger.info("Warm-up disabled; the first audit will load the retrieval stack")

#     logger.info("Reguard AI backend listening on port %s", port)
#     app.run(host="0.0.0.0", port=port, debug=debug)







"""Flask API backend for Reguard AI.

Exposes REST endpoints for health tracking, system readiness, evaluation metrics,
and clause-level multi-agent auditing.
"""

import os
import sys
import threading
import time
import uuid
from pathlib import Path

# Thread pool optimization settings to prevent memory crashes on small server instances
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

# Ensure project root is available in system paths
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.chdir(PROJECT_ROOT)

from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)

# Configure CORS access
ALLOWED_ORIGINS = [origin.strip() for origin in os.environ.get("ALLOWED_ORIGINS", "*").split(",") if origin.strip()]
CORS(app, origins=ALLOWED_ORIGINS or ["*"], expose_headers=["X-Request-Id"])

MIN_CLAUSE_CHARS = 10
MAX_CLAUSE_CHARS = 10000
MAX_BODY_BYTES = 64 * 1024
app.config["MAX_CONTENT_LENGTH"] = MAX_BODY_BYTES

RATE_LIMIT_REQUESTS = int(os.environ.get("RATE_LIMIT_REQUESTS", "30"))
RATE_LIMIT_WINDOW_SECONDS = int(os.environ.get("RATE_LIMIT_WINDOW_SECONDS", "60"))

_orchestrator = None
_orchestrator_lock = threading.Lock()
_rate_windows = {}
_rate_lock = threading.Lock()


def get_orchestrator():
    """Build the orchestrator lazily on first use."""
    global _orchestrator
    if _orchestrator is None:
        with _orchestrator_lock:
            if _orchestrator is None:
                from src.agents.orchestrator import ReguardOrchestrator
                print("Loading agents, corpus, and vector store...")
                _orchestrator = ReguardOrchestrator()
                print("Orchestrator pipeline ready.")
    return _orchestrator


def error_response(code, message, status, request_id):
    """Generate uniform JSON error payloads."""
    return jsonify({"error": message, "code": code, "request_id": request_id}), status


def validate(body):
    """Validate incoming request body structure and parameters."""
    if not isinstance(body, dict):
        return None, "Request body must be a JSON object."

    clause_text = body.get("clause_text")
    if clause_text is None or (isinstance(clause_text, str) and not clause_text.strip()):
        return None, "clause_text is required."
    if not isinstance(clause_text, str):
        return None, "clause_text must be a string."

    clause_text = clause_text.strip()
    if len(clause_text) < MIN_CLAUSE_CHARS:
        return None, f"clause_text must be at least {MIN_CLAUSE_CHARS} characters."
    if len(clause_text) > MAX_CLAUSE_CHARS:
        return None, f"clause_text must be at most {MAX_CLAUSE_CHARS} characters."

    return clause_text, None


def _optional_string(body, key, fallback):
    value = body.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


def rate_limit(caller, now=None):
    """Evaluate simple in-process rate limiting rules per caller."""
    if RATE_LIMIT_REQUESTS <= 0:
        return True, RATE_LIMIT_REQUESTS, 0

    now = now if now is not None else time.time()
    with _rate_lock:
        window_start, count = _rate_windows.get(caller, (now, 0))
        if now - window_start >= RATE_LIMIT_WINDOW_SECONDS:
            window_start, count = now, 0
        count += 1
        _rate_windows[caller] = (window_start, count)

        if len(_rate_windows) > 1024:
            cutoff = now - RATE_LIMIT_WINDOW_SECONDS
            for key in [k for k, (start, _) in _rate_windows.items() if start < cutoff]:
                del _rate_windows[key]

    retry_after = max(0, int(window_start + RATE_LIMIT_WINDOW_SECONDS - now))
    return count <= RATE_LIMIT_REQUESTS, max(0, RATE_LIMIT_REQUESTS - count), retry_after


@app.before_request
def assign_request_id():
    request.request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex[:12]


@app.after_request
def tag_response(response):
    response.headers["X-Request-Id"] = getattr(request, "request_id", "-")
    return response


@app.errorhandler(404)
def handle_not_found(_error):
    return error_response("not_found", f"{request.method} {request.path} is not a valid route.", 404, getattr(request, "request_id", "-"))


@app.errorhandler(405)
def handle_method_not_allowed(_error):
    return error_response("method_not_allowed", f"{request.method} is not allowed on {request.path}.", 405, getattr(request, "request_id", "-"))


@app.errorhandler(413)
def handle_too_large(_error):
    return error_response("body_too_large", f"Request body exceeds {MAX_BODY_BYTES} bytes limit.", 413, getattr(request, "request_id", "-"))


@app.errorhandler(500)
def handle_server_error(_error):
    return error_response("internal_error", "The audit pipeline encountered an internal failure.", 500, getattr(request, "request_id", "-"))


@app.route("/", methods=["GET"])
def index():
    return jsonify({
        "service": "reguard-ai",
        "status": "ok",
        "endpoints": {
            "health": "GET /api/health",
            "ready": "GET /api/ready",
            "metrics": "GET /api/metrics",
            "audit": "POST /api/audit",
        },
    }), 200


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "reguard-ai"}), 200


@app.route("/api/ready", methods=["GET"])
def ready():
    from src.retrieval.health import corpus_status
    status = corpus_status()
    return jsonify({
        "status": "ready" if status["retrieval_ready"] else "degraded",
        "service": "reguard-ai",
        "orchestrator_loaded": _orchestrator is not None,
        "retrieval": status,
    }), (200 if status["retrieval_ready"] else 503)


@app.route("/api/metrics", methods=["GET"])
def metrics():
    from src.evaluation import results
    return jsonify(results.headline()), 200


@app.route("/api/audit", methods=["POST"])
def run_audit():
    started = time.time()
    request_id = request.request_id

    forwarded = request.headers.get("X-Forwarded-For", "")
    caller = forwarded.split(",")[0].strip() or request.remote_addr or "unknown"

    allowed, remaining, retry_after = rate_limit(caller)
    if not allowed:
        print(f"Rate limit exceeded by caller {caller} (request {request_id})")
        response, status = error_response("rate_limited", f"Too many audits. Retry in {retry_after}s.", 429, request_id)
        response.headers["Retry-After"] = str(retry_after)
        return response, status

    body = request.get_json(silent=True)
    clause_text, error = validate(body)
    if error:
        return error_response("invalid_request", error, 400, request_id)

    policy_name = _optional_string(body, "policy_name", "policy.txt")
    full_text = _optional_string(body, "full_text", clause_text)

    try:
        result = get_orchestrator().run(policy_name, full_text, clause_text)
    except Exception as exc:
        print(f"Pipeline execution failed for request {request_id}: {exc}")
        return error_response("audit_failed", "The audit pipeline failed during execution.", 500, request_id)

    print(f"Audit {request_id} completed in {time.time() - started:.1f}s with status={result.get('status')}")
    result["request_id"] = request_id
    return jsonify(result), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    print(f"Reguard AI backend listening on port {port}")
    app.run(host="0.0.0.0", port=port, debug=debug)
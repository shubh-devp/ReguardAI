"""Flask API for Reguard AI.

One endpoint does the work: POST /api/audit runs the whole agent pipeline for a
single policy clause and returns the result as JSON.
"""

import logging
import os
import sys
import threading
import time
from pathlib import Path

# Keep OpenMP/BLAS thread pools small. Render's smaller instances are memory
# bound, and these pools are one of the biggest fixed costs of loading torch.
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

# The project root has to be importable for `from src....` to work. Render starts
# the app as `python app.py`, which puts src/api/ on sys.path instead of the root.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# data/corpus, data/chroma_db, data/database and data/processed are all resolved
# relative to the working directory, so pin it to the project root.
os.chdir(PROJECT_ROOT)

from flask import Flask, jsonify, request
from flask_cors import CORS

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

# Only our own modules and the HTTP access log talk at INFO. Third-party
# libraries are left at WARNING, otherwise httpx prints a line for every
# request it makes while downloading the embedding model.
for logger_name in ("reguard", "src", "werkzeug"):
    logging.getLogger(logger_name).setLevel(logging.INFO)

logger = logging.getLogger("reguard.api")

app = Flask(__name__)

# Comma-separated list of allowed origins. Defaults to "*" so local development
# and preview URLs keep working; set ALLOWED_ORIGINS in production.
CORS(app, origins=os.environ.get("ALLOWED_ORIGINS", "*").split(","))

MIN_CLAUSE_CHARS = 10
MAX_CLAUSE_CHARS = 10000

# The agents are imported inside get_orchestrator() on purpose. Importing them
# pulls in torch, sentence-transformers and ChromaDB, which takes tens of
# seconds and hundreds of megabytes. Doing that at module level kept the port
# closed for too long, so Render's port scan reported "No open ports detected".
_orchestrator = None
_orchestrator_lock = threading.Lock()


def get_orchestrator():
    """Build the orchestrator once, on first use, and reuse it afterwards."""
    global _orchestrator
    if _orchestrator is None:
        with _orchestrator_lock:
            if _orchestrator is None:
                from src.agents.orchestrator import ReguardOrchestrator

                logger.info("Loading agents, corpus and vector store (first run only)")
                _orchestrator = ReguardOrchestrator()
                logger.info("Orchestrator ready")
    return _orchestrator


def warm_up():
    """Load the agents in the background so the first audit does not have to."""
    try:
        get_orchestrator()
    except Exception:
        logger.exception("Warm-up failed; the first audit will try again")


def validate(body):
    """Returns (clause_text, error_message). One of the two is always None."""
    if not isinstance(body, dict):
        return None, "Request body must be a JSON object."

    clause_text = (body.get("clause_text") or "").strip()
    if not clause_text:
        return None, "clause_text is required."
    if len(clause_text) < MIN_CLAUSE_CHARS:
        return None, f"clause_text must be at least {MIN_CLAUSE_CHARS} characters."
    if len(clause_text) > MAX_CLAUSE_CHARS:
        return None, f"clause_text must be at most {MAX_CLAUSE_CHARS} characters."

    return clause_text, None


@app.route("/", methods=["GET"])
def index():
    """Opening the base URL should not look like a broken deployment."""
    return jsonify(
        {
            "service": "reguard-ai",
            "status": "ok",
            "endpoints": {"health": "GET /api/health", "audit": "POST /api/audit"},
        }
    ), 200


@app.route("/api/health", methods=["GET"])
def health():
    """Cheap check that does not touch the models, for uptime monitoring."""
    return jsonify({"status": "ok", "service": "reguard-ai"}), 200


@app.route("/api/audit", methods=["POST"])
def run_audit():
    started = time.time()
    body = request.get_json(silent=True)

    clause_text, error = validate(body)
    if error:
        logger.warning("Rejected audit request: %s", error)
        return jsonify({"error": error}), 400

    policy_name = (body.get("policy_name") or "policy.txt").strip()
    full_text = (body.get("full_text") or clause_text).strip()

    try:
        result = get_orchestrator().run(policy_name, full_text, clause_text)
    except Exception as exc:
        logger.exception("Audit failed")
        return jsonify({"error": str(exc)}), 500

    logger.info(
        "Audit finished in %.1fs with status=%s", time.time() - started, result.get("status")
    )
    return jsonify(result), 200


if __name__ == "__main__":
    # Render routes traffic to the port given in $PORT; it is only 5000 locally.
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"

    # The models take a while to load, so start that in the background. The port
    # opens straight away and Render's health check passes; by the time the user
    # submits a clause the pipeline is usually already loaded.
    threading.Thread(target=warm_up, daemon=True).start()

    logger.info("Reguard AI backend listening on port %s", port)
    app.run(host="0.0.0.0", port=port, debug=debug)

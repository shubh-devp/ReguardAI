import os
import sys
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

from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# The agents are imported inside the handler on purpose. Importing them pulls in
# torch, sentence-transformers and ChromaDB, which takes tens of seconds and
# hundreds of megabytes. Doing that at module level kept the port closed for too
# long, so Render's port scan reported "No open ports detected" and gave up.
_orchestrator = None


def get_orchestrator() -> ReguardOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        from src.agents.orchestrator import ReguardOrchestrator

        _orchestrator = ReguardOrchestrator()
    return _orchestrator


@app.route("/api/audit", methods=["POST"])
def run_audit():
    try:
        data = request.get_json()
        result = get_orchestrator().run(
            data.get("policy_name", "policy.txt"),
            data.get("full_text", ""),
            data.get("clause_text", "")
        )
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    # Render routes traffic to the port given in $PORT; it is only 5000 locally.
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"

    print(f"Reguard AI backend listening on port {port}")
    app.run(host="0.0.0.0", port=port, debug=debug)

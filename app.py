# from flask import Flask, request, jsonify
# from flask_cors import CORS
# import os
# from src.agents.orchestrator import ReguardOrchestrator

# app = Flask(__name__)
# CORS(app)

# orchestrator = ReguardOrchestrator()

# @app.route("/api/audit", methods=["POST"])
# def run_audit():
#     try:
#         data = request.get_json()
#         result = orchestrator.run(
#             data.get("policy_name", "policy.txt"),
#             data.get("full_text", ""),
#             data.get("clause_text", "")
#         )
#         return jsonify(result), 200
#     except Exception as e:
#         return jsonify({"error": str(e)}), 500

# if __name__ == "__main__":
#     # Fetch the dynamic port provided by Railway/Render (defaults to 5000 locally)
#     port = int(os.environ.get("PORT", 5000))
#     print(f"🚀 Reguard AI Backend API Server running on port {port}...")
    
#     debug_mode = os.environ.get("FLASK_DEBUG", "False").lower() == "true"
#     app.run(host="0.0.0.0", port=port, debug=debug_mode)


from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from src.agents.orchestrator import ReguardOrchestrator

app = Flask(__name__)
CORS(app)

# Remove this from the global level:
# orchestrator = ReguardOrchestrator()

@app.route("/api/audit", methods=["POST"])
def run_audit():
    try:
        data = request.get_json()
        
        # Instantiate it right when the request hits instead
        orchestrator = ReguardOrchestrator()
        
        result = orchestrator.run(
            data.get("policy_name", "policy.txt"),
            data.get("full_text", ""),
            data.get("clause_text", "")
        )
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    # Change the default fallback port from 5000 to 10000 to match Render
    port = int(os.environ.get("PORT", 10000))
    print(f"🚀 Reguard AI Backend API Server running on port {port}...")
    
    debug_mode = os.environ.get("FLASK_DEBUG", "False").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug_mode)

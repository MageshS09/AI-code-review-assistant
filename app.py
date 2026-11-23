import os

from flask import Flask, jsonify, request
from flask_cors import CORS

from analyzer import analyze_code

MAX_CODE_LENGTH = 20000
SUPPORTED_LANGUAGES = {"python", "javascript", "cpp", "java", "go"}

app = Flask(__name__)

# Same-origin deployments (Vite dev proxy, Vercel) need no CORS at all. When the
# frontend is hosted elsewhere, set CORS_ORIGINS to a comma-separated allow-list.
# The default of "*" keeps the previous open behaviour.
_cors_origins = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "*").split(",") if origin.strip()]
CORS(app, origins=_cors_origins or "*")


def _bad_request(message):
    return jsonify({"error": message}), 400


@app.post("/api/review")
def review_code():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _bad_request("Request body must be a JSON object with 'code' and 'language'.")

    raw_code = payload.get("code")
    raw_language = payload.get("language")
    if raw_code is not None and not isinstance(raw_code, str):
        return _bad_request("'code' must be a string.")
    if raw_language is not None and not isinstance(raw_language, str):
        return _bad_request("'language' must be a string.")

    code = (raw_code or "").strip()
    language = (raw_language or "").strip().lower()

    if not code:
        return _bad_request("Code input cannot be empty.")
    if language not in SUPPORTED_LANGUAGES:
        return _bad_request(f"Unsupported language '{language}'.")
    if len(code) > MAX_CODE_LENGTH:
        return _bad_request(f"Code exceeds the {MAX_CODE_LENGTH} character limit.")

    # Currently analyzed locally with rule-based heuristics (analyzer.py), no
    # external API calls. Swap this for a Claude API call later by replacing
    # analyze_code(code, language) with a request to the Anthropic SDK.
    review_result = analyze_code(code, language)

    return jsonify(review_result), 200


@app.get("/api/health")
def health_check():
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    # The Werkzeug debugger allows arbitrary code execution, so debug mode and
    # binding to all interfaces are opt-in instead of the default.
    app.run(
        host=os.getenv("FLASK_HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG", "0") == "1",
    )

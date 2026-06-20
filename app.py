from flask import Flask, jsonify, request
from flask_cors import CORS

from analyzer import analyze_code

MAX_CODE_LENGTH = 20000
SUPPORTED_LANGUAGES = {"python", "javascript", "cpp", "java", "go"}

app = Flask(__name__)
CORS(app)


@app.post("/api/review")
def review_code():
    payload = request.get_json(silent=True) or {}
    code = (payload.get("code") or "").strip()
    language = (payload.get("language") or "").strip().lower()

    if not code:
        return jsonify({"error": "Code input cannot be empty."}), 400
    if language not in SUPPORTED_LANGUAGES:
        return jsonify({"error": f"Unsupported language '{language}'."}), 400
    if len(code) > MAX_CODE_LENGTH:
        return jsonify({"error": f"Code exceeds the {MAX_CODE_LENGTH} character limit."}), 400

    # Currently analyzed locally with rule-based heuristics (analyzer.py), no
    # external API calls. Swap this for a Claude API call later by replacing
    # analyze_code(code, language) with a request to the Anthropic SDK.
    review_result = analyze_code(code, language)

    return jsonify(review_result), 200


@app.get("/api/health")
def health_check():
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

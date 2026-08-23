import os

from flask import Flask, jsonify, request

from job_pipeline import collect_jobs


app = Flask(__name__)


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.get("/jobs")
def jobs():
    expected_token = os.getenv("COLLECTOR_TOKEN")
    supplied_token = request.headers.get("X-Collector-Token")
    if expected_token and supplied_token != expected_token:
        return jsonify({"error": "unauthorized"}), 401

    result = collect_jobs()
    rows = result.to_dict(orient="records") if hasattr(result, "to_dict") else result
    return jsonify({"jobs": rows, "count": len(rows)})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))

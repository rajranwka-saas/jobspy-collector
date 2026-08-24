import json
import os
import threading
import tempfile
from pathlib import Path

from flask import Flask, jsonify, request

from job_pipeline import collect_jobs


app = Flask(__name__)
queue_path = Path(os.getenv("JOB_OUTPUT_JSON", "job_queue.json"))
refresh_lock = threading.Lock()
refresh_state = {"running": False, "last_error": None}


def refresh_queue():
    if not refresh_lock.acquire(blocking=False):
        return
    refresh_state["running"] = True
    refresh_state["last_error"] = None
    try:
        result = collect_jobs()
        rows = result.to_dict(orient="records") if hasattr(result, "to_dict") else result
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=queue_path.parent, delete=False
        ) as temporary_file:
            json.dump(rows, temporary_file, indent=2, default=str)
            temporary_path = Path(temporary_file.name)
        temporary_path.replace(queue_path)
    except Exception as error:
        refresh_state["last_error"] = str(error)
    finally:
        refresh_state["running"] = False
        refresh_lock.release()


@app.get("/health")
def health():
    return jsonify(
        {
            "status": "ok",
            "refresh_running": refresh_state["running"],
            "last_error": refresh_state["last_error"],
        }
    )


@app.get("/")
def root():
    return jsonify(
        service="jobspy-collector",
        status="ok",
        health="/health",
        jobs="/jobs",
    )


@app.get("/jobs")
def jobs():
    expected_token = os.getenv("COLLECTOR_TOKEN")
    supplied_token = request.headers.get("X-Collector-Token")
    if expected_token and supplied_token != expected_token:
        return jsonify({"error": "unauthorized"}), 401

    if not queue_path.exists():
        threading.Thread(target=refresh_queue, daemon=True).start()
        return jsonify(
            jobs=[],
            count=0,
            refresh_running=True,
            message="Initial refresh started. Run this node again after the refresh completes.",
        )

    try:
        rows = json.loads(queue_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return jsonify(
            error="queue is being refreshed; retry shortly",
            detail=str(error),
        ), 503
    if not refresh_state["running"]:
        threading.Thread(target=refresh_queue, daemon=True).start()
    return jsonify(
        jobs=rows,
        count=len(rows),
        refresh_running=refresh_state["running"],
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))

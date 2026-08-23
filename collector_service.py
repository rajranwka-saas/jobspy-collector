import json
import os
import threading
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
        queue_path.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
    except Exception as error:
        refresh_state["last_error"] = str(error)
    finally:
        refresh_state["running"] = False

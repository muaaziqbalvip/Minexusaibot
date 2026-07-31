"""
Lightweight persistent storage using JSON files committed back to the repo
by the GitHub Actions workflow. This is what gives us "restart logic":
every run picks up exactly where the last run left off.
"""
import json
import os
import logging
from bot.config import STATE_FILE, QUEUE_FILE, DATA_DIR, LOG_FILE

os.makedirs(DATA_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("mi_nexus")


def _load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        log.warning(f"Could not read {path}, using default. Error: {e}")
        return default


def _save_json(path, data):
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)  # atomic write, avoids corruption if run is killed mid-write


def load_state():
    return _load_json(STATE_FILE, {"last_update_id": 0})


def save_state(state):
    _save_json(STATE_FILE, state)


def load_queue():
    return _load_json(QUEUE_FILE, {"pending": [], "failed": []})


def save_queue(queue):
    _save_json(QUEUE_FILE, queue)


def enqueue_job(job: dict):
    """job: {chat_id, message_id, file_id, attempts, ...}"""
    queue = load_queue()
    job.setdefault("attempts", 0)
    queue["pending"].append(job)
    save_queue(queue)


def mark_job_failed(job, error_msg):
    queue = load_queue()
    job["last_error"] = error_msg
    job["attempts"] = job.get("attempts", 0) + 1
    queue["failed"].append(job)
    save_queue(queue)
    log.error(f"Job permanently failed after {job['attempts']} attempts: {error_msg}")

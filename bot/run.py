"""
MI NEXUS Bot - single-cycle runner.

Designed to be invoked repeatedly by a GitHub Actions scheduled workflow.
Each invocation:
  1. Loads persisted state (last_update_id) and queue (data/*.json)
  2. Polls Telegram for new messages since last_update_id
  3. Enqueues any photo messages as analysis jobs
  4. Processes pending jobs (Gemini analyze -> render card -> send back),
     retrying failed jobs up to MAX_RETRIES before giving up on them
  5. Saves state + queue back to disk so the *next* run (next workflow
     trigger) picks up exactly where this one left off — this is the
     "restart logic": no run needs to remember anything in memory.
"""
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.config import (
    MAX_RETRIES, RETRY_BACKOFF_SECONDS, TELEGRAM_POLL_TIMEOUT,
    MAX_JOBS_PER_RUN, TELEGRAM_BOT_TOKEN, GEMINI_API_KEY,
)
from bot.storage import load_state, save_state, load_queue, save_queue, log
from bot import telegram_api as tg
from bot.gemini_analyzer import analyze_chart
from bot.card_renderer import render_signal_card

WELCOME_TEXT = (
    "🤖 *MI NEXUS* — chart screenshot bhejein, main analysis aur signal card bhej dunga.\n\n"
    "⚠️ _Educational analysis only — not financial advice._"
)

ERROR_TEXT_USER = (
    "⚠️ Is image ko analyze karne me masla aaya. Barah-e-karam thodi der baad "
    "dobara try karein, ya clearer screenshot bhejein."
)


def _handle_incoming_messages(state):
    """Poll Telegram, enqueue photo jobs, return updated state + list of new jobs."""
    updates = tg.get_updates(offset=state["last_update_id"] + 1, timeout=TELEGRAM_POLL_TIMEOUT)
    new_jobs = []

    for upd in updates:
        state["last_update_id"] = max(state["last_update_id"], upd["update_id"])
        msg = upd.get("message")
        if not msg:
            continue

        chat_id = msg["chat"]["id"]

        if "photo" in msg:
            # Telegram sends multiple resolutions; take the largest.
            file_id = msg["photo"][-1]["file_id"]
            new_jobs.append({
                "chat_id": chat_id,
                "message_id": msg["message_id"],
                "file_id": file_id,
                "attempts": 0,
            })
        elif "text" in msg:
            text = msg["text"].strip().lower()
            if text in ("/start", "/help"):
                tg.send_message(chat_id, WELCOME_TEXT)

    return state, new_jobs


def _process_job(job):
    """Run one job end-to-end. Raises on failure so caller can retry/park it."""
    chat_id = job["chat_id"]
    image_bytes = tg.download_file(job["file_id"])

    result = analyze_chart(image_bytes, mime_type="image/jpeg")

    out_path = f"/tmp/mi_nexus_signal_{chat_id}_{job['message_id']}.png"
    render_signal_card(result, out_path)

    caption = (
        f"🎯 *DIRECTION:* {'🟢 UP' if result['direction']=='UP' else '🔻 DOWN'}\n"
        f"🔥 *CONFIDENCE:* {result['confidence']}%\n"
        f"⏳ *EXPIRY:* {result['expiry']}"
    )
    tg.send_photo(chat_id, out_path, caption=caption)
    tg.send_message(chat_id, result["raw_markdown"])

    try:
        os.remove(out_path)
    except OSError:
        pass


def main():
    if not TELEGRAM_BOT_TOKEN:
        log.error("TELEGRAM_BOT_TOKEN is not set. Aborting run.")
        sys.exit(1)
    if not GEMINI_API_KEY:
        log.error("GEMINI_API_KEY is not set. Aborting run.")
        sys.exit(1)

    state = load_state()
    queue = load_queue()

    # 1. Pull new messages, enqueue any photo jobs
    try:
        state, new_jobs = _handle_incoming_messages(state)
        queue["pending"].extend(new_jobs)
        if new_jobs:
            log.info(f"Enqueued {len(new_jobs)} new job(s).")
    except Exception as e:
        log.error(f"Failed to fetch/handle Telegram updates: {e}")
        log.error(traceback.format_exc())
        # Don't touch state.last_update_id if the fetch itself failed —
        # next run will retry the same offset.

    # 2. Process pending queue (bounded per run so a bad run can't hang forever)
    still_pending = []
    processed = 0
    for job in queue["pending"]:
        if processed >= MAX_JOBS_PER_RUN:
            still_pending.append(job)  # leave for next run
            continue
        try:
            _process_job(job)
            processed += 1
            log.info(f"Job for chat {job['chat_id']} msg {job['message_id']} completed.")
        except Exception as e:
            job["attempts"] = job.get("attempts", 0) + 1
            log.warning(
                f"Job failed (attempt {job['attempts']}/{MAX_RETRIES}) "
                f"for chat {job['chat_id']}: {e}"
            )
            if job["attempts"] >= MAX_RETRIES:
                try:
                    tg.send_message(job["chat_id"], ERROR_TEXT_USER)
                except Exception:
                    pass
                queue["failed"].append(job)
                log.error(f"Job permanently failed and parked: {job}")
            else:
                time.sleep(RETRY_BACKOFF_SECONDS)
                still_pending.append(job)  # retry on this same run's next pass is
                                             # skipped for simplicity; picked up next run
            processed += 1

    queue["pending"] = still_pending

    # 3. Persist everything for the next scheduled run
    save_state(state)
    save_queue(queue)
    log.info(
        f"Run complete. last_update_id={state['last_update_id']}, "
        f"pending={len(queue['pending'])}, failed_parked={len(queue['failed'])}"
    )


if __name__ == "__main__":
    main()

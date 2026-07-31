"""
MI NEXUS Bot - long-running loop runner.

Unlike run.py (one cycle and exit), this stays alive inside a single
GitHub Actions job for up to ~5h30m, continuously long-polling Telegram
so replies feel instant instead of waiting for the next 5-min cron tick.

Design:
  - Single process, single loop: getUpdates (long-poll, ~20s) -> handle
    any photo messages immediately -> repeat.
  - State (last_update_id) and queue (failed jobs) are written to disk
    every STATE_COMMIT_INTERVAL_SECONDS via a lightweight background
    thread, so the workflow's periodic "git commit" step (see
    loop.yml) always has something recent to save - if this process
    gets killed unexpectedly, at most ~60s of update-id progress is
    ever at risk of being reprocessed (harmless - Telegram messages are
    just re-answered, not duplicated destructively).
  - After MAX_RUNTIME_SECONDS the loop exits cleanly on its own, *before*
    GitHub's 6-hour hard kill. loop.yml's own timeout-minutes is set
    with headroom above this so the process always gets to shut down
    and commit final state rather than being SIGKILLed mid-write.
  - watchdog.yml separately checks (via the GitHub API) whether a
    poll workflow run is currently in_progress, and starts a new one
    if not - this is what gives the "auto-restart, 24/7" behavior
    across the gap between one job ending and the next beginning.
"""
import os
import sys
import time
import threading
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.config import (
    MAX_RETRIES, RETRY_BACKOFF_SECONDS, TELEGRAM_POLL_TIMEOUT,
    TELEGRAM_BOT_TOKEN, GEMINI_API_KEY,
    MAX_RUNTIME_SECONDS, STATE_COMMIT_INTERVAL_SECONDS, IDLE_SLEEP_SECONDS,
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

# Shared, lock-protected state/queue so the periodic disk-writer thread
# and the main loop never write half-updated JSON to disk at the same time.
_lock = threading.Lock()
_state = None
_queue = None
_stop_flag = threading.Event()


def _persist():
    with _lock:
        save_state(_state)
        save_queue(_queue)


def _periodic_writer():
    while not _stop_flag.wait(STATE_COMMIT_INTERVAL_SECONDS):
        try:
            _persist()
            log.info("Periodic state/queue write completed.")
        except Exception as e:
            log.error(f"Periodic write failed: {e}")


def _process_job(job):
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


def _handle_job_with_retries(job):
    """Runs inline in the main loop (not a separate queue pass) since
    replies should go out immediately, not wait for a later cycle."""
    attempts = job.get("attempts", 0)
    while attempts < MAX_RETRIES:
        try:
            _process_job(job)
            log.info(f"Job for chat {job['chat_id']} msg {job['message_id']} completed.")
            return
        except Exception as e:
            attempts += 1
            job["attempts"] = attempts
            log.warning(
                f"Job failed (attempt {attempts}/{MAX_RETRIES}) "
                f"for chat {job['chat_id']}: {e}"
            )
            if attempts >= MAX_RETRIES:
                try:
                    tg.send_message(job["chat_id"], ERROR_TEXT_USER)
                except Exception:
                    pass
                with _lock:
                    _queue["failed"].append(job)
                log.error(f"Job permanently failed and parked: {job}")
                return
            time.sleep(RETRY_BACKOFF_SECONDS)


def main():
    global _state, _queue

    if not TELEGRAM_BOT_TOKEN:
        log.error("TELEGRAM_BOT_TOKEN is not set. Aborting.")
        sys.exit(1)
    if not GEMINI_API_KEY:
        log.error("GEMINI_API_KEY is not set. Aborting.")
        sys.exit(1)

    _state = load_state()
    _queue = load_queue()

    # Re-attempt any jobs left pending from a previous (killed/ended) run
    # before entering the live loop.
    leftover = _queue.get("pending", [])
    _queue["pending"] = []
    for job in leftover:
        log.info(f"Resuming leftover job from previous run: chat {job['chat_id']}")
        _handle_job_with_retries(job)

    writer_thread = threading.Thread(target=_periodic_writer, daemon=True)
    writer_thread.start()

    start_time = time.time()
    log.info(f"MI NEXUS long-running loop starting. Will run for up to {MAX_RUNTIME_SECONDS/3600:.1f}h.")

    try:
        while True:
            elapsed = time.time() - start_time
            if elapsed >= MAX_RUNTIME_SECONDS:
                log.info("Max runtime reached - shutting down cleanly for scheduled restart.")
                break

            try:
                updates = tg.get_updates(
                    offset=_state["last_update_id"] + 1,
                    timeout=TELEGRAM_POLL_TIMEOUT,
                )
            except Exception as e:
                log.error(f"getUpdates failed: {e}\n{traceback.format_exc()}")
                time.sleep(5)
                continue

            if not updates:
                time.sleep(IDLE_SLEEP_SECONDS)
                continue

            for upd in updates:
                with _lock:
                    _state["last_update_id"] = max(_state["last_update_id"], upd["update_id"])
                msg = upd.get("message")
                if not msg:
                    continue

                chat_id = msg["chat"]["id"]

                if "photo" in msg:
                    file_id = msg["photo"][-1]["file_id"]
                    job = {
                        "chat_id": chat_id,
                        "message_id": msg["message_id"],
                        "file_id": file_id,
                        "attempts": 0,
                    }
                    _handle_job_with_retries(job)  # handled immediately, not queued
                elif "text" in msg:
                    text = msg["text"].strip().lower()
                    if text in ("/start", "/help"):
                        tg.send_message(chat_id, WELCOME_TEXT)

    finally:
        _stop_flag.set()
        writer_thread.join(timeout=5)
        _persist()
        log.info(
            f"Loop exited. last_update_id={_state['last_update_id']}, "
            f"failed_parked={len(_queue['failed'])}"
        )


if __name__ == "__main__":
    main()

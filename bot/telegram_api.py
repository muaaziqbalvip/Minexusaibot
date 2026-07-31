"""
Minimal Telegram Bot API wrapper using requests (no heavy SDK needed for
a poll-once-per-run design). Every function raises on repeated failure so
the caller's retry logic can catch it.
"""
import requests
from bot.config import TELEGRAM_API_BASE
from bot.storage import log

TIMEOUT = 30


def get_updates(offset: int, timeout: int = 20):
    resp = requests.get(
        f"{TELEGRAM_API_BASE}/getUpdates",
        params={"offset": offset, "timeout": timeout, "allowed_updates": '["message"]'},
        timeout=timeout + 10,
    )
    resp.raise_for_status()
    return resp.json().get("result", [])


def send_message(chat_id, text, parse_mode="Markdown"):
    resp = requests.post(
        f"{TELEGRAM_API_BASE}/sendMessage",
        json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode},
        timeout=TIMEOUT,
    )
    if not resp.ok:
        log.warning(f"sendMessage failed ({resp.status_code}): {resp.text[:300]}")
    return resp.ok


def send_photo(chat_id, photo_path, caption=None, parse_mode="Markdown"):
    with open(photo_path, "rb") as f:
        files = {"photo": f}
        data = {"chat_id": chat_id}
        if caption:
            data["caption"] = caption[:1024]  # Telegram caption limit
            data["parse_mode"] = parse_mode
        resp = requests.post(
            f"{TELEGRAM_API_BASE}/sendPhoto",
            data=data, files=files, timeout=TIMEOUT,
        )
    if not resp.ok:
        log.warning(f"sendPhoto failed ({resp.status_code}): {resp.text[:300]}")
    return resp.ok


def download_file(file_id: str) -> bytes:
    resp = requests.get(
        f"{TELEGRAM_API_BASE}/getFile", params={"file_id": file_id}, timeout=TIMEOUT
    )
    resp.raise_for_status()
    file_path = resp.json()["result"]["file_path"]
    token = TELEGRAM_API_BASE.split("/bot")[-1]
    file_url = f"https://api.telegram.org/file/bot{token}/{file_path}"
    file_resp = requests.get(file_url, timeout=TIMEOUT)
    file_resp.raise_for_status()
    return file_resp.content

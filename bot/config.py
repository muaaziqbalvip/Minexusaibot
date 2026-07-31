"""
MI NEXUS Bot - Configuration
All secrets are read from environment variables ONLY.
Never hardcode API keys or tokens here.
"""
import os

# --- Secrets (set these as GitHub Actions repo secrets) ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# --- Gemini model ---
GEMINI_MODEL = "gemini-2.0-flash"  # vision-capable, fast
GEMINI_API_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)

# --- Telegram API base ---
TELEGRAM_API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# --- Paths ---
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
STATE_FILE = os.path.join(DATA_DIR, "state.json")       # last processed update_id
QUEUE_FILE = os.path.join(DATA_DIR, "queue.json")        # pending jobs (retry logic)
LOG_FILE = os.path.join(DATA_DIR, "bot.log")

# --- Behavior tuning ---
MAX_RETRIES = 3                 # per job, before giving up
RETRY_BACKOFF_SECONDS = 5
TELEGRAM_POLL_TIMEOUT = 20       # long-poll timeout per getUpdates call
MAX_JOBS_PER_RUN = 15            # safety cap so one workflow run can't run forever

# --- Branding (used by the signal image generator) ---
BRAND_NAME = "MI NEXUS"
BRAND_TAGLINE = "ANALYZE • PREDICT • PROFIT"
BRAND_FOOTER = "MI NEXUS © Muslim Islam Network"
DISCLAIMER_TEXT = "Educational analysis only — not financial advice"

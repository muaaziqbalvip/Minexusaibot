"""
Calls Gemini Flash (vision) with a chart screenshot and a strict prompt,
gets back a structured Roman-Urdu analysis, and parses it into a dict
that the image renderer can use to build the signal card.
"""
import base64
import re
import requests
from bot.config import GEMINI_API_URL, GEMINI_API_KEY
from bot.storage import log

ANALYSIS_PROMPT = """You are an elite Institutional Technical Analyst and Binary Options Trader
with 10+ years of experience analyzing price action, market structure, and candlestick dynamics.

Conduct a highly detailed, micro-level analysis of the attached chart image for a short-expiry
trade read (1-to-5 minute). Respond ENTIRELY in Roman-Urdu (Urdu written in English letters) using
clear Markdown, structured EXACTLY like this (keep the same headings and emoji, fill in the brackets):

### 📊 ADVANCED CHART ANALYSIS
* 🪙 Asset/Pair: [asset name if visible, else "Not clearly visible"]
* ⏱️ Timeframe: [timeframe if visible, else "Not specified"]
* 📈 Trend Direction: [Uptrend / Downtrend / Sideways]

### 🕯️ CANDLESTICK & MARKET STRUCTURE
* Current & Previous Candle Pattern: [...]
* Wick Analysis: [...]
* Market Momentum: [...]

### 🧱 KEY TECHNICAL LEVELS
* Support Levels: [...]
* Resistance Levels: [...]
* Dynamic Support/Resistance: [...]
* RSI(14) Status: [...]

DIRECTION: [UP or DOWN]
CONFIDENCE: [a number 1-99, your honest estimate, do not default to a round number]
EXPIRY: [e.g. "1 Minute" / "2 Minutes" / "Next Candle Close"]

### 💡 TRADE REASONING
[3-4 sentences in Roman-Urdu explaining why, based on wicks/levels/RSI/momentum]

### ⚠️ RISK & ENTRY ADVICE
[1 crucial tip on entry timing]

IMPORTANT: You are pattern-matching pixels in a screenshot, not observing real market data guaranteed
to repeat. Give your honest best-effort read. Do not claim certainty you don't have — if the chart is
unclear/ambiguous, say so and lower the confidence number accordingly instead of inventing details.
"""


def _extract_field(text, pattern, default="N/A"):
    m = re.search(pattern, text, re.IGNORECASE)
    return m.group(1).strip() if m else default


def analyze_chart(image_bytes: bytes, mime_type: str = "image/jpeg") -> dict:
    """
    Sends the image to Gemini Flash, returns a dict with both the raw
    markdown (to send as a Telegram message) and parsed fields (for the
    signal image renderer).
    """
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set in environment/secrets.")

    b64 = base64.b64encode(image_bytes).decode("utf-8")

    payload = {
        "contents": [{
            "parts": [
                {"text": ANALYSIS_PROMPT},
                {"inline_data": {"mime_type": mime_type, "data": b64}},
            ]
        }],
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": 1200,
        },
    }

    resp = requests.post(
        f"{GEMINI_API_URL}?key={GEMINI_API_KEY}",
        json=payload,
        timeout=60,
    )

    if resp.status_code != 200:
        log.error(f"Gemini API error {resp.status_code}: {resp.text[:500]}")
        raise RuntimeError(f"Gemini API error {resp.status_code}")

    data = resp.json()
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        log.error(f"Unexpected Gemini response shape: {data}")
        raise RuntimeError("Gemini returned an unexpected response shape") from e

    direction_raw = _extract_field(text, r"DIRECTION:\s*\**\s*(UP|DOWN)", "UP")
    direction = "UP" if "UP" in direction_raw.upper() else "DOWN"

    confidence_raw = _extract_field(text, r"CONFIDENCE:\s*\**\s*(\d{1,3})", "60")
    try:
        confidence = max(1, min(99, int(confidence_raw)))
    except ValueError:
        confidence = 60

    expiry = _extract_field(text, r"EXPIRY:\s*\**\s*(.+)", "1 Minute")
    asset = _extract_field(text, r"Asset/Pair:\s*\**\s*(.+)", "Not clearly visible")
    timeframe = _extract_field(text, r"Timeframe:\s*\**\s*(.+)", "Not specified")
    trend = _extract_field(text, r"Trend Direction:\s*\**\s*(.+)", "Sideways")

    return {
        "raw_markdown": text,
        "direction": direction,          # "UP" or "DOWN"
        "confidence": confidence,        # int 1-99
        "expiry": expiry.split("\n")[0].strip(),
        "asset": asset.split("\n")[0].strip(),
        "timeframe": timeframe.split("\n")[0].strip(),
        "trend": trend.split("\n")[0].strip(),
    }

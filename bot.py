"""
=============================================================================
👑 MI NEXUS AI TRADING BOT — VERSION 2 (PREMIUM BROADCAST EDITION)
=============================================================================
- Admin-only control (single owner ID lock)
- Full trading-session broadcast flow to groups/channels:
    1) SESSION START sticker
    2) Signal analysis -> premium MI NEXUS card + UP/DOWN sticker
    3) Community WIN/LOSS voting buttons under the signal
    4) Auto-tallied WIN or LOSS result card (after voting window)
    5) SESSION CLOSE sticker
- Broadcast ON/OFF toggle (admin only)
- Built on python-telegram-bot v20+ (async) + Google Gemini vision
=============================================================================
"""

import os
import sys
import io
import json
import random
import logging
import asyncio
import traceback
from typing import Dict, Any, Set, Optional
from datetime import datetime

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from telegram.constants import ChatAction

from google import genai

from card_engine import build_signal_card, build_result_card

# =============================================================================
# 1. LOGGING
# =============================================================================
logging.basicConfig(
    format='[%(asctime)s] [%(levelname)s] [%(name)s:%(lineno)d] - %(message)s',
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("MI_NEXUS_V2")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# =============================================================================
# 2. CONFIGURATION
# =============================================================================
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

# 🔒 SINGLE OWNER LOCK — Only this Telegram user ID may operate the bot.
OWNER_ID: int = int(os.getenv("OWNER_ID", "8865257002"))

# Voting window (seconds) before a WIN/LOSS session result auto-finalizes
VOTE_WINDOW_SECONDS: int = int(os.getenv("VOTE_WINDOW_SECONDS", "45"))

MAX_CONCURRENT_REQUESTS: int = 3
request_semaphore: asyncio.Semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

# Broadcast targets (groups/channels the bot has been added to & that opted in)
REGISTERED_GROUPS: Set[int] = set()
BROADCAST_ENABLED: bool = True

# Active vote sessions: message_key -> {chat_id, message_id, win_voters:set, loss_voters:set, task}
ACTIVE_VOTES: Dict[str, Dict[str, Any]] = {}

gemini_client: Optional[genai.Client] = None
try:
    if GEMINI_API_KEY:
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
        logger.info("✅ Gemini AI Client initialized.")
    else:
        logger.error("⚠️ GEMINI_API_KEY not set.")
except Exception as e:
    logger.critical(f"❌ Gemini init error: {e}")

# =============================================================================
# 3. PROMPT
# =============================================================================
ANALYSIS_PROMPT: str = """
You are an expert binary options chart analyst. Analyze this trading chart screenshot
and respond STRICTLY as compact JSON (no markdown, no code fences, no extra text) with
this exact schema:

{
  "asset": "string, best guess pair/OTC name or 'Unknown Asset'",
  "direction": "UP" or "DOWN",
  "confidence": integer 0-100,
  "timeframe": "1 Min" or "5 Min" etc,
  "trend_bias": "short phrase e.g. Strong Up / Flat / Strong Down",
  "market_condition": "short phrase e.g. Clean Trend / Choppy / Ranging",
  "sentiment": "BULLISH" or "BEARISH",
  "patterns": [ {"name": "pattern name", "reliability": integer 0-100}, up to 3 items ],
  "tip": "one short actionable tip sentence"
}

Base this purely on visible candlestick price action, momentum, wick rejections, and
support/resistance structure in the image. Respond with ONLY the JSON object.
"""

# =============================================================================
# 4. ADMIN GUARD
# =============================================================================
def is_owner(update: Update) -> bool:
    user = update.effective_user
    return bool(user and user.id == OWNER_ID)


async def deny_if_not_owner(update: Update) -> bool:
    """Returns True if the request was denied (i.e. caller should stop)."""
    if not is_owner(update):
        try:
            await update.message.reply_text(
                "⛔ **Access Denied**\nYe bot sirf iske Owner/Admin operate kar sakta hai."
                ,
                parse_mode="Markdown"
            )
        except Exception:
            pass
        return True
    return False

# =============================================================================
# 5. GROUP REGISTRY
# =============================================================================
async def track_group(update: Update):
    chat = update.effective_chat
    if chat and chat.type in ("group", "supergroup", "channel"):
        REGISTERED_GROUPS.add(chat.id)

# =============================================================================
# 6. COMMAND HANDLERS (OWNER ONLY)
# =============================================================================
async def command_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await track_group(update)
    if not is_owner(update):
        await update.message.reply_text(
            "👑 **MI NEXUS AI**\nYe ek private trading-signal broadcaster bot hai, "
            "sirf iske owner ke control mein.",
            parse_mode="Markdown"
        )
        return

    text = (
        "👑 **MI NEXUS AI — VERSION 2 (Owner Panel)** 🚀\n\n"
        "Smarter • Faster • Stronger\n\n"
        "**Session Commands:**\n"
        "• `/session_start` — Group/Channel me session start sticker bhejein\n"
        "• Chart photo bhejein (reply/caption ke sath) — signal card + UP/DOWN sticker + vote buttons broadcast honge\n"
        "• `/session_close` — Session close sticker bhejein\n\n"
        "**Broadcast Control:**\n"
        "• `/broadcast_on` — Broadcasting enable karein\n"
        "• `/broadcast_off` — Broadcasting disable karein\n"
        "• `/addgroup` — Is chat ko broadcast list me add karein (isi group me bhejein)\n"
        "• `/status` — Bot health & broadcast status\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def command_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_not_owner(update):
        return
    text = (
        "🟢 **MI NEXUS AI — STATUS**\n\n"
        f"• Broadcast: {'✅ ON' if BROADCAST_ENABLED else '⛔ OFF'}\n"
        f"• Registered Groups/Channels: {len(REGISTERED_GROUPS)}\n"
        f"• Active Vote Sessions: {len(ACTIVE_VOTES)}\n"
        f"• Gemini Engine: {'Ready ✅' if gemini_client else 'NOT CONFIGURED ❌'}\n"
        f"• Vote Window: {VOTE_WINDOW_SECONDS}s\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def command_addgroup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_not_owner(update):
        return
    chat = update.effective_chat
    REGISTERED_GROUPS.add(chat.id)
    await update.message.reply_text(f"✅ Ye chat broadcast list me add ho gayi: `{chat.id}`", parse_mode="Markdown")


async def command_broadcast_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global BROADCAST_ENABLED
    if await deny_if_not_owner(update):
        return
    BROADCAST_ENABLED = True
    await update.message.reply_text("✅ **Broadcasting ENABLED.**", parse_mode="Markdown")


async def command_broadcast_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global BROADCAST_ENABLED
    if await deny_if_not_owner(update):
        return
    BROADCAST_ENABLED = False
    await update.message.reply_text("⛔ **Broadcasting DISABLED.**", parse_mode="Markdown")


async def _send_sticker_everywhere(context: ContextTypes.DEFAULT_TYPE, asset_filename: str, caption: str = None):
    if not BROADCAST_ENABLED:
        return
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", asset_filename)
    if not REGISTERED_GROUPS:
        return
    for chat_id in list(REGISTERED_GROUPS):
        try:
            with open(path, "rb") as f:
                await context.bot.send_photo(chat_id=chat_id, photo=f, caption=caption, parse_mode="Markdown")
            await asyncio.sleep(0.05)
        except Exception as e:
            logger.warning(f"Failed sticker send to {chat_id}: {e}")


async def command_session_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_not_owner(update):
        return
    await update.message.reply_text("🚦 Session Start broadcast ho rahi hai...")
    await _send_sticker_everywhere(
        context, "sticker_session_start.png",
        caption="🏁 **TRADING SESSION START** 🏁\n_MI NEXUS AI live analysis shuru ho gaya hai!_"
    )


async def command_session_close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_not_owner(update):
        return
    await update.message.reply_text("🏁 Session Close broadcast ho rahi hai...")
    await _send_sticker_everywhere(
        context, "sticker_session_close.png",
        caption="🔚 **TRADING SESSION CLOSED** 🔚\n_Shukriya! Agla session jald hi._"
    )

# =============================================================================
# 7. VISION ANALYSIS -> JSON PARSE
# =============================================================================
def _safe_parse_json(raw_text: str) -> Optional[dict]:
    try:
        cleaned = raw_text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:]
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1:
            return None
        return json.loads(cleaned[start:end + 1])
    except Exception:
        return None


async def _run_gemini_analysis(image_bytes: bytes) -> Optional[dict]:
    from PIL import Image as PILImage
    pil_img = PILImage.open(io.BytesIO(image_bytes))
    loop = asyncio.get_running_loop()
    response = await loop.run_in_executor(
        None,
        lambda: gemini_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[pil_img, ANALYSIS_PROMPT]
        )
    )
    if not response or not response.text:
        return None
    return _safe_parse_json(response.text)

# =============================================================================
# 8. CHART PHOTO -> SIGNAL BROADCAST (OWNER ONLY TRIGGER)
# =============================================================================
def _vote_key(chat_id: int, message_id: int) -> str:
    return f"{chat_id}:{message_id}"


def _vote_keyboard(win_count: int, loss_count: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"✅ WIN ({win_count})", callback_data="vote_win"),
            InlineKeyboardButton(f"❌ LOSS ({loss_count})", callback_data="vote_loss"),
        ]
    ])


async def handle_chart_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await track_group(update)

    # Only the owner may trigger a broadcast analysis
    if not is_owner(update):
        return

    if not gemini_client:
        await update.message.reply_text("❌ Gemini API key set nahi hai. Environment variable check karein.")
        return

    if not BROADCAST_ENABLED:
        await update.message.reply_text("⛔ Broadcasting abhi OFF hai. `/broadcast_on` se enable karein.")
        return

    async with request_semaphore:
        status_msg = await update.message.reply_text("🔍 **Chart analyze ho raha hai...** ⏳")
        try:
            photo = update.message.photo[-1]
            file = await context.bot.get_file(photo.file_id)
            image_bytes = bytes(await file.download_as_bytearray())

            data = await _run_gemini_analysis(image_bytes)
            if not data:
                await status_msg.edit_text("❌ Analysis fail ho gaya. Dobara clear chart bhejein.")
                return

            direction = str(data.get("direction", "UP")).upper()
            if direction not in ("UP", "DOWN"):
                direction = "UP"
            confidence = int(data.get("confidence", 75))
            confidence = max(0, min(100, confidence))
            timeframe = str(data.get("timeframe", "1 Min"))
            trend_bias = str(data.get("trend_bias", "Flat"))
            market_condition = str(data.get("market_condition", "Clean Trend"))
            sentiment = str(data.get("sentiment", "BULLISH" if direction == "UP" else "BEARISH")).upper()
            patterns_raw = data.get("patterns", [])
            patterns = []
            for p in patterns_raw[:3]:
                try:
                    patterns.append((str(p.get("name", "Pattern")), int(p.get("reliability", 50))))
                except Exception:
                    continue
            if not patterns:
                patterns = [("Trend Continuation", 60)]
            tip = str(data.get("tip", "Wait for confirmation before entering a trade."))
            asset = str(data.get("asset", "Unknown Asset"))

            card_buf = build_signal_card(
                chart_image_bytes=image_bytes,
                asset_name=asset,
                direction=direction,
                confidence=confidence,
                timeframe=timeframe,
                trend_bias=trend_bias,
                market_condition=market_condition,
                sentiment=sentiment,
                patterns=patterns,
                tip=tip,
                session_label="LIVE SIGNAL",
            )

            await status_msg.delete()

            direction_sticker = "sticker_call_up.png" if direction == "UP" else "sticker_put_down.png"
            sticker_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", direction_sticker)

            if not REGISTERED_GROUPS:
                # No broadcast targets registered yet — send directly back to owner as preview
                card_buf.seek(0)
                await update.message.reply_photo(photo=card_buf, caption=f"📊 **{asset}** — Signal: {direction} ({confidence}%)\n\n⚠️ Koi group registered nahi hai broadcast ke liye. `/addgroup` us group me bhej kar register karein.", parse_mode="Markdown")
                return

            for chat_id in list(REGISTERED_GROUPS):
                try:
                    # 1) direction sticker (quick visual)
                    with open(sticker_path, "rb") as f:
                        await context.bot.send_photo(chat_id=chat_id, photo=f)

                    # 2) full premium signal card + vote buttons
                    card_buf.seek(0)
                    sent = await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=card_buf,
                        caption=(
                            f"📊 **{asset}**\n"
                            f"🎯 Signal: {'🟢 UP (CALL)' if direction=='UP' else '🔻 DOWN (PUT)'}\n"
                            f"🔥 Confidence: {confidence}%\n\n"
                            f"👇 Trade ke baad result vote karein:"
                        ),
                        parse_mode="Markdown",
                        reply_markup=_vote_keyboard(0, 0),
                    )

                    key = _vote_key(chat_id, sent.message_id)
                    ACTIVE_VOTES[key] = {
                        "chat_id": chat_id,
                        "message_id": sent.message_id,
                        "win_voters": set(),
                        "loss_voters": set(),
                        "asset": asset,
                        "finalized": False,
                    }
                    context.application.create_task(
                        _finalize_vote_after_delay(context, key, VOTE_WINDOW_SECONDS)
                    )
                    await asyncio.sleep(0.05)
                except Exception as e:
                    logger.warning(f"Broadcast failed for {chat_id}: {e}")

            await update.message.reply_text(f"✅ Signal broadcast ho gaya {len(REGISTERED_GROUPS)} chat(s) me.")

        except Exception:
            logger.error(f"Vision analysis error: {traceback.format_exc()}")
            try:
                await status_msg.edit_text("❌ Image process karne me masla aaya. Dobara try karein.")
            except Exception:
                pass

# =============================================================================
# 9. VOTE HANDLING & AUTO-FINALIZE
# =============================================================================
async def handle_vote_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat_id
    message_id = query.message.message_id
    key = _vote_key(chat_id, message_id)

    session = ACTIVE_VOTES.get(key)
    if not session or session.get("finalized"):
        await query.answer("⏱️ Voting is closed for this signal.", show_alert=False)
        return

    voter_id = query.from_user.id
    if query.data == "vote_win":
        session["loss_voters"].discard(voter_id)
        session["win_voters"].add(voter_id)
        await query.answer("✅ Vote recorded: WIN")
    elif query.data == "vote_loss":
        session["win_voters"].discard(voter_id)
        session["loss_voters"].add(voter_id)
        await query.answer("❌ Vote recorded: LOSS")
    else:
        await query.answer()
        return

    win_count = len(session["win_voters"])
    loss_count = len(session["loss_voters"])
    try:
        await query.edit_message_reply_markup(reply_markup=_vote_keyboard(win_count, loss_count))
    except Exception:
        pass


async def _finalize_vote_after_delay(context: ContextTypes.DEFAULT_TYPE, key: str, delay: int):
    await asyncio.sleep(delay)
    session = ACTIVE_VOTES.get(key)
    if not session or session.get("finalized"):
        return
    session["finalized"] = True

    win_count = len(session["win_voters"])
    loss_count = len(session["loss_voters"])
    is_win = win_count >= loss_count  # tie defaults to WIN (optimistic)

    try:
        # lock the vote buttons
        await context.bot.edit_message_reply_markup(
            chat_id=session["chat_id"],
            message_id=session["message_id"],
            reply_markup=None,
        )
    except Exception:
        pass

    try:
        result_buf = build_result_card(is_win, win_count, loss_count, session.get("asset", ""))
        result_sticker = "sticker_profit.png" if is_win else "sticker_loss.png"
        sticker_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", result_sticker)

        with open(sticker_path, "rb") as f:
            await context.bot.send_photo(chat_id=session["chat_id"], photo=f)

        await context.bot.send_photo(
            chat_id=session["chat_id"],
            photo=result_buf,
            caption=(
                f"{'✅ SESSION WIN' if is_win else '❌ SESSION LOSS'} — {session.get('asset','')}\n"
                f"👥 Votes: {win_count} WIN / {loss_count} LOSS"
            ),
        )
    except Exception as e:
        logger.warning(f"Result finalize failed for {key}: {e}")

    ACTIVE_VOTES.pop(key, None)

# =============================================================================
# 10. MAIN ENTRY
# =============================================================================
def main():
    logger.info("=" * 60)
    logger.info(" Starting MI NEXUS AI V2 — Premium Broadcast Edition")
    logger.info("=" * 60)

    if not TELEGRAM_BOT_TOKEN:
        logger.critical("❌ TELEGRAM_BOT_TOKEN missing. Exiting.")
        sys.exit(1)

    builder = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN)
    builder.concurrent_updates(True)
    app = builder.build()

    app.add_handler(CommandHandler("start", command_start))
    app.add_handler(CommandHandler("status", command_status))
    app.add_handler(CommandHandler("addgroup", command_addgroup))
    app.add_handler(CommandHandler("broadcast_on", command_broadcast_on))
    app.add_handler(CommandHandler("broadcast_off", command_broadcast_off))
    app.add_handler(CommandHandler("session_start", command_session_start))
    app.add_handler(CommandHandler("session_close", command_session_close))

    app.add_handler(MessageHandler(filters.PHOTO, handle_chart_image))
    app.add_handler(CallbackQueryHandler(handle_vote_callback, pattern="^vote_"))

    logger.info(f"🔒 Owner-only lock active for ID: {OWNER_ID}")
    logger.info("🚀 MI NEXUS AI V2 is live!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()

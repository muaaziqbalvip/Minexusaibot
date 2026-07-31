"""
=============================================================================
👑 MI NEXUS AI TRADING BOT — VERSION 2 (PREMIUM BROADCAST EDITION)
=============================================================================
- STRICT single-owner lock: only OWNER_ID can use the bot at all. Everyone
  else who touches the bot in private chat gets "not available" message.
- Full menu (reply keyboard) restored for the owner, same spirit as v1,
  PLUS new session-broadcast controls as buttons (not slash commands).
- Chart analysis restores the annotated-image style AND adds the premium
  MI NEXUS dark card, both driven from one Gemini call.
- Group/channel broadcast flow:
    1) SESSION START sticker
    2) Signal -> premium card + UP/DOWN sticker + community WIN/LOSS voting
    3) Auto-tallied WIN/LOSS result card (after voting window)
    4) SESSION CLOSE sticker
- Model: gemini-3.5-flash
=============================================================================
"""

import os
import sys
import io
import json
import logging
import asyncio
import traceback
from typing import Dict, Any, Set, Optional

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
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

# 🔒 SINGLE OWNER LOCK — Only this Telegram user ID may use the bot at all.
OWNER_ID: int = int(os.getenv("OWNER_ID", "8865257002"))

# Voting window (seconds) before a WIN/LOSS session result auto-finalizes
VOTE_WINDOW_SECONDS: int = int(os.getenv("VOTE_WINDOW_SECONDS", "45"))

MAX_CONCURRENT_REQUESTS: int = 3
request_semaphore: asyncio.Semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

MODEL_NAME = "gemini-3.5-flash"

# Broadcast targets (groups/channels the bot has been added to & registered)
REGISTERED_GROUPS: Set[int] = set()
BROADCAST_ENABLED: bool = True

# "awaiting" state per owner chat: what the next photo should do
# values: None | "personal" | "broadcast"
OWNER_MODE: Dict[int, str] = {}

# Active vote sessions: message_key -> {...}
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

ASSET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

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
  "tip": "one short actionable tip sentence",
  "reason": "two short powerful sentences explaining the call, in Roman-Urdu"
}

Base this purely on visible candlestick price action, momentum, wick rejections, and
support/resistance structure in the image. Respond with ONLY the JSON object.
"""

# =============================================================================
# 4. ACCESS CONTROL — STRICT SINGLE OWNER
# =============================================================================
def is_owner(update: Update) -> bool:
    user = update.effective_user
    return bool(user and user.id == OWNER_ID)


async def block_non_owner_private(update: Update) -> bool:
    """
    In private chats, any non-owner user is told the bot is not available
    and nothing else happens. Returns True if the message was blocked.
    """
    chat = update.effective_chat
    if chat and chat.type == "private" and not is_owner(update):
        try:
            await update.message.reply_text(
                "🚫 This bot is not available for you."
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
# 6. KEYBOARDS (Owner-only main menu — restored & extended)
# =============================================================================
def get_main_reply_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton("📊 Analyze Chart Now"), KeyboardButton("📡 Broadcast Chart to Groups")],
        [KeyboardButton("🏁 Session Start"), KeyboardButton("🔚 Session Close")],
        [KeyboardButton("📶 Broadcast ON"), KeyboardButton("🛑 Broadcast OFF")],
        [KeyboardButton("➕ Register This Group"), KeyboardButton("⚡ Bot Status")],
        [KeyboardButton("💡 Golden Rules")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_inline_action_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("📊 Send Another Chart", callback_data="action_send_chart")]
    ]
    return InlineKeyboardMarkup(keyboard)


def _vote_keyboard(win_count: int, loss_count: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"✅ WIN ({win_count})", callback_data="vote_win"),
            InlineKeyboardButton(f"❌ LOSS ({loss_count})", callback_data="vote_loss"),
        ]
    ])

# =============================================================================
# 7. IMAGE OVERLAY (restored classic style — quick banner over the chart)
# =============================================================================
def generate_annotated_chart_image(image_bytes: bytes, is_up: bool) -> io.BytesIO:
    from PIL import Image, ImageDraw, ImageFont
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        draw = ImageDraw.Draw(img)
        w, h = img.size

        bg_color = (0, 180, 80) if is_up else (220, 40, 40)
        banner_text = "🚀 MI NEXUS SIGNAL: 🟢 UP (BUY)" if is_up else "🔥 MI NEXUS SIGNAL: 🔻 DOWN (SELL)"

        banner_height = max(40, int(h * 0.08))
        draw.rectangle([(0, 0), (w, banner_height)], fill=bg_color)
        draw.rectangle([(0, 0), (w, banner_height)], outline=(255, 255, 255), width=2)

        font_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts", "DejaVuSans-Bold.ttf")
        try:
            font_size = max(16, int(banner_height * 0.4))
            font = ImageFont.truetype(font_path, font_size)
        except Exception:
            font = ImageFont.load_default()

        text_position = (int(w * 0.03), int(banner_height * 0.22))
        draw.text(text_position, banner_text, fill=(255, 255, 255), font=font)

        output_buffer = io.BytesIO()
        img.save(output_buffer, format='JPEG', quality=90)
        output_buffer.seek(0)
        return output_buffer
    except Exception as e:
        logger.error(f"Overlay error: {e}")
        fallback_stream = io.BytesIO(image_bytes)
        fallback_stream.seek(0)
        return fallback_stream

# =============================================================================
# 8. GEMINI ANALYSIS
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
            model=MODEL_NAME,
            contents=[pil_img, ANALYSIS_PROMPT]
        )
    )
    if not response or not response.text:
        return None
    return _safe_parse_json(response.text)


def _normalize_analysis(data: dict) -> dict:
    direction = str(data.get("direction", "UP")).upper()
    if direction not in ("UP", "DOWN"):
        direction = "UP"
    confidence = int(data.get("confidence", 75) or 75)
    confidence = max(0, min(100, confidence))
    patterns_raw = data.get("patterns", []) or []
    patterns = []
    for p in patterns_raw[:3]:
        try:
            patterns.append((str(p.get("name", "Pattern")), int(p.get("reliability", 50))))
        except Exception:
            continue
    if not patterns:
        patterns = [("Trend Continuation", 60)]
    return {
        "asset": str(data.get("asset", "Unknown Asset")),
        "direction": direction,
        "confidence": confidence,
        "timeframe": str(data.get("timeframe", "1 Min")),
        "trend_bias": str(data.get("trend_bias", "Flat")),
        "market_condition": str(data.get("market_condition", "Clean Trend")),
        "sentiment": str(data.get("sentiment", "BULLISH" if direction == "UP" else "BEARISH")).upper(),
        "patterns": patterns,
        "tip": str(data.get("tip", "Wait for confirmation before entering a trade.")),
        "reason": str(data.get("reason", "")),
    }

# =============================================================================
# 9. COMMAND HANDLERS
# =============================================================================
async def command_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await block_non_owner_private(update):
        return
    await track_group(update)

    if update.effective_chat.type != "private":
        return  # menu only relevant in private chat with owner

    welcome_text = (
        "👑 **MI NEXUS AI TRADING BOT (V2 — PREMIUM)** 🚀\n\n"
        "Smarter • Faster • Stronger — Gemini 3.5 Flash Powered\n\n"
        "📸 **Personal Analysis:** 'Analyze Chart Now' dabayein aur chart bhejein.\n"
        "📡 **Group Broadcast:** 'Broadcast Chart to Groups' dabayein, phir chart bhejein — "
        "MI NEXUS card + UP/DOWN sticker + WIN/LOSS voting sabhi registered groups me chala jayega.\n"
        "🏁 **Session Control:** Session Start / Close se group me flag stickers bhejein.\n\n"
        "👇 Menu se control karein:"
    )
    await update.message.reply_text(
        welcome_text,
        parse_mode="Markdown",
        reply_markup=get_main_reply_keyboard()
    )


async def command_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await block_non_owner_private(update):
        return
    if update.effective_chat.type != "private":
        return
    help_text = (
        "❓ **مدد اور رہنما ہدایات:**\n\n"
        "• **Analyze Chart Now:** apna chart bhejein, sirf aapko signal milega.\n"
        "• **Broadcast Chart to Groups:** chart bhejein, sab registered group/channel me broadcast hoga "
        "with WIN/LOSS voting.\n"
        "• **Register This Group:** kisi group me ye command bhej kar use broadcast list me add karein.\n"
        "• **Session Start / Close:** trading session ke flag stickers broadcast karein.\n"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

# =============================================================================
# 10. STICKER BROADCAST HELPERS
# =============================================================================
async def _send_sticker_everywhere(context: ContextTypes.DEFAULT_TYPE, asset_filename: str, caption: str = None):
    if not BROADCAST_ENABLED or not REGISTERED_GROUPS:
        return 0
    path = os.path.join(ASSET_DIR, asset_filename)
    sent = 0
    for chat_id in list(REGISTERED_GROUPS):
        try:
            with open(path, "rb") as f:
                await context.bot.send_photo(chat_id=chat_id, photo=f, caption=caption, parse_mode="Markdown")
            sent += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            logger.warning(f"Sticker send failed {chat_id}: {e}")
    return sent

# =============================================================================
# 11. TEXT / MENU BUTTON HANDLER (owner only, private chat only)
# =============================================================================
async def handle_text_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await block_non_owner_private(update):
        return
    await track_group(update)

    chat = update.effective_chat
    text = update.message.text

    # In groups, ignore plain text (only owner-triggered photo/session actions matter there)
    if chat.type != "private":
        return

    user_id = update.effective_user.id

    if text == "📊 Analyze Chart Now":
        OWNER_MODE[user_id] = "personal"
        await update.message.reply_text("📸 Apna chart screenshot bhejein — sirf aapko yahan signal milega.")

    elif text == "📡 Broadcast Chart to Groups":
        if not REGISTERED_GROUPS:
            await update.message.reply_text(
                "⚠️ Abhi koi group/channel registered nahi hai.\n"
                "Pehle us group me `➕ Register This Group` bhejein ya wahan se command chalayein."
            )
            return
        OWNER_MODE[user_id] = "broadcast"
        await update.message.reply_text(
            f"📸 Chart bhejein — ye {len(REGISTERED_GROUPS)} registered group(s)/channel(s) me "
            f"MI NEXUS card + sticker + WIN/LOSS voting ke sath broadcast hoga."
        )

    elif text == "🏁 Session Start":
        n = await _send_sticker_everywhere(
            context, "sticker_session_start.png",
            caption="🏁 **TRADING SESSION START** 🏁\n_MI NEXUS AI live analysis shuru ho gaya hai!_"
        )
        await update.message.reply_text(f"✅ Session Start bheja gaya {n} chat(s) me.")

    elif text == "🔚 Session Close":
        n = await _send_sticker_everywhere(
            context, "sticker_session_close.png",
            caption="🔚 **TRADING SESSION CLOSED** 🔚\n_Shukriya! Agla session jald hi._"
        )
        await update.message.reply_text(f"✅ Session Close bheja gaya {n} chat(s) me.")

    elif text == "📶 Broadcast ON":
        global BROADCAST_ENABLED
        BROADCAST_ENABLED = True
        await update.message.reply_text("✅ Broadcasting ENABLED.")

    elif text == "🛑 Broadcast OFF":
        BROADCAST_ENABLED = False
        await update.message.reply_text("⛔ Broadcasting DISABLED.")

    elif text == "➕ Register This Group":
        await update.message.reply_text(
            "ℹ️ Ye button sirf group/channel me kaam karta hai. "
            "Bot ko us group me add karke wahan yehi text bhejein."
        )

    elif text == "⚡ Bot Status":
        status_text = (
            "🟢 **MI NEXUS AI — STATUS**\n\n"
            f"• Broadcast: {'✅ ON' if BROADCAST_ENABLED else '⛔ OFF'}\n"
            f"• Registered Groups/Channels: {len(REGISTERED_GROUPS)}\n"
            f"• Active Vote Sessions: {len(ACTIVE_VOTES)}\n"
            f"• Gemini Engine ({MODEL_NAME}): {'Ready ✅' if gemini_client else 'NOT CONFIGURED ❌'}\n"
            f"• Vote Window: {VOTE_WINDOW_SECONDS}s"
        )
        await update.message.reply_text(status_text, parse_mode="Markdown")

    elif text == "💡 Golden Rules":
        rules = (
            "🎯 **تجارتی اصول (Golden Trading Rules):**\n\n"
            "1. ⏱️ **Timeframe:** 1M یا 5M چارٹس پر فوکس کریں۔\n"
            "2. 💰 **Risk Management:** ٹوٹل ایکویٹی کا صرف 1-2% فی ٹریڈ رسک لیں۔\n"
            "3. 📰 **News Filter:** ہائی امپیکٹ نیوز کے وقت ٹریڈ نہ کریں۔\n"
            "4. 📉 **Trend Rules:** ہمیشہ ٹرینڈ کی سمت میں سگنل فالو کریں۔"
        )
        await update.message.reply_text(rules, parse_mode="Markdown")

    elif text == "➕ Register This Group" or text.strip().lower() == "/addgroup":
        pass  # handled above

# =============================================================================
# 12. GROUP-SIDE TEXT: register group command works when sent inside a group
# =============================================================================
async def handle_group_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup", "channel"):
        return
    if not is_owner(update):
        return  # silently ignore non-owner text in groups
    text = (update.message.text or "").strip()
    if text in ("➕ Register This Group", "/addgroup", "/register"):
        REGISTERED_GROUPS.add(chat.id)
        await update.message.reply_text(f"✅ Ye chat broadcast list me register ho gayi. (ID: `{chat.id}`)", parse_mode="Markdown")

# =============================================================================
# 13. CHART PHOTO HANDLER — personal OR broadcast, owner only
# =============================================================================
async def handle_chart_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat

    if chat.type == "private":
        if await block_non_owner_private(update):
            return
    else:
        # in groups, only the owner's photos are ever analyzed
        if not is_owner(update):
            return

    await track_group(update)

    if not gemini_client:
        await update.message.reply_text(f"❌ Gemini API key set nahi hai ({MODEL_NAME}). Environment variable check karein.")
        return

    user_id = update.effective_user.id
    mode = OWNER_MODE.get(user_id, "personal")

    async with request_semaphore:
        status_msg = await update.message.reply_text("🔍 **Chart analyze ho raha hai... 3-5 sec intezar karein.** ⏳")
        try:
            photo = update.message.photo[-1]
            file = await context.bot.get_file(photo.file_id)
            image_bytes = bytes(await file.download_as_bytearray())

            raw = await _run_gemini_analysis(image_bytes)
            if not raw:
                await status_msg.edit_text("❌ Analysis fail ho gaya. Dobara clear chart bhejein.")
                return
            data = _normalize_analysis(raw)
            direction = data["direction"]
            is_up = direction == "UP"

            await status_msg.delete()

            if chat.type == "private" and mode != "broadcast":
                # ---------- PERSONAL MODE: classic annotated image reply ----------
                annotated = generate_annotated_chart_image(image_bytes, is_up)
                caption = (
                    f"📊 **ASSET:** {data['asset']}\n"
                    f"📈 **TREND:** {data['trend_bias']}\n\n"
                    f"🎯 **SIGNAL:** {'🟢 UP (BUY)' if is_up else '🔻 DOWN (SELL)'}\n"
                    f"⏳ **EXPIRY:** {data['timeframe']}\n"
                    f"🔥 **CONFIDENCE:** {data['confidence']}%\n\n"
                    f"💡 **REASON:** {data['reason'] or data['tip']}"
                )
                await update.message.reply_photo(
                    photo=annotated,
                    caption=caption,
                    parse_mode="Markdown",
                    reply_markup=get_inline_action_keyboard()
                )
                return

            # ---------- BROADCAST MODE ----------
            if not BROADCAST_ENABLED:
                await update.message.reply_text("⛔ Broadcasting abhi OFF hai. Pehle '📶 Broadcast ON' dabayein.")
                return
            if not REGISTERED_GROUPS:
                await update.message.reply_text("⚠️ Koi group registered nahi hai. Pehle group me jaakar register karein.")
                return

            card_buf = build_signal_card(
                chart_image_bytes=image_bytes,
                asset_name=data["asset"],
                direction=direction,
                confidence=data["confidence"],
                timeframe=data["timeframe"],
                trend_bias=data["trend_bias"],
                market_condition=data["market_condition"],
                sentiment=data["sentiment"],
                patterns=data["patterns"],
                tip=data["tip"],
                session_label="LIVE SIGNAL",
            )
            direction_sticker = "sticker_call_up.png" if is_up else "sticker_put_down.png"
            sticker_path = os.path.join(ASSET_DIR, direction_sticker)

            sent_count = 0
            for chat_id in list(REGISTERED_GROUPS):
                try:
                    with open(sticker_path, "rb") as f:
                        await context.bot.send_photo(chat_id=chat_id, photo=f)

                    card_buf.seek(0)
                    sent = await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=card_buf,
                        caption=(
                            f"📊 **{data['asset']}**\n"
                            f"🎯 Signal: {'🟢 UP (CALL)' if is_up else '🔻 DOWN (PUT)'}\n"
                            f"🔥 Confidence: {data['confidence']}%\n\n"
                            f"👇 Trade ke baad result vote karein:"
                        ),
                        parse_mode="Markdown",
                        reply_markup=_vote_keyboard(0, 0),
                    )
                    key = f"{chat_id}:{sent.message_id}"
                    ACTIVE_VOTES[key] = {
                        "chat_id": chat_id,
                        "message_id": sent.message_id,
                        "win_voters": set(),
                        "loss_voters": set(),
                        "asset": data["asset"],
                        "finalized": False,
                    }
                    context.application.create_task(_finalize_vote_after_delay(context, key, VOTE_WINDOW_SECONDS))
                    sent_count += 1
                    await asyncio.sleep(0.05)
                except Exception as e:
                    logger.warning(f"Broadcast failed for {chat_id}: {e}")

            await update.message.reply_text(f"✅ Signal broadcast ho gaya {sent_count} chat(s) me.")

        except Exception:
            logger.error(f"Vision analysis error: {traceback.format_exc()}")
            try:
                await status_msg.edit_text("❌ Image process karne me masla aaya. Dobara try karein.")
            except Exception:
                pass

# =============================================================================
# 14. VOTE HANDLING & AUTO-FINALIZE (group members CAN vote)
# =============================================================================
async def handle_vote_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat_id
    message_id = query.message.message_id
    key = f"{chat_id}:{message_id}"

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
    elif query.data == "action_send_chart":
        await query.answer()
        await query.message.reply_text("📸 Nya chart bhejein.")
        return
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
    is_win = win_count >= loss_count

    try:
        await context.bot.edit_message_reply_markup(
            chat_id=session["chat_id"], message_id=session["message_id"], reply_markup=None
        )
    except Exception:
        pass

    try:
        result_buf = build_result_card(is_win, win_count, loss_count, session.get("asset", ""))
        result_sticker = "sticker_profit.png" if is_win else "sticker_loss.png"
        sticker_path = os.path.join(ASSET_DIR, result_sticker)

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
# 15. CALLBACK ROUTER (single entry, dispatch by prefix)
# =============================================================================
async def handle_callback_queries(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_vote_callback(update, context)

# =============================================================================
# 16. MAIN ENTRY
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
    app.add_handler(CommandHandler("help", command_help))

    app.add_handler(MessageHandler(filters.PHOTO, handle_chart_image))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, handle_text_messages))
    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUPS, handle_group_text))
    app.add_handler(CallbackQueryHandler(handle_callback_queries))

    logger.info(f"🔒 Strict owner-only lock active for ID: {OWNER_ID}")
    logger.info(f"🤖 Model: {MODEL_NAME}")
    logger.info("🚀 MI NEXUS AI V2 is live!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()

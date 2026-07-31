"""
=============================================================================
👑 NEXUS AI TRADING MASTER BOT - ENTERPRISE & HIGH LOAD EDITION
=============================================================================
Designed for: High Concurrency, Zero 501 Errors, Group Broadcaster & Signal Visualizer
Target Framework: python-telegram-bot (v20+ Async) & google-genai
=============================================================================
"""

import os
import sys
import io
import time
import logging
import asyncio
import traceback
from typing import Dict, Any, List, Set, Optional
from datetime import datetime

# Telegram Framework Imports
from telegram import (
    Update, 
    ReplyKeyboardMarkup, 
    KeyboardButton, 
    InlineKeyboardMarkup, 
    InlineKeyboardButton,
    InputFile
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from telegram.error import TelegramError, NetworkError, TimedOut, RetryAfter

# Google Gemini SDK
from google import genai
from google.genai import types

# Image Processing Engine (Pillow)
from PIL import Image, ImageDraw, ImageFont

# =============================================================================
# 1. ADVANCED SYSTEM LOGGING CONFIGURATION
# =============================================================================
logging.basicConfig(
    format='[%(asctime)s] [%(levelname)s] [%(name)s:%(lineno)d] - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("NEXUS_VIP_BOT")

# Disable overly verbose third-party logs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# =============================================================================
# 2. CONFIGURATION & ENVIRONMENT SETUP
# =============================================================================
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

# Parse Admin IDs safely
ADMIN_IDS_RAW: str = os.getenv("ADMIN_IDS", "")
ADMIN_IDS: Set[int] = set()
if ADMIN_IDS_RAW:
    for aid in ADMIN_IDS_RAW.split(","):
        aid_clean = aid.strip()
        if aid_clean.isdigit():
            ADMIN_IDS.add(int(aid_clean))

# Global Concurrency Semaphore (To prevent HTTP 501/503 Service Unavailable under heavy load)
MAX_CONCURRENT_REQUESTS: int = 3
request_semaphore: asyncio.Semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

# Simple In-Memory Database for Active Users & Groups (Persistence Layer Ready)
REGISTERED_USERS: Set[int] = set()
REGISTERED_GROUPS: Set[int] = set()

# Initialize Gemini Client
gemini_client: Optional[genai.Client] = None
try:
    if GEMINI_API_KEY:
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
        logger.info("✅ Gemini AI Client initialized successfully.")
    else:
        logger.error("⚠️ GEMINI_API_KEY is not set in environment variables.")
except Exception as e:
    logger.critical(f"❌ Critical error initializing Gemini Client: {e}")

# =============================================================================
# 3. PROMPT ARCHITECTURE FOR SHORT & HIGH-ACCURACY SIGNALS
# =============================================================================
PRO_SHORT_PROMPT: str = """
You are an expert binary options analyst. Quickly analyze this chart image for a high-probability 1-2 min trade decision.
Respond strictly in Roman-Urdu with this precise short format:

📊 **ASSET:** [Identify Pair / OTC]
📈 **TREND:** [Strong Uptrend / Downtrend / Sideways]
🧱 **KEY LEVEL:** [Nearest Support/Resistance Level]

🎯 **SIGNAL:** [🟢 UP (BUY) or 🔻 DOWN (SELL)]
⏳ **EXPIRY:** [1 Min / 2 Min]
🔥 **CONFIDENCE:** [e.g., 85% / 90%]

💡 **REASON:** [2 short, powerful sentences explaining why based on price action, momentum, and wick rejections.]
"""

# =============================================================================
# 4. HIGH-SPEED IMAGE ANNOTATION & OVERLAY ENGINE
# =============================================================================
def generate_annotated_chart_image(image_bytes: bytes, signal_text: str) -> io.BytesIO:
    """
    Overlays a professional glowing banner on top of the chart image
    indicating UP or DOWN signal for instant visual clarity in groups.
    """
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        draw = ImageDraw.Draw(img)
        w, h = img.size

        # Determine signal direction
        is_up = "UP" in signal_text.upper() or "BUY" in signal_text.upper()
        
        # Color palettes
        bg_color = (0, 180, 80) if is_up else (220, 40, 40)
        banner_text = "🚀 NEXUS VIP SIGNAL: 🟢 UP (BUY)" if is_up else "🔥 NEXUS VIP SIGNAL: 🔻 DOWN (SELL)"

        # Calculate Banner Height (approx 8% of image height)
        banner_height = max(40, int(h * 0.08))
        
        # Draw Background Banner Box
        draw.rectangle([(0, 0), (w, banner_height)], fill=bg_color)
        
        # Draw Border Line
        draw.rectangle([(0, 0), (w, banner_height)], outline=(255, 255, 255), width=2)

        # Try to load clean font
        try:
            font_size = max(16, int(banner_height * 0.45))
            font = ImageFont.truetype("arial.ttf", font_size)
        except Exception:
            font = ImageFont.load_default()

        # Render Text onto Banner
        text_position = (int(w * 0.03), int(banner_height * 0.2))
        draw.text(text_position, banner_text, fill=(255, 255, 255), font=font)

        # Save to byte stream
        output_buffer = io.BytesIO()
        img.save(output_buffer, format='JPEG', quality=90)
        output_buffer.seek(0)
        return output_buffer

    except Exception as e:
        logger.error(f"Error rendering image overlay: {e}")
        fallback_stream = io.BytesIO(image_bytes)
        fallback_stream.seek(0)
        return fallback_stream

# =============================================================================
# 5. USER & CHAT TRACKING MIDDLEWARE
# =============================================================================
async def register_chat_middleware(update: Update):
    """Tracks active user IDs and group IDs for broadcast features."""
    try:
        if update.effective_user:
            REGISTERED_USERS.add(update.effective_user.id)
        if update.effective_chat and update.effective_chat.type in ['group', 'supergroup']:
            REGISTERED_GROUPS.add(update.effective_chat.id)
    except Exception as e:
        logger.warning(f"Error in tracking middleware: {e}")

# =============================================================================
# 6. TELEGRAM KEYBOARDS & MENUS
# =============================================================================
def get_main_reply_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton("📊 Analyze Chart Now"), KeyboardButton("💡 Golden Rules")],
        [KeyboardButton("👥 VIP Group Info"), KeyboardButton("⚡ Bot Health Status")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_inline_action_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("📊 Send Another Chart", callback_data="action_send_chart"),
            InlineKeyboardButton("🚀 VIP Signals Channel", url="https://t.me")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# =============================================================================
# 7. COMMAND HANDLERS
# =============================================================================
async def command_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await register_chat_middleware(update)
    
    welcome_text = (
        "👑 **NEXUS AI TRADING MASTER BOT (PRO EDITION)** 🚀\n\n"
        "خوش آمدید! یہ بوٹ **Google Gemini 2.5 Flash** کے ذریعے گراف اسکرین شاٹ کا فوری مائیکرو لیول اینالیسس کرتا ہے۔\n\n"
        "📸 **استعمال کا طریقہ:**\n"
        "1️⃣ کسی بھی Quotex، IQ Option یا TradingView کے چارٹ کا اسکرین شاٹ لیں۔\n"
        "2️⃣ اس چیٹ میں اپ لوڈ کریں (یا گروپ میں بوٹ کو ٹیگ کریں)۔\n"
        "3️⃣ AI چند سیکنڈز میں آپ کو اینالائزڈ امیج اور سگنل بھیج دے گا!\n\n"
        "👇 نیچے مینو کے بٹنز استعمال کریں:"
    )
    
    await update.message.reply_text(
        welcome_text,
        parse_mode="Markdown",
        reply_markup=get_main_reply_keyboard()
    )

async def command_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await register_chat_middleware(update)
    help_text = (
        "❓ **مدد اور رہنما ہدایات (Help Guide):**\n\n"
        "• **واضح اسکرین شاٹ:** یقینی بنائیں کہ چارٹ میں کینڈلز اور انڈیکیٹرز صاف نظر آ رہے ہوں۔\n"
        "• **ٹائم فریم:** 1 منٹ یا 5 منٹ کے کینڈل چارٹ کا استعمال کریں۔\n"
        "• **گروپس میں استعمال:** گروپ میں اسکرین شاٹ بھیجتے وقت بوٹ کو مینشن یا ریپلائی کریں۔\n"
        "• **کمانڈز:**\n"
        "  - `/start` : مینو دوبارہ کھولیں\n"
        "  - `/help` : یہ مددگار پیغام دیکھیں"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def command_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin-only command to broadcast announcements across all chats."""
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS and len(ADMIN_IDS) > 0:
        await update.message.reply_text("⛔ آپ کے پاس براڈکاسٹ کی اجازت نہیں ہے۔")
        return

    if not context.args:
        await update.message.reply_text("ℹ️ **طریقہ کار:** `/broadcast آپ کا پیغام`", parse_mode="Markdown")
        return

    broadcast_msg = " ".join(context.args)
    status_msg = await update.message.reply_text("📡 **براڈکاسٹ شروع کی جا رہی ہے...**")

    success = 0
    failed = 0
    target_chats = REGISTERED_USERS.union(REGISTERED_GROUPS)

    for cid in target_chats:
        try:
            await context.bot.send_message(
                chat_id=cid,
                text=f"📢 **VIP ANNOUNCEMENT:**\n\n{broadcast_msg}",
                parse_mode="Markdown"
            )
            success += 1
            await asyncio.sleep(0.05)  # Telegram API rate-limit buffer
        except Exception:
            failed += 1

    await status_msg.edit_text(
        f"✅ **براڈکاسٹ مکمل!**\n\n"
        f"🎯 کامیاب: {success}\n"
        f"❌ ناکام: {failed}"
    )

# =============================================================================
# 8. TEXT COMMANDS & BUTTON HANDLER
# =============================================================================
async def handle_text_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await register_chat_middleware(update)
    text = update.message.text

    if text == "📊 Analyze Chart Now":
        await update.message.reply_text("📸 **برائے مہربانی اپنے ٹریڈنگ چارٹ کا صاف اسکرین شاٹ یہاں اپ لوڈ کریں!**")

    elif text == "💡 Golden Rules":
        rules = (
            "🎯 **تجارتی اصول (Golden Trading Rules):**\n\n"
            "1. ⏱️ **Timeframe:** 1M یا 5M چارٹس پر فوکس کریں۔\n"
            "2. 💰 **Risk Management:** اپنی ٹوٹل ایکویٹی کا صرف 1% سے 2% فی ٹریڈ پر رسک لیں۔\n"
            "3. 📰 **News Filter:** ہائی امپیکٹ نیوز (High Impact News) کے وقت ٹریڈ نہ کریں۔\n"
            "4. 📉 **Trend Rules:** ہمیشہ ٹرینڈ کی ڈائریکشن میں سگنل کو فالو کریں۔"
        )
        await update.message.reply_text(rules, parse_mode="Markdown")

    elif text == "👥 VIP Group Info":
        info = "🚀 **NEXUS VIP Engine:** یہ بوٹ Gemini 2.5 Flash API پر چلتا ہے تاکہ آپ کو انسانی غلطیوں سے پاک لاجیکل اینالیسس مل سکے۔"
        await update.message.reply_text(info, parse_mode="Markdown")

    elif text == "⚡ Bot Health Status":
        status_text = (
            "🟢 **SYSTEM HEALTH STATUS:**\n\n"
            "• **Status:** Active & Ready\n"
            "• **Engine:** Gemini 2.5 Flash\n"
            "• **Queue Handler:** Active (Zero 501 Error Policy)\n"
            f"• **Active Users Tracked:** {len(REGISTERED_USERS)}\n"
            f"• **Active Groups Tracked:** {len(REGISTERED_GROUPS)}"
        )
        await update.message.reply_text(status_text, parse_mode="Markdown")

# =============================================================================
# 9. HIGH PERFORMANCE VISION ANALYSIS ENGINE
# =============================================================================
async def handle_chart_image_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await register_chat_middleware(update)
    
    chat_type = update.effective_chat.type
    
    # Filter group messages: Only analyze if tagged or directly replied
    if chat_type in ['group', 'supergroup']:
        bot_username = context.bot.username
        has_tag = update.message.caption and f"@{bot_username}" in update.message.caption
        is_reply = (
            update.message.reply_to_message 
            and update.message.reply_to_message.from_user.id == context.bot.id
        )
        if not (has_tag or is_reply):
            return

    # Check Gemini API Initialization
    if not gemini_client:
        await update.message.reply_text("❌ Gemini API Key سیٹ نہیں ہے۔ براہ کرم GitHub Secrets چیک کریں۔")
        return

    # Acquire Semaphore Lock to Prevent Overload (HTTP 501 / 503 Mitigation)
    async with request_semaphore:
        status_msg = await update.message.reply_text("🔍 **چارٹ کا معائنہ کیا جا رہا ہے... برائے مہربانی 3-5 سیکنڈ انتظار کریں۔** ⏳")
        
        try:
            # Get Highest Resolution Photo
            photo = update.message.photo[-1]
            file = await context.bot.get_file(photo.file_id)
            image_bytes = await file.download_as_bytearray()
            
            # Load PIL Image
            pil_img = Image.open(io.BytesIO(image_bytes))

            # Non-blocking async API call to Gemini
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None,
                lambda: gemini_client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=[pil_img, PRO_SHORT_PROMPT]
                )
            )

            analysis_text = response.text if response and response.text else "❌ کوئی تجزیہ حاصل نہیں ہو سکا۔"

            # Overlay Signal Banner on Chart Image
            annotated_buffer = generate_annotated_chart_image(image_bytes, analysis_text)

            # Clean up waiting message
            await status_msg.delete()

            # Send Annotated Chart Photo back with Signal Caption
            await update.message.reply_photo(
                photo=annotated_buffer,
                caption=analysis_text,
                parse_mode="Markdown",
                reply_markup=get_inline_action_keyboard()
            )

        except Exception as e:
            logger.error(f"Error during vision analysis: {traceback.format_exc()}")
            try:
                await status_msg.edit_text("❌ **معذرت! امیج پروسیس کرنے میں مسئلہ آیا ہے۔ دوبارہ واضح اسکرین شاٹ بھیجیں۔**")
            except Exception:
                pass

# =============================================================================
# 10. CALLBACK QUERY HANDLER
# =============================================================================
async def handle_callback_queries(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "action_send_chart":
        await query.message.reply_text("📸 **جی! اپنا نیا چارٹ اسکرین شاٹ اپ لوڈ کریں۔**")

# =============================================================================
# 11. MAIN ENTRY POINT & APPLICATION BUILDER
# =============================================================================
def main():
    logger.info("==================================================")
    logger.info(" Starting NEXUS VIP Trading Bot Initialization...")
    logger.info("==================================================")

    if not TELEGRAM_BOT_TOKEN:
        logger.critical("❌ TELEGRAM_BOT_TOKEN missing. Exiting.")
        sys.exit(1)

    # Initialize Telegram Application
    builder = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN)
    
    # Enable concurrent processing
    builder.concurrent_updates(True)
    app = builder.build()

    # Add Command Handlers
    app.add_handler(CommandHandler("start", command_start))
    app.add_handler(CommandHandler("help", command_help))
    app.add_handler(CommandHandler("broadcast", command_broadcast))

    # Add Message Handlers
    app.add_handler(MessageHandler(filters.PHOTO, handle_chart_image_analysis))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_messages))
    
    # Add Callback Handlers
    app.add_handler(CallbackQueryHandler(handle_callback_queries))

    logger.info("🚀 NEXUS VIP Trading Bot is Live and Ready for Requests!")
    
    # Start Bot in Polling Mode (Clears pending updates to avoid backlog on restart)
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()

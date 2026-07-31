import os
import logging
import asyncio
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from google import genai
from PIL import Image
import io

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# 🔑 GitHub Secrets یا Environment Variables سے ٹوکن اٹھائے گا
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Initialize Gemini Client
client = genai.Client(api_key=GEMINI_API_KEY)

# 💎 Advanced Trading Prompt Setup
TRADING_PROMPT = """
You are an elite Institutional Technical Analyst and Binary Options Trader with 10+ years of experience analyzing price action, market structure, and candlestick dynamics.

Your task is to conduct a highly accurate, micro-level analysis of the provided chart image for a binary trade decision (1-to-5 minute expiration). Respond ENTIRELY in Urdu/Roman-Urdu using clear Markdown formatting, structured exactly as shown below:

### 📊 **ADVANCED CHART ANALYSIS**

* 🪙 **Asset / Pair:** [Identify Asset Name, e.g., CAD/JPY or OTC pair if visible]
* ⏱️ **Timeframe:** [Identify Timeframe, e.g., 1M / 5M]
* 📈 **Trend Direction:** [Major Trend: Uptrend / Downtrend / Sideways]

---

### 🕯️ **CANDLESTICK & MARKET STRUCTURE**
* **Current & Previous Candle Pattern:** [Detailed inspection: Engulfing, Hammer, Shooting Star, Pinbar, Marubozu, Doji, etc.]
* **Wick Analysis (Rejection):** [Analyze top and bottom wicks to confirm buyer or seller dominance]
* **Market Momentum:** [Exhaustion, Acceleration, or Retracement phase]

---

### 🧱 **KEY TECHNICAL LEVELS**
* **Support Levels:** [Identify nearest static support levels or round numbers]
* **Resistance Levels:** [Identify nearest static resistance levels or round numbers]
* **Dynamic Support/Resistance:** [Trendlines, Moving Averages, ZigZag turning points]
* **RSI (14) Status:** [Overbought (>70), Oversold (<30), Neutral (~50), or Slope direction]

---

🎯 **DIRECTION SIGNAL:** [🟢 **UP (BUY)** OR 🔻 **DOWN (SELL)**]
⏳ **RECOMMENDED EXPIRY TIME:** [e.g., 1 Minute / 2 Minutes / Next Candle Close]
🔥 **CONFIDENCE LEVEL:** [e.g., 85% High Confidence]

---

💡 **DETAILED TRADE REASONING (تجارتی حکمت عملی):**
[Provide a clear 3-4 sentence explanation in Roman-Urdu detailing EXACTLY why this trade direction was chosen based on the wicks, key levels, RSI slope, and momentum].

⚠️ **RISK & ENTRY ADVICE:**
[Give 1 crucial tip on exact entry timing, e.g., "Wait for a small pullback to level X before pressing BUY"].
"""

# Custom Menu Keyboards
def get_main_menu():
    keyboard = [
        [KeyboardButton("📊 Analyze Chart"), KeyboardButton("💡 Trading Rules")],
        [KeyboardButton("ℹ️ Help / How to use"), KeyboardButton("🚀 VIP Info")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# /start Command Handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "👑 **Welcome to NEXUS AI Trading Master Bot!** 🚀\n\n"
        "میں آپ کا ذاتی **AI Chart Analyst** ہوں۔ مجھے کسی بھی Quotex، IQ Option یا TradingView کا اسکرین شاٹ بھیجیں، "
        "میں مائیکرو لیول پر Candle Structure، RSI اور Support/Resistance کا تجزیہ کر کے سگنل دوں گا!\n\n"
        "👇 نیچے مینو میں سے کوئی بھی آپشن منتخب کریں یا ڈائریکٹ **چارٹ کا اسکرین شاٹ** اپ لوڈ کریں!"
    )
    await update.message.reply_text(
        welcome_text, 
        parse_mode="Markdown", 
        reply_markup=get_main_menu()
    )

# Text Message Handler (Menu Button Clicks)
async def handle_text_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "📊 Analyze Chart":
        msg = "📸 **برائے مہربانی اپنے 1-Min یا 5-Min چارٹ کا صاف اسکرین شاٹ یہاں بھیجیں!**"
        await update.message.reply_text(msg, parse_mode="Markdown")

    elif text == "💡 Trading Rules":
        rules = (
            "🎯 **تجارتی اصول (Golden Trading Rules):**\n\n"
            "1. ⏱️ **Timeframe:** ہمیشہ 1 یا 5 منٹ کے واضح چارٹ استعمال کریں۔\n"
            "2. ⚠️ **Money Management:** اپنی کل رقم کا صرف 1% سے 2% ایک ٹریڈ پر لگائیں۔\n"
            "3. 📰 **News Avoid:** بڑی نیوز (High Impact News) کے وقت ٹریڈ نہ کریں۔\n"
            "4. 📉 **Trend is Friend:** ہمیشہ ٹرینڈ کی سمت میں سگنل کو ترجیح دیں۔"
        )
        await update.message.reply_text(rules, parse_mode="Markdown")

    elif text == "ℹ️ Help / How to use":
        help_msg = (
            "❓ **بوٹ استعمال کرنے کا طریقہ:**\n\n"
            "1️⃣ اپنے بروکر (Quotex وغیرہ) پر چارٹ کھولیں۔\n"
            "2️⃣ چارٹ کا صاف اسکرین شاٹ لیں۔\n"
            "3️⃣ اس چیٹ میں امیج سینڈ کریں۔\n"
            "4️⃣ AI چند سیکنڈز میں مکمل اینالیسس اور سگنل فراہم کر دے گا!"
        )
        await update.message.reply_text(help_msg, parse_mode="Markdown")

    elif text == "🚀 VIP Info":
        vip_msg = (
            "🔥 **NEXUS AI VIP System**\n\n"
            "یہ بوٹ **Google Gemini 2.5 Flash API** کے ساتھ مربوط ہے جو آپ کو انسانی غلطیوں سے پاک، تیز رفتار اور 100% لاجیکل تجزیہ دیتا ہے۔"
        )
        await update.message.reply_text(vip_msg, parse_mode="Markdown")

# Image Handler for Chart Analysis
async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = await update.message.reply_text("🔍 **چارٹ کا گہرا معائنہ کیا جا رہا ہے... برائے مہربانی 3-5 سیکنڈ انتظار کریں۔** ⏳")
    
    try:
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        image_bytes = await file.download_as_bytearray()
        
        img = Image.open(io.BytesIO(image_bytes))

        response = client.models.generate_content(
            model='gemini-1.5-flash',
            contents=[img, TRADING_PROMPT]
        )

        try:
            await status_msg.edit_text(response.text, parse_mode="Markdown")
        except Exception:
            await status_msg.edit_text(response.text)

    except Exception as e:
        logging.error(f"Error: {e}")
        await status_msg.edit_text("❌ **معذرت! امیج ریڈ کرنے میں کوئی مسئلہ آیا ہے۔ براہ کرم دوبارہ واضح اسکرین شاٹ بھیجیں۔**")

def main():
    if not TELEGRAM_BOT_TOKEN or not GEMINI_API_KEY:
        print("❌ Error: Telegram Token or Gemini API Key is missing in environment variables!")
        return

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_image))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_menu))

    print("🚀 NEXUS VIP Trading Bot is Live & Polling...")
    app.run_polling()

if __name__ == "__main__":
    main()

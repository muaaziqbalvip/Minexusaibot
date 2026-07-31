# 👑 MI NEXUS AI — Version 2 (Premium Broadcast Edition)

Trading-session broadcaster bot jo groups/channels me poora session live dikhata hai:
Session Start → Signal (UP/DOWN sticker + premium analysis card) → Community WIN/LOSS voting → Result card → Session Close.

**Sirf Owner (Telegram ID `8865257002`) is bot ko chala sakta hai.** Koi aur user commands
nahi chala sakta — sirf WIN/LOSS buttons dabaa sakta hai jo bot khud group me post karta hai.

---

## 🔧 Setup

### 1. Environment Variables (Secrets)
| Variable | Required | Description |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | ✅ | BotFather se liya gaya token |
| `GEMINI_API_KEY` | ✅ | Google Gemini API key (chart vision analysis ke liye) |
| `OWNER_ID` | Optional (default `8865257002`) | Sirf yehi Telegram user ID bot control kar sakti hai |
| `VOTE_WINDOW_SECONDS` | Optional (default `45`) | Kitni der WIN/LOSS voting khuli rahegi |

GitHub Actions me: **Settings → Secrets and variables → Actions** me ye add karein.

### 2. Install (local/VPS run)
```bash
pip install -r requirements.txt
python bot.py
```

### 3. GitHub Actions (24/7 free hosting)
`.github/workflows/loop.yml` aur `watchdog.yml` already included hain — jaisa aapke
pehle repo me tha, bas ab `OWNER_ID` aur `VOTE_WINDOW_SECONDS` secrets bhi add kar sakte hain.

---

## 📋 Owner Commands (sirf Owner ID se kaam karengi)

| Command | Kaam |
|---|---|
| `/start` | Owner panel/menu dikhaye |
| `/addgroup` | Jis group/channel me ye command bheji jaye, wahi broadcast list me register ho jata hai |
| `/session_start` | Sabhi registered groups me "Session Start" sticker bhejta hai |
| Chart photo bhejna (owner se) | Gemini se analysis karke premium signal card + UP/DOWN sticker + WIN/LOSS vote buttons sabhi groups me broadcast karta hai |
| `/session_close` | Sabhi registered groups me "Session Close" sticker bhejta hai |
| `/broadcast_on` | Broadcasting ON karein |
| `/broadcast_off` | Broadcasting OFF karein |
| `/status` | Bot health, broadcast state, active votes dikhata hai |

## 🗳️ WIN/LOSS Voting Flow

1. Owner chart bhejta hai → bot Gemini se analysis karta hai
2. Har registered group me: UP/DOWN sticker + premium "MI NEXUS" signal card + `✅ WIN / ❌ LOSS` buttons post hote hain
3. Group ke sabhi members vote kar sakte hain (koi bhi apna vote WIN se LOSS ya vice-versa badal sakta hai jab tak window khuli hai)
4. `VOTE_WINDOW_SECONDS` (default 45s) baad — jis side ke zyada votes hon, wahi final result maana jata hai
5. Bot automatic result card post karta hai jisme total WIN/LOSS vote counts show hote hain, sath hi WIN/LOSS sticker

## 🖼️ Assets Used
Sab stickers `assets/` folder me hain (aapke bheje hue MI NEXUS PNG stickers se):
- `sticker_session_start.png` — Session Start
- `sticker_session_close.png` — Session Close
- `sticker_call_up.png` — UP/CALL signal
- `sticker_put_down.png` — DOWN/PUT signal
- `sticker_profit.png` — WIN result
- `sticker_loss.png` — LOSS result
- `logo_round.png` — Card header logo

## 🎨 Premium Card Design
`card_engine.py` dark-theme "MI NEXUS" card banata hai (aapke sample jaisa):
- Header logo + "MI NEXUS — Analyze Predict Profit"
- Chart image panel with STRONG/UP-DOWN pills
- "NEXT CANDLE" + confidence progress bar
- Timeframe / Trend Bias / Market Condition + Patterns Detected
- Market Sentiment box + Volatility box
- Tip bar + footer

Result card (`build_result_card`) WIN ya LOSS ke liye alag design + vote bar chart deta hai.

---

## ⚠️ Important Notes
- Bot sirf Owner se photo accept karke analyze karta hai — group members chart bhej kar
  trigger nahi kar sakte, sirf vote kar sakte hain.
- `/addgroup` zaroor chalayein har us group/channel me jaha broadcast chahiye, warna
  bot ko pata nahi chalega kaha bhejna hai.
- Gemini model `gemini-2.5-flash` use ho raha hai; agar aapke pass different model
  access hai to `bot.py` me `ANALYSIS_PROMPT` ke neeche wali line me model name badal dein.

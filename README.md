# 👑 MI NEXUS AI — Version 2 (Premium Broadcast Edition)

Sirf **Owner (Telegram ID `8865257002`)** ye bot use kar sakta hai — koi aur user private
chat me `/start` bhi kare to bot seedha reply karta hai:
> 🚫 This bot is not available for you.

Group/channel me bhi sirf Owner ke commands/photos par bot react karta hai. Baaki
members sirf **✅ WIN / ❌ LOSS** vote buttons dabaa sakte hain jo bot khud post karta hai.

---

## 🔧 Setup

### Environment Variables (Secrets)
| Variable | Required | Description |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | ✅ | BotFather se liya gaya token |
| `GEMINI_API_KEY` | ✅ | Google Gemini API key |
| `OWNER_ID` | Optional (default `8865257002`) | Sirf yehi ID bot use kar sakti hai |
| `VOTE_WINDOW_SECONDS` | Optional (default `45`) | WIN/LOSS voting kitni der khuli rahegi |

Model: **`gemini-3.5-flash`**

### Run
```bash
pip install -r requirements.txt
python bot.py
```
GitHub Actions workflows (`loop.yml` + `watchdog.yml`) already included for 24/7 free hosting,
same tarah jaisa aapke original repo me tha.

---

## 📱 Owner Menu (private chat me `/start` karne par)

Reply-keyboard menu (jaisa original bot tha, extra buttons ke sath):

| Button | Kaam |
|---|---|
| 📊 Analyze Chart Now | Apna chart bhejein → sirf aapko private me classic annotated-image signal milta hai |
| 📡 Broadcast Chart to Groups | Chart bhejein → sabhi **registered** groups/channels me premium MI NEXUS card + UP/DOWN sticker + WIN/LOSS voting broadcast hota hai |
| 🏁 Session Start | Sabhi registered groups me "Session Start" sticker |
| 🔚 Session Close | Sabhi registered groups me "Session Close" sticker |
| 📶 Broadcast ON / 🛑 Broadcast OFF | Broadcasting on/off karein |
| ➕ Register This Group | (group me use karein) us chat ko broadcast list me add karta hai |
| ⚡ Bot Status | Broadcast state, registered groups count, active votes |
| 💡 Golden Rules | Trading tips |

### Group ko register karna
Bot ko us group/channel me add karein, phir **owner** wahan `➕ Register This Group` text bhej de
(ya `/addgroup`) — us chat ki ID broadcast list me save ho jayegi.

---

## 🗳️ WIN/LOSS Voting Flow

1. Owner "Broadcast Chart to Groups" dabakar chart bhejta hai
2. Har registered group me: UP/DOWN sticker → premium MI NEXUS analysis card → `✅ WIN / ❌ LOSS` buttons
3. Group ke members vote karte hain (vote badal bhi sakte hain jab tak window khuli hai)
4. `VOTE_WINDOW_SECONDS` (default 45s) baad — zyada votes wala side final result banta hai
5. Bot khud WIN ya LOSS sticker + result card (total vote counts ke sath) post karta hai

---

## 🖼️ Assets (`assets/` folder)
- `sticker_session_start.png`, `sticker_session_close.png`
- `sticker_call_up.png` (UP), `sticker_put_down.png` (DOWN)
- `sticker_profit.png` (WIN), `sticker_loss.png` (LOSS)
- `logo_round.png` — card header logo

## 🎨 Card Engine (`card_engine.py`)
Dark-theme premium "MI NEXUS" analysis card (broadcast mode) — logo header, chart panel,
confidence bar, timeframe/trend/condition, patterns detected, sentiment + volatility boxes,
tip bar, footer. WIN/LOSS result card shows vote totals as bar charts.

Personal-mode chart replies still use the lightweight classic style: chart image with a
colored UP/DOWN banner overlaid directly on top (fast, like the original bot).

---

## ⚠️ Notes
- Non-owner users get an instant "not available" message in private chat — bot does
  nothing else for them.
- In groups, only the owner's photos/messages trigger anything; everyone else can only
  press the WIN/LOSS buttons.
- If you have access to a different Gemini model, change `MODEL_NAME` near the top of `bot.py`.

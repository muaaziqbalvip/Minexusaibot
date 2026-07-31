# MI NEXUS — Telegram Chart Analysis Bot

Chart screenshot bhejein → Gemini Flash (vision) usay analyze karta hai → bot
Urdu/Roman-Urdu me structured analysis + branded signal card (PNG) wapas
bhejta hai. GitHub Actions ke zariye scheduled polling se chalta hai, saath
me ek watchdog jo fail/cancelled runs ko dobara trigger karta hai.

## ⚠️ Zaroori baatein pehle padh lein

1. **Ye "24/7 live" GitHub Actions free tier ki asal limit ke andar hai.**
   GitHub Actions me koi hamesha-chalne-wala process nahi rakha ja sakta —
   ye repo **har ~3 minute me ek naya short run** karta hai (poll → process →
   commit state → exit). Iska matlab worst case me user ko reply milne me
   kuch minute lag sakte hain, turant nahin. Agar aapko **instant** reply
   chahiye, to ek chhota VPS ($4-5/month) par ek continuously-running bot
   (jaise `python-telegram-bot`'s `run_polling()`) is design se behtar hoga.

2. **Trading signals AI-generated hain, guaranteed nahi.** Gemini chart ki
   image dekh kar pattern-matching karta hai — ye asal market data nahi
   padhta, na koi backtested statistical model hai. Confidence % sirf
   Gemini ka apna text estimate hai. Binary options trading high-risk hai;
   bot har message ke sath disclaimer bhejta hai, ise hataayein na.

3. **Apni API key turant revoke/regenerate karein** agar wo kabhi bhi kisi
   chat, screenshot, ya public jagah share hui ho — chahe accidentally hi
   ho. [Google AI Studio](https://aistudio.google.com/apikey) me jaakar
   purani key delete karein aur nayi banayein.

## Setup

### 1. Telegram bot banayein
[@BotFather](https://t.me/BotFather) se `/newbot` — token milega.

### 2. Gemini API key
[Google AI Studio](https://aistudio.google.com/apikey) se nayi key banayein.

### 3. Repo secrets set karein
GitHub repo → Settings → Secrets and variables → Actions → New repository secret:

| Secret name          | Value                          |
|-----------------------|---------------------------------|
| `TELEGRAM_BOT_TOKEN`  | BotFather se mila token         |
| `GEMINI_API_KEY`      | AI Studio se mili key           |

**In dono ko kabhi bhi code me hardcode na karein** — sirf secrets ke
through.

### 4. Actions enable karein
Repo → Settings → Actions → General → "Allow all actions" ON karein, aur
"Read and write permissions" workflow permissions me select karein (state
file commit karne ke liye zaroori hai).

### 5. Pehli run manually trigger karein
Actions tab → "MI NEXUS Bot Poll" → Run workflow. Uske baad ye har ~3 min
apne aap chalega, aur "MI NEXUS Watchdog" har 15 min check karega ke last
run fail to nahi hui.

## Structure

```
bot/
  config.py            # env vars, tuning constants
  storage.py            # JSON-file state/queue persistence + logging
  telegram_api.py        # thin Telegram Bot API wrapper
  gemini_analyzer.py     # Gemini Flash vision call + response parsing
  card_renderer.py       # branded PNG signal card generator
  run.py                 # single-cycle entrypoint (called by workflow)
.github/workflows/
  poll.yml                # scheduled run, every ~3 min
  watchdog.yml            # detects failed runs, re-triggers
data/
  state.json              # last processed Telegram update_id
  queue.json              # pending/failed analysis jobs (retry logic)
```

## Restart / retry logic (kaise kaam karta hai)

- Har run apna kaam **state.json aur queue.json** me save karke khatam
  hota hai, aur commit kar deta hai.
- Agli run **wahi se shuru hoti hai** jahan pichli chhodi thi — koi update
  miss ya duplicate nahi hota.
- Agar koi job (image analyze karna) fail ho jaye, wo **3 dafa retry**
  hoti hai (alag runs me); 3 baar fail hone ke baad user ko error message
  milta hai aur job "failed" list me park ho jati hai (queue.json me
  dikhegi, taake aap debug kar sakein).
- Watchdog workflow har 15 min check karta hai ke poll workflow ka last
  run fail/cancel to nahi hua — agar hua ho to turant dobara trigger karta
  hai.

## Local testing

```bash
export TELEGRAM_BOT_TOKEN="..."
export GEMINI_API_KEY="..."
pip install -r requirements.txt
python -m bot.run
```

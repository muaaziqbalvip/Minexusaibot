# MI NEXUS — Telegram Chart Analysis Bot

Chart screenshot bhejein → Gemini Flash (vision) usay analyze karta hai → bot
Urdu/Roman-Urdu me structured analysis + branded signal card (PNG) wapas
bhejta hai. Bot ek **long-running loop** ke through chalta hai jo GitHub
Actions ke andar ~5h30m tak zinda rehta hai (turant reply deta hai, 5-min
poll wait nahi), phir khud clean-exit karke agli job ko restart karne deta
hai — is tarah continuous "24/7" uptime milti hai.

## ⚠️ Zaroori baatein pehle padh lein

1. **"24/7" yahan ek continuous loop + auto-restart pattern hai, na ke
   ek hamesha-zinda server.** `loop.yml` ek job start karta hai jo andar
   `bot/loop_run.py` chalata hai — ye Telegram ko musalsal long-poll karta
   rehta hai (turant reply), 5h30m tak, phir khud ruk jata hai (GitHub ka
   hard 6-hour job limit takrane se pehle). `watchdog.yml` har 5 min check
   karta hai ke koi loop job `in_progress` hai ya nahi — agar nahi, to
   turant naya start kar deta hai. Is tarah ek job khatam hone aur agli
   shuru hone ke darmiyan sirf chand second ka gap hota hai, ghante nahi.

2. **Gap ka risk zero nahi hai, bohat chhota hai.** Agar ek job crash ho
   jaye (na ke clean exit), agli watchdog check tak (max 5 min) bot down
   reh sakta hai. Agar wahi window me koi image aaye, wo miss nahi hoti —
   agli job start hote hi `last_update_id` se aage se poll karti hai aur
   koi bhi beech me chhoda job (`data/queue.json` ka `pending`) pehle
   resume karti hai.

3. **True zero-gap 24/7** sirf ek dedicated server (VPS) par milta hai
   jahan process kabhi rukta hi nahi. GitHub Actions is design ke sath
   uske bohat qareeb pahunch jata hai, lekin bilkul wahi guarantee nahi
   deta — agar aapke trading use-case ke liye missed 2-3 minutes bhi
   acceptable nahi, VPS behtar rahega.

4. **Trading signals AI-generated hain, guaranteed nahi.** Gemini chart ki
   image dekh kar pattern-matching karta hai — ye asal market data nahi
   padhta, na koi backtested statistical model hai. Confidence % sirf
   Gemini ka apna text estimate hai. Binary options trading high-risk hai;
   bot har message ke sath disclaimer bhejta hai, ise hataayein na.

5. **Apni API key turant revoke/regenerate karein** agar wo kabhi bhi kisi
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
Actions tab → "MI NEXUS Bot Loop" → Run workflow. Uske baad watchdog
(har 5 min check karta hai) is loop ko apne aap zinda rakhega — jab bhi
ek job khatam ho (5h30m baad, ya kisi wajah se crash), agla turant shuru
ho jayega.

## Structure

```
bot/
  config.py            # env vars, tuning constants
  storage.py            # JSON-file state/queue persistence + logging
  telegram_api.py        # thin Telegram Bot API wrapper
  gemini_analyzer.py     # Gemini Flash vision call + response parsing
  card_renderer.py       # branded PNG signal card generator
  loop_run.py             # long-running loop entrypoint (called by loop.yml)
.github/workflows/
  loop.yml                 # long-running job (~5h30m), periodic state commits
  watchdog.yml             # checks every 5 min that a loop job is in_progress;
                             # starts one immediately if not
data/
  state.json              # last processed Telegram update_id
  queue.json              # jobs that permanently failed after 3 retries
```

## Restart logic (kaise kaam karta hai)

- `loop.yml` ek job start karta hai jo `bot/loop_run.py` chalata hai — ye
  process **Telegram ko musalsal long-poll karta rehta hai**, har naya
  image turant process karke reply bhejta hai (5-min wait nahi).
- Har ~60 second me process khud `data/state.json`/`data/queue.json`
  disk par likhta hai; workflow ke andar ek background committer har
  ~90 second me dekh kar in files ko repo me commit+push karta hai — is
  tarah agar job kabhi beech me mar bhi jaye, zyada se zyada ~90s ki
  progress hi risk me hoti hai.
- Process khud **5h30m** ke baad clean-exit ho jata hai (GitHub ka hard
  6-hour job kill hone se pehle), state save karke.
- `watchdog.yml` har 5 min check karta hai ke koi `loop.yml` run abhi
  `in_progress` hai ya nahi. Agar nahi (ya to naturally khatam hua, ya
  crash hua), turant naya run trigger kar deta hai — is tarah continuous
  restart-loop banta hai.
- Agar koi job (image analyze karna) fail ho jaye, wo **usi run ke andar
  3 dafa retry** hoti hai; 3 baar fail hone ke baad user ko error message
  milta hai aur job `data/queue.json`'s `failed` list me park ho jata hai
  (debugging ke liye).
- Agar process kisi wajah se beech me mar jaye jab koi job process ho raha
  ho, wo job agli run ke shuru me automatically resume hoti hai (queue me
  `pending` reh jati hai).

## Local testing

```bash
export TELEGRAM_BOT_TOKEN="..."
export GEMINI_API_KEY="..."
pip install -r requirements.txt
python -m bot.loop_run   # Ctrl+C to stop; runs until MAX_RUNTIME_SECONDS otherwise
```

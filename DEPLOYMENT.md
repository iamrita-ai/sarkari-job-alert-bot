# Deployment Guide

Every deployment option runs the **same code**. The only differences are where
the Python process lives and how you provide environment variables.

- [Option A — PC / laptop terminal (Linux, macOS, WSL, Windows)](#option-a--pc--laptop-terminal)
- [Option B — Termux on an Android phone](#option-b--termux-android-phone)
- [Option C — Cloud Docker (Render / Voroa)](#option-c--cloud-docker-render--voroa)
- [Optional — MongoDB instead of SQLite](#optional--mongodb-atlas-instead-of-sqlite)
- [Troubleshooting](#troubleshooting)

---

## First time, for every option

1. Create the bot: Telegram → **@BotFather** → `/newbot` → copy the token.
2. (Recommended) In BotFather send `/setinline`, pick your bot, and set the
   placeholder to `Search government jobs…` — this enables the `@bot query`
   inline search.
3. Have the token ready: it goes into an environment variable called
   `BOT_TOKEN`.

### About "Telegram serverless"

Telegram itself **does not host bot logic** — there is no Telegram-run server
for your code. A bot always needs *some* process that calls Telegram:

| Where it runs | Stays online when | Best for |
|---|---|---|
| Cloud container (Render/Voroa) | your PC/phone is off | 24×7 production |
| Your PC terminal | the PC is awake | testing / always-on home machine |
| Termux on your phone | the phone is on (battery-friendly) | zero-cost personal hosting |

A *true* serverless design (AWS Lambda / Cloudflare Workers + webhooks) would
require rewriting the long-polling loop into stateless webhook functions. The
three options above cover the same need without that complexity.

---

## Option A — PC / laptop terminal

### Linux / macOS / WSL

```bash
git clone https://github.com/iamrita-ai/sarkari-job-alert-bot.git
cd sarkari-job-alert-bot

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install --retries 5 --timeout 120 -r requirements.txt

cp .env.example .env
nano .env                 # paste BOT_TOKEN, save (Ctrl+O, Enter, Ctrl+X)

python -m bot.main
```

Windows PowerShell (same flow, different venv command):

```powershell
git clone https://github.com/iamrita-ai/sarkari-job-alert-bot.git
cd sarkari-job-alert-bot
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
notepad .env
python -m bot.main
```

### Providing environment variables (three equivalent ways)

1. **`.env` file** (recommended) — `python-dotenv` loads it automatically.
2. Export in the shell (not saved between reboots):
   ```bash
   export BOT_TOKEN="8123456789:AAH..."
   export CHECK_INTERVAL_MINUTES=30
   python -m bot.main
   ```
3. Inline for a single run:
   ```bash
   BOT_TOKEN="8123456789:AAH..." python -m bot.main
   ```

### Run in the background / on boot (Linux)

```bash
# quick background process with logs
nohup python -m bot.main > bot.log 2>&1 &
tail -f bot.log

# proper auto-restart service (systemd):
sudo tee /etc/systemd/system/sarkari-bot.service >/dev/null <<'UNIT'
[Unit]
Description=Sarkari Job Alert Bot
After=network-online.target

[Service]
WorkingDirectory=/home/youruser/sarkari-job-alert-bot
ExecStart=/home/youruser/sarkari-job-alert-bot/.venv/bin/python -m bot.main
EnvironmentFile=/home/youruser/sarkari-job-alert-bot/.env
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable --now sarkari-bot
journalctl -u sarkari-bot -f      # live logs
```

---

## Option B — Termux (Android phone)

> Install Termux from **F-Droid** (the Play Store build is deprecated and
> misses newer Python packages). No root required.

### Automatic setup

```bash
pkg install git -y
git clone https://github.com/iamrita-ai/sarkari-job-alert-bot
cd sarkari-job-alert-bot
bash scripts/termux_setup.sh
```

### Manual step-by-step (what the script does)

```bash
pkg update -y && pkg upgrade -y
pkg install python git -y

git clone https://github.com/iamrita-ai/sarkari-job-alert-bot
cd sarkari-job-alert-bot
python -m venv "$HOME/sarkari-bot-venv"
source "$HOME/sarkari-bot-venv/bin/activate"
pip install --upgrade pip
pip install --retries 5 --timeout 120 -r requirements.txt

cp .env.example .env
nano .env                 # paste BOT_TOKEN; Ctrl+O, Enter, Ctrl+X
python -m bot.main
```

### How to add environment variables in Termux

There is no separate "Telegram serverless" env screen — you have two options:

**Option 1 — `.env` file (recommended).** Edit it with `nano .env`:

```ini
BOT_TOKEN=8123456789:AAH-your-real-token
CHECK_INTERVAL_MINUTES=30
OWNER_USERNAMES=TechnicalSerena,Xioqui_xin
ENABLE_HEALTH_SERVER=false
DATABASE_BACKEND=sqlite
DATABASE_PATH=data/bot.db
```

**Option 2 — shell exports.** Add them to `~/.bashrc` so every Termux session
has them:

```bash
echo 'export BOT_TOKEN="8123456789:AAH-your-real-token"' >> ~/.bashrc
echo 'export ENABLE_HEALTH_SERVER=false' >> ~/.bashrc
source ~/.bashrc
```

Set `ENABLE_HEALTH_SERVER=false` on a phone — the `/health` port is only
needed by cloud platforms. Your SQLite database lives in `~/sarkari-job-alert-bot/data/`.

### Keep it running 24×7 on the phone

```bash
termux-wake-lock                          # stop Android dozing the process
nohup ./start_bot.sh > bot.log 2>&1 &     # after running termux_setup.sh
tail -f bot.log
./stop_bot.sh                             # stop
```

Battery tips: disable battery optimisation for Termux in Android settings, and
keep the phone charged. A single user bot uses negligible data (one small
listing fetch every 30 minutes).

### Auto-start after reboot

```bash
pkg install termux-services termux-boot -y
mkdir -p ~/.termux/boot
cat > ~/.termux/boot/start-sarkari-bot <<'EOF'
#!/data/data/com.termux/files/usr/bin/bash
cd ~/sarkari-job-alert-bot
source ~/sarkari-bot-venv/bin/activate
termux-wake-lock
nohup python -m bot.main > bot.log 2>&1 &
EOF
chmod +x ~/.termux/boot/start-sarkari-bot
```

Open the **Termux:Boot** app once after installing it; the bot then starts on
every phone restart.

---

## Option C — Cloud Docker (Render / Voroa)

The repository already contains `Dockerfile`, `docker-compose.yml` and
`render.yaml`. Short version:

```bash
# self-hosted Docker anywhere
cp .env.example .env       # fill BOT_TOKEN
docker compose up --build -d
docker compose logs -f
```

On Render: **New → Blueprint → select the GitHub repo → add the `BOT_TOKEN`
secret → Deploy**. On Voroa: create a Docker service from the repo, set the
same env vars, and (if offered) attach a persistent volume at `/app/data` so
the SQLite file survives redeploys.

### ⚠️ Only ONE instance per token

Telegram allows exactly one `getUpdates` poller per bot token. Running the bot
in Voroa **and** Termux (or an old container and a new one) causes:

```
telegram.error.Conflict: terminated by other getUpdates request
```

Stop every other instance before starting a new one.

**Since v1.5.1 the bot no longer dies in this situation:** it logs the
conflict, keeps the `/health` endpoint up, retries the polling every 15-300
seconds and sends you a direct message ("Another instance is polling with
this bot token"). As soon as the old instance is stopped, the new one takes
over automatically - no redeploy needed.

> The old service on the platform must be deleted (or at least stopped),
> otherwise the two keep fighting over the same token.

---

## Optional — MongoDB Atlas instead of SQLite

Useful if you run several instances or want data independent of the container
disk. Free 512 MB tier is plenty for this bot.

1. Create a cluster at <https://www.mongodb.com/cloud/atlas> and a database
   user. In **Network Access**, allow `0.0.0.0/0` (or your host's IP range).
2. Copy the connection string (`mongodb+srv://…`).
3. Install the extra driver:
   ```bash
   pip install -r requirements-mongo.txt      # PC/Termux
   # Docker: add "motor" to requirements.txt or build with:
   #   pip install -r requirements.txt -r requirements-mongo.txt
   ```
4. Set the environment variables (in `.env`, your shell, or the cloud dashboard):
   ```ini
   DATABASE_BACKEND=mongodb
   MONGODB_URI=mongodb+srv://USER:PASS@cluster.xxxxx.mongodb.net/?retryWrites=true&w=majority
   MONGODB_DATABASE=sarkari_job_bot
   ```
5. Start normally. The same collections back every feature; switching back is
   one env change (`DATABASE_BACKEND=sqlite`).

For Docker, create a small `Dockerfile.mongo` if you don't want motor in the
default image:

```dockerfile
FROM sarkari-job-alert-bot:latest
RUN pip install --no-cache-dir motor
```

---

## Troubleshooting

| Symptom | Cause & fix |
|---|---|
| `Can't parse entities: character '.' is reserved` | Fixed in v1.3 — update to the latest image. All MarkdownV2 text is now lint-tested. |
| Next / Previous buttons do nothing | Fixed in v1.4 — the browser callbacks were never registered. Pull the latest image (`docker compose pull && docker compose up -d`). |
| A setup button (category / degrees / documents) does nothing | Either the bot restarted (state is persisted now, v1.5) or **a second instance with the same token is eating the updates**. The bot now answers such taps with "session expired" and the owner gets a "duplicate instance" DM — stop every copy except one. |
| The bot feels silent for a whole day | Enable the daily digest (`DIGEST_ENABLED=true`, `DIGEST_HOUR=9`) and the notice-update watch list (`WATCH_JOBS_PER_RUN=4`). |
| Deploy aborted: "we did not see your service listening on any port" | Fixed in v1.5.1 - the `/health` server now starts **before** the Telegram connection and listens on `PORT` plus the fallbacks 8000 / 8080 / 3000. Make sure `ENABLE_HEALTH_SERVER` is not `false`. |
| Crash on shutdown: `TypeError: cannot pickle 'sqlite3.Connection' object` | Fixed in v1.5.1 - the persistence now stores **only** the conversation states; the database and HTTP client in `bot_data` are never pickled. |
| `telegram.error.Conflict: terminated by other getUpdates` | Another instance is using the same token. The bot retries by itself and DMs the owner; stop the old instance. |
| `TypeError: JobQueue.run_daily() got an unexpected keyword argument 'tz'` | Fixed in v1.5.2 - PTB v22 has no `tz` argument. The digest now uses a timezone-aware time object. |
| `RuntimeError: Event loop is closed` | Fixed in v1.5.2 - the polling restart creates a new event loop. |
| `Can't parse entities: character '+' is reserved` | Fixed in v1.5.4 - an unescaped `+` made Telegram reject the whole message (400 Bad Request). Every outgoing MarkdownV2 message is now covered by a lint test. |
| A setup button does nothing when tapped | Fixed in v1.5.3 - the reservation button now works without a live conversation, every tap is confirmed with a toast, and steps fall back to a new message when the old one can no longer be edited. |
| Old users have no degrees/documents after the v1.4 update | Normal — the columns default to empty. Send them `/edit` → Degrees / Documents, or they can tick them from `/start`. |
| `Conflict: terminated by other getUpdates request` | Two instances share the token. Stop the duplicate (cloud service, Termux, old container). |
| `/start` shows an error but scraping works | Redeploy latest commit; the welcome caption bug is fixed and the banner now falls back to text. |
| `original` / `original-jina` show 🟡 *standby* in `/sources` | Expected on cloud IPs (CloudFront blocks datacenter ranges). They are **fallbacks**: the `mirror` source ✅ is primary and the bot works normally. Only a ❌ on `mirror` means a real problem. |
| PyPI `ReadTimeoutError` while building | The Dockerfile retries 5× with a 120 s timeout; rebuild once, or set `PIP_INDEX_URL` to a regional mirror. |
| Bot stops when Termux is swiped away | Run `termux-wake-lock`, disable Android battery optimisation, use the Termux:Boot script. |
| Data lost after cloud redeploy | SQLite is file-based; attach a volume at `/app/data`, or switch to MongoDB. |


---

## Optional v1.5 extras

| Variable | Default | What it does |
|---|---|---|
| `PERSISTENCE_PATH` | `data/conversation.pickle` | Keeps the onboarding conversation alive across restarts |
| `DIGEST_ENABLED` / `DIGEST_HOUR` | `true` / `9` | Daily digest at 09:05 IST (new jobs + jobs closing soon) |
| `WATCH_JOBS_PER_RUN` | `4` | How many live notices are re-checked per cycle for admit card / exam date / extension |
| `WATCH_WINDOW_DAYS` | `21` | How far back the watch list looks |
| `CARD_LANGUAGE` | `both` | `en`, `hi` or `both` (Hindi block under the English card) |
| `GROQ_API_KEY` | *(empty)* | Optional AI summary (free key: https://console.groq.com/keys) |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Which Groq model to use |
| `AI_SUMMARY_ENABLED` | `true` when a key is set | Turn the AI summary on/off |
| `AI_SUMMARY_LANGUAGE` | `en` | Language of the AI summary |
| `BROADCAST_CHANNEL_ID` | *(empty)* | Mirror every new job into your channel (`@your_channel` or `-100…`) |
| `ENABLE_WEB_APP` | `false` | Start the FastAPI dashboard (needs `pip install -r requirements-web.txt`) |
| `WEB_APP_PORT` | `8081` | Port of the dashboard |
| `WEB_APP_SECRET` | *(empty)* | Secret that signs the personal `/webapp` links — generate with `python -c "import secrets;print(secrets.token_urlsafe(32))"` |
| `PUBLIC_BASE_URL` | *(empty)* | Public address of your deployment, used to build dashboard links |

### Groq AI summary (optional)

```bash
# 1. create a free key at https://console.groq.com/keys
# 2. add to .env
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxx
AI_SUMMARY_ENABLED=true
```

Without a key the bot is exactly as before — the original eligibility text is
shown. With a key each card gains a "🧠 In short: …" line (and a Hindi one
when `CARD_LANGUAGE=both`).

### Broadcast channel

1. Create a Telegram channel, add the bot as an **admin** with "post messages".
2. Put the channel id in `.env`:

```bash
BROADCAST_CHANNEL_ID=@your_channel      # or -1001234567890
```

3. Test it with `/channel` (owner only).

### Web dashboard

```bash
pip install -r requirements-web.txt
ENABLE_WEB_APP=true
WEB_APP_SECRET=$(python -c "import secrets;print(secrets.token_urlsafe(32))")
PUBLIC_BASE_URL=https://your-public-domain
```

Every user gets a signed personal link with `/webapp`. The dashboard shows
the latest vacancies (with search + state filter), their saved jobs and a
form to edit name, DOB, category, degrees, documents and sectors.

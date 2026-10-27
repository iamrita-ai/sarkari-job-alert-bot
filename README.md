# 🚨 Sarkari Job Alert Bot

A personalised Telegram bot that scrapes **[SarkariResult.com](https://www.sarkariresult.com/)**
for the latest government job notifications and pushes **instant Telegram
alerts** matched against each user's profile — name, reservation category,
highest qualification and preferred job sectors.

Built with **python-telegram-bot (PTB v21)**, **BeautifulSoup**, **httpx** and
**SQLite**, packaged in Docker so it runs identically on **Render**,
**getvoroa**, a VPS or your laptop.

> 👑 Bot owners: **@TechnicalSerena** & **@Xioqui_xin**

---

## ✨ Features

- 🧑‍💼 **Full user profiles** — guided 4-step setup: name → category (UR / OBC /
  EWS / SC / ST) → qualification → multi-select job sectors
- 🎯 **Smart matching**
  - sector keyword matching on vacancy title + URL slug
  - qualification ranking — a Graduate automatically qualifies for jobs asking
    for 12th/10th pass, but a 10th-pass user is not alerted for degree-only jobs
- 🗂️ **12 job sectors** — Railway, SSC, UPSC, Defence & Police, Banking &
  Insurance, Teaching, State Govt, PSU, Courts, Medical, Clerk/DEO, Apprentice
- 💳 **Rich job cards** — post name, organisation, eligibility, age limit, last
  apply date, user's category and inline buttons for **Full Details**,
  **Apply Online** and the **notification PDF**
- 🔄 **Automatic background checks** every 30 minutes (configurable) via PTB JobQueue
- 🛡️ **No spam** — first deployment bootstraps the existing listing silently;
  every user is notified about a job at most once
- 🌐 **Anti-block design** — browser headers, HTTP/2, retries with back-off and
  an automatic `r.jina.ai` reader fallback when CloudFront returns `403`
- 🗄️ **SQLite storage** — zero external database required; mount a volume to persist
- ➕ **Owner tools** — `/stats`, `/broadcast`, `/scrape_now` (owner-only)
- 🩺 **Health endpoint** (`/health`) so Render/getvoroa can monitor the container
- 🧪 **Unit tests + CI** for every parser and matching rule

---

## 🧠 How it works

```
Telegram users ──/start──► profile conversation ──► SQLite (users table)
                                   ▲
                                   │ read preferences
PTB JobQueue (every N min)
      │
      ├─ 1. GET sarkariresult.com/latestjob/  (httpx, browser fingerprint)
      │        └─ fallback: r.jina.ai reader proxy on 403
      ├─ 2. Parse listing → new JobSummary rows (jobs table)
      ├─ 3. For jobs someone subscribes to: fetch detail page
      │        → eligibility, age limit, apply link, PDF link
      ├─ 4. Match sector + qualification against every active user
      └─ 5. Send formatted card, log it (notifications table)
```

---

## 🤖 Bot commands

| Command | Purpose |
|---|---|
| `/start` | Create your profile (or view it if already registered) |
| `/profile` | Show saved preferences |
| `/edit` | Update name / category / qualification / sectors |
| `/latest` | Fetch currently matching jobs on demand |
| `/pause` / `/resume` | Stop / restart automatic alerts |
| `/help` / `/about` | Usage guide and bot credits |
| `/stats` | 👑 Owners — user/job/alert statistics |
| `/broadcast <text>` | 👑 Owners — message all active users |
| `/scrape_now` | 👑 Owners — trigger a scrape cycle immediately |

---

## 📁 Project structure

```
sarkari-job-alert-bot/
├── bot/
│   ├── config.py       # all settings from environment variables
│   ├── constants.py    # categories, qualification levels, sector keywords
│   ├── models.py       # JobSummary, JobDetail, UserProfile dataclasses
│   ├── db.py           # async SQLite layer (users / jobs / notifications)
│   ├── scraper.py      # httpx fetcher + HTML/Markdown parsers (one file to fix if the site changes)
│   ├── matcher.py      # sector & qualification matching
│   ├── cards.py        # Telegram message cards
│   ├── keyboards.py    # inline keyboards
│   ├── handlers.py     # commands, profile conversation, menus, admin tools
│   ├── scheduler.py    # periodic scrape → match → notify pipeline
│   ├── health.py       # /health HTTP server
│   └── main.py         # entry point
├── tests/              # offline parser & matcher tests (pytest)
├── scripts/github_push.sh
├── Dockerfile
├── docker-compose.yml
├── render.yaml
├── requirements.txt
├── .env.example
└── LICENSE
```

---

## 🚀 Local development

### 1. Create the bot token

1. Open Telegram, search **@BotFather**
2. Send `/newbot`, choose a name and username
3. Copy the token (looks like `8123456789:AAH...`)

### 2. Install & configure

```bash
git clone https://github.com/<your-user>/sarkari-job-alert-bot.git
cd sarkari-job-alert-bot

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# edit .env and paste your BOT_TOKEN
```

### 3. Run

```bash
python -m bot.main
```

Open your bot in Telegram and send `/start`.

### 4. Run the tests

```bash
pip install pytest
pytest -q
```

---

## 🐳 Docker

```bash
cp .env.example .env      # fill BOT_TOKEN
docker compose up --build
```

The SQLite database lives in the named volume `sarkari_job_data` mounted at
`/app/data`, so it survives container rebuilds.

Plain Docker without compose:

```bash
docker build -t sarkari-job-alert-bot .
docker run -d --name sarkari-bot \
  --env-file .env \
  -p 8080:8080 \
  -v sarkari_job_data:/app/data \
  sarkari-job-alert-bot
```

---

## ☁️ Deploy on Render

### Option A — Blueprint (recommended)

1. Push this repo to GitHub (see below).
2. Render dashboard → **New → Blueprint** → select the repository.
3. `render.yaml` wires the Docker service and `/health` check automatically.
4. Add the secret env var **`BOT_TOKEN`** (and optionally `JINA_API_KEY`).
5. Deploy. The bot starts polling Telegram; logs show each scrape cycle.

### Option B — Manual

**New → Web Service → Connect repo → Runtime: Docker**

| Setting | Value |
|---|---|
| Health check path | `/health` |
| Env: `BOT_TOKEN` | token from @BotFather |
| Env: `OWNER_USERNAMES` | `TechnicalSerena,Xioqui_xin` |
| Env: `CHECK_INTERVAL_MINUTES` | `30` |

> ⚠️ **Persistence note:** Render's free tier has an ephemeral filesystem — the
> SQLite database resets on redeploy (the bot re-bootstraps safely without
> spamming, but users would need to `/start` again). For production, use a paid
> instance and attach a **1 GB disk mounted at `/app/data`**.

---

## 🟣 Deploy on getvoroa

1. Push the repo to GitHub (getvoroa deploys from Git).
2. Create a new **Docker service** using the included `Dockerfile`.
3. Set the environment variables from `.env.example` (minimum: `BOT_TOKEN`).
4. Expose the container port (`8080`) and use `/health` as the health check.
5. Attach a **persistent volume at `/app/data`** for the SQLite database.
6. Deploy — logs will show `Sarkari Job Alert Bot starting`.

---

## ⚙️ Environment variables

| Variable | Default | Description |
|---|---|---|
| `BOT_TOKEN` | — | **Required.** Telegram token from @BotFather |
| `CHECK_INTERVAL_MINUTES` | `30` | Delay between automatic scrape cycles |
| `OWNER_USERNAMES` | `TechnicalSerena,Xioqui_xin` | Comma-separated admin usernames (no `@`) |
| `DATABASE_PATH` | `data/bot.db` | SQLite file location |
| `ENABLE_HEALTH_SERVER` | `true` | Serve `/health` on `PORT` |
| `PORT` | `8080` | Health-server port (Render sets this automatically) |
| `USE_JINA_FALLBACK` | `true` | Use reader proxy if the site blocks the server IP |
| `JINA_API_KEY` | — | Optional key for higher r.jina.ai rate limits |
| `MAX_DETAIL_FETCHES_PER_RUN` | `8` | Detail pages fetched per cycle (politeness cap) |
| `REQUEST_DELAY_SECONDS` | `2` | Pause between detail-page requests |
| `LISTING_URLS` | latestjob page | Comma-separated source pages |
| `HTTPS_PROXY` | — | Standard env var; httpx uses it automatically if needed |

---

## 🌐 About the scraping

- The bot identifies vacancy links by their URL pattern
  (`sarkariresult.com/<section>/<slug>/`) and parses the listing page
  defensively — section/navigation links are filtered out.
- Detail pages are fetched only for jobs that match at least one subscriber,
  are rate-limited and cached in the database.
- Sarkari Result sits behind **CloudFront** and may return `403` to datacenter
  IPs. The scraper retries with back-off and then automatically routes through
  the `r.jina.ai` reader (set `JINA_API_KEY` for reliable limits). You can also
  supply `HTTPS_PROXY` to route requests through a residential proxy.
- If the site changes its markup, all selectors are isolated in
  **`bot/scraper.py`** — update that one module and extend the fixtures under
  `tests/fixtures/` to lock the new behaviour.

### Legal / etiquette

This project is for **educational and personal use**. Respect
SarkariResult.com's terms of service and robots policy, keep the request
interval polite (the default 30-minute cycle is), and always verify details on
the official notification before applying. The bot is not affiliated with
SarkariResult.com.

---

## 🔧 Pushing to your GitHub account

The repo includes a helper that creates a **public** repository and pushes
everything in one shot. Create a token at
<https://github.com/settings/tokens> (classic token with `repo` scope), then:

```bash
export GITHUB_USER="your-github-username"
export GITHUB_TOKEN="ghp_your_token"
./scripts/github_push.sh
# -> https://github.com/your-github-username/sarkari-job-alert-bot
```

Alternatively, create an empty public repo in the GitHub UI and:

```bash
git init --initial-branch=main
git add . && git commit -m "Initial commit: Sarkari Job Alert Telegram bot"
git remote add origin https://github.com/<your-user>/sarkari-job-alert-bot.git
git push -u origin main
```

---

## 📜 License

MIT © TechnicalSerena & Xioqui_xin

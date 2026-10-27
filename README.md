# 🚨 Sarkari Job Alert Bot

A personalised Telegram bot that scrapes **[SarkariResult.com](https://www.sarkariresult.com/)**
for the latest government job notifications and pushes **instant Telegram
alerts** matched against each user's profile — name, reservation category,
highest qualification and preferred job sectors.

Built with **python-telegram-bot (PTB v22)**, **BeautifulSoup**, **httpx** and
**SQLite**, packaged in Docker so it runs identically on **Render**,
**Voroa / getvoroa**, a VPS or your laptop.

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
- 🌐 **Anti-block multi-source design** — primary source is the CloudFront-free
  mirror `sarkariresult.com.cm`; the original site and an `r.jina.ai` reader are
  automatic fallbacks. Browser headers, HTTP/2, retries with back-off, and
  CloudFront error pages are detected instead of silently returning zero jobs
- 🚨 **Owner outage alerts** — if every source fails twice in a row, owners get
  a Telegram DM (rate-limited); `/sources` runs a live connectivity diagnostic
- 🗄️ **SQLite storage** — zero external database required; mount a volume to persist
- ➕ **Owner tools** — `/stats`, `/broadcast`, `/scrape_now`, `/sources` (owner-only)
- 🩺 **Health endpoint** (`/health`) with live scraper status for Render/Voroa
- 🛡️ **Production hardening** — global error handler, overlap-safe scheduler,
  bootstrap protection against mass-notifications on deploy
- 🎨 **Colour-coded emoji buttons** (see the note on Telegram's button limits below)
- 🧪 **Unit tests + CI** for every parser and matching rule

---

## 🧠 How it works

```
Telegram users ──/start──► profile conversation ──► SQLite (users table)
                                   ▲
                                   │ read preferences
PTB JobQueue (every N min)
      │
      ├─ 1. Source chain until one returns jobs:
      │       sarkariresult.com.cm/latest-jobs/  (mirror, direct HTML)
      │    → www.sarkariresult.com/latestjob/    (original, direct)
      │    → r.jina.ai reader proxy              (last resort)
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
| `/sources` | 👑 Owners — live health check of every scraping source |

### 🎨 About "coloured" inline buttons

Telegram's Bot API **does not allow custom button colours** — every inline
button renders in the user's own Telegram theme. The standard production
approach (used here) is colour-coded emoji prefixes so options are instantly
scannable: 🟢🔵🟡🟣🟠 for categories, one unique emoji per job sector
(🚆 📋 🏛️ 🛡️ 🏦 👨‍🏫 🏢 ⚙️ ⚖️ 🏥 💻 🔧), and ✅/⬜ selection states.

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
| `MIRROR_BASE_URL` | `https://sarkariresult.com.cm` | Primary CloudFront-free mirror |
| `MIRROR_LISTING_PATH` | `/latest-jobs/` | Mirror listing page |
| `ORIGINAL_BASE_URL` | `https://www.sarkariresult.com` | Original site (backup) |
| `ORIGINAL_LISTING_PATH` | `/latestjob/` | Original listing page |
| `SOURCE_ORDER` | `mirror,original,original-jina` | Failover order for data sources |
| `USE_JINA_FALLBACK` | `true` | Allow the reader-proxy last resort |
| `JINA_API_KEY` | — | Optional key for higher r.jina.ai rate limits |
| `MAX_DETAIL_FETCHES_PER_RUN` | `8` | Detail pages fetched per cycle (politeness cap) |
| `REQUEST_DELAY_SECONDS` | `2` | Pause between detail-page requests |
| `HTTPS_PROXY` | — | Standard env var; httpx uses it automatically if needed |

---

## 🌐 About the scraping

### Why a source chain?

The original **www.sarkariresult.com** sits behind **CloudFront** and returns
`403 Request blocked` to most cloud-server IPs (Render, Voroa, AWS, …). The
reader proxy `r.jina.ai` is blocked by the same CloudFront distribution today,
so relying on either of those from a hosting provider yields **zero jobs**.

The bot therefore uses this ordered chain (configurable via `SOURCE_ORDER`):

1. **`mirror` — `sarkariresult.com.cm`** (default primary). A WordPress mirror
   publishing the same notifications, **not behind CloudFront**, with an
   explicit `robots.txt` allowing all crawlers. Listing: `/latest-jobs/`,
   vacancy pages: `/<slug>/`. Verified to return ~100 live vacancies from
   cloud hosts.
2. **`original` — `www.sarkariresult.com`** direct request. Works from
   residential IPs / local machines; kept for development and as a backup.
3. **`original-jina`** — the original site through `r.jina.ai`. Last resort;
   CloudFront error pages are detected and raised as failures instead of being
   treated as empty successes.

### Parser design

- Vacancy links are identified by URL pattern; navigation, section and social
  links are filtered out, and each source has its own parser.
- Detail pages are fetched only for jobs matching at least one subscriber,
  rate-limited (`REQUEST_DELAY_SECONDS`) and cached in the database.
- Apply-portal and PDF links are extracted from the "Apply Online Link"
  section; PDFs are recognised even when the URL does not end in `.pdf`.
- If a site changes its markup, every selector is isolated in
  **`bot/scraper.py`** — update that one module and extend the saved fixtures
  under `tests/fixtures/` to lock the new behaviour.
- A residential/rotating proxy can be supplied via the standard `HTTPS_PROXY`
  environment variable; httpx honours it automatically.

### Legal / etiquette

This project is for **educational and personal use**. Respect each site's
terms of service and robots policy, keep the request interval polite (the
default 30-minute cycle is), and always verify details on the official
notification before applying. The bot is not affiliated with SarkariResult.com
or sarkariresult.com.cm.

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

# 🚨 Sarkari Job Alert Bot

A personalised Telegram bot that scrapes **[SarkariResult.com](https://www.sarkariresult.com/)**
for the latest government job notifications and pushes **instant Telegram
alerts** matched against each user's profile — name, reservation category,
degrees, documents on hand and preferred job sectors.

Built with **python-telegram-bot (PTB v22)**, **BeautifulSoup**, **httpx** and
**SQLite**, packaged in Docker so it runs identically on **Render**,
**Voroa / getvoroa**, a VPS or your laptop.

> 👑 Bot owners: **@TechnicalSerena** & **@Xioqui_xin**

---

## ✨ Features

- 🧑‍💼 **Full user profiles** — guided 6-step setup: name → **date of birth** →
  category (UR / OBC / EWS / SC / ST) → **multi-select degrees** →
  **multi-select documents** → multi-select job sectors. `/edit` opens a menu
  where any single section can be changed without redoing the whole flow
- 🎓 **Multi-degree matching** — tick *every* degree you hold (ITI **and**
  B.Ed, B.Sc **and** M.Com …). A notice asking for one of them matches you even
  when the generic rank scale would say "too low"
- 📎 **Document readiness** — mark the papers you own; each job card then
  shows ✅ / ❌ for every document that notice asks for, so nothing is missed
  at the document counter
- 🎯 **Smart matching on three dimensions**
  - sector keyword matching on vacancy title + URL slug
  - qualification ranking — a Graduate automatically qualifies for jobs asking
    for 12th/10th pass, but a 10th-pass user is not alerted for degree-only jobs
  - **age matching** — the DOB is turned into an age and checked against each
    post's min/max age with the standard GoI category relaxation (OBC/EWS +3,
    SC/ST +5); the card explains the decision
- 🗂️ **12 job sectors** — Railway, SSC, UPSC, Defence & Police, Banking &
  Insurance, Teaching, State Govt, PSU, Courts, Medical, Clerk/DEO, Apprentice
- 🖼️ **Rich MarkdownV2 job cards with images** — job name (hyperlink),
  organisation, notification date, **total posts**, selection process, the
  **complete qualification text**, **salary/pay**, **application fee**, age
  limit (plus your age & relaxation) and the full **important-dates block**
  (apply start date, apply last date, fee-payment last date, correction
  window, exam date, admit card, result date). A **📃 Full Notification Text**
  button sends the entire notice (qualification + dates + how to apply) in
  safe chunks — nothing is lost to the 4096-character limit. Alerts are sent
  as photo captions when the vacancy image is available, falling back to text
  automatically
- 🎨 **Genuinely coloured inline buttons** — Bot API `style` (PTB 22.7+):
  blue `primary`, green `success` (Apply / Done), red `danger` (Pause / last-date)
- 📄 **Paginated browsing** — `/latest` and `/scrape_now` render clean
  **Previous / Next** browsers; each job title is a deep link that reopens the
  full card (with Save / Reminder / Apply) inside the bot *(the browser
  callbacks were re-registered in v1.4 — Next/Previous now respond again)*
- 👑 **Owner subscriber browser** — `/users` lists every subscriber with their
  category, degrees and sectors; tapping a name opens that person's full
  profile (degrees, documents, saved jobs) plus a **💬 Open Chat** button
- 🔍 **Inline mode** — type `@your_bot <keyword>` in any chat, pick a result and
  it posts the job card; an *Open in Bot* deep link reopens it inside the bot DM
- 🔖 **Save jobs & set date reminders** — bookmark any vacancy, then get a
  one-tap reminder (1 day / 3 days before / on last date, or a custom date at
  9:00 AM IST); reminders survive restarts and are managed under `/saved`
- 📬 **Never silent** — three new proactive loops:
  - **🔁 Notice updates**: the bot re-checks live notices and alerts the
    people who already got that job when the **admit card is published**, the
    **exam date is fixed** or the **last date is extended**;
  - **☀️ Daily digest** every morning at 09:05 IST — yesterday's new
    matching jobs plus the saved jobs closing within three days;
  - **📢 Channel mirror**: every new vacancy is also posted to your own
    Telegram channel (`BROADCAST_CHANNEL_ID`)
- 🧠 **Optional AI summary** (Groq, free tier) — the long eligibility text is
  turned into three plain lines ("🧠 In short: …"), optionally in Hindi.
  Completely optional: without a key the bot shows the original text
- 🇮🇳 **Hindi + English cards** — the same notification in both languages
  (`CARD_LANGUAGE=both`)
- 👥 **Category-wise vacancy breakdown** — "General 542 · OBC 296 · SC 176"
  with the user's own category marked
- 📍 **State filters** — `/latest bihar`, `/latest "uttar pradesh"`, and a
  state filter in the web dashboard
- 🌐 **Web dashboard** (optional FastAPI app) — a phone-friendly page to
  edit degrees/documents and browse vacancies with filters; every user gets
  a signed personal link via `/webapp`
- 🧩 **Robust conversations** — the onboarding state is persisted, so a
  button pressed after a restart still works; a tap that arrives without a
  live session is answered with a "session expired" message instead of
  silence; duplicate instances now trigger an owner alert
- 🏁 **Welcome banner image** on `/start`
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
- ➕ **Owner tools** — `/stats`, `/broadcast`, `/scrape_now` (lists every
  catalogued job in a browser), `/sources` (owner-only)
- 🩺 **Health endpoint** (`/health`) with live scraper status for Render/Voroa
- 🛡️ **Production hardening** — global error handler, overlap-safe scheduler,
  bootstrap protection against mass-notifications on deploy
- 🧪 **74 unit tests + CI** for parsers, MarkdownV2 cards, age rules, degrees,
  documents, coloured buttons and storage

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
      │        → eligibility, age limits, fee, salary, image, apply/PDF links
      ├─ 4. Match sector + degrees + qualification + age per user
      └─ 5. Send photo card with coloured Apply button, log notification;
             users can bookmark the job or schedule a date reminder
```

---

## 🤖 Bot commands

| Command | Purpose |
|---|---|
| `/start` | Welcome banner, deep-link job cards, create/view profile |
| `/profile` | Show saved preferences (incl. D.O.B and computed age) |
| `/edit` | Profile menu — change name, D.O.B, category, degrees, documents or sectors |
| `/latest` | Browse matching jobs with Next / Previous pagination |
| `/saved` | Bookmarked jobs and your active date reminders |
| `/pause` / `/resume` | Stop / restart automatic alerts |
| `/help` / `/about` | Usage guide and bot credits |
| `@bot <keyword>` | Inline search from any chat (enable via BotFather `/setinline`) |
| `/stats` | 👑 Owners — user/job/alert statistics |
| `/broadcast <text>` | 👑 Owners — message all active users |
| `/scrape_now` | 👑 Owners — run a cycle, then browse all catalogued jobs |
| `/sources` | 👑 Owners — live health check of every scraping source |
| `/users` | 👑 Owners — browse every subscriber and open their profile |
| `/webapp` | Open your personal web dashboard (if enabled) |
| `/latest <state>` | Browse matching jobs of one state (`/latest bihar`) |
| `/digest` | 👑 Owners — preview the daily digest |
| `/channel` | 👑 Owners — post a test message to the broadcast channel |

### 📰 What exactly is "Sarkari Result"? (and what it is *not*)

**sarkariresult.com is not a government website.** It is an **independent
job-aggregator site** that re-publishes the official recruitment
notifications of Indian public bodies (Railway, SSC, UPSC, BPSC, UPSSSC,
PSUs…) into one feed — with the extras people actually search for: last date,
age limit, fee, vacancy table and an "apply online" link.

* The **official application always happens on the government body's own
  portal.** Sarkari Result only aggregates and links to it. That is why
  every card carries an **🏛 Official Website** and **📄 Notification PDF**
  link and why the footer repeats the disclaimer.
* Because it is a WordPress blog it changes its markup often and sits behind
  **CloudFront**, which blocks most datacenter IPs (Render, Voroa, VPS…).
* That is exactly why the bot runs a **source chain** — three ways of reading
  *the same* website, tried in order until one answers:

| # | Source | What it is | Why |
|---|---|---|---|
| 1 | `sarkariresult.com.cm` | **The mirror** — an independent copy of the same blog | Not behind CloudFront → works from cloud hosts (primary) |
| 2 | `www.sarkariresult.com` | **The original site** | Direct read, works from residential IPs |
| 3 | `r.jina.ai` reader | **A text-extraction proxy** for the original | Last resort when the original blocks us |

So `/sources` does **not** list three different job boards — it lists three
*readers of one site*. All of them publish the same notifications; the bot
uses the first that answers. A 🟡 *standby* on a fallback is normal and
harmless: only a ❌ on **mirror** means a real problem.

### 🎨 Coloured inline buttons

Since Bot API 9.x (PTB 22.7+, Telegram clients released after 9 Feb 2026)
inline buttons accept a **`style`** parameter:

- `primary` → **blue** (navigation, details)
- `success` → **green** (Apply Online, Save Profile, Resume)
- `danger` → **red** (Pause, last-date actions)

Older Telegram clients simply render the same buttons without colour, so
nothing breaks. Colour-coded emoji (🟢🔵🟡🟣🟠 categories, one unique emoji per
sector, ✅/⬜ selection states) are kept alongside for extra scannability.

### 🔍 Inline mode & deep links

Enable inline mode for the bot via **@BotFather → /setinline** (pick a placeholder
like `Search government jobs…`). Users can then type `@your_bot railway` in any
chat, choose a result, and the formatted job card is posted there. Every result
also carries an *Open in Bot* button using a `/start` deep-link payload, so the
same card opens inside the bot DM with Save / Reminder actions.

---

## 📁 Project structure

```
sarkari-job-alert-bot/
├── bot/
│   ├── config.py       # all settings from environment variables
│   ├── constants.py    # categories, degrees, documents, sectors, states
│   ├── models.py       # JobSummary, JobDetail, UserProfile, SavedJob dataclasses
│   ├── db.py           # async SQLite (users / jobs / notifications / bookmarks)
│   ├── scraper.py      # httpx fetcher + mirror/original parsers (one file to fix)
│   ├── matcher.py      # sector, qualification & age (with relaxation) matching
│   ├── cards.py        # MarkdownV2 cards + 1024-char photo captions
│   ├── keyboards.py    # coloured inline keyboards (primary/success/danger)
│   ├── browser.py      # paginated Next/Previous job browsers
│   ├── digest.py       # daily 09:05 IST digest
│   ├── ai.py           # optional Groq summaries (never required)
│   ├── webapp.py       # optional FastAPI dashboard + signed links
│   ├── inline.py       # inline-mode search + deep-link cards
│   ├── reminders.py    # save jobs, date reminders, JobQueue re-arming
│   ├── handlers.py     # commands, 6-step profile conversation, edit menu, admin
│   ├── scheduler.py    # periodic scrape → match → photo/text notify pipeline
│   ├── storage_mongo.py # optional MongoDB backend (same interface as db.py)
│   ├── health.py       # /health HTTP server
│   ├── utils.py        # MarkdownV2 escaping, DOB/age maths, deep-link codec
│   └── main.py         # entry point
├── assets/
│   └── start_banner.jpg
├── scripts/
│   ├── github_push.sh  # create + push the GitHub repo
│   └── termux_setup.sh # one-shot Termux/Android setup
├── DEPLOYMENT.md       # PC, Termux, Docker, MongoDB Atlas guides
├── tests/              # 74 offline tests (parsers, MD lint, age, degrees, storage,
│   │                    # dispatch, v1.5 features, web dashboard)
├── scripts/github_push.sh
├── Dockerfile
├── docker-compose.yml
├── render.yaml
├── requirements.txt
├── .env.example
└── LICENSE
```

### 📦 Release notes

- **v1.5.3** — the setup buttons can no longer die silently: the reservation
  (category) button also works **without** a live conversation (old keyboard,
  after a redeploy) - it then resumes the profile instead of showing
  "session expired"; every tap gets a visible toast; steps that cannot edit
  an old message (Telegram blocks edits after 48 h) fall back to a fresh
  message; and the error handler answers the button instead of leaving a
  spinning loader
- **v1.5.2** — the two bugs that kept the bot offline: `JobQueue.run_daily()`
  has **no** `tz` argument in PTB v22 (the digest job now uses a timezone-aware
  `time` object + `Defaults(tzinfo=Asia/Kolkata)`), and the polling restart now
  creates a **fresh event loop** (PTB closes the old one, so every retry died
  with "Event loop is closed"). The owner warning for a duplicate instance now
  fires on the very first conflict as well.
- **v1.5.1** — deployment hotfix: the persistence now stores only the
  conversation states (the SQLite connection in `bot_data` could not be
  pickled and killed the service on shutdown), the `/health` endpoint starts
  **before** the Telegram connection and listens on `PORT` + 8000/8080/3000,
  and the bot survives a duplicate instance (409) by retrying with back-off
  and DM-ing the owner instead of dying
- **v1.5** — never-silent bot: admit-card / exam-date / last-date-extension
  update alerts, daily 09:05 IST digest, broadcast-channel mirror, optional
  Groq AI summaries, Hindi + English cards, category-wise vacancy breakdown,
  state filters, optional FastAPI dashboard, persisted conversations and an
  anti-silence fallback for orphaned buttons
- **v1.4** — full notification cards (start/last date, full qualification,
  total posts, selection process, documents), multi-select degrees & documents
  with document-aware matching, `/edit` profile menu, owner `/users` browser,
  every inline button coloured, browser Next/Previous callbacks fixed,
  `/sources` now reports blocked fallbacks as *standby* instead of failure
- **v1.3** — strict MarkdownV2 linting (fixes the `/start` parse-entity crash),
  banner text fallback, Previous/Next-only browsers with bot deep-link titles,
  graceful 409 conflict handling, optional MongoDB backend, Termux + PC
  terminal deployment guides
- **v1.2** — DOB + age matching with category relaxation, coloured `style`
  buttons, MarkdownV2 cards with salary/fee/image, inline mode, paginated
  browsers, save & reminder system, welcome banner, PTB v22.8
- **v1.1** — multi-source scraper (mirror-first), owner outage alerts,
  `/sources`, global error handler
- **v1.0** — initial PTB bot, profile onboarding, sector/qualification matching

---

## 🚀 Quick start (PC terminal)

```bash
git clone https://github.com/iamrita-ai/sarkari-job-alert-bot.git
cd sarkari-job-alert-bot

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env               # paste BOT_TOKEN from @BotFather
python -m bot.main
```

Then open your bot in Telegram and send `/start`.

### 📱 Termux (Android), systemd, Docker & MongoDB

**Full step-by-step guides live in [DEPLOYMENT.md](DEPLOYMENT.md):**

- PC terminal on Linux / macOS / WSL / Windows (+ background systemd service)
- Termux on Android: install, env vars, 24×7 background, reboot auto-start
- Render / Voroa Docker deploys and the single-instance token rule
- Optional **MongoDB Atlas** backend (`DATABASE_BACKEND=mongodb`)
- Troubleshooting table (409 conflict, parse-entity errors, timeouts…)

### Run the tests

```bash
pip install pytest
pytest -q        # 74 tests: parsers, MarkdownV2 lint, age rules, storage, keyboards,
                 # dispatch flow, v1.5 features, web dashboard
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
| `DATABASE_BACKEND` | `sqlite` | `sqlite` or `mongodb` (Mongo needs requirements-mongo.txt) |
| `DATABASE_PATH` | `data/bot.db` | SQLite file location |
| `MONGODB_URI` | — | Atlas/self-hosted Mongo connection string when backend=mongodb |
| `MONGODB_DATABASE` | `sarkari_job_bot` | Mongo database name |
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

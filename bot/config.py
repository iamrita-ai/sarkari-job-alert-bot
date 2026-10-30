"""Central configuration - every setting is read from environment variables.

A local ``.env`` file is loaded automatically during development.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


def _get_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


# --- Telegram -------------------------------------------------------------
# The product name shown in the bot (brand: SERENA / Technical Serena)
BRAND_NAME: str = os.getenv("BRAND_NAME", "SERENA").strip()
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "").strip()
OWNER_USERNAMES: set[str] = {
    u.strip().lstrip("@").lower()
    for u in os.getenv("OWNER_USERNAMES", "TechnicalSerena,Xioqui_xin").split(",")
    if u.strip()
}

# --- Scheduler ------------------------------------------------------------
CHECK_INTERVAL_MINUTES: float = float(os.getenv("CHECK_INTERVAL_MINUTES", "30"))

# --- Storage --------------------------------------------------------------
# "sqlite" (default, zero setup) or "mongodb" (needs requirements-mongo.txt)
DATABASE_BACKEND: str = os.getenv("DATABASE_BACKEND", "sqlite").strip().lower()
DATABASE_PATH: str = os.getenv("DATABASE_PATH", str(BASE_DIR / "data" / "bot.db"))
Path(DATABASE_PATH).parent.mkdir(parents=True, exist_ok=True)
MONGODB_URI: str = os.getenv("MONGODB_URI", "").strip()
MONGODB_DATABASE: str = os.getenv("MONGODB_DATABASE", "sarkari_job_bot").strip()

# --- Conversation persistence -------------------------------------------
# Keeps the onboarding conversation alive across restarts (a restart used to
# turn every pending button press into a no-op). Set to "" to disable.
PERSISTENCE_PATH: str = os.getenv(
    "PERSISTENCE_PATH", str(BASE_DIR / "data" / "conversation.pickle")
)

# --- Broadcast channel (optional) ---------------------------------------
# Every new job is also posted to this channel (@your_channel or
# -1001234567890). Leave empty to disable.
BROADCAST_CHANNEL_ID: str = os.getenv("BROADCAST_CHANNEL_ID", "").strip()

# --- Optional AI summary (Groq) -----------------------------------------
# Free tier: https://console.groq.com - turns the long eligibility text into
# three plain lines (and optionally Hindi). Without a key the bot simply
# shows the original text.
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
AI_SUMMARY_ENABLED: bool = _get_bool("AI_SUMMARY_ENABLED", bool(GROQ_API_KEY))
AI_SUMMARY_LANGUAGE: str = os.getenv("AI_SUMMARY_LANGUAGE", "en").strip().lower()
# Card language: "en", "hi" or "both" (Hindi block under the English card)
CARD_LANGUAGE: str = os.getenv("CARD_LANGUAGE", "both").strip().lower()

# --- Hosting port (Render / getvoroa / Voroa) ---------------------------
# The platform probes this port - it is the only port the public URL reaches.
PORT: int = int(os.getenv("PORT", "8080"))

# --- Web app (optional FastAPI dashboard) -------------------------------
ENABLE_WEB_APP: bool = _get_bool("ENABLE_WEB_APP", False)
# The dashboard listens on WEB_APP_PORT when it is set explicitly. Otherwise
# it listens on the platform port (PORT), because that is the only port the
# public URL (PUBLIC_BASE_URL) reaches.
WEB_APP_PORT: int = int(os.getenv("WEB_APP_PORT", "") or PORT)
# Secret used to sign per-user links (/webapp). Generate with:
#   python -c "import secrets; print(secrets.token_urlsafe(32))"
WEB_APP_SECRET: str = os.getenv("WEB_APP_SECRET", "").strip()
# Public address of this deployment (used for the dashboard links).
PUBLIC_BASE_URL: str = os.getenv(
    "PUBLIC_BASE_URL", os.getenv("RENDER_EXTERNAL_URL", "")
).strip()

# --- Digests & watch list ------------------------------------------------
# Daily digest time (IST) - "today's new jobs + jobs closing soon".
DIGEST_HOUR: int = int(os.getenv("DIGEST_HOUR", "9"))
DIGEST_ENABLED: bool = _get_bool("DIGEST_ENABLED", True)
# How many catalogued jobs are re-checked per cycle for admit-card / exam
# date / last-date-extension changes.
WATCH_JOBS_PER_RUN: int = int(os.getenv("WATCH_JOBS_PER_RUN", "4"))
WATCH_WINDOW_DAYS: int = int(os.getenv("WATCH_WINDOW_DAYS", "21"))

# --- Health-check server (Render / getvoroa / Voroa) ----------------------
ENABLE_HEALTH_SERVER: bool = _get_bool("ENABLE_HEALTH_SERVER", True)

# --------------------------------------------------------------- data sources
# The original www.sarkariresult.com sits behind CloudFront and blocks most
# datacenter IPs. This WordPress mirror is not behind CloudFront and publishes
# the same notifications, so it is the primary production source.
MIRROR_BASE_URL: str = os.getenv(
    "MIRROR_BASE_URL", "https://sarkariresult.com.cm"
).rstrip("/")
MIRROR_LISTING_PATH: str = os.getenv("MIRROR_LISTING_PATH", "/latest-jobs/")

ORIGINAL_BASE_URL: str = os.getenv(
    "ORIGINAL_BASE_URL", "https://www.sarkariresult.com"
).rstrip("/")
ORIGINAL_LISTING_PATH: str = os.getenv("ORIGINAL_LISTING_PATH", "/latestjob/")

# Comma-separated source chain, tried in order until one returns jobs.
#   mirror          -> sarkariresult.com.cm (direct HTML, works on cloud hosts)
#   original        -> www.sarkariresult.com direct (works on residential IPs)
#   original-jina   -> www.sarkariresult.com via r.jina.ai reader (last resort)
# Section pages of the mirror (used by /admit and /result)
MIRROR_ADMIT_CARD_PATH: str = os.getenv("MIRROR_ADMIT_CARD_PATH", "/admit-card/")
MIRROR_RESULT_PATH: str = os.getenv("MIRROR_RESULT_PATH", "/result/")

SOURCE_ORDER: list[str] = [
    s.strip()
    for s in os.getenv(
        "SOURCE_ORDER", "mirror,mirror-jina,original,original-jina"
    ).split(",")
    if s.strip()
]

# Reader proxy used when the source site blocks the host IP
USE_JINA_FALLBACK: bool = _get_bool("USE_JINA_FALLBACK", True)
JINA_API_KEY: str = os.getenv("JINA_API_KEY", "").strip()

# Politeness / safety limits
MAX_DETAIL_FETCHES_PER_RUN: int = int(os.getenv("MAX_DETAIL_FETCHES_PER_RUN", "8"))
REQUEST_DELAY_SECONDS: float = float(os.getenv("REQUEST_DELAY_SECONDS", "2.0"))
REQUEST_TIMEOUT: float = float(os.getenv("REQUEST_TIMEOUT", "25"))
MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", "3"))

USER_AGENT: str = os.getenv(
    "SCRAPER_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
)

# Bot credits shown on cards and the about page
OWNER_HANDLES: str = "@TechnicalSerena & @Xioqui_xin"
# The owner handle users are pointed to (contact form, direct chat link)
OWNER_PRIMARY: str = os.getenv("OWNER_PRIMARY", "TechnicalSerena")

# Bundled visual assets
START_BANNER_PATH: str = str(BASE_DIR / "assets" / "start_banner.jpg")

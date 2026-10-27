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
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "").strip()
OWNER_USERNAMES: set[str] = {
    u.strip().lstrip("@").lower()
    for u in os.getenv("OWNER_USERNAMES", "TechnicalSerena,Xioqui_xin").split(",")
    if u.strip()
}

# --- Scheduler ------------------------------------------------------------
CHECK_INTERVAL_MINUTES: float = float(os.getenv("CHECK_INTERVAL_MINUTES", "30"))

# --- Storage --------------------------------------------------------------
DATABASE_PATH: str = os.getenv("DATABASE_PATH", str(BASE_DIR / "data" / "bot.db"))
Path(DATABASE_PATH).parent.mkdir(parents=True, exist_ok=True)

# --- Health-check server (Render / getvoroa / Voroa) ----------------------
ENABLE_HEALTH_SERVER: bool = _get_bool("ENABLE_HEALTH_SERVER", True)
PORT: int = int(os.getenv("PORT", "8080"))

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
SOURCE_ORDER: list[str] = [
    s.strip()
    for s in os.getenv("SOURCE_ORDER", "mirror,original,original-jina").split(",")
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

# Bundled visual assets
START_BANNER_PATH: str = str(BASE_DIR / "assets" / "start_banner.jpg")

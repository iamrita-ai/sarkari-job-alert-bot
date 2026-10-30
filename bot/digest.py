"""Daily digest - one message every morning instead of a silent bot.

Sends each subscriber:
  * the jobs catalogued in the last 24 h that match their sectors,
  * the saved jobs whose last date is within the next three days,
  * how many new vacancies are still open.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from telegram.constants import ParseMode
from telegram.error import TelegramError

from bot import config, matcher
from bot.keyboards import digest_keyboard
from bot.utils import md_escape, parse_slash_date

logger = logging.getLogger(__name__)

DIVIDER = "━━━━━━━━━━━━━━━"
CLOSING_WINDOW_DAYS = 3


def _closing_soon(last_date: str | None) -> bool:
    target = parse_slash_date(last_date)
    if target is None:
        return False
    today = datetime.now(timezone.utc).date()
    return today <= target <= today + timedelta(days=CLOSING_WINDOW_DAYS)


async def collect_digest(application, profile):  # noqa: ANN001
    """The jobs of one digest: (new matches, saved jobs closing soon)."""
    db = application.bot_data["db"]
    since = (datetime.now(timezone.utc) - timedelta(hours=26)).isoformat(
        timespec="seconds")
    new_jobs = await db.list_jobs_since(since, limit=60)
    matched = [job for job in new_jobs if matcher.title_matches(profile, job)]
    saved = await db.list_saved(profile.user_id)
    closing = [item for item in saved if _closing_soon(item.last_date)]
    return matched, closing


async def build_digest(application, profile, jobs=None) -> str | None:  # noqa: ANN001
    """Digest text for one subscriber (None when there is nothing to say).

    ``jobs`` is the optional ``(matched, closing)`` tuple of
    :func:`collect_digest` - pass it to avoid a second database round trip.
    """
    matched, closing = jobs if jobs is not None else await collect_digest(
        application, profile)

    if not matched and not closing:
        return None

    lines = [
        f"☀️ *Good morning, {md_escape(profile.full_name)}*",
        DIVIDER,
        f"📊 *New jobs since yesterday:* {len(matched)}",
    ]
    for job in matched[:8]:
        date_tag = f" ⏳ `{job.last_date}`" if job.last_date else ""
        lines.append(f"• [{md_escape(job.title[:80])}]({job.url}){date_tag}")
    if len(matched) > 8:
        lines.append(f"…and {len(matched) - 8} more — send /latest to browse")
    if closing:
        lines.append("")
        lines.append("⏳ *Closing within 3 days:*")
        for item in closing[:6]:
            date_tag = f" — `{item.last_date}`" if item.last_date else ""
            lines.append(f"• [{md_escape(item.title[:80])}]({item.url}){date_tag}")
    lines.append(DIVIDER)
    return "\n".join(lines)


async def send_daily_digest(context) -> int:  # noqa: ANN001
    """JobQueue entry - runs every day at DIGEST_HOUR (IST).

    ``context`` is the PTB ``CallbackContext`` the job queue passes in.
    """
    if not config.DIGEST_ENABLED:
        return 0
    application = context.application
    db = application.bot_data["db"]
    users = await db.all_active_users()
    sent = 0
    for profile in users:
        try:
            matched, closing = await collect_digest(application, profile)
            text = await build_digest(application, profile, (matched, closing))
        except Exception:  # noqa: BLE001
            logger.exception("Digest failed for %s", profile.user_id)
            continue
        if not text:
            continue
        try:
            await context.bot.send_message(
                chat_id=profile.user_id, text=text,
                parse_mode=ParseMode.MARKDOWN_V2, disable_web_page_preview=True,
                reply_markup=digest_keyboard(matched, closing),
            )
            sent += 1
        except TelegramError:
            logger.exception("Could not send digest to %s", profile.user_id)
    logger.info("Daily digest sent to %d users", sent)
    return sent

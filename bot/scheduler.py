"""Periodic scrape -> match -> notify pipeline."""
from __future__ import annotations

import asyncio
import logging
import time

from telegram.constants import ParseMode
from telegram.error import Forbidden, RetryAfter, TelegramError

from bot import config, matcher
from bot.cards import job_card
from bot.models import JobSummary, UserProfile
from bot.scraper import ScraperError

logger = logging.getLogger(__name__)

BOOTSTRAP_FLAG = "bootstrap_v2_done"
OWNER_ALERT_AFTER_FAILURES = 2
OWNER_ALERT_COOLDOWN_SECONDS = 3 * 3600


class JobMonitor:
    def __init__(self, application) -> None:  # noqa: ANN001 - circular typing
        self.app = application
        self.db = application.bot_data["db"]
        self.scraper = application.bot_data["scraper"]
        self.bot = application.bot
        self._lock = asyncio.Lock()

    async def periodic_check(self, context=None) -> None:  # noqa: ANN001
        """JobQueue entry point. Skips overlapping runs."""
        if self._lock.locked():
            logger.info("Previous check still running - skipping this tick")
            return
        async with self._lock:
            try:
                await self._run_cycle()
            except Exception:  # never let the scheduler die
                logger.exception("Job monitor cycle failed")

    async def _run_cycle(self) -> None:
        # 1. Refresh the listing(s) through the source chain
        try:
            jobs = await self.scraper.fetch_latest_jobs()
        except ScraperError as exc:
            logger.error("Every listing source failed: %s", exc)
            await self._maybe_alert_owners(str(exc))
            return

        await self.db.upsert_jobs(jobs)

        # Fresh deployment OR upgrade from the old single-source version:
        # silently catalogue everything that already exists, no mass alerts.
        if await self.db.get_meta(BOOTSTRAP_FLAG) is None:
            await self.db.mark_bootstrap_complete()
            await self.db.set_meta(BOOTSTRAP_FLAG, "1")
            logger.info(
                "Bootstrap run: %d existing jobs catalogued, no alerts sent", len(jobs)
            )
            return

        users = await self.db.all_active_users()
        if not users:
            logger.info("No active subscribers yet")
            return

        # 2. Fetch detail pages for not-yet-processed jobs (rate limited)
        pending = await self.db.get_pending_jobs(
            limit=config.MAX_DETAIL_FETCHES_PER_RUN
        )
        details: dict[str, object] = {}
        for job in pending:
            interested = [u for u in users if matcher.title_matches(u, job)]
            if not interested:
                # Nobody subscribes to this sector - no need to hit the page
                await self.db.mark_detail_fetched(job.job_id, None)
                continue
            try:
                detail = await self.scraper.fetch_job_detail(job.url)
                await self.db.mark_detail_fetched(job.job_id, detail)
                details[job.job_id] = detail
            except Exception:
                logger.exception("Detail fetch failed for %s - will retry", job.url)
            await asyncio.sleep(config.REQUEST_DELAY_SECONDS)

        # 3. Match and notify
        sent = 0
        for job in pending:
            detail = details.get(job.job_id)
            for user in users:
                if not matcher.title_matches(user, job):
                    continue
                if detail is not None and not matcher.qualification_matches(user, detail):
                    continue
                if await self.db.was_notified(user.user_id, job.job_id):
                    continue
                if await self._notify(user, job, detail):
                    sent += 1
                await asyncio.sleep(0.06)  # stay well under Telegram's 30 msg/s
        logger.info("Cycle complete: %d pending jobs, %d alerts sent", len(pending), sent)

    async def _notify(self, user: UserProfile, job: JobSummary, detail) -> bool:  # noqa: ANN001
        text, keyboard = job_card(job, detail, user)
        try:
            await self.bot.send_message(
                chat_id=user.user_id,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
                disable_web_page_preview=True,
            )
        except Forbidden:
            logger.info("User %s blocked the bot - pausing their alerts", user.user_id)
            await self.db.set_active(user.user_id, False)
            return False
        except RetryAfter as exc:
            logger.warning("Rate limited, sleeping %ss", exc.retry_after)
            await asyncio.sleep(exc.retry_after + 1)
            return await self._notify(user, job, detail)
        except TelegramError:
            logger.exception("Failed to send alert to %s", user.user_id)
            return False
        await self.db.mark_notified(user.user_id, job.job_id)
        return True

    async def _maybe_alert_owners(self, error: str) -> None:
        """Tell owners once (with cooldown) when all scrape sources are down."""
        failures = int(self.scraper.status.get("consecutive_failures", 0))
        if failures < OWNER_ALERT_AFTER_FAILURES:
            return
        now = time.monotonic()
        last = self.app.bot_data.get("last_owner_failure_alert")
        # None means "never alerted" - do NOT compare against monotonic 0,
        # because on a fresh container monotonic() itself is close to zero.
        if last is not None and now - last < OWNER_ALERT_COOLDOWN_SECONDS:
            return
        owner_ids: set[int] = self.app.bot_data.get("owner_chat_ids", set())
        if not owner_ids:
            return
        self.app.bot_data["last_owner_failure_alert"] = now
        text = (
            "🚨 <b>Scraper alert</b>\n"
            f"All data sources failed {failures} time(s) in a row.\n"
            f"<code>{error[:600]}</code>\n"
            "Use /sources to diagnose. The bot keeps retrying automatically."
        )
        for chat_id in owner_ids:
            try:
                await self.bot.send_message(chat_id, text, parse_mode=ParseMode.HTML)
            except TelegramError:
                logger.exception("Could not deliver owner alert to %s", chat_id)

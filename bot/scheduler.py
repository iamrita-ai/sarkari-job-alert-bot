"""Periodic scrape -> match -> notify pipeline."""
from __future__ import annotations

import asyncio
import logging

from telegram.constants import ParseMode
from telegram.error import Forbidden, RetryAfter, TelegramError

from bot import config, matcher
from bot.cards import job_card
from bot.models import JobSummary, UserProfile

logger = logging.getLogger(__name__)


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
        # 1. Refresh the listing(s)
        try:
            jobs = await self.scraper.fetch_latest_jobs()
        except Exception:
            logger.exception("Could not fetch job listing")
            return
        if not jobs:
            logger.warning("Listing returned zero parseable jobs")
            return

        seen_before = await self.db.get_seen_job_ids()
        bootstrap = not seen_before
        await self.db.upsert_jobs(jobs)
        if bootstrap:
            await self.db.mark_bootstrap_complete()
            logger.info(
                "Bootstrap run: %d existing jobs marked as seen, no alerts sent",
                len(jobs),
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

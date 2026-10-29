"""Entry point - wires the database, scraper, scheduler and bot together."""
from __future__ import annotations

import logging
from datetime import time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

from telegram import BotCommand, Update
from telegram.ext import Application, PicklePersistence

from bot import config
from bot.db import build_database
from bot.digest import send_daily_digest
from bot.handlers import register_handlers
from bot.health import start_health_server
from bot.inline import register_inline
from bot.reminders import register_reminders, schedule_all_pending
from bot.scheduler import JobMonitor
from bot.scraper import SarkariScraper

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def _post_init(app: Application) -> None:
    db = await build_database()

    scraper = SarkariScraper()
    app.bot_data["db"] = db
    app.bot_data["scraper"] = scraper
    app.bot_data["owner_chat_ids"] = set()
    app.bot_data["last_owner_failure_alert"] = None
    app.bot_data["browsers"] = {}
    app.bot_data["saved_browsers"] = {}

    me = await app.bot.get_me()
    app.bot_data["bot_username"] = me.username
    logger.info("Running as @%s", me.username)

    monitor = JobMonitor(app)
    app.bot_data["monitor"] = monitor
    app.job_queue.run_repeating(
        monitor.periodic_check,
        interval=config.CHECK_INTERVAL_MINUTES * 60,
        first=20,
        name="sarkari-job-monitor",
    )

    # Re-arm bookmark reminders that were scheduled before this restart
    await schedule_all_pending(app)

    # Daily digest - one message every morning (IST) so the bot is never
    # silent for a whole day.
    if config.DIGEST_ENABLED:
        app.job_queue.run_daily(
            send_daily_digest,
            time=dtime(hour=config.DIGEST_HOUR, minute=5),
            days=tuple(range(7)),
            tz=ZoneInfo("Asia/Kolkata"),
            name="daily-digest",
        )
        logger.info("Daily digest scheduled at %02d:05 IST", config.DIGEST_HOUR)

    # Optional web dashboard (FastAPI) - needs requirements-web.txt
    if config.ENABLE_WEB_APP:
        try:
            from bot.webapp import start_web_app

            start_web_app(app)
        except ImportError:
            logger.warning(
                "ENABLE_WEB_APP is on but fastapi/uvicorn are missing - "
                "run: pip install -r requirements-web.txt"
            )

    await app.bot.set_my_commands([
        BotCommand("start", "Create / view your job profile"),
        BotCommand("profile", "Show your saved preferences"),
        BotCommand("edit", "Edit name, DOB, category, degrees, documents, sectors"),
        BotCommand("latest", "Browse matching jobs (Next / Previous)"),
        BotCommand("saved", "Your bookmarked jobs & reminders"),
        BotCommand("pause", "Pause job alerts"),
        BotCommand("resume", "Resume job alerts"),
        BotCommand("help", "Help & usage"),
        BotCommand("about", "About this bot & owners"),
        BotCommand("webapp", "Open your personal web dashboard"),
    ])

    if config.ENABLE_HEALTH_SERVER:
        app.bot_data["health_server"] = start_health_server(
            config.PORT, status_provider=lambda: scraper.status
        )


async def _post_shutdown(app: Application) -> None:
    await app.bot_data["scraper"].close()
    await app.bot_data["db"].close()
    server = app.bot_data.get("health_server")
    if server is not None:
        server.shutdown()
    logger.info("Shutdown complete")


def main() -> None:
    if not config.BOT_TOKEN:
        raise SystemExit(
            "BOT_TOKEN is missing. Copy .env.example to .env and add the "
            "token you got from @BotFather."
        )

    app = (
        Application.builder()
        .token(config.BOT_TOKEN)
        .post_init(_post_init)
        .post_shutdown(_post_shutdown)
        .build()
    )
    # Conversation persistence: the onboarding steps survive a restart, so a
    # button pressed after a redeploy still works.
    if config.PERSISTENCE_PATH:
        try:
            Path(config.PERSISTENCE_PATH).parent.mkdir(parents=True, exist_ok=True)
            app.persistence = PicklePersistence(filepath=config.PERSISTENCE_PATH)
            logger.info("Conversation persistence: %s", config.PERSISTENCE_PATH)
        except Exception:  # noqa: BLE001 - never block the bot on this
            logger.exception("Could not enable conversation persistence")

    register_handlers(app)
    register_reminders(app)
    register_inline(app)
    logger.info(
        "Sarkari Job Alert Bot starting (check every %.0f min, owners: %s)",
        config.CHECK_INTERVAL_MINUTES,
        ", ".join(sorted(config.OWNER_USERNAMES)),
    )
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

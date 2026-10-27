"""Entry point - wires the database, scraper, scheduler and bot together."""
from __future__ import annotations

import logging

from telegram import BotCommand, Update
from telegram.ext import Application

from bot import config
from bot.db import Database
from bot.handlers import register_handlers
from bot.health import start_health_server
from bot.scheduler import JobMonitor
from bot.scraper import SarkariScraper

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def _post_init(app: Application) -> None:
    db = Database(config.DATABASE_PATH)
    await db.connect()

    scraper = SarkariScraper()
    app.bot_data["db"] = db
    app.bot_data["scraper"] = scraper

    monitor = JobMonitor(app)
    app.bot_data["monitor"] = monitor
    app.job_queue.run_repeating(
        monitor.periodic_check,
        interval=config.CHECK_INTERVAL_MINUTES * 60,
        first=20,
        name="sarkari-job-monitor",
    )

    await app.bot.set_my_commands([
        BotCommand("start", "Create / view your job profile"),
        BotCommand("profile", "Show your saved preferences"),
        BotCommand("edit", "Update your profile & preferences"),
        BotCommand("latest", "Fetch matching jobs now"),
        BotCommand("pause", "Pause job alerts"),
        BotCommand("resume", "Resume job alerts"),
        BotCommand("help", "Help & usage"),
        BotCommand("about", "About this bot & owners"),
    ])

    if config.ENABLE_HEALTH_SERVER:
        app.bot_data["health_server"] = start_health_server(config.PORT)


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
    register_handlers(app)
    logger.info(
        "Sarkari Job Alert Bot starting (check every %.0f min, owners: %s)",
        config.CHECK_INTERVAL_MINUTES,
        ", ".join(sorted(config.OWNER_USERNAMES)),
    )
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

"""Entry point - wires the database, scraper, scheduler and bot together."""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

from telegram import BotCommand, Update
from telegram.error import Conflict, NetworkError, TimedOut
from telegram.ext import Application, Defaults, PersistenceInput, PicklePersistence

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

# Everything the bot schedules runs on Indian time.
IST = ZoneInfo("Asia/Kolkata")

# Runtime objects shared between the health endpoint and the bot itself.
_RUNTIME: dict = {}

# The hosting platform probes ONE port and (Voroa) aborts the deploy when
# the service listens on more than one. So we bind exactly the port the
# platform provides - no extra fallbacks.


def _health_status() -> dict:
    """Scraper status for /health (never raises)."""
    scraper = _RUNTIME.get("scraper")
    status: dict = {"status": "starting"}
    if scraper is not None:
        try:
            status = dict(scraper.status)
        except Exception:  # noqa: BLE001 - health must never crash
            status = {"status": "unknown"}
    conflict = _RUNTIME.get("last_conflict")
    if conflict:
        status["last_conflict"] = conflict
        status["status"] = "duplicate-instance"
    return status


def build_persistence(path: str) -> PicklePersistence:
    """Conversation-state persistence.

    ONLY the conversation states are stored. ``bot_data`` holds live runtime
    objects (the SQLite connection, the HTTP client) which can not be pickled -
    persisting them kills the bot on shutdown with
    ``TypeError: cannot pickle 'sqlite3.Connection' object``.
    """
    return PicklePersistence(
        filepath=path,
        store_data=PersistenceInput(
            bot_data=False,
            chat_data=False,
            user_data=False,
            callback_data=False,
        ),
    )


def schedule_daily_digest(app: Application) -> None:
    """Schedule the daily digest (09:05 IST).

    PTB v22 has no ``tz`` argument on ``run_daily`` - the timezone comes from
    the timezone-aware ``time`` object (and from the bot defaults).
    """
    if not config.DIGEST_ENABLED:
        return
    app.job_queue.run_daily(
        send_daily_digest,
        time=dtime(hour=config.DIGEST_HOUR, minute=5, tzinfo=IST),
        days=tuple(range(7)),
        name="daily-digest",
    )
    logger.info("Daily digest scheduled at %02d:05 IST", config.DIGEST_HOUR)


def fresh_event_loop() -> asyncio.AbstractEventLoop:
    """A brand-new event loop.

    PTB closes the loop when ``run_polling`` returns or raises, so a restart
    of the polling loop needs a new one - otherwise the retry dies with
    "RuntimeError: Event loop is closed".
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop


async def _post_init(app: Application) -> None:
    db = await build_database()

    scraper = SarkariScraper()
    _RUNTIME["scraper"] = scraper
    app.bot_data["db"] = db
    app.bot_data["scraper"] = scraper
    app.bot_data["owner_chat_ids"] = set()
    app.bot_data["last_owner_failure_alert"] = None
    app.bot_data["browsers"] = {}
    app.bot_data["saved_browsers"] = {}

    me = None
    for attempt in range(1, 4):
        try:
            me = await app.bot.get_me()
            break
        except Exception:  # noqa: BLE001 - never block the start-up
            logger.warning("get_me failed (attempt %s/3)", attempt, exc_info=True)
            await asyncio.sleep(3)
    if me is not None:
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
    try:
        schedule_daily_digest(app)
    except Exception:  # noqa: BLE001 - a scheduling error must not kill the bot
        logger.exception("Could not schedule the daily digest")

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
        except Exception:  # noqa: BLE001 - the dashboard must never kill the bot
            logger.exception("Could not start the web dashboard")

    await app.bot.set_my_commands([
        BotCommand("start", "Create / view your job profile"),
        BotCommand("profile", "Show your saved preferences"),
        BotCommand("edit", "Edit name, DOB, category, degrees, documents, sectors"),
        BotCommand("latest", "Browse matching jobs (Next / Previous)"),
        BotCommand("admit", "Latest admit cards"),
        BotCommand("result", "Latest results"),
        BotCommand("saved", "Your bookmarked jobs & reminders"),
        BotCommand("pause", "Pause job alerts"),
        BotCommand("resume", "Resume job alerts"),
        BotCommand("why", "Why SERENA is useful for you"),
        BotCommand("contact", "Contact the owner - bugs & suggestions"),
        BotCommand("help", "Help & usage"),
        BotCommand("about", "About this bot & owners"),
        BotCommand("webapp", "Open your personal web dashboard"),
    ])


async def _post_shutdown(app: Application) -> None:
    scraper = app.bot_data.get("scraper")
    if scraper is not None:
        try:
            await scraper.close()
        except Exception:  # noqa: BLE001
            logger.exception("Could not close the scraper cleanly")
    db = app.bot_data.get("db")
    if db is not None:
        try:
            await db.close()
        except Exception:  # noqa: BLE001
            logger.exception("Could not close the database cleanly")
    # NOTE: the health server keeps running on purpose - if the bot restarts
    # after a crash the platform must still see a live service.
    logger.info("Shutdown complete")


def _start_health_servers() -> None:
    """Start /health on EXACTLY the port the platform provides.

    Voroa aborts the deployment when the service listens on more than one
    port ("your service is listening on more than one port"), so the bot
    must never open a second socket. When the web dashboard is enabled it
    takes over that port and answers /health itself.
    """
    if not config.ENABLE_HEALTH_SERVER:
        return
    port = config.PORT
    if config.ENABLE_WEB_APP and port == config.WEB_APP_PORT:
        # The dashboard owns this port and answers /health itself.
        return
    try:
        server = start_health_server(port, status_provider=_health_status)
    except OSError:
        logger.warning("Port %s is not available - skipping", port)
        return
    _RUNTIME.setdefault("health_servers", []).append(server)


async def _notify_owners(owner_ids, text: str) -> None:
    """Tell the owners about a problem (best effort, never raises)."""
    if not owner_ids:
        return
    from telegram import Bot

    bot = Bot(config.BOT_TOKEN)
    try:
        for chat_id in owner_ids:
            try:
                await bot.send_message(chat_id=chat_id, text=text)
            except Exception:  # noqa: BLE001
                logger.exception("Could not notify owner %s", chat_id)
    finally:
        await bot.shutdown()


def _run_with_retries(app: Application) -> None:
    """Keep the bot alive.

    A duplicate instance (409) or a network hiccup must never take the
    service down for good - we retry with a growing back-off instead.
    """
    delay = 15
    # ``None`` = the owners were not warned yet (the first conflict always
    # warns them - even on a container that was booted a minute ago).
    last_conflict_alert: float | None = None
    while True:
        fresh_event_loop()
        try:
            app.run_polling(
                allowed_updates=Update.ALL_TYPES,
                bootstrap_retries=-1,  # retry the start-up forever
            )
            return
        except (Conflict, TimedOut, NetworkError) as exc:
            logger.warning(
                "Polling stopped (%s). Another instance may be using the same "
                "bot token - retrying in %s seconds.",
                exc,
                delay,
            )
            if isinstance(exc, Conflict):
                _RUNTIME["last_conflict"] = str(exc)
                now = time.monotonic()
                if last_conflict_alert is None or now - last_conflict_alert > 1800:
                    last_conflict_alert = now
                    try:
                        asyncio.run(_notify_owners(
                            app.bot_data.get("owner_chat_ids") or set(),
                            "⚠️ *Another instance is polling with this bot token.*\n\n"
                            "The updates are going to that instance. Stop the old "
                            "service (or revoke the old token) - this one keeps "
                            "retrying every few minutes.",
                        ))
                    except Exception:  # noqa: BLE001
                        logger.exception("Could not notify the owners about the conflict")
            time.sleep(delay)
            delay = min(delay * 2, 300)
        except Exception:  # noqa: BLE001 - the bot must never stay down
            logger.exception("Unexpected polling error - restarting in 30 seconds")
            time.sleep(30)


def main() -> None:
    if not config.BOT_TOKEN:
        raise SystemExit(
            "BOT_TOKEN is missing. Copy .env.example to .env and add the "
            "token you got from @BotFather."
        )

    app = (
        Application.builder()
        .token(config.BOT_TOKEN)
        # The job queue (digest, reminders) runs on Indian time.
        .defaults(Defaults(tzinfo=IST))
        .post_init(_post_init)
        .post_shutdown(_post_shutdown)
        .build()
    )
    # Conversation persistence: the onboarding steps survive a restart, so a
    # button pressed after a redeploy still works. Only the conversation
    # states are stored - bot_data holds live objects that cannot be pickled.
    if config.PERSISTENCE_PATH:
        try:
            Path(config.PERSISTENCE_PATH).parent.mkdir(parents=True, exist_ok=True)
            app.persistence = build_persistence(config.PERSISTENCE_PATH)
            logger.info(
                "Conversation persistence: %s (conversation states only)",
                config.PERSISTENCE_PATH,
            )
        except Exception:  # noqa: BLE001 - never block the bot on this
            logger.exception("Could not enable conversation persistence")

    # The health endpoint comes up BEFORE the Telegram connection, so the
    # platform always sees a listening service (even if Telegram is slow).
    _start_health_servers()

    register_handlers(app)
    register_reminders(app)
    register_inline(app)
    logger.info(
        "SERENA starting (check every %.0f min, owners: %s)",
        config.CHECK_INTERVAL_MINUTES,
        ", ".join(sorted(config.OWNER_USERNAMES)),
    )
    _run_with_retries(app)


if __name__ == "__main__":
    main()

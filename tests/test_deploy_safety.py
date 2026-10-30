"""Deployment-safety tests (v1.5.1).

These guard the two failure modes that killed a production deploy:

1. ``TypeError: cannot pickle 'sqlite3.Connection' object`` - the persistence
   tried to serialise ``bot_data`` (database + HTTP client).
2. "we did not see your service listening on any port" - the health endpoint
   only came up *after* the Telegram connection was established.
"""
import asyncio
import sqlite3

import pytest
from telegram.error import Conflict
from telegram.ext import Application

from bot import main as bot_main


def test_persistence_never_pickles_bot_data(tmp_path):
    """The exact production crash: sqlite3.Connection inside bot_data."""
    app = Application.builder().token("123:TEST").build()
    app.persistence = bot_main.build_persistence(str(tmp_path / "conversation.pickle"))
    app.bot_data["db"] = sqlite3.connect(":memory:")  # cannot be pickled
    app.bot_data["scraper"] = object()

    async def run():
        await app.update_persistence()

    asyncio.run(run())  # must not raise TypeError


def test_persistence_stores_only_conversation_states(tmp_path):
    app = Application.builder().token("123:TEST").build()
    app.persistence = bot_main.build_persistence(str(tmp_path / "conversation.pickle"))
    store = app.persistence.store_data
    assert store.bot_data is False
    assert store.chat_data is False
    assert store.user_data is False
    assert store.callback_data is False


def test_conversation_states_are_still_persisted(tmp_path):
    """The persistence must keep the onboarding states (the dead-button fix)."""
    app = Application.builder().token("123:TEST").build()
    app.persistence = bot_main.build_persistence(str(tmp_path / "conversation.pickle"))

    async def run():
        await app.persistence.update_conversation(
            name="onboarding", key=(123, "chat"), new_state=2
        )
        await app.persistence.flush()
        return await app.persistence.get_conversations("onboarding")

    stored = asyncio.run(run())
    assert stored[(123, "chat")] == 2


def test_health_server_starts_on_exactly_one_port(monkeypatch):
    """Voroa aborts the deploy when the service listens on more than one port
    ("your service is listening on more than one port (8000, 8080)"), so the
    bot must open exactly ONE socket - the port the platform provides."""
    started: list[int] = []

    class _FakeServer:
        def shutdown(self):
            pass

    def fake_start(port, status_provider=None):
        started.append(port)
        return _FakeServer()

    monkeypatch.setattr(bot_main, "start_health_server", fake_start)
    monkeypatch.setattr(bot_main.config, "ENABLE_HEALTH_SERVER", True)
    monkeypatch.setattr(bot_main.config, "PORT", 8080)
    bot_main._RUNTIME.pop("health_servers", None)
    bot_main._start_health_servers()
    assert started == [8080], started
    # no extra fallback sockets - they made Voroa abort the deployment
    assert 8000 not in started and 8081 not in started


def test_bot_restarts_instead_of_dying_on_a_duplicate_instance(monkeypatch):
    """A 409 from another instance must not take the service down."""
    calls: list[int] = []
    sleeps: list[float] = []

    async def fake_notify(owner_ids, text):
        return None

    class _FakeApp:
        def __init__(self):
            self.bot_data = {"owner_chat_ids": set()}

        def run_polling(self, **kwargs):
            calls.append(1)
            if len(calls) == 1:
                raise Conflict("terminated by other getUpdates")
            return None

    monkeypatch.setattr(bot_main, "_notify_owners", fake_notify)
    monkeypatch.setattr(bot_main.time, "sleep", lambda s: sleeps.append(s))
    bot_main._run_with_retries(_FakeApp())
    assert len(calls) == 2, "the bot did not retry after the conflict"
    assert sleeps and sleeps[0] > 0


def test_conflict_notifies_the_owners(monkeypatch):
    """The owner must learn that a second instance steals the updates."""
    notified: list[tuple] = []

    async def fake_notify(owner_ids, text):
        notified.append((set(owner_ids), text))

    class _FakeApp:
        def __init__(self):
            self.bot_data = {"owner_chat_ids": {42}}
            self.calls = 0

        def run_polling(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise Conflict("terminated by other getUpdates")
            return None

    monkeypatch.setattr(bot_main, "_notify_owners", fake_notify)
    monkeypatch.setattr(bot_main.time, "sleep", lambda s: None)
    bot_main._run_with_retries(_FakeApp())
    assert notified, "the owners were not notified about the duplicate instance"
    assert notified[0][0] == {42}
    assert "Another instance" in notified[0][1]


def test_daily_digest_uses_the_supported_ptb_api():
    """PTB v22 has no ``tz`` argument on run_daily - that killed the bot."""
    app = Application.builder().token("123:TEST").build()
    bot_main.schedule_daily_digest(app)
    jobs = app.job_queue.scheduler.get_jobs()
    assert jobs, "the daily digest was not scheduled"
    trigger = jobs[0].trigger
    trigger_text = str(trigger)
    assert "hour='9'" in trigger_text, f"wrong hour: {trigger_text}"
    assert "minute='5'" in trigger_text, f"wrong minute: {trigger_text}"
    tz = trigger.timezone
    assert tz is not None, "the digest job has no timezone"
    assert str(tz) == "Asia/Kolkata", f"wrong timezone: {tz}"


def test_retry_loop_uses_a_fresh_event_loop(monkeypatch):
    """PTB closes the loop when run_polling raises - the retry needs a new one."""
    loops = []

    class _FakeApp:
        def run_polling(self, **kwargs):
            loop = asyncio.get_event_loop()
            loops.append(loop)
            if len(loops) == 1:
                loop.close()  # exactly what PTB does on shutdown
                raise RuntimeError("Event loop is closed")
            return None

    monkeypatch.setattr(bot_main.time, "sleep", lambda s: None)
    bot_main._run_with_retries(_FakeApp())
    assert len(loops) == 2
    assert loops[0] is not loops[1], "the closed loop was reused"
    assert not loops[1].is_closed()


def test_first_conflict_always_notifies_even_on_a_fresh_container(monkeypatch):
    """A container that booted two minutes ago must still warn the owners."""
    notified: list[tuple] = []

    async def fake_notify(owner_ids, text):
        notified.append((set(owner_ids), text))

    class _FakeApp:
        def __init__(self):
            self.bot_data = {"owner_chat_ids": {42}}
            self.calls = 0

        def run_polling(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise Conflict("terminated by other getUpdates")
            return None

    monkeypatch.setattr(bot_main, "_notify_owners", fake_notify)
    monkeypatch.setattr(bot_main.time, "sleep", lambda s: None)
    monkeypatch.setattr(bot_main.time, "monotonic", lambda: 123.0)  # fresh boot
    bot_main._run_with_retries(_FakeApp())
    assert notified, "the owners were not warned about the very first conflict"


def test_post_init_completes_without_errors(monkeypatch):
    """The whole start-up path must run - this caught run_daily(tz=...)."""
    from telegram.ext import ExtBot

    class _FakeDB:
        async def pending_reminders(self):
            return []

        async def close(self):
            return None

    async def fake_build_database():
        return _FakeDB()

    async def fake_get_me(self, *args, **kwargs):
        class _User:
            username = "jobtestbot"

        return _User()

    async def fake_set_my_commands(self, *args, **kwargs):
        return True

    monkeypatch.setattr(bot_main, "build_database", fake_build_database)
    monkeypatch.setattr(ExtBot, "get_me", fake_get_me)
    monkeypatch.setattr(ExtBot, "set_my_commands", fake_set_my_commands)

    app = Application.builder().token("123:TEST").build()
    asyncio.run(bot_main._post_init(app))
    jobs = app.job_queue.scheduler.get_jobs()
    assert jobs, "no job was scheduled (digest / monitor missing)"
    assert app.bot_data["bot_username"] == "jobtestbot"


def test_health_server_takes_the_port_when_the_dashboard_cannot_start(monkeypatch):
    """ENABLE_WEB_APP=true + a missing fastapi must not leave the service
    without an open port - Voroa aborts such a deployment."""
    import sys

    import bot.main as bot_main

    started: list[int] = []

    class _FakeServer:
        def shutdown(self):
            pass

    def fake_start(port, status_provider=None):
        started.append(port)
        return _FakeServer()

    monkeypatch.setattr(bot_main, "start_health_server", fake_start)
    monkeypatch.setattr(bot_main.config, "ENABLE_HEALTH_SERVER", True)
    monkeypatch.setattr(bot_main.config, "ENABLE_WEB_APP", True)
    monkeypatch.setattr(bot_main.config, "PORT", 8080)
    monkeypatch.setitem(sys.modules, "fastapi", None)  # simulate a missing dep
    bot_main._RUNTIME.pop("health_servers", None)
    bot_main._start_health_servers()
    assert started == [8080], started


def test_health_server_answers_the_root_path():
    """Render and Voroa probe '/' - a 404 there means 'the service is down'."""
    import urllib.request

    from bot.health import start_health_server

    server = start_health_server(8123, status_provider=lambda: {"status": "ok"})
    try:
        with urllib.request.urlopen("http://127.0.0.1:8123/") as response:
            assert response.status == 200
        with urllib.request.urlopen("http://127.0.0.1:8123/health") as response:
            assert response.status == 200
    finally:
        server.shutdown()
        server.server_close()


def test_platform_port_is_read_from_the_environment(monkeypatch):
    """Voroa injects the port as $PORT - the bot must bind exactly that one."""
    from bot import config

    monkeypatch.setenv("PORT", "4321")
    assert config._platform_port() == 4321
    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.setenv("SOME_OTHER_PORT", "5555")
    assert config._platform_port() == 5555
    monkeypatch.delenv("SOME_OTHER_PORT", raising=False)

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


def test_health_server_starts_on_the_configured_port(monkeypatch):
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
    assert started[0] == 8080
    assert 8000 in started  # fallbacks for platforms that pick another port


def test_bot_restarts_instead_of_dying_on_a_duplicate_instance(monkeypatch):
    """A 409 from another instance must not take the service down."""
    calls: list[int] = []
    sleeps: list[float] = []

    class _FakeApp:
        def run_polling(self, **kwargs):
            calls.append(1)
            if len(calls) == 1:
                raise Conflict("terminated by other getUpdates")
            return None

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

        def run_polling(self, **kwargs):
            if not notified:
                raise Conflict("terminated by other getUpdates")
            return None

    monkeypatch.setattr(bot_main, "_notify_owners", fake_notify)
    monkeypatch.setattr(bot_main.time, "sleep", lambda s: None)
    bot_main._run_with_retries(_FakeApp())
    assert notified, "the owners were not notified about the duplicate instance"
    assert notified[0][0] == {42}
    assert "Another instance" in notified[0][1]

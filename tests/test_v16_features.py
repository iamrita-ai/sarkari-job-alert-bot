"""v1.6 feature tests.

Covers the "production polish" wave:
  * the daily digest without the /pause footer and with tappable job buttons,
  * /admit and /result (notice sections as first class content),
  * the owner contact flow (/contact, /reply, "Contact owner" button),
  * the SERENA branding and the richer /help,
  * compact job references (Telegram allows only 64 bytes of callback data),
  * the web dashboard on the platform port + its /health route,
  * the redundant source chain.
"""
import asyncio

import pytest

from bot import config
from bot.cards import about_text, help_text, welcome_caption
from bot.db import Database
from bot.digest import build_digest
from bot.keyboards import (digest_keyboard, job_action_keyboard,
                           job_detail_keyboard, main_menu_keyboard,
                           reminder_keyboard)
from bot.models import JobSummary, UserProfile
from bot.utils import job_ref

JOB = JobSummary("/railway-x-2026/", "Railway X Online Form 2026",
                 "https://sarkariresult.com.cm/railway-x-2026/", "25/11/2026")

# A real notice slug from the source site - longer than 64 bytes once encoded.
LONG_JOB = JobSummary(
    "/rajasthan-police-constable-telecommunication-online-form-2025-correction-last-date",
    "Rajasthan Police Constable Telecommunication 2025 - Correction Last Date",
    "https://sarkariresult.com.cm/rajasthan-police-constable-telecommunication-online-form-2025-correction-last-date/",
    "25/11/2026")


# --------------------------------------------------------------- helpers
def _fake_app(tmp_path, name: str = "v16.db"):
    from telegram.ext import Application

    application = Application.builder().token("123:TEST").build()
    return application


def _user(update_id: int = 1, username: str = "rahul"):
    from telegram import Chat, Message, Update, User

    user = User(id=555, first_name="Rahul", username=username, is_bot=False)
    chat = Chat(id=555, type="private")
    message = Message(message_id=9, date=None, chat=chat, from_user=user, text="hi")
    return Update(update_id=update_id, message=message)


def _callback(data: str, user_id: int = 555, username: str = "rahul"):
    from telegram import CallbackQuery, Chat, Message, Update, User

    user = User(id=user_id, first_name="Rahul", username=username, is_bot=False)
    chat = Chat(id=user_id, type="private")
    message = Message(message_id=9, date=None, chat=chat, from_user=user, text="x")
    query = CallbackQuery(id="1", from_user=user, chat_instance="ci", data=data,
                           message=message)
    return Update(update_id=1, callback_query=query)


class _Recorder:
    """Captures everything the bot sends."""

    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []
        self.answers: list[str] = []

    async def send_message(self, chat_id, text, **kwargs):
        self.sent.append((chat_id, text))
        from telegram import Chat, Message, User
        return Message(message_id=1, date=None, chat=Chat(id=chat_id, type="private"),
                       from_user=User(id=1, first_name="x", is_bot=False), text=text)

    async def message(self, chat_id, text, bot=None):
        """A reply message (the bot must be attached to it)."""
        from telegram import Chat, Message, User
        msg = Message(message_id=1, date=None, chat=Chat(id=chat_id, type="private"),
                      from_user=User(id=1, first_name="x", is_bot=False), text=text)
        if bot is not None:
            msg.set_bot(bot)  # PTB's set_bot does not return the message
        return msg

    async def answer_callback_query(self, *args, **kwargs):
        self.answers.append(str(args))
        return True


def _patch_bot(recorder: _Recorder):
    """Silence the network for the duration of a test."""
    from telegram.ext import ExtBot

    async def fake_send_message(self, chat_id, text, **kwargs):
        recorder.sent.append((chat_id, text))
        return await recorder.message(chat_id, text, bot=self)

    async def fake_answer(self, *args, **kwargs):
        recorder.answers.append(str(args))
        return True

    async def fake_initialize(self, *args, **kwargs):
        return None

    async def fake_edit(self, *args, **kwargs):
        return True

    async def fake_edit_message_text(self, *args, **kwargs):
        from telegram import Chat, Message, User
        text = args[0] if args else kwargs.get("text", "")
        msg = Message(message_id=1, date=None, chat=Chat(id=1, type="private"),
                      from_user=User(id=1, first_name="x", is_bot=False), text=text)
        msg.set_bot(self)
        return msg

    ExtBot.send_message = fake_send_message
    ExtBot.answer_callback_query = fake_answer
    ExtBot.initialize = fake_initialize
    ExtBot.edit_message_text = fake_edit_message_text
    return (ExtBot.send_message, ExtBot.answer_callback_query,
            ExtBot.initialize, ExtBot.edit_message_text)


def _restore_bot(orig):
    from telegram.ext import ExtBot

    (ExtBot.send_message, ExtBot.answer_callback_query, ExtBot.initialize,
     ExtBot.edit_message_text) = orig


# ------------------------------------------------------------- 1. digest
def test_digest_text_has_no_pause_footer(tmp_path):
    """The user asked to remove 'Turn these off with /pause'."""
    db = Database(str(tmp_path / "d.db"))

    class FakeApp:
        def __init__(self):
            self.bot_data = {"db": db}

    async def run():
        await db.connect()
        profile = UserProfile(7, "u", "Rahul", "OBC", "graduate", ["railway"],
                              "15/08/2000")
        await db.upsert_jobs([JobSummary("/railway-new-2026/", "Railway New 2026",
                                         "https://sarkariresult.com.cm/railway-new-2026/",
                                         "30/11/2026")])
        text = await build_digest(FakeApp(), profile)
        await db.close()
        return text

    text = asyncio.run(run())
    assert text is not None
    assert "/pause" not in text
    assert "/profile" not in text
    assert "Good morning" in text


def test_digest_buttons_open_the_job_card():
    kb = digest_keyboard([JOB])
    data = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert any(d.startswith("dig:") for d in data)
    for value in data:
        assert len(value.encode()) <= 64


def test_digest_job_button_sends_the_full_card(tmp_path):
    """Tapping a job in the digest opens the same card as an alert."""
    from telegram.ext import Application

    from bot import handlers

    recorder = _Recorder()
    orig = _patch_bot(recorder)
    try:
        async def run():
            app = Application.builder().token("123:TEST").build()
            db = Database(str(tmp_path / "dig.db"))
            await db.connect()
            await db.upsert_jobs([JOB])
            app.bot_data["db"] = db
            update = _callback(f"dig:{job_ref(JOB.job_id)}")
            update.set_bot(app.bot)
            update.callback_query.set_bot(app.bot)
            update.callback_query.message.set_bot(app.bot)
            context = app.context_types.context.from_update(update, app)
            await handlers.digest_job_callback(update, context)
            await db.close()
        asyncio.run(run())
    finally:
        _restore_bot(orig)
    assert recorder.sent, "the digest button did not answer"
    assert "Railway X" in recorder.sent[-1][1]


# -------------------------------------------------------- 2. /admit, /result
def test_admit_and_result_commands_list_the_section(tmp_path):
    from telegram.ext import Application

    from bot import handlers

    recorder = _Recorder()
    orig = _patch_bot(recorder)
    calls: list[str] = []

    class FakeScraper:
        async def fetch_section(self, path):
            calls.append(path)
            return [JOB]

    try:
        async def run():
            app = Application.builder().token("123:TEST").build()
            app.bot_data["scraper"] = FakeScraper()
            app.bot_data["db"] = Database(str(tmp_path / "a.db"))
            update = _user()
            update.set_bot(app.bot)
            update.message.set_bot(app.bot)
            context = app.context_types.context.from_update(update, app)
            await handlers.admit_cards(update, context)
            await handlers.results(update, context)
        asyncio.run(run())
    finally:
        _restore_bot(orig)
    assert calls == [config.MIRROR_ADMIT_CARD_PATH, config.MIRROR_RESULT_PATH]
    assert any("Railway X" in text for _, text in recorder.sent)


def test_section_paths_are_configurable():
    assert config.MIRROR_ADMIT_CARD_PATH == "/admit-card/"
    assert config.MIRROR_RESULT_PATH == "/result/"


# ------------------------------------------------------- 3. owner contact
def test_contact_forwards_the_message_to_the_owner(tmp_path):
    from telegram.ext import Application

    from bot import handlers

    recorder = _Recorder()
    orig = _patch_bot(recorder)
    try:
        async def run():
            app = Application.builder().token("123:TEST").build()
            app.bot_data["owner_chat_ids"] = {999}
            app.bot_data["db"] = Database(str(tmp_path / "c.db"))
            update = _user()
            update.set_bot(app.bot)
            update.message.set_bot(app.bot)
            context = app.context_types.context.from_update(update, app)
            context.args = ["there", "is", "a", "bug"]
            await handlers.contact_owner(update, context)
        asyncio.run(run())
    finally:
        _restore_bot(orig)
    from tests.test_markdown_lint import lint_markdown_v2

    for _, text in recorder.sent:
        if "New message from a user" in text:
            assert not lint_markdown_v2(text), lint_markdown_v2(text)
    forwarded = [(chat, text) for chat, text in recorder.sent if chat == 999]
    assert forwarded, "the owner never received the message"
    assert "bug" in forwarded[0][1]
    assert "555" in forwarded[0][1]  # the chat id for /reply


def test_reply_command_is_owner_only(tmp_path):
    from telegram.ext import Application

    from bot import handlers

    recorder = _Recorder()
    orig = _patch_bot(recorder)
    try:
        async def run():
            app = Application.builder().token("123:TEST").build()
            app.bot_data["db"] = Database(str(tmp_path / "r.db"))
            update = _user(username="stranger")
            update.set_bot(app.bot)
            update.message.set_bot(app.bot)
            context = app.context_types.context.from_update(update, app)
            context.args = ["555", "hello"]
            await handlers.owner_reply(update, context)
        asyncio.run(run())
    finally:
        _restore_bot(orig)
    assert recorder.sent
    assert "owner" in recorder.sent[-1][1].lower()
    assert all(chat == 555 for chat, _ in recorder.sent)


def test_main_menu_has_the_contact_button():
    labels = [b.text for row in main_menu_keyboard(True).inline_keyboard for b in row]
    assert any("Contact" in label for label in labels)


def test_main_menu_offers_admit_cards_and_results():
    data = [b.callback_data for row in main_menu_keyboard(True).inline_keyboard
            for b in row]
    assert "menu:admit" in data
    assert "menu:result" in data


# ------------------------------------------------------------ 4. branding
def test_brand_is_serena():
    assert "SERENA" in welcome_caption()
    assert "SERENA" in about_text()
    assert "SERENA" in help_text()


def test_new_messages_are_valid_markdown_v2():
    """A single unescaped character would make Telegram reject the message."""
    from tests.test_markdown_lint import lint_markdown_v2

    for text in (welcome_caption(), help_text(), about_text()):
        problems = lint_markdown_v2(text)
        assert not problems, f"{problems} :: {text[:120]!r}"


def test_help_explains_every_new_command():
    text = help_text()
    for command in ("/admit", "/result", "/contact", "/latest", "/saved",
                    "/pause", "/resume", "/profile", "/digest"):
        assert command in text, command


# ------------------------------------------------- 5. compact job references
def test_callback_data_never_exceeds_the_telegram_limit():
    """Long notice slugs used to break the whole message (64 byte limit)."""
    for kb in (job_action_keyboard(LONG_JOB),
               job_detail_keyboard(LONG_JOB, None),
               reminder_keyboard(LONG_JOB.job_id, True),
               digest_keyboard([LONG_JOB])):
        for row in kb.inline_keyboard:
            for button in row:
                data = button.callback_data or ""
                assert len(data.encode()) <= 64, data


def test_job_reference_resolves_from_the_database(tmp_path):
    db = Database(str(tmp_path / "ref.db"))

    async def run():
        await db.connect()
        await db.upsert_jobs([LONG_JOB])
        found = await db.get_job_by_ref(job_ref(LONG_JOB.job_id))
        await db.close()
        return found

    found = asyncio.run(run())
    assert found is not None
    assert found.job_id == LONG_JOB.job_id


def test_old_database_is_migrated_without_crashing(tmp_path):
    """A v1.5 database has no job_ref column - the bot must still start."""
    import sqlite3

    path = str(tmp_path / "old.db")
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE jobs (
            job_id TEXT PRIMARY KEY, url TEXT NOT NULL, title TEXT NOT NULL,
            last_date TEXT, first_seen TEXT NOT NULL,
            detail_fetched INTEGER NOT NULL DEFAULT 0, detail_json TEXT);
        INSERT INTO jobs VALUES ('/old-job-2026/', 'https://x/y',
            'Old Job 2026', '25/11/2026', '2026-10-01', 0, NULL);
        """
    )
    conn.commit()
    conn.close()

    async def run():
        db = Database(path)
        await db.connect()
        found = await db.get_job_by_ref(job_ref("/old-job-2026/"))
        await db.upsert_jobs([JobSummary("/new-job-2026/", "New Job",
                                         "https://x/z", "30/11/2026")])
        fresh = await db.get_job_by_ref(job_ref("/new-job-2026/"))
        await db.close()
        return found, fresh

    found, fresh = asyncio.run(run())
    assert found is not None, "the old row was not migrated"
    assert found.job_id == "/old-job-2026/"
    assert fresh is not None


def test_legacy_base64_buttons_still_work(tmp_path):
    """Buttons sent by an older version must keep working after the update."""
    import base64

    db = Database(str(tmp_path / "legacy.db"))

    async def run():
        await db.connect()
        await db.upsert_jobs([JOB])
        legacy = base64.urlsafe_b64encode(JOB.job_id.encode()).rstrip(b"=").decode()
        found = await db.get_job_by_ref(legacy)
        await db.close()
        return found

    assert asyncio.run(run()) is not None


# ------------------------------------------------------------- 6. web app
def test_web_app_uses_the_platform_port():
    """The dashboard must listen on the port the public URL reaches."""
    assert config.WEB_APP_PORT == config.PORT


def test_web_app_serves_health(tmp_path):
    """The dashboard needs the optional web requirements (CI installs only
    the core ones), so the test is skipped when they are missing."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from bot.webapp import create_app

    class FakeApp:
        def __init__(self):
            self.bot_data = {"db": None}

    client = TestClient(create_app(FakeApp()))
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


# -------------------------------------------------------- 7. source chain
def test_source_chain_has_several_fallbacks():
    assert config.SOURCE_ORDER[0] == "mirror"
    assert "mirror-jina" in config.SOURCE_ORDER
    assert "original" in config.SOURCE_ORDER
    assert len(config.SOURCE_ORDER) >= 3


def test_listing_sources_parse_the_mirror():
    import bot.scraper as scraper

    assert hasattr(scraper, "parse_mirror_listing_markdown")
    assert hasattr(scraper.SarkariScraper, "fetch_section")
    assert hasattr(scraper.SarkariScraper, "_fetch_listing_from_source")


def test_mirror_markdown_parser_reads_the_reader_proxy():
    """The reader proxy returns markdown bullets, not HTML."""
    from bot.scraper import parse_mirror_listing_markdown

    markdown = (
        "* [Railway RRB Station Master 2026](https://sarkariresult.com.cm/"
        "railway-rrb-station-master-2026/) \u2013 Last Date: 25 November 2026\n"
        "* [Some Category Page](https://sarkariresult.com.cm/category/jobs/)\n"
    )
    jobs = parse_mirror_listing_markdown(markdown, "https://sarkariresult.com.cm")
    assert len(jobs) == 1
    assert jobs[0].title.startswith("Railway RRB Station Master 2026")
    assert jobs[0].last_date == "25/11/2026"


# --------------------------------------------------- v1.6.1 (deploy + polish)
def test_why_command_is_personalised_and_lint_clean(tmp_path):
    """/why explains what the bot does FOR THIS user."""
    from telegram.ext import Application

    from bot import handlers
    from tests.test_markdown_lint import lint_markdown_v2

    recorder = _Recorder()
    orig = _patch_bot(recorder)
    try:
        async def run():
            app = Application.builder().token("123:TEST").build()
            db = Database(str(tmp_path / "why.db"))
            await db.connect()
            await db.upsert_user(555, "rahul", "Rahul", "OBC", "graduate",
                                 ["railway"], "15/08/2000", ["b_ed"], ["aadhaar"])
            await db.upsert_jobs([JOB])
            app.bot_data["db"] = db
            update = _user()
            update.set_bot(app.bot)
            update.message.set_bot(app.bot)
            context = app.context_types.context.from_update(update, app)
            await handlers.why_useful(update, context)
            await db.close()
        asyncio.run(run())
    finally:
        _restore_bot(orig)
    assert recorder.sent, "/why did not answer"
    text = recorder.sent[-1][1]
    assert "useful for you" in text
    assert "OBC" in text
    problems = lint_markdown_v2(text)
    assert not problems, problems


def test_health_server_listens_on_exactly_one_port(monkeypatch):
    """Voroa aborts the deploy when the service listens on more than one port."""
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
    monkeypatch.setattr(bot_main.config, "PORT", 8080)
    monkeypatch.setattr(bot_main.config, "ENABLE_WEB_APP", False)
    bot_main._RUNTIME.pop("health_servers", None)
    bot_main._start_health_servers()
    assert started == [8080], started


def test_listing_is_capped_per_source(monkeypatch):
    """A source that serves the whole archive must not flood the catalogue."""
    import asyncio

    import bot.scraper as scraper

    monkeypatch.setattr(scraper.config, "MAX_LISTING_JOBS", 5)

    class _FakeScraper(scraper.SarkariScraper):
        def __init__(self):
            self.status = {}

        async def _get(self, url):
            return "<html><body></body></html>"

    fake = _FakeScraper()
    # 50 jobs come back from the parser -> only the 5 newest are kept
    monkeypatch.setattr(scraper, "parse_mirror_listing_html",
                        lambda html, url: [JobSummary(f"/job-{i}/", f"Job {i}",
                                                      "https://x/y", None)
                                           for i in range(50)])
    jobs = asyncio.run(fake._fetch_listing_from_source("mirror"))
    assert len(jobs) == 5


def test_merge_sweep_combines_every_reachable_source():
    """The sweep makes sure a notice only one source carries is not missed."""
    import asyncio

    import bot.scraper as scraper

    class _FakeScraper(scraper.SarkariScraper):
        def __init__(self):
            self.status = {}
            self.calls = []

        async def _fetch_listing_from_source(self, source):
            self.calls.append(source)
            if source == "mirror":
                return [JobSummary("/a/", "A", "https://x/a", None)]
            if source == "mirror-jina":
                return [JobSummary("/a/", "A", "https://x/a", None),
                        JobSummary("/b/", "B", "https://x/b", None)]
            raise scraper.ScraperError("blocked")

    fake = _FakeScraper()
    import bot.config as config
    old_order = config.SOURCE_ORDER
    config.SOURCE_ORDER = ["mirror", "mirror-jina", "original"]
    try:
        merged = asyncio.run(fake.fetch_latest_jobs(merge_all=True))
    finally:
        config.SOURCE_ORDER = old_order
    ids = {job.job_id for job in merged}
    assert ids == {"/a/", "/b/"}
    assert "original" in fake.calls


def test_sticker_greeting_is_optional(monkeypatch):
    """Without a sticker configured the bot just does not send one."""
    from bot import stickers

    monkeypatch.setattr(stickers.config, "WELCOME_STICKER_FILE_ID", "")
    monkeypatch.setattr(stickers.config, "STICKER_SET_NAME", "")

    class _Bot:
        async def send_sticker(self, **kwargs):
            raise AssertionError("no sticker is configured")

    assert asyncio.run(stickers.welcome_sticker(_Bot(), 1)) is None

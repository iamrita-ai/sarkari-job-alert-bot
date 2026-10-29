"""Every message the onboarding sends must be valid MarkdownV2.

Telegram rejects a whole message with 400 Bad Request when a single
reserved character ('+', '.', '-', '(' ...) is not escaped - the message
simply never arrives. This test drives the real flow and lints every
single outgoing text.
"""
import asyncio

import pytest
from telegram import CallbackQuery, Chat, Message, Update, User
from telegram.ext import Application, ExtBot

from bot import handlers
from bot.db import Database
from tests.test_markdown_lint import lint_markdown_v2

USER = User(id=888, first_name="Test", username="tester", is_bot=False)
CHAT = Chat(id=666, type=Chat.PRIVATE)


class _Capture:
    """Records every outgoing text together with its parse mode."""

    def __init__(self):
        self.texts: list = []

    def _add(self, text, kwargs):
        self.texts.append((text, kwargs.get("parse_mode")))

    async def send_message(self, chat_id, text, **kwargs):
        self._add(text, kwargs)
        return Message(message_id=1, date=None, chat=CHAT, from_user=USER, text=text)

    async def reply_text(self, chat_id, text, **kwargs):
        self._add(text, kwargs)
        return Message(message_id=1, date=None, chat=CHAT, from_user=USER, text=text)

    async def reply_markdown_v2(self, chat_id, text, **kwargs):
        self._add(text, {"parse_mode": "MarkdownV2", **kwargs})
        return Message(message_id=1, date=None, chat=CHAT, from_user=USER, text=text)

    async def edit_message_text(self, *args, **kwargs):
        text = args[0] if args else kwargs.get("text", "")
        self._add(text, kwargs)
        return Message(message_id=1, date=None, chat=CHAT, from_user=USER, text="x")

    async def edit_message_reply_markup(self, *args, **kwargs):
        return True

    async def answer_callback_query(self, *args, **kwargs):
        return True

    async def initialize(self, *args, **kwargs):
        return None


@pytest.fixture()
def capture(monkeypatch):
    cap = _Capture()
    for name in ("send_message", "reply_text", "reply_markdown_v2",
                 "edit_message_text", "edit_message_reply_markup",
                 "answer_callback_query", "initialize"):
        monkeypatch.setattr(ExtBot, name, getattr(cap, name), raising=False)
    return cap


@pytest.fixture()
def app(tmp_path):
    async def build():
        application = Application.builder().token("123:TEST").build()
        database = Database(str(tmp_path / "lint.db"))
        await database.connect()
        application.bot_data["db"] = database
        application.bot_data["bot_username"] = "jobtestbot"
        application.bot_data["browsers"] = {}
        application.bot_data["saved_browsers"] = {}
        application.bot_data["owner_chat_ids"] = set()
        application.bot_data["admin_users"] = {}
        handlers.register_handlers(application)
        return application

    application = asyncio.run(build())
    yield application
    asyncio.run(application.bot_data["db"].close())


def _text_update(text: str, update_id: int) -> Update:
    return Update(update_id=update_id, message=Message(
        message_id=update_id, date=None, chat=CHAT, from_user=USER, text=text))


def _callback_update(data: str, update_id: int) -> Update:
    query = CallbackQuery(
        id=str(update_id), from_user=USER, chat_instance="ci", data=data,
        message=Message(message_id=100 + update_id, date=None, chat=CHAT,
                        from_user=USER, text="menu"),
    )
    return Update(update_id=update_id, callback_query=query)


async def _dispatch(app: Application, update: Update) -> None:
    update.set_bot(app.bot)
    for nested in (update.message, update.callback_query,
                   getattr(update.callback_query, "message", None)):
        if nested is not None:
            nested.set_bot(app.bot)
    context = app.context_types.context.from_update(update, app)
    for group in app.handlers.values():
        for handler in group:
            check = handler.check_update(update)
            if check is None or check is False:
                continue
            await handler.handle_update(update, app, check, context)
            break


def test_onboarding_messages_are_valid_markdown_v2(app, capture):
    """Not one message of the setup flow may be rejected by Telegram."""
    async def run():
        await _dispatch(app, _text_update("/start", 1))
        await _dispatch(app, _callback_update("start:begin", 2))
        await _dispatch(app, _text_update("Smoke Tester", 3))
        await _dispatch(app, _text_update("15/08/2000", 4))
        await _dispatch(app, _callback_update("cat:OBC", 5))
        await _dispatch(app, _callback_update("deg:iti", 6))
        await _dispatch(app, _callback_update("deg:done", 7))
        await _dispatch(app, _callback_update("doc:aadhaar", 8))
        await _dispatch(app, _callback_update("doc:done", 9))
        await _dispatch(app, _callback_update("sec:railway", 10))
        await _dispatch(app, _callback_update("sec:done", 11))

    asyncio.run(run())
    assert capture.texts, "no message was sent at all"
    problems: list[str] = []
    for text, mode in capture.texts:
        if mode != "MarkdownV2":
            continue  # plain text needs no escaping
        for issue in lint_markdown_v2(text):
            problems.append(f"{issue} :: {text[:120]!r}")
    assert not problems, "\n".join(problems)


def test_edit_menu_messages_are_valid_markdown_v2(app, capture):
    """The /edit menu must be valid MarkdownV2 as well."""
    async def run():
        await _dispatch(app, _text_update("/start", 1))
        await _dispatch(app, _callback_update("start:begin", 2))
        await _dispatch(app, _text_update("Smoke Tester", 3))
        await _dispatch(app, _text_update("15/08/2000", 4))
        await _dispatch(app, _callback_update("cat:OBC", 5))
        await _dispatch(app, _callback_update("deg:iti", 6))
        await _dispatch(app, _callback_update("deg:done", 7))
        await _dispatch(app, _callback_update("doc:aadhaar", 8))
        await _dispatch(app, _callback_update("doc:done", 9))
        await _dispatch(app, _callback_update("sec:railway", 10))
        await _dispatch(app, _callback_update("sec:done", 11))
        # now the profile exists -> open the edit menu and every sub-menu
        await _dispatch(app, _text_update("/edit", 12))
        await _dispatch(app, _callback_update("pe:category", 13))
        await _dispatch(app, _callback_update("cat:SC", 14))
        await _dispatch(app, _callback_update("pe:degrees", 15))
        await _dispatch(app, _callback_update("deg:iti", 16))
        await _dispatch(app, _callback_update("deg:done", 17))
        await _dispatch(app, _callback_update("pe:documents", 18))
        await _dispatch(app, _callback_update("doc:aadhaar", 19))
        await _dispatch(app, _callback_update("doc:done", 20))
        await _dispatch(app, _callback_update("pe:close", 21))

    asyncio.run(run())
    problems: list[str] = []
    for text, mode in capture.texts:
        if mode != "MarkdownV2":
            continue  # plain text needs no escaping
        for issue in lint_markdown_v2(text):
            problems.append(f"{issue} :: {text[:120]!r}")
    assert not problems, "\n".join(problems)


OWNER = User(id=999, first_name="Owner", username="technicalserena", is_bot=False)


def test_owner_and_digest_messages_are_valid_markdown_v2(app, capture, monkeypatch):
    """The owner commands and the daily digest must be valid MarkdownV2 too."""
    from bot import config

    monkeypatch.setattr(config, "OWNER_USERNAMES", {"technicalserena"})

    async def run():
        for index, command in enumerate(["/help", "/about", "/profile", "/saved",
                                         "/sources", "/stats", "/users", "/digest"],
                                        start=30):
            update = Update(update_id=index, message=Message(
                message_id=index, date=None, chat=CHAT, from_user=OWNER,
                text=command))
            update.set_bot(app.bot)
            update.message.set_bot(app.bot)
            context = app.context_types.context.from_update(update, app)
            for group in app.handlers.values():
                for handler in group:
                    check = handler.check_update(update)
                    if check is None or check is False:
                        continue
                    await handler.handle_update(update, app, check, context)
                    break

    asyncio.run(run())
    problems: list[str] = []
    for text, mode in capture.texts:
        if mode != "MarkdownV2":
            continue
        for issue in lint_markdown_v2(text):
            problems.append(f"{issue} :: {text[:140]!r}")
    assert not problems, "\n".join(problems)


def test_daily_digest_is_valid_markdown_v2(app, capture):
    """The daily digest is sent every morning - it must never be rejected."""
    from bot.digest import build_digest
    from bot.models import JobSummary, UserProfile

    profile = UserProfile(
        user_id=888, username="tester", full_name="Smoke Tester", category="OBC",
        qualification="graduate", sectors=["railway"], dob="15/08/2000",
        degrees=["iti"], documents=["aadhaar"],
    )

    async def run():
        await app.bot_data["db"].upsert_user(
            user_id=profile.user_id, username=profile.username,
            full_name=profile.full_name, category=profile.category,
            qualification=profile.qualification, sectors=profile.sectors,
            dob=profile.dob, degrees=profile.degrees,
            documents=profile.documents,
        )
        await app.bot_data["db"].upsert_jobs([JobSummary(
            job_id="/railway-alert-2026/",
            title="Railway Recruitment 2026 - Apply Online",
            url="https://sarkariresult.com.cm/railway-alert-2026/",
            last_date="25/11/2026",
        )])
        text = await build_digest(app, profile)
        assert text, "the digest was empty"
        capture.texts.append((text, "MarkdownV2"))

    asyncio.run(run())
    problems: list[str] = []
    for text, mode in capture.texts:
        if mode != "MarkdownV2":
            continue
        for issue in lint_markdown_v2(text):
            problems.append(f"{issue} :: {text[:140]!r}")
    assert not problems, "\n".join(problems)

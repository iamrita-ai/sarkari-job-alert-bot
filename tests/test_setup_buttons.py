"""Setup buttons must ALWAYS answer (v1.5.3).

The reservation (category) buttons are the most important buttons of the
bot - a dead button there means the user can never create a profile. These
tests drive the real dispatcher and check every situation:

* a normal onboarding run,
* a tap without a live conversation (after a restart / on an old keyboard),
* a message that Telegram refuses to edit (older than 48 h),
* an existing profile (the tap must edit it, not create a second one).
"""
import asyncio

import pytest
from telegram import CallbackQuery, Chat, Message, Update, User
from telegram.error import BadRequest
from telegram.ext import Application, ExtBot

from bot import handlers
from bot.db import Database

USER = User(id=777, first_name="Test", username="tester", is_bot=False)
CHAT = Chat(id=555, type=Chat.PRIVATE)


class _Recorder:
    """Records everything the bot sends."""

    def __init__(self):
        self.messages: list = []
        self.edits: list = []
        self.answers: list = []
        self.fail_edits = False

    async def send_message(self, chat_id, text, **kwargs):
        self.messages.append((chat_id, text, kwargs))
        return Message(message_id=len(self.messages), date=None, chat=CHAT,
                       from_user=USER, text=text)

    async def reply_text(self, chat_id, text, **kwargs):
        self.messages.append((chat_id, text, kwargs))
        return Message(message_id=len(self.messages), date=None, chat=CHAT,
                       from_user=USER, text=text)

    async def edit_message_text(self, *args, **kwargs):
        if self.fail_edits:
            raise BadRequest("Message can't be edited")
        self.edits.append((args, kwargs))
        return Message(message_id=1, date=None, chat=CHAT, from_user=USER, text="x")

    async def edit_message_reply_markup(self, *args, **kwargs):
        if self.fail_edits:
            raise BadRequest("Message can't be edited")
        self.edits.append((args, kwargs))
        return True

    async def answer_callback_query(self, *args, **kwargs):
        self.answers.append((args, kwargs))
        return True

    async def initialize(self, *args, **kwargs):
        return None


@pytest.fixture()
def rec(monkeypatch):
    recorder = _Recorder()
    monkeypatch.setattr(ExtBot, "send_message", recorder.send_message, raising=False)
    monkeypatch.setattr(ExtBot, "reply_text", recorder.reply_text, raising=False)
    monkeypatch.setattr(ExtBot, "edit_message_text", recorder.edit_message_text,
                        raising=False)
    monkeypatch.setattr(ExtBot, "edit_message_reply_markup",
                        recorder.edit_message_reply_markup, raising=False)
    monkeypatch.setattr(ExtBot, "answer_callback_query", recorder.answer_callback_query,
                        raising=False)
    monkeypatch.setattr(ExtBot, "initialize", recorder.initialize, raising=False)
    return recorder


@pytest.fixture()
def app(tmp_path):
    async def build():
        application = Application.builder().token("123:TEST").build()
        database = Database(str(tmp_path / "buttons.db"))
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


async def _dispatch(app: Application, update: Update) -> bool:
    update.set_bot(app.bot)
    for nested in (update.message, update.callback_query,
                   getattr(update.callback_query, "message", None)):
        if nested is not None:
            nested.set_bot(app.bot)
    context = app.context_types.context.from_update(update, app)
    handled = False
    for group in app.handlers.values():
        for handler in group:
            check = handler.check_update(update)
            if check is None or check is False:
                continue
            await handler.handle_update(update, app, check, context)
            handled = True
            break
    return handled


def test_category_button_works_in_a_normal_run(app, rec):
    """The happy path: onboarding -> category -> degrees."""
    async def run():
        await _dispatch(app, _callback_update("start:begin", 1))
        await _dispatch(app, _text_update("Smoke Tester", 2))
        await _dispatch(app, _text_update("15/08/2000", 3))
        handled = await _dispatch(app, _callback_update("cat:OBC", 4))
        assert handled, "the category button was not handled"
        assert rec.answers, "the button press was never acknowledged"
        assert any("degree" in str(payload).lower() for payload in rec.edits), rec.edits

    asyncio.run(run())


def test_category_button_works_without_a_live_conversation(app, rec):
    """Old keyboard / after a restart: the tap must answer and continue."""
    async def run():
        handled = await _dispatch(app, _callback_update("cat:OBC", 1))
        assert handled, "the orphaned category button was ignored"
        assert rec.answers, "the button press was never acknowledged"
        assert rec.messages, "the user got no answer at all"
        text = " ".join(str(m[1]) for m in rec.messages)
        assert "OBC" in text, text
        assert "name" in text.lower(), text

    asyncio.run(run())


def test_category_button_works_when_the_message_cannot_be_edited(app, rec):
    """Telegram refuses to edit messages older than 48 h - we send a new one."""
    rec.fail_edits = True

    async def run():
        await _dispatch(app, _callback_update("start:begin", 1))
        await _dispatch(app, _text_update("Smoke Tester", 2))
        await _dispatch(app, _text_update("15/08/2000", 3))
        handled = await _dispatch(app, _callback_update("cat:OBC", 4))
        assert handled
        assert rec.answers, "the button press was never acknowledged"
        assert rec.messages, "the user got no answer - the button looks dead"
        assert any("degree" in str(m[1]).lower() for m in rec.messages), rec.messages

    asyncio.run(run())


def test_category_button_updates_an_existing_profile(app, rec):
    """A returning user taps a category -> the profile is updated."""
    async def seed():
        await app.bot_data["db"].upsert_user(
            user_id=USER.id, username=USER.username, full_name="Smoke Tester",
            category="UR", qualification="graduate", sectors=["railway"],
            dob="15/08/2000", degrees=["graduation"], documents=["aadhaar"],
        )

    asyncio.run(seed())

    async def run():
        handled = await _dispatch(app, _callback_update("cat:OBC", 1))
        assert handled
        assert rec.answers, "the button press was never acknowledged"
        profile = await app.bot_data["db"].get_user(USER.id)
        assert profile.category == "OBC", profile.category

    asyncio.run(run())


def test_every_setup_button_answers(app, rec):
    """cat / deg / doc / sec must never be swallowed silently."""
    async def run():
        for index, data in enumerate(["cat:OBC", "deg:iti", "doc:aadhaar",
                                      "sec:railway"], start=1):
            before = len(rec.answers)
            await _dispatch(app, _callback_update(data, index))
            assert len(rec.answers) > before, f"{data} was not acknowledged"

    asyncio.run(run())

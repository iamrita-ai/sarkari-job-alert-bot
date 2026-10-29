"""Real PTB dispatch tests - drive the whole handler chain like Telegram does.

These catch the class of bug where a handler works when called directly but
is never reached by the dispatcher (that is exactly what broke the
reservation-category button: the conversation state machine never advanced).
"""
import asyncio

import pytest
import telegram
from telegram import CallbackQuery, Chat, Message, Update, User
from telegram.ext import Application, ExtBot

from bot import handlers
from bot.db import Database

CHAT = Chat(id=555, type=Chat.PRIVATE)
USER = User(id=777, first_name="Test", username="tester", is_bot=False)
BOT = telegram.User(id=1, first_name="JobBot", username="jobtestbot", is_bot=True)


@pytest.fixture()
def fake_bot(monkeypatch):
    """Patch every network call of ExtBot and record what was sent."""
    calls: dict = {"messages": [], "edits": [], "answers": [], "photos": []}

    async def fake_initialize(self, *args, **kwargs):
        # ExtBot is frozen (slots) - simply skip the network handshake.
        return None

    async def fake_get_me(self, *args, **kwargs):
        return BOT

    async def fake_send_message(self, chat_id, text, **kwargs):
        calls["messages"].append((chat_id, text, kwargs))
        return Message(message_id=len(calls["messages"]), date=None, chat=CHAT,
                       from_user=BOT, text=text)

    async def fake_edit_message_text(self, *args, **kwargs):
        calls["edits"].append((args, kwargs))
        return Message(message_id=1, date=None, chat=CHAT, from_user=BOT, text="x")

    async def fake_answer_callback_query(self, *args, **kwargs):
        calls["answers"].append((args, kwargs))
        return True

    async def fake_send_photo(self, *args, **kwargs):
        calls["photos"].append((args, kwargs))
        return Message(message_id=1, date=None, chat=CHAT, from_user=BOT, text="x")

    async def fake_edit_message_reply_markup(self, *args, **kwargs):
        calls["edits"].append((args, kwargs))
        return True

    async def fake_edit_message_text(self, *args, **kwargs):  # noqa: F811
        calls["edits"].append((args, kwargs))
        return Message(message_id=1, date=None, chat=CHAT, from_user=BOT, text="x")

    monkeypatch.setattr(ExtBot, "initialize", fake_initialize, raising=False)
    monkeypatch.setattr(ExtBot, "get_me", fake_get_me, raising=False)
    monkeypatch.setattr(ExtBot, "send_message", fake_send_message, raising=False)
    monkeypatch.setattr(ExtBot, "edit_message_text", fake_edit_message_text, raising=False)
    monkeypatch.setattr(ExtBot, "answer_callback_query", fake_answer_callback_query,
                        raising=False)
    monkeypatch.setattr(ExtBot, "send_photo", fake_send_photo, raising=False)
    monkeypatch.setattr(ExtBot, "edit_message_reply_markup", fake_edit_message_reply_markup,
                        raising=False)
    return calls


async def _dispatch(app: Application, update: Update) -> bool:
    """Mimic Application.process_update (PTB v22 signature)."""
    update.set_bot(app.bot)
    for nested in (update.message, update.callback_query,
                   getattr(update.callback_query, "message", None)):
        if nested is not None:
            nested.set_bot(app.bot)
    context = app.context_types.context.from_update(update, app)
    handled = False
    for group in app.handlers.values():
        # PTB: every group is evaluated, but only ONE handler per group runs
        for handler in group:
            check = handler.check_update(update)
            if check is None or check is False:
                continue
            await handler.handle_update(update, app, check, context)
            handled = True
            break
    return handled


def _text_update(text: str, update_id: int) -> Update:
    return Update(update_id=update_id, message=Message(
        message_id=update_id, date=None, chat=CHAT, from_user=USER, text=text))


def _callback_update(data: str, update_id: int) -> Update:
    query = CallbackQuery(
        id=str(update_id), from_user=USER, chat_instance="ci",
        data=data,
        message=Message(message_id=100 + update_id, date=None, chat=CHAT,
                        from_user=USER, text="menu"),
    )
    return Update(update_id=update_id, callback_query=query)


@pytest.fixture()
def app(tmp_path, fake_bot):
    async def build():
        application = Application.builder().token("123:TEST").build()
        database = Database(str(tmp_path / "dispatch.db"))
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


def test_reservation_category_button_is_reachable(app, fake_bot):
    """The category button must be handled by the conversation, not ignored."""
    asyncio.run(_run_category_flow(app, fake_bot))


async def _run_category_flow(app, fake_bot):
    user = app.bot_data  # noqa: F841 - readability
    await _dispatch(app, _callback_update("start:begin", 1))
    await _dispatch(app, _text_update("Smoke Tester", 2))
    await _dispatch(app, _text_update("15/08/2000", 3))

    # the category keyboard was offered
    assert any("category" in str(text).lower()
               for _, text, _ in fake_bot["messages"]), fake_bot["messages"]

    handled = await _dispatch(app, _callback_update("cat:OBC", 4))
    assert handled, "the category button was not handled by any handler"
    assert fake_bot["answers"], "the button press was never acknowledged"
    # the conversation moved on to the degrees step
    assert any("degree" in str(payload).lower() for payload in fake_bot["edits"]), \
        fake_bot["edits"]

    # finish the flow
    for step, data in enumerate(["deg:iti", "deg:done", "doc:aadhaar",
                                  "doc:done", "sec:railway", "sec:done"], start=5):
        await _dispatch(app, _callback_update(data, step))

    profile = await app.bot_data["db"].get_user(777)
    assert profile is not None, "no profile was created"
    assert profile.category == "OBC", profile.category
    assert profile.dob == "15/08/2000"
    assert profile.degrees == ["iti"]
    assert profile.documents == ["aadhaar"]
    assert profile.sectors == ["railway"]

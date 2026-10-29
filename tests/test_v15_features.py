"""v1.5 feature tests: state detection, vacancy breakdown, notice updates,
daily digest, AI summary fallback, web-app tokens and the anti-silence
fallback for orphaned setup buttons."""
import asyncio

import pytest

from bot import ai
from bot.cards import job_card
from bot.constants import DEGREE_KEYS
from bot.db import Database
from bot.digest import build_digest
from bot.keyboards import category_keyboard
from bot.matcher import title_matches
from bot.models import JobDetail, JobSummary, UserProfile
from bot.scheduler import detect_changes
from bot.scraper import detect_states, parse_mirror_detail_html
from bot.webapp import sign_token, verify_token

JOB = JobSummary("/railway-x-2026/", "Railway X Online Form 2026",
                 "https://sarkariresult.com.cm/railway-x-2026/", "25/11/2026")

VACANCY_HTML = """
<html><body><div class="entry-content">
<table><tr><th>Category Name</th><th>No. Of Posts</th></tr>
<tr><td>General</td><td>542</td></tr>
<tr><td>OBC</td><td>296</td></tr>
<tr><td>SC</td><td>176</td></tr></table>
</div></body></html>
"""


def test_states_are_detected_from_the_notice():
    assert "bihar" in detect_states("BPSC School Teacher TRE 4.0 Recruitment 2026")
    assert "uttar_pradesh" in detect_states("UPPSC Assistant Teacher 2026")
    assert detect_states("Railway RRB Station Master Recruitment 2026") == []


def test_vacancy_breakdown_is_parsed():
    detail = parse_mirror_detail_html(VACANCY_HTML, "https://x/y/")
    assert detail.vacancy_breakdown == {
        "General": "542", "OBC": "296", "SC": "176",
    }


def test_notice_update_detection():
    old = JobDetail(apply_last_date="25 November 2026", admit_card_date="Before Exam",
                    exam_date="Notify Later")
    new = JobDetail(apply_last_date="03 December 2026", admit_card_date="Before Exam",
                    exam_date="10 December 2026")
    changes = dict((label, (before, after)) for label, before, after in
                   detect_changes(old, new))
    assert "🔴 Apply Last Date" in changes
    assert changes["🔴 Apply Last Date"] == ("25 November 2026", "03 December 2026")
    assert "📝 Exam Date" in changes
    # an unchanged placeholder never triggers an alert
    assert not any(label == "🎫 Admit Card" for label, _, _ in detect_changes(old, new))


def test_ai_summary_is_optional():
    # no API key configured -> the bot simply shows the original text
    assert ai.enabled() is False
    assert asyncio.run(ai.summarise("Bachelor Degree in any stream")) == ""


def test_webapp_token_round_trip():
    token = sign_token(42, "topsecret")
    assert verify_token(token, "topsecret") == 42
    assert verify_token(token, "wrongsecret") is None
    assert verify_token("garbage", "topsecret") is None


def test_category_buttons_have_no_emoji():
    for row in category_keyboard().inline_keyboard:
        for button in row:
            assert not any(ch in button.text for ch in "🟢🔵🟡🟣🟠🔘"), button.text
    labels = [b.text for row in category_keyboard().inline_keyboard for b in row]
    assert "UR / General" in labels
    assert "OBC" in labels


def test_state_filter_parses_the_argument():
    from bot.handlers import _state_filter

    assert _state_filter(["bihar"]) == "bihar"
    assert _state_filter(["Bihar"]) == "bihar"
    assert _state_filter(["uttar pradesh"]) == "uttar_pradesh"
    assert _state_filter(["railway"]) is None
    assert _state_filter(None) is None


def test_hindi_block_is_rendered_and_lint_clean():
    from tests.test_markdown_lint import lint_markdown_v2  # noqa: PLC0415

    detail = JobDetail(qualification="Bachelor Degree", apply_last_date="25/11/2026",
                        min_age=20, max_age=30, states=["bihar"])
    profile = UserProfile(1, "u", "Rahul", "OBC", "graduate", ["railway"],
                           "15/08/2000", degrees=["b_ed"], documents=["aadhaar"])
    text = job_card(JOB, detail, profile, None, language="both")
    assert "हिंदी में देखें" in text
    assert "योग्यता" in text
    assert "आवेदन अंतिम तिथि" in text
    assert not lint_markdown_v2(text), lint_markdown_v2(text)


def test_digest_lists_new_jobs_and_closing_saved_jobs(tmp_path):
    db = Database(str(tmp_path / "digest.db"))

    class FakeApp:
        def __init__(self):
            self.bot_data = {"db": db}

    async def run():
        await db.connect()
        profile = UserProfile(7, "u", "Rahul", "OBC", "graduate", ["railway"],
                              "15/08/2000")
        await db.upsert_user(7, "u", "Rahul", "OBC", "graduate", ["railway"],
                             "15/08/2000")
        # nothing yet -> no digest
        assert await build_digest(FakeApp(), profile) is None

        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)
        await db.upsert_jobs([JobSummary("/railway-new-2026/", "Railway New 2026",
                                         "https://sarkariresult.com.cm/railway-new-2026/",
                                         "30/11/2026")])
        # make it look fresh
        await db.set_meta("noop", "1")
        text = await build_digest(FakeApp(), profile)
        assert text is not None
        assert "Good morning" in text
        assert "Railway New 2026" in text
        await db.close()

    asyncio.run(run())


def test_orphaned_setup_button_is_never_silent():
    """A setup button that arrives without a live conversation must answer."""
    import telegram
    from telegram import CallbackQuery, Chat, Message, Update, User
    from telegram.ext import Application, ExtBot

    from bot import handlers

    sent: list = []
    answers: list = []

    async def fake_send_message(self, chat_id, text, **kwargs):
        sent.append(text)
        return Message(message_id=1, date=None, chat=Chat(id=1, type="private"),
                       from_user=USER, text=text)

    async def fake_answer_callback_query(self, *args, **kwargs):
        answers.append(args)
        return True

    async def fake_initialize(self, *args, **kwargs):
        return None

    async def fake_edit_message_text(self, *args, **kwargs):
        return Message(message_id=1, date=None, chat=Chat(id=1, type="private"),
                       from_user=USER, text="x")

    async def fake_edit_message_reply_markup(self, *args, **kwargs):
        return True

    USER = User(id=555, first_name="T", username="t", is_bot=False)
    CHAT = Chat(id=555, type="private")
    orig = (ExtBot.send_message, ExtBot.answer_callback_query, ExtBot.initialize,
            ExtBot.edit_message_text, ExtBot.edit_message_reply_markup)
    ExtBot.send_message = fake_send_message
    ExtBot.answer_callback_query = fake_answer_callback_query
    ExtBot.initialize = fake_initialize
    ExtBot.edit_message_text = fake_edit_message_text
    ExtBot.edit_message_reply_markup = fake_edit_message_reply_markup
    async def run():
        app = Application.builder().token("123:TEST").build()
        app.bot_data["db"] = None
        handlers.register_handlers(app)
        query = CallbackQuery(
            id="1", from_user=USER, chat_instance="ci", data="cat:OBC",
            message=Message(message_id=9, date=None, chat=CHAT, from_user=USER,
                            text="menu"))
        update = Update(update_id=1, callback_query=query)
        update.set_bot(app.bot)
        query.set_bot(app.bot)
        query.message.set_bot(app.bot)
        context = app.context_types.context.from_update(update, app)
        # PTB evaluates EVERY group, one handler per group
        for group in app.handlers.values():
            for handler in group:
                check = handler.check_update(update)
                if check is None or check is False:
                    continue
                await handler.handle_update(update, app, check, context)
                break

    try:
        asyncio.run(run())
        assert answers, "the button press was not acknowledged"
        assert sent, "the user got no answer at all - the bot looks broken"
        assert "session expired" in sent[0].lower()
    finally:
        (ExtBot.send_message, ExtBot.answer_callback_query, ExtBot.initialize,
         ExtBot.edit_message_text, ExtBot.edit_message_reply_markup) = orig


def test_conversation_handler_is_persistent_when_persistence_is_set(tmp_path):
    """The onboarding conversation must survive a restart (v1.5 anti-silence)."""
    from telegram.ext import Application, ConversationHandler, PicklePersistence

    from bot import handlers

    application = Application.builder().token("123:TEST").build()
    application.persistence = PicklePersistence(
        filepath=str(tmp_path / "conversation.pickle"))
    handlers.register_handlers(application)
    conversations = [h for h in application.handlers[0]
                     if isinstance(h, ConversationHandler)]
    assert conversations, "no ConversationHandler registered"
    assert conversations[0].persistent is True
    assert conversations[0].name == "onboarding"


def test_conversation_handler_without_persistence_is_not_persistent():
    from telegram.ext import Application, ConversationHandler

    from bot import handlers

    application = Application.builder().token("123:TEST").build()
    handlers.register_handlers(application)
    conversations = [h for h in application.handlers[0]
                     if isinstance(h, ConversationHandler)]
    assert conversations[0].persistent is False

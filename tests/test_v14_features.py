"""v1.4 feature tests: multi-select degrees/documents, rich cards, coloured
buttons, the owner /users browser and the browser-callback registration that
makes the Next button work again."""
import asyncio

import pytest

from bot.cards import (
    admin_user_card,
    full_detail_text,
    job_card,
    photo_caption,
    profile_card,
)
from bot.constants import DEGREE_KEYS, DOCUMENT_KEYS
from bot.db import Database
from bot.handlers import format_sources_report
from bot.keyboards import (
    admin_profile_keyboard,
    admin_users_keyboard,
    browse_keyboard,
    category_keyboard,
    degrees_keyboard,
    documents_keyboard,
    job_detail_keyboard,
    main_menu_keyboard,
    profile_edit_keyboard,
    reminder_keyboard,
    saved_browse_keyboard,
    sectors_keyboard,
)
from bot.matcher import (
    detect_degree_keys,
    detect_documents,
    document_gaps,
    qualification_matches,
)
from bot.models import JobDetail, JobSummary, UserProfile

JOB = JobSummary("/railway-x-2026", "Railway X Online Form 2026",
                 "https://sarkariresult.com.cm/railway-x-2026/", "25/11/2026")


def _profile(**kwargs) -> UserProfile:
    base = dict(
        user_id=1, username="u", full_name="Rahul", category="OBC",
        qualification="graduate", sectors=["railway"], dob="15/08/2000",
        degrees=["b_ed"], documents=["aadhaar", "caste_certificate"],
    )
    base.update(kwargs)
    return UserProfile(**base)


# ------------------------------------------------------------------ storage
def test_sqlite_stores_degrees_and_documents(tmp_path):
    db = Database(str(tmp_path / "t.db"))

    async def run():
        await db.connect()
        profile = await db.upsert_user(
            user_id=7, username="tester", full_name="Test User",
            category="SC", qualification="graduate", sectors=["ssc"],
            dob="01/01/1998", degrees=["iti", "b_ed"], documents=["aadhaar", "pan"],
        )
        assert sorted(profile.degrees) == ["b_ed", "iti"]
        assert sorted(profile.documents) == ["aadhaar", "pan"]

        updated = await db.update_user(7, degrees=["b_sc"], documents=[])
        assert updated.degrees == ["b_sc"]
        assert updated.documents == []
        # untouched fields survive a partial update
        assert updated.full_name == "Test User"
        assert updated.category == "SC"
        await db.close()

    asyncio.run(run())


def test_mongo_backend_exposes_the_same_update_methods():
    from bot.storage_mongo import MongoDatabase

    assert hasattr(Database, "update_user")
    assert hasattr(MongoDatabase, "update_user")


# ------------------------------------------------------------------ matcher
def test_degree_and_document_detection():
    text = ("Candidates must have a B.Ed Degree and ITI. "
            "Carry your caste certificate and 10th marksheet.")
    assert "b_ed" in detect_degree_keys(text)
    assert "iti" in detect_degree_keys(text)
    docs = detect_documents(text)
    assert "caste_certificate" in docs
    assert "tenth_marksheet" in docs


def test_selected_degree_overrides_generic_rank_matching():
    detail = JobDetail(qualification="Candidates with ITI qualification only.")
    # A 10th-pass profile cannot satisfy the generic rank scale ...
    weak = _profile(qualification="tenth", degrees=[])
    assert not qualification_matches(weak, detail)
    # ... but the user explicitly ticked ITI, so the notice matches.
    skilled = _profile(qualification="tenth", degrees=["iti"])
    assert qualification_matches(skilled, detail)


def test_document_gaps_reports_missing_papers():
    detail = JobDetail(documents_required=["aadhaar", "domicile_certificate"])
    profile = _profile(documents=["aadhaar"])
    assert document_gaps(profile, detail) == ["domicile_certificate"]


# ------------------------------------------------------------------- cards
def test_job_card_shows_every_important_date():
    detail = JobDetail(
        qualification="Bachelor Degree with 50% Marks and B.Ed Degree",
        apply_start_date="27 October 2026",
        apply_last_date="25 November 2026",
        fee_last_date="27 November 2026",
        correction_date="28 November – 07 December 2026",
        exam_date="Notify Later",
        admit_card_date="Before Exam",
        result_date="Will Be Updated Here Soon",
        total_posts="1265 Posts",
        selection_process="Online Examination",
        post_date="October 29, 2026",
        min_age=20, max_age=33,
        documents_required=["aadhaar", "caste_certificate"],
    )
    profile = _profile(documents=["aadhaar"])
    text = job_card(JOB, detail, profile, {"user_age": 26, "relaxation": 3,
                                           "effective_max": 36})
    for needle in ("27 October 2026", "25 November 2026", "27 November 2026",
                   "Notify Later", "1265 Posts", "Online Examination",
                   "Bachelor Degree with 50% Marks and B\\.Ed Degree",
                   "October 29, 2026"):
        assert needle in text, needle
    # documents the user does not own are flagged
    assert "❌" in text
    assert "✅" in text


def test_card_never_exceeds_telegram_limits():
    detail = JobDetail(qualification="X" * 9000, raw_text="y" * 9000)
    text = job_card(JOB, detail, _profile(), None)
    assert len(text) <= 4096
    caption = photo_caption(JOB, detail, _profile(), None)
    assert len(caption) <= 1024


def test_full_notification_text_contains_everything():
    detail = JobDetail(
        qualification="Bachelor Degree",
        important_dates="Apply Online Last Date : 25/11/2026",
        how_to_apply="Fill the form online.",
        documents_required=["aadhaar"],
    )
    text = full_detail_text(JOB, detail)
    assert "Bachelor Degree" in text
    assert "25/11/2026" in text
    assert "Fill the form online" in text
    assert "Aadhaar Card" in text


def test_profile_card_lists_degrees_and_documents():
    text = profile_card(_profile())
    assert "B\\.Ed" in text
    assert "Aadhaar Card" in text
    assert "Caste / Category Certificate" in text


def test_admin_user_card_shows_saved_count():
    text = admin_user_card(_profile(), saved_count=3)
    assert "3" in text
    assert "Rahul" in text


# ---------------------------------------------------------------- keyboards
def test_every_button_is_coloured():
    keyboards = [
        category_keyboard(), degrees_keyboard({"b_ed"}),
        documents_keyboard({"aadhaar"}), sectors_keyboard({"railway"}),
        main_menu_keyboard(True), profile_edit_keyboard(),
        browse_keyboard(0, 3, [JOB]), saved_browse_keyboard(0, 3, [JOB]),
        reminder_keyboard(JOB.job_id, True),
        job_detail_keyboard(JOB, JobDetail(apply_url="https://x.in/a"), False),
        admin_users_keyboard([_profile()], 0, 1),
        admin_profile_keyboard(_profile(), 2),
    ]
    for markup in keyboards:
        for row in markup.inline_keyboard:
            for button in row:
                assert button.style is not None, f"uncoloured button: {button.text}"


def test_multi_select_keyboards_toggle_and_confirm():
    kb = degrees_keyboard({"iti"})
    callbacks = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert "deg:iti" in callbacks
    assert "deg:done" in callbacks
    selected = next(b for row in kb.inline_keyboard for b in row
                    if b.callback_data == "deg:iti")
    assert selected.text.startswith("✅")
    kb = documents_keyboard(set())
    assert "doc:done" in [
        b.callback_data for row in kb.inline_keyboard for b in row
    ]


# ------------------------------------------------------------------ wiring
def test_browser_next_button_is_registered():
    """Regression: the Previous/Next callbacks were never registered, so the
    /scrape_now and /latest browsers did not react to the buttons."""
    from telegram.ext import Application, CallbackQueryHandler

    from bot.handlers import register_handlers

    app = Application.builder().token("123:TEST").build()
    register_handlers(app)
    patterns = [
        getattr(handler.pattern, "pattern", handler.pattern)
        for group in app.handlers.values()
        for handler in group
        if isinstance(handler, CallbackQueryHandler)
    ]
    assert "^br:" in patterns, patterns


def test_sources_report_marks_fallbacks_as_standby():
    report = [
        {"source": "mirror", "ok": True, "jobs": 99, "error": None},
        {"source": "original", "ok": False, "jobs": 0,
         "error": "Could not fetch https://x/: HTTP 403 for https://x/"},
        {"source": "original-jina", "ok": False, "jobs": 0,
         "error": "Reader proxy could not reach the source (blocked)"},
    ]
    text = format_sources_report(report, {"last_success_at": "2026-10-29T11:14:17+00:00",
                                           "last_success_source": "mirror"})
    assert "✅ *mirror* — 99 jobs · primary" in text
    # a blocked fallback is a standby state, not a failure
    assert "❌" not in text
    assert "🟡 *original* — standby · HTTP 403" in text
    assert "Primary source is healthy" in text


def test_option_sets_are_not_empty():
    assert len(DEGREE_KEYS) >= 20
    assert len(DOCUMENT_KEYS) >= 15


def test_long_qualification_never_pushes_out_the_apply_link():
    detail = JobDetail(qualification="Bachelor Degree " * 400,
                        apply_url="https://apply.example.in/x")
    text = job_card(JOB, detail, _profile(), None)
    assert len(text) <= 4096
    assert "CLICK HERE TO FILL THE FORM" in text
    assert "Notification PDF" not in text  # nothing was there
    assert "TechnicalSerena" in text


def test_long_notifications_are_split_into_safe_chunks():
    from bot.handlers import _split_for_telegram

    detail = JobDetail(qualification="Bachelor Degree in any stream. " * 300,
                        how_to_apply="Step one. " * 200)
    text = full_detail_text(JOB, detail)
    chunks = _split_for_telegram(text)
    assert len(chunks) > 1
    assert all(len(chunk) <= 3900 for chunk in chunks)
    # no chunk may end in the middle of a MarkdownV2 escape sequence
    assert all(not chunk.endswith("\\") for chunk in chunks)

"""In-chat paginated job browsers (Next / Previous)."""
from __future__ import annotations

import logging
from math import ceil

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from bot import cards, keyboards
from bot.constants import PAGE_SIZE
from bot.models import JobSummary
from bot.utils import md_escape

logger = logging.getLogger(__name__)


def _store(context: ContextTypes.DEFAULT_TYPE, user_id: int,
           jobs: list[JobSummary], kind: str, heading: str) -> None:
    context.application.bot_data.setdefault("browsers", {})[user_id] = {
        "jobs": jobs,
        "kind": kind,
        "heading": heading,
        "page": 0,
    }


def _session(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> dict | None:
    return context.application.bot_data.get("browsers", {}).get(user_id)


def _render(session: dict) -> tuple[str, object]:
    jobs: list[JobSummary] = session["jobs"]
    page: int = session["page"]
    total_pages = max(1, ceil(len(jobs) / PAGE_SIZE))
    page = min(page, total_pages - 1)
    session["page"] = page
    slice_jobs = jobs[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
    text = cards.list_page(slice_jobs, page, total_pages, session["heading"])
    markup = keyboards.browse_keyboard(page, total_pages, slice_jobs)
    return text, markup


async def open_browser(update: Update, context: ContextTypes.DEFAULT_TYPE,
                       user_id: int, jobs: list[JobSummary],
                       kind: str, heading: str) -> None:
    _store(context, user_id, jobs, kind, heading)
    text, markup = _render(_session(context, user_id))
    msg = update.effective_message
    if msg is not None:
        await msg.reply_markdown_v2(text, reply_markup=markup)


async def browser_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    action = query.data.split(":", 2)[1] if query.data.startswith("br:") else ""
    session = _session(context, user_id)

    if action == "noop":
        await query.answer()
        return
    if action == "home":
        await query.answer()
        profile = await context.application.bot_data["db"].get_user(user_id)
        from bot.cards import profile_card
        from bot.keyboards import main_menu_keyboard
        if profile:
            await query.message.reply_markdown_v2(
                profile_card(profile), reply_markup=main_menu_keyboard(profile.active)
            )
        return
    if session is None:
        await query.answer("This list expired — run /latest again.", show_alert=True)
        return

    if action in {"n", "p"}:
        session["page"] += 1 if action == "n" else -1
        session["page"] = max(0, session["page"])
        await query.answer()
        text, markup = _render(session)
        await query.edit_message_text(
            text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=markup,
            disable_web_page_preview=True,
        )
        return

    if action == "o":
        # data shape: br:o:<page>:<index>
        _, _, page_raw, idx_raw = query.data.split(":")
        page, idx = int(page_raw), int(idx_raw)
        jobs = session["jobs"]
        flat = page * PAGE_SIZE + idx
        if not 0 <= flat < len(jobs):
            await query.answer("Job no longer available.", show_alert=True)
            return
        await query.answer()
        await _open_job_card(update, context, jobs[flat])
        return

    if action == "back":
        await query.answer()
        text, markup = _render(session)
        await query.edit_message_text(
            text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=markup,
            disable_web_page_preview=True,
        )


async def _open_job_card(update: Update, context: ContextTypes.DEFAULT_TYPE,
                         job: JobSummary) -> None:
    db = context.application.bot_data["db"]
    user_id = update.callback_query.from_user.id
    profile = await db.get_user(user_id)
    detail = await db.get_job_detail(job.job_id)
    saved = await db.is_saved(user_id, job.job_id)
    if profile:
        from bot.matcher import age_matches
        _, age_info = age_matches(profile, detail) if detail else (True, None)
        text = cards.job_card(job, detail, profile, age_info)
    else:
        text = cards.job_card(job, detail, _anonymous_profile(), None)
    await update.callback_query.message.reply_markdown_v2(
        text,
        reply_markup=keyboards.job_detail_keyboard(job, detail, saved),
        disable_web_page_preview=True,
    )


def _anonymous_profile():
    """Fallback for users browsing without a saved profile."""
    from bot.models import UserProfile

    return UserProfile(
        user_id=0, username=None, full_name="Guest", category="UR",
        qualification="graduate", sectors=[], dob=None,
    )

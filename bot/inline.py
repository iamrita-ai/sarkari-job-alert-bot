"""Inline mode: type @botusername <keyword> in any chat to search jobs."""
from __future__ import annotations

import logging

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
    InputTextMessageContent,
)
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, InlineQueryHandler

from bot.matcher import title_matches
from bot.models import JobDetail, JobSummary, UserProfile
from bot.utils import bold, link, md_escape

logger = logging.getLogger(__name__)

INLINE_RESULT_LIMIT = 20


def _inline_card(job: JobSummary, detail: JobDetail | None,
                 profile: UserProfile | None) -> str:
    detail = detail or JobDetail()
    lines = ["🔔 *SARKARI JOB MATCH*", f"📝 {link(job.title, job.url)}"]
    if detail.organization:
        lines.append(f"🏢 {md_escape(detail.organization)}")
    if detail.eligibility:
        lines.append(f"🎓 {bold('Eligibility:')} {md_escape(detail.eligibility[:220])}")
    if detail.fee:
        lines.append(f"💳 {bold('Fee:')} {md_escape(detail.fee)}")
    if detail.min_age or detail.max_age:
        lines.append(f"📆 {bold('Age:')} {detail.min_age or '—'} – {detail.max_age or '—'} Yrs")
    if job.last_date:
        lines.append(f"⏳ {bold('Last Date:')} `{md_escape(job.last_date)}`")
    if detail.apply_url:
        lines.append(f"👉 {link('CLICK HERE TO FILL FORM', detail.apply_url)}")
    return "\n".join(lines)


def _inline_keyboard(job: JobSummary, detail: JobDetail | None,
                     bot_username: str | None) -> InlineKeyboardMarkup:
    from telegram.constants import KeyboardButtonStyle
    from bot.utils import encode_job_id
    row: list[InlineKeyboardButton] = []
    if detail and detail.apply_url:
        row.append(InlineKeyboardButton(
            "👉 Apply Online", url=detail.apply_url, style=KeyboardButtonStyle.SUCCESS
        ))
    row.append(InlineKeyboardButton(
        "🌐 Full Details", url=job.url, style=KeyboardButtonStyle.PRIMARY
    ))
    rows = [row]
    if bot_username:
        deep_payload = "j" + encode_job_id(job.job_id)
        rows.append([InlineKeyboardButton(
            "🤖 Open in Bot", url=f"https://t.me/{bot_username}?start={deep_payload}",
            style=KeyboardButtonStyle.PRIMARY,
        )])
    return InlineKeyboardMarkup(rows)


async def inline_query(update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.inline_query
    keyword = (query.query or "").strip()
    db = context.application.bot_data["db"]
    profile = await db.get_user(query.from_user.id)

    jobs = await db.search_jobs(keyword, limit=50)
    if profile:
        jobs = [job for job in jobs if title_matches(profile, job)] or jobs[:INLINE_RESULT_LIMIT]
    jobs = jobs[:INLINE_RESULT_LIMIT]

    bot_username = context.application.bot_data.get("bot_username")
    results: list[InlineQueryResultArticle] = []
    for job in jobs:
        detail = await db.get_job_detail(job.job_id)
        card = _inline_card(job, detail, profile)
        results.append(InlineQueryResultArticle(
            id=job.job_id[-63:],
            title=job.title[:200],
            description=(
                f"Last date: {job.last_date}" if job.last_date
                else (detail.organization or "Tap to view full job card")
            )[:200],
            thumbnail_url=detail.image_url if detail else None,
            input_message_content=InputTextMessageContent(
                message_text=card,
                parse_mode=ParseMode.MARKDOWN_V2,
                disable_web_page_preview=True,
            ),
            reply_markup=_inline_keyboard(job, detail, bot_username),
        ))

    if not results:
        results.append(InlineQueryResultArticle(
            id="no-results",
            title="No matching jobs found",
            description="Tap to open the bot and create your profile",
            input_message_content=InputTextMessageContent(
                message_text="No matching jobs right now\\. New alerts arrive automatically 🔔"
            ),
        ))

    await query.answer(results, cache_time=5, is_personal=True)


def register_inline(app) -> None:
    app.add_handler(InlineQueryHandler(inline_query))

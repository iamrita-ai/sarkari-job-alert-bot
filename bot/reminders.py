"""Bookmarks, date reminders and the saved-jobs browser."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from math import ceil
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot import cards, keyboards
from bot.constants import PAGE_SIZE, S_REMINDER_DATE
from bot.models import JobSummary
from bot.utils import md_escape, parse_dob, parse_slash_date, resolve_job

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")


# ------------------------------------------------------------- scheduling
def _job_name(user_id: int, job_id: str) -> str:
    return f"rem:{user_id}:{job_id}"


def _schedule(context: ContextTypes.DEFAULT_TYPE, user_id: int,
              job_id: str, when_utc: datetime) -> None:
    job_queue = context.application.job_queue
    job_queue.get_jobs_by_name(_job_name(user_id, job_id))
    for existing in job_queue.get_jobs_by_name(_job_name(user_id, job_id)):
        existing.schedule_removal()
    job_queue.run_once(
        reminder_fired,
        when=when_utc,
        name=_job_name(user_id, job_id),
        data=(user_id, job_id),
    )


async def schedule_all_pending(application) -> None:  # noqa: ANN001
    """Re-arm reminders after a restart (JobQueue itself is in-memory)."""
    db = application.bot_data["db"]
    now = datetime.now(timezone.utc)
    for saved in await db.pending_reminders():
        when = datetime.fromisoformat(saved.reminder_date)
        if when <= now:
            # Stale reminder: fire if recently due, otherwise drop it
            if now - when < timedelta(hours=26):
                application.job_queue.run_once(
                    reminder_fired, when=timedelta(seconds=10),
                    name=_job_name(saved.user_id, saved.job_id),
                    data=(saved.user_id, saved.job_id),
                )
            else:
                await db.mark_reminded(saved.user_id, saved.job_id)
            continue
        application.job_queue.run_once(
            reminder_fired, when=when,
            name=_job_name(saved.user_id, saved.job_id),
            data=(saved.user_id, saved.job_id),
        )
    logger.info("Pending reminders re-armed")


async def reminder_fired(context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id, job_id = context.job.data
    db = context.application.bot_data["db"]
    job = await db.get_job(job_id)
    if job is None:
        await db.mark_reminded(user_id, job_id)
        return
    detail = await db.get_job_detail(job_id)
    profile = await db.get_user(user_id)
    age_info = None
    if profile and detail:
        from bot.matcher import age_matches
        _, age_info = age_matches(profile, detail)
    text = "⏰ *JOB REMINDER*\n\n" + cards.job_card(
        job, detail, profile or _guest(), age_info
    )
    try:
        await context.bot.send_message(
            chat_id=user_id, text=text, parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.job_detail_keyboard(
                job, detail, saved=await db.is_saved(user_id, job_id)
            ),
            disable_web_page_preview=True,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Reminder delivery failed for %s", user_id)
        return
    await db.mark_reminded(user_id, job_id)


def _guest():
    from bot.models import UserProfile

    return UserProfile(
        user_id=0, username=None, full_name="Guest", category="UR",
        qualification="graduate", sectors=[], dob=None,
    )


# ------------------------------------------------------------- save buttons
async def save_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    ref = query.data.split(":", 1)[1]
    db = context.application.bot_data["db"]
    job = await resolve_job(context.application, ref)
    if job is None:
        await query.answer("Job no longer exists.", show_alert=True)
        return
    job_id = job.job_id
    is_new = await db.save_job(query.from_user.id, job)
    await query.answer("Saved to /saved ✓" if is_new else "Already in your saved jobs")
    # Refresh the keyboard so the button reflects the new state
    detail = await db.get_job_detail(job_id)
    try:
        await query.edit_message_reply_markup(
            reply_markup=keyboards.job_detail_keyboard(job, detail, saved=True)
        )
    except Exception:  # noqa: BLE001 - photo messages / older clients
        pass


# ------------------------------------------------------------- reminder flow
async def rem_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    ref = query.data.split(":", 1)[1]
    db = context.application.bot_data["db"]
    job = await resolve_job(context.application, ref)
    if job is None:
        await query.answer("Job no longer exists.", show_alert=True)
        return
    job_id = job.job_id
    await db.save_job(query.from_user.id, job)
    await query.answer()
    await query.message.reply_markdown_v2(
        f"⏰ *Set a reminder for*\n{md_escape(job.title)}\n\n"
        "Pick a quick option, or choose a custom date:",
        reply_markup=keyboards.reminder_keyboard(job_id, bool(job.last_date)),
    )


async def rem_quick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    _, ref, option = query.data.split(":")
    db = context.application.bot_data["db"]
    job = await resolve_job(context.application, ref)
    if job is None:
        await query.answer("Job no longer exists.", show_alert=True)
        return
    job_id = job.job_id
    last_date = parse_slash_date(job.last_date)
    if last_date is None:
        await query.answer("No official last date — use Custom Date.", show_alert=True)
        return

    if option == "1d":
        target = last_date - timedelta(days=1)
    elif option == "3d":
        target = last_date - timedelta(days=3)
    else:
        target = last_date
    if target < datetime.now(IST).date():
        await query.answer("That date has already passed.", show_alert=True)
        return

    when_utc = datetime.combine(target, datetime.min.time(), IST).astimezone(timezone.utc)
    await db.set_reminder(query.from_user.id, job_id, when_utc.isoformat())
    _schedule(context, query.from_user.id, job_id, when_utc)
    await query.answer("Reminder set ✓")
    await query.edit_message_text(
        f"⏰ Reminder set for *{target.strftime('%d/%m/%Y')}* at 9:00 AM IST\n"
        f"📝 {md_escape(job.title)}",
        parse_mode=ParseMode.MARKDOWN_V2,
    )


async def rem_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer("Cancelled")
    await query.edit_message_text("Reminder cancelled.")


async def rem_custom_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    job = await resolve_job(context.application, query.data.split(":", 1)[1])
    if job is None:
        await query.answer("Invalid button.", show_alert=True)
        return ConversationHandler.END
    job_id = job.job_id
    context.user_data["reminder_job_id"] = job_id
    await query.answer()
    await query.message.reply_markdown_v2(
        "✍️ Send the reminder date as *DD/MM/YYYY* "
        "\\(e\\.g\\. `20/11/2026`\\)\\. I'll ping you at 9:00 AM IST\\."
    )
    return S_REMINDER_DATE


async def _reminder_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("reminder_job_id", None)
    if update.callback_query:
        await update.callback_query.answer("Cancelled")
    else:
        await update.message.reply_text("Reminder setup cancelled.")
    return ConversationHandler.END


async def rem_custom_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    target = parse_dob(update.message.text)  # same DD/MM/YYYY parser
    if target is None:
        await update.message.reply_text(
            "⚠️ Invalid date. Please send DD/MM/YYYY, e.g. 20/11/2026."
        )
        return S_REMINDER_DATE
    if target < datetime.now(IST).date():
        await update.message.reply_text("⚠️ That date is in the past. Pick a future date.")
        return S_REMINDER_DATE

    job_id = context.user_data.pop("reminder_job_id", None)
    if not job_id:
        await update.message.reply_text("Session expired — tap Remind Me again.")
        return ConversationHandler.END
    db = context.application.bot_data["db"]
    when_utc = datetime.combine(target, datetime.min.time(), IST).astimezone(timezone.utc)
    await db.set_reminder(update.effective_user.id, job_id, when_utc.isoformat())
    _schedule(context, update.effective_user.id, job_id, when_utc)
    job = await db.get_job(job_id)
    await update.message.reply_markdown_v2(
        f"⏰ Custom reminder set for *{target.strftime('%d/%m/%Y')}* at 9:00 AM IST\n"
        f"📝 {md_escape(job.title if job else 'your saved job')}"
    )
    return ConversationHandler.END


# ------------------------------------------------------------- /saved browser
async def saved_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = context.application.bot_data["db"]
    user_id = update.effective_user.id
    saved = await db.list_saved(user_id)
    if not saved:
        await update.message.reply_markdown_v2(
            "🔖 *No saved jobs yet\\.*\n\nOpen any job card and tap *Save Job* to bookmark it\\."
        )
        return
    context.application.bot_data.setdefault("saved_browsers", {})[user_id] = {"page": 0}
    await _render_saved(update, context, user_id)


async def _render_saved(update: Update, context: ContextTypes.DEFAULT_TYPE,
                        user_id: int, edit: bool = False) -> None:
    db = context.application.bot_data["db"]
    saved = await db.list_saved(user_id)
    state = context.application.bot_data.setdefault(
        "saved_browsers", {}
    ).setdefault(user_id, {"page": 0})
    total_pages = max(1, ceil(len(saved) / PAGE_SIZE))
    state["page"] = min(state["page"], total_pages - 1)
    page = state["page"]
    page_items = saved[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
    username = context.application.bot_data.get("bot_username")
    deep_base = f"https://t.me/{username}?start=j" if username else None
    text = cards.saved_list_card(page_items, page, total_pages, deep_base)
    markup = keyboards.saved_browse_keyboard(page, total_pages, page_items)
    if edit and update.callback_query is not None:
        await update.callback_query.edit_message_text(
            text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=markup,
            disable_web_page_preview=True,
        )
    else:
        await update.effective_message.reply_markdown_v2(
            text, reply_markup=markup, disable_web_page_preview=True
        )


async def saved_browser_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    action = query.data.split(":", 1)[1]
    state = context.application.bot_data.get("saved_browsers", {}).get(user_id)
    if action == "noop":
        await query.answer()
        return
    if action in {"n", "p"} and state is not None:
        state["page"] += 1 if action == "n" else -1
        state["page"] = max(0, state["page"])
        await query.answer()
        await _render_saved(update, context, user_id, edit=True)
        return
    # Titles are deep links handled by /start; nothing else to do here.
    await query.answer()


# ------------------------------------------------------------- registration
def register_reminders(app) -> None:
    app.add_handler(CallbackQueryHandler(save_callback, pattern="^save:"))
    app.add_handler(CallbackQueryHandler(rem_quick_callback, pattern="^remset:"))
    app.add_handler(CallbackQueryHandler(rem_cancel_callback, pattern="^remcancel:"))
    app.add_handler(CallbackQueryHandler(rem_menu_callback, pattern="^rem:"))
    app.add_handler(CommandHandler("saved", saved_command))
    app.add_handler(CallbackQueryHandler(saved_browser_callback, pattern="^sv:"))

    custom = ConversationHandler(
        entry_points=[CallbackQueryHandler(rem_custom_entry, pattern="^remcustom:")],
        states={
            S_REMINDER_DATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, rem_custom_date)
            ],
        },
        fallbacks=[CommandHandler("cancel", _reminder_cancel)],
        allow_reentry=True,
        per_message=False,
    )
    app.add_handler(custom)

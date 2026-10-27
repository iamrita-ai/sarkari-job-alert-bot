"""Telegram command / conversation / menu handlers."""
from __future__ import annotations

import logging
from pathlib import Path

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    TypeHandler,
    filters,
)

from bot import config, matcher
from bot.browser import open_browser
from bot.cards import (
    about_text,
    help_text,
    profile_card,
    welcome_caption,
)
from bot.constants import (
    S_CATEGORY,
    CATEGORY_MAP,
    S_DOB,
    S_NAME,
    S_QUALIFICATION,
    QUAL_MAP,
    S_SECTORS,
    SECTOR_KEYS,
)
from bot.keyboards import (
    category_keyboard,
    get_started_keyboard,
    main_menu_keyboard,
    qualification_keyboard,
    sectors_keyboard,
)
from bot.scraper import ScraperError
from bot.utils import decode_job_id, md_escape, parse_dob

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------- utils
def _db(context: ContextTypes.DEFAULT_TYPE):
    return context.application.bot_data["db"]


def _scraper(context: ContextTypes.DEFAULT_TYPE):
    return context.application.bot_data["scraper"]


def _is_owner(update: Update) -> bool:
    user = update.effective_user
    return bool(user and user.username and user.username.lower() in config.OWNER_USERNAMES)


async def track_owner(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remember owner chat IDs so the scheduler can DM them outage alerts."""
    user = update.effective_user
    if user and user.username and user.username.lower() in config.OWNER_USERNAMES:
        context.application.bot_data.setdefault("owner_chat_ids", set()).add(user.id)


async def _send_banner(message, caption: str, markup=None) -> None:
    banner = Path(config.START_BANNER_PATH)
    if banner.exists():
        try:
            with banner.open("rb") as photo:
                await message.reply_photo(
                    photo=photo, caption=caption,
                    parse_mode=ParseMode.MARKDOWN_V2, reply_markup=markup,
                )
            return
        except Exception:  # noqa: BLE001 - caption/image issue must never block /start
            logger.exception("Banner photo failed, falling back to a text message")
    # Graceful degradation: missing asset OR any Telegram send error
    await message.reply_markdown_v2(caption, reply_markup=markup)


# ------------------------------------------------------------- deep links
async def _show_deep_linked_job(update: Update, context: ContextTypes.DEFAULT_TYPE,
                                payload: str) -> bool:
    if not payload.startswith("j"):
        return False
    job_id = decode_job_id(payload[1:])
    if not job_id:
        return False
    job = await _db(context).get_job(job_id)
    if job is None:
        return False
    db = _db(context)
    profile = await db.get_user(update.effective_user.id)
    detail = await db.get_job_detail(job_id)
    age_info = None
    if profile and detail:
        _, age_info = matcher.age_matches(profile, detail)
    from bot.cards import job_card
    from bot.keyboards import job_detail_keyboard
    from bot.reminders import _guest
    target = profile or _guest()
    await update.message.reply_markdown_v2(
        job_card(job, detail, target, age_info),
        reply_markup=job_detail_keyboard(job, detail, await db.is_saved(target.user_id, job_id) if profile else False),
        disable_web_page_preview=True,
    )
    if not profile:
        await update.message.reply_markdown_v2(
            "👆 That's how every alert looks\\. Send /start to create your profile "
            "and get personalised job matches\\."
        )
    return True


# ------------------------------------------------------------- onboarding
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    db = _db(context)
    if context.args:
        if await _show_deep_linked_job(update, context, context.args[0]):
            return ConversationHandler.END

    profile = await db.get_user(update.effective_user.id)
    if profile:
        await _send_banner(
            update.message,
            f"Welcome back, {md_escape(profile.full_name)} 👋\n\n" + profile_card(profile),
            main_menu_keyboard(profile.active),
        )
        return ConversationHandler.END

    await _send_banner(update.message, welcome_caption(), get_started_keyboard())
    return ConversationHandler.END


async def begin_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["draft"] = {"sectors": set()}
    await query.message.reply_markdown_v2(
        "Step 1️⃣/5 — Type your *full name* now:"
    )
    return S_NAME


async def edit_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    profile = await _db(context).get_user(update.effective_user.id)
    draft = {"sectors": set(profile.sectors) if profile else set()}
    if profile:
        draft.update(
            full_name=profile.full_name,
            dob=profile.dob,
            category=profile.category,
            qualification=profile.qualification,
        )
    context.user_data["draft"] = draft
    current = f" Current name: *{md_escape(profile.full_name)}*\\." if profile else ""
    await update.message.reply_markdown_v2(
        f"✏️ Updating your profile\\.{current}\n\nStep 1️⃣/5 — Type your *full name*:"
    )
    return S_NAME


async def name_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = update.message.text.strip()
    if not (2 <= len(name) <= 64):
        await update.message.reply_text(
            "⚠️ Please send a valid name between 2 and 64 characters."
        )
        return S_NAME
    context.user_data["draft"]["full_name"] = name
    await update.message.reply_markdown_v2(
        f"Thanks, *{md_escape(name)}* 🙂\n\n"
        "Step 2️⃣/5 — Type your *date of birth* as `DD/MM/YYYY` "
        "\\(used to check age limits with your category relaxation\\):"
    )
    return S_DOB


async def dob_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    dob = parse_dob(update.message.text)
    if dob is None:
        await update.message.reply_text(
            "⚠️ Invalid date. Please send a real date as DD/MM/YYYY, e.g. 15/08/2000."
        )
        return S_DOB
    from bot.utils import dob_to_storage, calculate_age
    stored = dob_to_storage(dob)
    context.user_data["draft"]["dob"] = stored
    await update.message.reply_markdown_v2(
        f"🎂 Recorded: `{stored}` \\(age {calculate_age(stored)} Yrs\\)\n\n"
        "Step 3️⃣/5 — Choose your *reservation category*:",
        reply_markup=category_keyboard(),
    )
    return S_CATEGORY


async def category_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    key = query.data.split(":", 1)[1]
    if key not in CATEGORY_MAP:
        await query.answer()
        return S_CATEGORY
    context.user_data["draft"]["category"] = key
    await query.answer()
    await query.edit_message_text(
        "Step 4️⃣/5 — Choose your *highest qualification* "
        "\\(you automatically qualify for jobs asking for a lower one\\):",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=qualification_keyboard(),
    )
    return S_QUALIFICATION


async def qualification_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    key = query.data.split(":", 1)[1]
    if key not in QUAL_MAP:
        await query.answer()
        return S_QUALIFICATION
    context.user_data["draft"]["qualification"] = key
    await query.answer()
    await query.edit_message_text(
        "Step 5️⃣/5 — Tick the *job sectors* you want alerts for "
        "\\(select several\\), then press *Done*:",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=sectors_keyboard(context.user_data["draft"].get("sectors", set())),
    )
    return S_SECTORS


async def sector_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    key = query.data.split(":", 1)[1]
    draft = context.user_data["draft"]
    selected: set[str] = draft.setdefault("sectors", set())

    if key != "done":
        if key not in SECTOR_KEYS:
            await query.answer()
            return S_SECTORS
        selected.symmetric_difference_update({key})
        await query.answer()
        await query.edit_message_reply_markup(reply_markup=sectors_keyboard(selected))
        return S_SECTORS

    if not selected:
        await query.answer("Please pick at least one sector 🙂", show_alert=True)
        return S_SECTORS

    tg_user = update.effective_user
    profile = await _db(context).upsert_user(
        user_id=tg_user.id,
        username=tg_user.username,
        full_name=draft["full_name"],
        category=draft["category"],
        qualification=draft["qualification"],
        sectors=sorted(selected),
        dob=draft.get("dob"),
    )
    context.user_data.pop("draft", None)
    await query.answer("Profile saved ✅")
    await query.edit_message_text(
        f"✅ *Profile saved successfully\\!*\n\n{profile_card(profile)}",
        parse_mode=ParseMode.MARKDOWN_V2,
        disable_web_page_preview=True,
    )
    await context.bot.send_message(
        chat_id=tg_user.id,
        text="You're all set\\! New matching jobs arrive here automatically 🔔",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=main_menu_keyboard(True),
    )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("draft", None)
    await update.message.reply_text(
        "Setup cancelled. Send /start whenever you want to try again."
    )
    return ConversationHandler.END


# ------------------------------------------------------------- plain commands
async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    profile = await _db(context).get_user(update.effective_user.id)
    if not profile:
        await update.message.reply_text("You don't have a profile yet. Send /start to create one.")
        return
    await update.message.reply_markdown_v2(
        profile_card(profile), reply_markup=main_menu_keyboard(profile.active)
    )


async def pause(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _db(context).set_active(update.effective_user.id, False)
    await update.message.reply_markdown_v2("⏸ Alerts paused\\. Send /resume to turn them back on\\.")


async def resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _db(context).set_active(update.effective_user.id, True)
    await update.message.reply_markdown_v2("▶️ Alerts resumed — stay tuned\\!")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    bot_username = context.application.bot_data.get("bot_username", "your_bot")
    await update.message.reply_markdown_v2(help_text().replace("@<bot_username>", f"@{bot_username}"))


async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_markdown_v2(about_text(), disable_web_page_preview=True)


async def latest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    profile = await _db(context).get_user(update.effective_user.id)
    if not profile:
        await update.effective_message.reply_text(
            "Please create your profile first with /start so I know what to match."
        )
        return
    status = await update.effective_message.reply_text("🔎 Fetching the latest jobs…")
    try:
        jobs = await _scraper(context).fetch_latest_jobs()
    except ScraperError:
        logger.exception("Latest-jobs fetch failed")
        await status.edit_text(
            "⚠️ Couldn't reach the job sources right now. Please try again in a few minutes."
        )
        return
    matched = [job for job in jobs if matcher.title_matches(profile, job)]
    await status.edit_text(f"✅ {len(matched)} matching jobs — use Next / Previous to browse.")
    await open_browser(
        update, context, profile.user_id, matched,
        kind="latest", heading="Latest Matching Jobs",
    )


# ------------------------------------------------------------------ menu taps
async def menu_edit_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    profile = await _db(context).get_user(query.from_user.id)
    draft = {"sectors": set(profile.sectors) if profile else set()}
    if profile:
        draft.update(
            full_name=profile.full_name,
            dob=profile.dob,
            category=profile.category,
            qualification=profile.qualification,
        )
    context.user_data["draft"] = draft
    current = f" Current name: *{md_escape(profile.full_name)}*\\." if profile else ""
    await query.message.reply_markdown_v2(
        f"✏️ Updating your profile\\.{current}\n\nStep 1️⃣/5 — Type your *full name*:"
    )
    return S_NAME


async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    action = query.data.split(":", 1)[1]
    if action == "edit":
        return  # owned by the ConversationHandler entry point
    await query.answer()
    db = _db(context)
    profile = await db.get_user(query.from_user.id)

    if action == "help":
        bot_username = context.application.bot_data.get("bot_username", "your_bot")
        await query.edit_message_text(
            help_text().replace("@<bot_username>", f"@{bot_username}"),
            parse_mode=ParseMode.MARKDOWN_V2,
        )
    elif action == "about":
        await query.edit_message_text(
            about_text(), parse_mode=ParseMode.MARKDOWN_V2,
            disable_web_page_preview=True,
        )
    elif action in {"pause", "resume"}:
        if not profile:
            await query.message.reply_text("Send /start to create your profile first.")
            return
        active = action == "resume"
        await db.set_active(query.from_user.id, active)
        profile = await db.get_user(query.from_user.id)
        await query.edit_message_text(
            profile_card(profile), parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=main_menu_keyboard(active),
            disable_web_page_preview=True,
        )
        await query.message.reply_markdown_v2(
            "▶️ Alerts resumed\\." if active else "⏸ Alerts paused\\."
        )
    elif action == "saved":
        from bot.reminders import saved_command
        await saved_command(update, context)
    elif action == "latest":
        if not profile:
            await query.message.reply_text("Send /start to create your profile first.")
            return
        status = await query.message.reply_text("🔎 Fetching the latest jobs…")
        try:
            jobs = await _scraper(context).fetch_latest_jobs()
        except ScraperError:
            await status.edit_text("⚠️ Couldn't reach the job sources. Try again shortly.")
            return
        matched = [job for job in jobs if matcher.title_matches(profile, job)]
        await status.edit_text(f"✅ {len(matched)} matching jobs — use Next / Previous.")
        await open_browser(
            update, context, profile.user_id, matched,
            kind="latest", heading="Latest Matching Jobs",
        )


async def fallback_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.user_data.get("draft") or context.user_data.get("reminder_job_id"):
        return  # a conversation handler owns this input
    await update.message.reply_text(
        "Use /start to set up your profile or /help to see everything I can do."
    )


# ------------------------------------------------------------------ admin
async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_owner(update):
        await update.message.reply_text("🚫 Owner-only command.")
        return
    db = _db(context)
    users = await db.all_users()
    active = sum(1 for u in users if u.active)
    text = (
        "📊 *Bot Statistics*\n"
        f"• Total users: *{len(users)}*\n"
        f"• Active alerts: *{active}*\n"
        f"• Jobs catalogued: *{await db.job_count()}*\n"
        f"• Notifications sent: *{await db.notification_count()}*\n"
        f"• Scraper source: *{md_escape(_scraper(context).status.get('last_success_source') or 'none')}*"
    )
    await update.message.reply_markdown_v2(text)


async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_owner(update):
        await update.message.reply_text("🚫 Owner-only command.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /broadcast <your message>")
        return
    db = _db(context)
    message = update.message.text.split(maxsplit=1)[1]
    sent = failed = 0
    for user in await db.all_active_users():
        try:
            await context.bot.send_message(user.user_id, message)
            sent += 1
        except Exception:  # noqa: BLE001 - keep broadcasting
            logger.exception("Broadcast failed for %s", user.user_id)
            failed += 1
    await update.message.reply_text(
        f"📢 Broadcast finished — sent: {sent}, failed: {failed}"
    )


async def admin_scrape_now(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_owner(update):
        await update.message.reply_text("🚫 Owner-only command.")
        return
    status = await update.message.reply_text("🔄 Running a scrape cycle now…")
    monitor = context.application.bot_data["monitor"]
    await monitor.periodic_check()
    db = _db(context)
    all_jobs = await db.list_jobs(limit=100)
    await status.edit_text(
        f"✅ Cycle complete\\. {len(all_jobs)} jobs currently catalogued — browse them below:",
        parse_mode=ParseMode.MARKDOWN_V2,
    )
    await open_browser(
        update, context, update.effective_user.id, all_jobs,
        kind="all", heading="All Catalogued Jobs",
    )


async def admin_sources(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_owner(update):
        await update.message.reply_text("🚫 Owner-only command.")
        return
    status = await update.message.reply_text("🩺 Probing every data source…")
    report = await _scraper(context).source_healthcheck()
    lines = ["🩺 *Data\\-source health*", "━━━━━━━━━━━━━━━━━━"]
    for entry in report:
        if entry["ok"]:
            lines.append(f"✅ *{md_escape(entry['source'])}* — {entry['jobs']} jobs")
        else:
            lines.append(f"❌ *{md_escape(entry['source'])}* — {md_escape(entry['error'])}")
    scraper_status = _scraper(context).status
    lines.append("━━━━━━━━━━━━━━━━━━")
    lines.append(
        f"Last success: {md_escape(scraper_status.get('last_success_at') or 'never')} "
        f"via {md_escape(scraper_status.get('last_success_source') or '—')}"
    )
    await status.edit_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN_V2)


async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Last-resort guard: log the failure and keep the bot alive."""
    from telegram.error import Conflict, NetworkError, TimedOut

    error = context.error
    # Two instances polling with the same token - operational, not a code bug.
    if isinstance(error, Conflict):
        logger.warning(
            "Polling conflict: another instance is using this token. Stop the "
            "duplicate deployment (only ONE bot instance can run per token)."
        )
        return
    if isinstance(error, (NetworkError, TimedOut)):
        logger.warning("Telegram network hiccup: %s", error)
        return

    logger.exception("Unhandled error while processing update %s", update, exc_info=error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "⚠️ Something went wrong on my side. Please try again in a moment."
            )
        except Exception:  # noqa: BLE001
            logger.exception("Failed to deliver the generic error message")


# -------------------------------------------------------------- registration
def register_handlers(app: Application) -> None:
    conversation = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CommandHandler("edit", edit_profile),
            CallbackQueryHandler(menu_edit_entry, pattern="^menu:edit$"),
            CallbackQueryHandler(begin_conversation, pattern="^start:begin$"),
        ],
        states={
            S_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, name_received)],
            S_DOB: [MessageHandler(filters.TEXT & ~filters.COMMAND, dob_received)],
            S_CATEGORY: [CallbackQueryHandler(category_chosen, pattern="^cat:")],
            S_QUALIFICATION: [CallbackQueryHandler(qualification_chosen, pattern="^qual:")],
            S_SECTORS: [CallbackQueryHandler(sector_chosen, pattern="^sec:")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )
    app.add_handler(conversation)

    app.add_handler(CommandHandler("profile", show_profile))
    app.add_handler(CommandHandler("latest", latest))
    app.add_handler(CommandHandler("pause", pause))
    app.add_handler(CommandHandler("resume", resume))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("about", about_command))

    app.add_handler(CommandHandler("stats", admin_stats))
    app.add_handler(CommandHandler("broadcast", admin_broadcast))
    app.add_handler(CommandHandler("scrape_now", admin_scrape_now))
    app.add_handler(CommandHandler("sources", admin_sources))

    app.add_handler(TypeHandler(Update, track_owner), group=-1)
    app.add_handler(CallbackQueryHandler(menu_handler, pattern="^menu:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, fallback_text))
    app.add_error_handler(global_error_handler)

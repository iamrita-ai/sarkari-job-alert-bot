"""Telegram command / conversation / menu handlers."""
from __future__ import annotations

import logging

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
from bot.cards import (
    ABOUT_TEXT,
    HELP_TEXT,
    esc,
    latest_jobs_card,
    profile_card,
)
from bot.keyboards import (
    category_keyboard,
    main_menu_keyboard,
    qualification_keyboard,
    sectors_keyboard,
)
from bot.constants import CATEGORY_MAP, QUAL_MAP, SECTOR_KEYS
from bot.scraper import ScraperError

logger = logging.getLogger(__name__)

NAME, CATEGORY, QUALIFICATION, SECTORS = range(4)


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


# ------------------------------------------------------------- onboarding
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    db = _db(context)
    tg_user = update.effective_user
    profile = await db.get_user(tg_user.id)

    if profile:
        await update.message.reply_html(
            f"Welcome back, {esc(profile.full_name)}! 👋\n\n{profile_card(profile)}",
            reply_markup=main_menu_keyboard(profile.active),
        )
        return ConversationHandler.END

    context.user_data["draft"] = {"sectors": set()}
    await update.message.reply_html(
        "👋 Welcome to <b>Sarkari Job Alert Bot</b>!\n\n"
        "I continuously watch SarkariResult.com and instantly message you "
        "whenever a government job matches your profile.\n\n"
        "Let's build your profile in 4 quick steps.\n\n"
        "Step 1️⃣ — Type your <b>full name</b> now:"
    )
    return NAME


async def edit_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    profile = await _db(context).get_user(update.effective_user.id)
    draft = {"sectors": set(profile.sectors) if profile else set()}
    if profile:
        draft.update(
            full_name=profile.full_name,
            category=profile.category,
            qualification=profile.qualification,
        )
    context.user_data["draft"] = draft
    current = f" Current name: <b>{esc(profile.full_name)}</b>." if profile else ""
    await update.message.reply_html(
        f"✏️ Updating your profile.{current}\n\nStep 1️⃣ — Type your <b>full name</b>:"
    )
    return NAME


async def name_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = update.message.text.strip()
    if not (2 <= len(name) <= 64):
        await update.message.reply_text(
            "⚠️ Please send a valid name between 2 and 64 characters."
        )
        return NAME
    context.user_data["draft"]["full_name"] = name
    await update.message.reply_html(
        f"Nice to meet you, <b>{esc(name)}</b>! 🙂\n\n"
        "Step 2️⃣ — Choose your <b>reservation category</b>:",
        reply_markup=category_keyboard(),
    )
    return CATEGORY


async def category_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    key = query.data.split(":", 1)[1]
    if key not in CATEGORY_MAP:
        await query.answer()
        return CATEGORY
    context.user_data["draft"]["category"] = key
    await query.answer()
    await query.edit_message_text(
        "Step 3️⃣ — Choose your <b>highest qualification</b> "
        "(you'll automatically qualify for jobs asking for a lower one):",
        parse_mode=ParseMode.HTML,
        reply_markup=qualification_keyboard(),
    )
    return QUALIFICATION


async def qualification_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    key = query.data.split(":", 1)[1]
    if key not in QUAL_MAP:
        await query.answer()
        return QUALIFICATION
    context.user_data["draft"]["qualification"] = key
    await query.answer()
    await query.edit_message_text(
        "Step 4️⃣ — Tick the <b>job sectors</b> you want alerts for "
        "(you can select several), then press <b>Done</b>:",
        parse_mode=ParseMode.HTML,
        reply_markup=sectors_keyboard(context.user_data["draft"].get("sectors", set())),
    )
    return SECTORS


async def sector_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    key = query.data.split(":", 1)[1]
    draft = context.user_data["draft"]
    selected: set[str] = draft.setdefault("sectors", set())

    if key != "done":
        if key not in SECTOR_KEYS:
            await query.answer()
            return SECTORS
        selected.symmetric_difference_update({key})
        await query.answer()
        await query.edit_message_reply_markup(reply_markup=sectors_keyboard(selected))
        return SECTORS

    if not selected:
        await query.answer("Please pick at least one sector 🙂", show_alert=True)
        return SECTORS

    tg_user = update.effective_user
    profile = await _db(context).upsert_user(
        user_id=tg_user.id,
        username=tg_user.username,
        full_name=draft["full_name"],
        category=draft["category"],
        qualification=draft["qualification"],
        sectors=sorted(selected),
    )
    context.user_data.pop("draft", None)
    await query.answer("Profile saved ✅")
    await query.edit_message_text(
        f"✅ <b>Profile saved successfully!</b>\n\n{profile_card(profile)}",
        parse_mode=ParseMode.HTML,
    )
    await context.bot.send_message(
        chat_id=tg_user.id,
        text="You're all set! New matching jobs will arrive here automatically. 🔔",
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
    await update.message.reply_html(
        profile_card(profile), reply_markup=main_menu_keyboard(profile.active)
    )


async def pause(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _db(context).set_active(update.effective_user.id, False)
    await update.message.reply_text(
        "⏸ Alerts paused. Send /resume whenever you want them back."
    )


async def resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _db(context).set_active(update.effective_user.id, True)
    await update.message.reply_text("▶️ Alerts resumed — stay tuned!")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_html(HELP_TEXT)


async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_html(ABOUT_TEXT, disable_web_page_preview=True)


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
            "⚠️ Couldn't reach Sarkari Result right now. Please try again in a few minutes."
        )
        return
    matched = [job for job in jobs if matcher.title_matches(profile, job)]
    await status.edit_text(
        latest_jobs_card(matched, profile),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


# ------------------------------------------------------------------ menu taps
async def menu_edit_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Conversation entry point triggered by the 'Edit Profile' inline button."""
    query = update.callback_query
    await query.answer()
    profile = await _db(context).get_user(query.from_user.id)
    draft = {"sectors": set(profile.sectors) if profile else set()}
    if profile:
        draft.update(
            full_name=profile.full_name,
            category=profile.category,
            qualification=profile.qualification,
        )
    context.user_data["draft"] = draft
    current = f" Current name: <b>{esc(profile.full_name)}</b>." if profile else ""
    await query.message.reply_html(
        f"✏️ Updating your profile.{current}\n\nStep 1️⃣ — Type your <b>full name</b>:"
    )
    return NAME


async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    action = query.data.split(":", 1)[1]
    if action == "edit":
        return  # owned by the ConversationHandler entry point
    await query.answer()
    db = _db(context)
    profile = await db.get_user(query.from_user.id)

    if action == "help":
        await query.edit_message_text(HELP_TEXT, parse_mode=ParseMode.HTML)
    elif action == "about":
        await query.edit_message_text(ABOUT_TEXT, parse_mode=ParseMode.HTML,
                                     disable_web_page_preview=True)
    elif action in {"pause", "resume"}:
        if not profile:
            await query.message.reply_text("Send /start to create your profile first.")
            return
        active = action == "resume"
        await db.set_active(query.from_user.id, active)
        profile = await db.get_user(query.from_user.id)
        await query.edit_message_text(
            profile_card(profile), parse_mode=ParseMode.HTML,
            reply_markup=main_menu_keyboard(active),
        )
        await query.message.reply_text(
            "▶️ Alerts resumed." if active else "⏸ Alerts paused."
        )
    elif action == "latest":
        if not profile:
            await query.message.reply_text("Send /start to create your profile first.")
            return
        status = await query.message.reply_text("🔎 Fetching the latest jobs…")
        try:
            jobs = await _scraper(context).fetch_latest_jobs()
        except ScraperError:
            await status.edit_text(
                "⚠️ Couldn't reach Sarkari Result right now. Try again shortly."
            )
            return
        matched = [job for job in jobs if matcher.title_matches(profile, job)]
        await status.edit_text(
            latest_jobs_card(matched, profile),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )


async def fallback_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.user_data.get("draft"):
        return  # conversation handler owns this input
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
    await update.message.reply_html(
        "📊 <b>Bot Statistics</b>\n"
        f"• Total users: <b>{len(users)}</b>\n"
        f"• Active alerts: <b>{active}</b>\n"
        f"• Jobs catalogued: <b>{await db.job_count()}</b>\n"
        f"• Notifications sent: <b>{await db.notification_count()}</b>"
    )


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
    await update.message.reply_text("🔄 Running a scrape cycle now…")
    monitor = context.application.bot_data["monitor"]
    await monitor.periodic_check()
    await update.message.reply_text("✅ Scrape cycle complete.")


async def admin_sources(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_owner(update):
        await update.message.reply_text("🚫 Owner-only command.")
        return
    status = await update.message.reply_text("🩺 Probing every data source…")
    report = await _scraper(context).source_healthcheck()
    lines = ["🩺 <b>Data-source health</b>", "━━━━━━━━━━━━━━━━━━"]
    for entry in report:
        if entry["ok"]:
            lines.append(f"✅ <b>{entry['source']}</b> — {entry['jobs']} jobs")
        else:
            lines.append(f"❌ <b>{entry['source']}</b> — {esc(entry['error'])}")
    scraper_status = _scraper(context).status
    lines.append("━━━━━━━━━━━━━━━━━━")
    lines.append(
        f"Last success: {esc(scraper_status.get('last_success_at') or 'never')} "
        f"via {esc(scraper_status.get('last_success_source') or '—')}"
    )
    await status.edit_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Last-resort guard: log the failure and keep the bot alive."""
    logger.exception("Unhandled error while processing update %s", update, exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "⚠️ Something went wrong on my side. Please try again in a moment."
            )
        except Exception:  # noqa: BLE001 - never raise out of the error handler
            logger.exception("Failed to deliver the generic error message")


# -------------------------------------------------------------- registration
def register_handlers(app: Application) -> None:
    conversation = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CommandHandler("edit", edit_profile),
            CallbackQueryHandler(menu_edit_entry, pattern="^menu:edit$"),
        ],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, name_received)],
            CATEGORY: [CallbackQueryHandler(category_chosen, pattern="^cat:")],
            QUALIFICATION: [CallbackQueryHandler(qualification_chosen, pattern="^qual:")],
            SECTORS: [CallbackQueryHandler(sector_chosen, pattern="^sec:")],
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

    # Runs for every update, in every group, to remember owner chat IDs
    app.add_handler(TypeHandler(Update, track_owner), group=-1)
    app.add_handler(CallbackQueryHandler(menu_handler, pattern="^menu:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, fallback_text))
    app.add_error_handler(global_error_handler)

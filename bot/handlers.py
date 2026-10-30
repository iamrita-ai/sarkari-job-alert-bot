"""Telegram command / conversation / menu handlers."""
from __future__ import annotations

import logging
import re
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
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
from bot.browser import browser_callback, open_browser
from bot.cards import (
    about_text,
    admin_user_card,
    full_detail_text,
    help_text,
    profile_card,
    welcome_caption,
)
from bot.constants import (
    CATEGORY_MAP,
    STATE_MAP,
    DEGREE_MAP,
    DEGREE_KEYS,
    DOCUMENT_KEYS,
    QUAL_MAP,
    S_CATEGORY,
    S_DEGREES,
    S_DOB,
    S_DOCUMENTS,
    S_EDIT_MENU,
    S_NAME,
    S_SECTORS,
    SECTOR_KEYS,
)
from bot.keyboards import (
    BLUE,
    GREEN,
    admin_profile_keyboard,
    admin_users_keyboard,
    category_keyboard,
    degrees_keyboard,
    documents_keyboard,
    get_started_keyboard,
    main_menu_keyboard,
    profile_edit_keyboard,
    resume_setup_keyboard,
    sectors_keyboard,
)
from bot.scraper import ScraperError
from bot.utils import decode_job_id, md_escape, parse_dob, remember_jobs, resolve_job
from bot.webapp import sign_token

logger = logging.getLogger(__name__)

# Number of subscribers shown per page in the owner /users browser
ADMIN_USERS_PAGE = 10


# --------------------------------------------------------------------- utils
def _db(context: ContextTypes.DEFAULT_TYPE):
    return context.application.bot_data["db"]


def _scraper(context: ContextTypes.DEFAULT_TYPE):
    return context.application.bot_data["scraper"]


def _is_owner(update: Update) -> bool:
    user = update.effective_user
    return bool(user and user.username and user.username.lower() in config.OWNER_USERNAMES)


def _draft(context: ContextTypes.DEFAULT_TYPE) -> dict:
    draft = context.user_data.setdefault("draft", {})
    draft.setdefault("sectors", set())
    draft.setdefault("degrees", set())
    draft.setdefault("documents", set())
    return draft


def _editing(context: ContextTypes.DEFAULT_TYPE) -> bool:
    return bool(context.user_data.get("editing"))


def _derive_qualification(degrees: set[str]) -> str | None:
    """Highest qualification implied by the degrees the user selected."""
    best_rank = -1
    best_key: str | None = None
    for key in degrees:
        degree = DEGREE_MAP.get(key)
        if not degree or key == "other":
            continue
        qual_key = degree["qual_key"]
        rank = QUAL_MAP[qual_key]["rank"]
        if rank > best_rank:
            best_rank = rank
            best_key = qual_key
    return best_key


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
    ref = payload[1:]
    db = _db(context)
    job = await resolve_job(context.application, ref)
    if job is None:
        return False
    job_id = job.job_id
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



async def _safe_edit(query, text: str, reply_markup=None,  # noqa: ANN001
                     parse_mode: str | None = None,
                     disable_web_page_preview: bool = True) -> bool:
    """Show the next step - edit the message, or send a new one.

    Telegram refuses to edit messages older than 48 hours (and complains
    "message is not modified" when nothing changed). Without this fallback
    the setup buttons would look completely dead.
    """
    try:
        await query.edit_message_text(
            text,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
            disable_web_page_preview=disable_web_page_preview,
        )
        return True
    except BadRequest as exc:
        if "not modified" in str(exc).lower():
            return True
        logger.warning("Could not edit the message (%s) - sending a new one", exc)
    except Exception:  # noqa: BLE001
        logger.exception("Could not edit the message - sending a new one")
    try:
        await query.message.reply_text(
            text,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
            disable_web_page_preview=disable_web_page_preview,
        )
        try:  # remove the stale keyboard so it cannot be tapped again
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:  # noqa: BLE001
            pass
        return True
    except Exception:  # noqa: BLE001
        logger.exception("Could not answer the callback query")
        return False


async def _safe_edit_markup(query, reply_markup) -> bool:  # noqa: ANN001
    """Refresh the keyboard of a multi-select step."""
    try:
        await query.edit_message_reply_markup(reply_markup=reply_markup)
        return True
    except Exception:  # noqa: BLE001
        logger.warning("Could not refresh the keyboard - sending a new one",
                       exc_info=True)
    try:
        await query.message.reply_text(
            "Tick the boxes that apply, then press *Done* -",
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=reply_markup,
        )
        return True
    except Exception:  # noqa: BLE001
        logger.exception("Could not answer the callback query")
        return False


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
    context.user_data["draft"] = {
        "sectors": set(), "degrees": set(), "documents": set(),
    }
    context.user_data.pop("editing", None)
    await query.message.reply_markdown_v2(
        "Step 1️⃣/6 — Type your *full name* now:"
    )
    return S_NAME


async def _show_edit_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    profile = await _db(context).get_user(update.effective_user.id)
    message = update.effective_message
    if profile:
        text = profile_card(profile)
    else:
        text = "You don't have a profile yet\\. Send /start to create one\\."
    if message is not None:
        await message.reply_markdown_v2(
            text, reply_markup=profile_edit_keyboard(),
            disable_web_page_preview=True,
        )
    return S_EDIT_MENU


async def edit_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    profile = await _db(context).get_user(update.effective_user.id)
    if not profile:
        await update.message.reply_text(
            "You don't have a profile yet. Send /start to create one."
        )
        return ConversationHandler.END
    draft = {
        "sectors": set(profile.sectors),
        "degrees": set(profile.degrees),
        "documents": set(profile.documents),
    }
    context.user_data["draft"] = draft
    context.user_data["editing"] = True
    return await _show_edit_menu(update, context)


async def name_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = update.message.text.strip()
    if not (2 <= len(name) <= 64):
        await update.message.reply_text(
            "⚠️ Please send a valid name between 2 and 64 characters."
        )
        return S_NAME
    draft = _draft(context)
    draft["full_name"] = name
    if _editing(context):
        await _db(context).update_user(update.effective_user.id, full_name=name)
        await update.message.reply_markdown_v2("✅ Name updated\\.")
        return await _show_edit_menu(update, context)
    await update.message.reply_markdown_v2(
        f"Thanks, *{md_escape(name)}* 🙂\n\n"
        "Step 2️⃣/6 — Type your *date of birth* as `DD/MM/YYYY` "
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
    draft = _draft(context)
    draft["dob"] = stored
    if _editing(context):
        await _db(context).update_user(update.effective_user.id, dob=stored)
        await update.message.reply_markdown_v2(
            f"✅ Date of birth updated to `{stored}` \\(age {calculate_age(stored)} Yrs\\)\\."
        )
        return await _show_edit_menu(update, context)
    if draft.get("category"):
        # The category was already picked (resumed flow) - do not ask twice.
        await update.message.reply_markdown_v2(
            f"🎂 Recorded: `{stored}` \\(age {calculate_age(stored)} Yrs\\)\n\n"
            "Step 4️⃣/6 — Tick *every degree* you hold "
            "\\(you can pick several — ITI \\+ B\\.Ed, B\\.Sc \\+ M\\.Com\\, …\\):",
            reply_markup=degrees_keyboard(draft.get("degrees", set())),
        )
        return S_DEGREES
    await update.message.reply_markdown_v2(
        f"🎂 Recorded: `{stored}` \\(age {calculate_age(stored)} Yrs\\)\n\n"
        "Step 3️⃣/6 — Choose your *reservation category*:",
        reply_markup=category_keyboard(),
    )
    return S_CATEGORY


async def category_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """The reservation category was picked.

    Works in three situations:
      * during the onboarding (the category step),
      * while editing an existing profile (/edit),
      * on an old keyboard after a restart, when there is no live
        conversation - the category is remembered and the flow continues
        instead of the button doing nothing.
    """
    query = update.callback_query
    key = query.data.split(":", 1)[1]
    if key not in CATEGORY_MAP:
        await query.answer()
        return S_CATEGORY

    draft = _draft(context)
    draft["category"] = key
    profile = await _db(context).get_user(query.from_user.id)

    # No profile and no name yet: the onboarding has to start at the top.
    if not _editing(context) and not profile and not draft.get("full_name"):
        await query.answer(f"✅ {CATEGORY_MAP[key]}", show_alert=True)
        await query.message.reply_markdown_v2(
            f"✅ Category: *{md_escape(CATEGORY_MAP[key])}*\\.\n\n"
            "Step 1️⃣/6 — Type your *full name* now:",
        )
        return S_NAME

    await query.answer(f"✅ {CATEGORY_MAP[key]}")

    if _editing(context) or profile:
        # An existing profile -> update it instead of creating a second one.
        context.user_data["editing"] = True
        if profile:
            draft.setdefault("degrees", set(profile.degrees))
            draft.setdefault("documents", set(profile.documents))
            draft.setdefault("sectors", set(profile.sectors))
        await _db(context).update_user(query.from_user.id, category=key)
        await query.message.reply_markdown_v2(
            f"✅ Category updated to *{md_escape(CATEGORY_MAP[key])}*\\.",
        )
        return await _show_edit_menu(update, context)

    await _safe_edit(
        query,
        "Step 4️⃣/6 — Tick *every degree* you hold "
        "\\(you can pick several — ITI \\+ B\\.Ed, B\\.Sc \\+ M\\.Com\\, …\\):",
        reply_markup=degrees_keyboard(draft.get("degrees", set())),
        parse_mode=ParseMode.MARKDOWN_V2,
    )
    return S_DEGREES


async def degree_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    key = query.data.split(":", 1)[1]
    draft = _draft(context)
    selected: set[str] = draft.setdefault("degrees", set())

    if key != "done":
        if key not in DEGREE_KEYS:
            await query.answer()
            return S_DEGREES
        selected.symmetric_difference_update({key})
        await query.answer(f"✅ {len(selected)} selected")
        await _safe_edit_markup(query, degrees_keyboard(selected))
        return S_DEGREES

    if not selected:
        await query.answer("Please pick at least one degree 🙂", show_alert=True)
        return S_DEGREES

    await query.answer("Degrees saved ✅")
    if _editing(context):
        await _db(context).update_user(query.from_user.id, degrees=sorted(selected))
        await query.message.reply_markdown_v2(
            f"✅ Degrees updated — {len(selected)} selected\\."
        )
        return await _show_edit_menu(update, context)

    await _safe_edit(
        query,
        "Step 5️⃣/6 — Tick the *documents* you already have "
        "\\(we use them to tell you exactly what a vacancy asks for\\):",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=documents_keyboard(draft.get("documents", set())),
    )
    return S_DOCUMENTS


async def document_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    key = query.data.split(":", 1)[1]
    draft = _draft(context)
    selected: set[str] = draft.setdefault("documents", set())

    if key != "done":
        if key not in DOCUMENT_KEYS:
            await query.answer()
            return S_DOCUMENTS
        selected.symmetric_difference_update({key})
        await query.answer(f"✅ {len(selected)} selected")
        await _safe_edit_markup(query, documents_keyboard(selected))
        return S_DOCUMENTS

    await query.answer("Documents saved ✅")
    if _editing(context):
        await _db(context).update_user(query.from_user.id, documents=sorted(selected))
        await query.message.reply_markdown_v2(
            f"✅ Documents updated — {len(selected)} selected\\."
        )
        return await _show_edit_menu(update, context)

    await _safe_edit(
        query,
        "Step 6️⃣/6 — Tick the *job sectors* you want alerts for "
        "\\(select several\\), then press *Done*:",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=sectors_keyboard(draft.get("sectors", set())),
    )
    return S_SECTORS


async def sector_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    key = query.data.split(":", 1)[1]
    draft = _draft(context)
    selected: set[str] = draft.setdefault("sectors", set())

    if key != "done":
        if key not in SECTOR_KEYS:
            await query.answer()
            return S_SECTORS
        selected.symmetric_difference_update({key})
        await query.answer(f"✅ {len(selected)} selected")
        await _safe_edit_markup(query, sectors_keyboard(selected))
        return S_SECTORS

    if not selected:
        await query.answer("Please pick at least one sector 🙂", show_alert=True)
        return S_SECTORS

    await query.answer("Profile saved ✅")
    tg_user = update.effective_user
    db = _db(context)
    degrees = draft.get("degrees", set())
    if _editing(context):
        await db.update_user(tg_user.id, sectors=sorted(selected))
        profile = await db.get_user(tg_user.id)
        await query.message.reply_markdown_v2(
            f"✅ Job preferences updated\\.\n\n{profile_card(profile)}",
            parse_mode=ParseMode.MARKDOWN_V2,
            disable_web_page_preview=True,
        )
        return await _show_edit_menu(update, context)

    profile = await db.upsert_user(
        user_id=tg_user.id,
        username=tg_user.username,
        full_name=draft["full_name"],
        category=draft["category"],
        qualification=_derive_qualification(degrees) or "graduate",
        sectors=sorted(selected),
        dob=draft.get("dob"),
        degrees=sorted(degrees),
        documents=sorted(draft.get("documents", set())),
    )
    context.user_data.pop("draft", None)
    context.user_data.pop("editing", None)
    await _safe_edit(
        query,
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


async def profile_edit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Buttons of the /edit menu."""
    query = update.callback_query
    action = query.data.split(":", 1)[1]
    await query.answer()
    draft = _draft(context)

    if action == "close":
        profile = await _db(context).get_user(query.from_user.id)
        if profile:
            await query.message.reply_markdown_v2(
                profile_card(profile),
                reply_markup=main_menu_keyboard(profile.active),
                disable_web_page_preview=True,
            )
        return ConversationHandler.END
    if action == "name":
        await query.message.reply_markdown_v2(
            "✏️ Send your *full name* now:"
        )
        return S_NAME
    if action == "dob":
        await query.message.reply_markdown_v2(
            "🎂 Send your *date of birth* as `DD/MM/YYYY`:"
        )
        return S_DOB
    if action == "category":
        await query.message.reply_markdown_v2(
            "🏷️ Choose your *reservation category*:",
            reply_markup=category_keyboard(),
        )
        return S_CATEGORY
    if action == "degrees":
        await query.message.reply_markdown_v2(
            "📚 Tick *every degree* you hold, then press *Done*:",
            reply_markup=degrees_keyboard(draft.get("degrees", set())),
        )
        return S_DEGREES
    if action == "documents":
        await query.message.reply_markdown_v2(
            "📎 Tick the *documents* you own, then press *Done*:",
            reply_markup=documents_keyboard(draft.get("documents", set())),
        )
        return S_DOCUMENTS
    if action == "sectors":
        await query.message.reply_markdown_v2(
            "📂 Tick the *job sectors* you want, then press *Done*:",
            reply_markup=sectors_keyboard(draft.get("sectors", set())),
        )
        return S_SECTORS
    return S_EDIT_MENU


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("draft", None)
    context.user_data.pop("editing", None)
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
    state_filter = _state_filter(context.args)
    status = await update.effective_message.reply_text("🔎 Fetching the latest jobs…")
    try:
        jobs = await _scraper(context).fetch_latest_jobs()
    except ScraperError:
        logger.exception("Latest-jobs fetch failed")
        await status.edit_text(
            "⚠️ Couldn't reach the job sources right now. Please try again in a few minutes."
        )
        return
    remember_jobs(context.application, jobs)
    matched = [job for job in jobs if matcher.title_matches(profile, job)]
    heading = "Latest Matching Jobs"
    if state_filter:
        matched = await _filter_by_state(context, matched, state_filter)
        heading = f"Latest Jobs · {STATE_MAP[state_filter]['label']}"
    await status.edit_text(f"✅ {len(matched)} matching jobs — use Next / Previous to browse.")
    await open_browser(
        update, context, profile.user_id, matched,
        kind="latest", heading=heading,
    )


def _state_filter(args) -> str | None:
    """Turn '/latest bihar' into the internal state key."""
    if not args:
        return None
    query = " ".join(args).strip().lower()
    if not query:
        return None
    for key, state in STATE_MAP.items():
        if query in {key, key.replace("_", " ")} or query in state["label"].lower():
            return key
    for key, state in STATE_MAP.items():
        if any(alias in query for alias in state["aliases"]):
            return key
    return None


async def _filter_by_state(context, jobs, state_key: str) -> list:
    """Keep only the vacancies published for one state."""
    db = _db(context)
    kept = []
    for job in jobs:
        detail = await db.get_job_detail(job.job_id)
        if detail and state_key in (detail.states or []):
            kept.append(job)
    return kept


# ------------------------------------------------------------------ menu taps
async def menu_edit_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await edit_profile(update, context)


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
    elif action == "admit":
        await admit_cards(update, context)
    elif action == "result":
        await results(update, context)
    elif action == "contact":
        await _contact_prompt(query.message)
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
        remember_jobs(context.application, jobs)
        matched = [job for job in jobs if matcher.title_matches(profile, job)]
        await status.edit_text(f"✅ {len(matched)} matching jobs — use Next / Previous.")
        await open_browser(
            update, context, profile.user_id, matched,
            kind="latest", heading="Latest Matching Jobs",
        )


async def full_text_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """'Full Notification Text' - sends the complete notice in safe chunks."""
    query = update.callback_query
    ref = query.data.split(":", 1)[1]
    db = _db(context)
    job = await resolve_job(context.application, ref)
    if job is None:
        await query.answer("Job no longer exists.", show_alert=True)
        return
    job_id = job.job_id
    detail = await db.get_job_detail(job_id)
    await query.answer()
    text = full_detail_text(job, detail)
    for chunk in _split_for_telegram(text):
        await query.message.reply_markdown_v2(
            chunk, disable_web_page_preview=True,
        )


def _split_for_telegram(text: str, limit: int = 3900) -> list[str]:
    """Split long text at line boundaries (never inside a MarkdownV2 escape).

    A single oversized line (a long qualification paragraph) is hard-split on
    a safe boundary so no chunk can exceed the Telegram limit.
    """
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for line in text.split("\n"):
        pieces = [line]
        if len(line) > limit:
            pieces = []
            rest = line
            while len(rest) > limit:
                cut = limit
                while cut > 0 and rest[cut - 1] == "\\":
                    cut -= 1
                pieces.append(rest[:cut])
                rest = rest[cut:]
            pieces.append(rest)
        for piece in pieces:
            if size + len(piece) + 1 > limit and current:
                chunks.append("\n".join(current))
                current, size = [], 0
            current.append(piece)
            size += len(piece) + 1
    if current:
        chunks.append("\n".join(current))
    return chunks


async def orphaned_setup_callback(update: Update,
                                   context: ContextTypes.DEFAULT_TYPE) -> None:
    """A setup button was tapped but the conversation no longer exists.

    This happens after a restart, or when a *second* instance of the bot
    (same token) receives the tap while the conversation lives in the other
    process. Ignoring the tap makes the bot look broken, so we always
    answer and offer a one-tap way back.
    """
    query = update.callback_query
    await query.answer("Session expired - please tap below", show_alert=True)
    profile = None
    try:
        profile = await _db(context).get_user(query.from_user.id)
    except Exception:  # noqa: BLE001 - the reply must go out anyway
        logger.exception("Could not read the profile for the expired session")
    if profile:
        await query.message.reply_markdown_v2(
            "⌛ *Your setup session expired*\\.\\n\\n"
            "That happens after a bot restart or when two instances run with "
            "the same token\\. Your profile is safe — tap *Edit Profile* to "
            "change anything, or *Get Started* to continue where you left off\\.",
            reply_markup=resume_setup_keyboard(),
            disable_web_page_preview=True,
        )
        return
    await query.message.reply_markdown_v2(
        "⌛ *Your setup session expired*\\.\\n\\n"
        "Tap *Get Started* and we will begin again — it only takes a minute\\.",
        reply_markup=resume_setup_keyboard(),
        disable_web_page_preview=True,
    )


async def webapp_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Personal link to the web dashboard."""
    secret = config.WEB_APP_SECRET
    if not secret:
        await update.message.reply_text(
            "🌐 The web dashboard is not enabled on this deployment."
        )
        return
    base = config.PUBLIC_BASE_URL.rstrip("/")
    if not base:
        await update.message.reply_text(
            "🌐 Set PUBLIC_BASE_URL (your public domain) to use the dashboard."
        )
        return
    token = sign_token(update.effective_user.id, secret)
    await update.message.reply_markdown_v2(
        "🌐 *Your personal dashboard*\n\n"
        "Open it on your phone to edit degrees/documents and browse the "
        "latest vacancies with filters\\.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🚀 Open Dashboard", url=f"{base}/?t={token}",
                                 style=BLUE)
        ]]),
        disable_web_page_preview=True,
    )


async def fallback_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.user_data.get("draft") or context.user_data.get("reminder_job_id"):
        return  # a conversation handler owns this input
    await update.message.reply_text(
        "Use /start to set up your profile or /help to see everything I can do."
    )


# ------------------------------------------------------------- admit cards
async def _section_browser(update: Update, context: ContextTypes.DEFAULT_TYPE,
                           path: str, heading: str, kind: str) -> None:
    """Show a section of the source site (admit cards, results, ...)."""
    status = await update.effective_message.reply_text("🔎 Fetching\u2026")
    try:
        jobs = await _scraper(context).fetch_section(path)
    except ScraperError:
        logger.exception("Section fetch failed: %s", path)
        try:
            await status.edit_text(
                "⚠️ Couldn't reach the job sources right now. "
                "Please try again in a few minutes."
            )
        except Exception:  # noqa: BLE001
            pass
        return
    await status.edit_text(f"✅ {len(jobs)} notices \u2014 tap a title for the full card.")
    await open_browser(
        update, context, update.effective_user.id, jobs[:60],
        kind=kind, heading=heading,
    )


async def admit_cards(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Latest admit cards."""
    await _section_browser(
        update, context, config.MIRROR_ADMIT_CARD_PATH,
        heading="🎫 Latest Admit Cards", kind="admit",
    )


async def results(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Latest results."""
    await _section_browser(
        update, context, config.MIRROR_RESULT_PATH,
        heading="🏁 Latest Results", kind="result",
    )


# ---------------------------------------------------------- owner contact
async def _contact_prompt(message) -> None:
    """The standard "reach the owner" message (button + instructions)."""
    await message.reply_markdown_v2(
        "💬 *Need help\\, found a bug or have a suggestion?*\n\n"
        f"• Write to *Technical Serena* directly: @{config.OWNER_PRIMARY}\n"
        "• Or send it here and it is forwarded automatically: "
        "`/contact your message`\n\n"
        "Bug reports are welcome \u2014 they make the bot better for everyone\\.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "💬 Open Telegram chat",
                url=f"https://t.me/{config.OWNER_PRIMARY}",
                style=GREEN,
            ),
        ]]),
    )


async def contact_owner(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Let a user reach the bot owner (bugs, suggestions, help)."""
    text = " ".join(context.args or []).strip()
    owner_ids = context.application.bot_data.get("owner_chat_ids") or set()
    if not text:
        await _contact_prompt(update.effective_message)
        return
    if not owner_ids:
        await update.effective_message.reply_text(
            f"Please write directly to @{config.OWNER_PRIMARY} \u2014 the owner "
            "account is not reachable for forwarding right now."
        )
        return
    user = update.effective_user
    header = (
        "\U0001f4e9 *New message from a user*\\n\\n"
        f"Name: {md_escape(user.full_name or '-')}\\n"
        f"Username: @{md_escape(user.username or '-')}\\n"
        f"Chat ID: `{user.id}`\\n\\n"
    )
    delivered = 0
    for chat_id in owner_ids:
        try:
            await context.bot.send_message(
                chat_id=chat_id, text=header + md_escape(text),
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            delivered += 1
        except Exception:  # noqa: BLE001
            logger.exception("Could not forward the message to owner %s", chat_id)
    if delivered:
        await update.effective_message.reply_text(
            "\u2705 Sent to the owner \u2014 @"
            f"{config.OWNER_PRIMARY} will get back to you."
        )
    else:
        await update.effective_message.reply_text(
            "Could not reach the owner right now \u2014 please write to "
            f"@{config.OWNER_PRIMARY}."
        )


async def owner_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Owner: /reply <chat_id> <message> - answers a user directly."""
    if not _is_owner(update):
        await update.effective_message.reply_text("Only the bot owner can use this.")
        return
    if not context.args or len(context.args) < 2:
        await update.effective_message.reply_text(
            "Usage: /reply <chat_id> your message"
        )
        return
    try:
        target = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("The chat id must be a number.")
        return
    body = " ".join(context.args[1:]).strip()
    try:
        await context.bot.send_message(
            chat_id=target,
            text=f"💬 *SERENA support*\n\n{md_escape(body)}",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Could not deliver the reply to %s", target)
        await update.effective_message.reply_text("Could not deliver that message.")
        return
    await update.effective_message.reply_text("✅ Message sent.")


# ------------------------------------------------------- digest job card
async def digest_job_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """A job tapped in the daily digest - show the full card."""
    query = update.callback_query
    await query.answer()
    ref = query.data.split(":", 1)[1]
    db = _db(context)
    job = await resolve_job(context.application, ref)
    if job is None:
        await query.message.reply_text("That job is no longer in the catalogue.")
        return
    job_id = job.job_id
    profile = await db.get_user(query.from_user.id)
    detail = await db.get_job_detail(job_id)
    age_info = None
    if profile and detail:
        _, age_info = matcher.age_matches(profile, detail)
    from bot.cards import job_card
    from bot.keyboards import job_detail_keyboard
    from bot.reminders import _guest
    target = profile or _guest()
    await query.message.reply_markdown_v2(
        job_card(job, detail, target, age_info),
        reply_markup=job_detail_keyboard(
            job, detail,
            await db.is_saved(target.user_id, job_id) if profile else False,
        ),
        disable_web_page_preview=True,
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


async def admin_digest_preview(update: Update,
                               context: ContextTypes.DEFAULT_TYPE) -> None:
    """Owner preview of the daily digest."""
    if not _is_owner(update):
        await update.message.reply_text("🚫 Owner-only command.")
        return
    from bot.digest import build_digest

    profile = await _db(context).get_user(update.effective_user.id)
    if profile is None:
        await update.message.reply_text("You have no profile - send /start first.")
        return
    text = await build_digest(context.application, profile)
    if not text:
        await update.message.reply_text(
            "📭 Nothing to report right now (no new jobs, nothing closing)."
        )
        return
    await update.message.reply_markdown_v2(text, disable_web_page_preview=True)


async def admin_channel_test(update: Update,
                              context: ContextTypes.DEFAULT_TYPE) -> None:
    """Owner: post a test message into the broadcast channel."""
    if not _is_owner(update):
        await update.message.reply_text("🚫 Owner-only command.")
        return
    channel = config.BROADCAST_CHANNEL_ID
    if not channel:
        await update.message.reply_text(
            "📢 Set `BROADCAST_CHANNEL_ID` (e.g. @your_channel) to enable it."
        )
        return
    try:
        await context.bot.send_message(
            chat_id=channel,
            text="📢 *Channel connected*\nEvery new vacancy will be mirrored here "
                 "automatically\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
    except Exception as exc:  # noqa: BLE001
        await update.message.reply_text(f"❌ Could not post: {exc}")
        return
    await update.message.reply_text(f"✅ Test message posted to {channel}.")


async def admin_sources(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_owner(update):
        await update.message.reply_text("🚫 Owner-only command.")
        return
    status = await update.message.reply_text("🩺 Probing every data source…")
    report = await _scraper(context).source_healthcheck()
    text = format_sources_report(report, _scraper(context).status)
    await status.edit_text(text, parse_mode=ParseMode.MARKDOWN_V2)


def format_sources_report(report: list[dict], scraper_status: dict) -> str:
    """Render the /sources health report.

    A failing *fallback* source is not an error - the bot only needs one
    working source, and the mirror is the primary one.
    """
    primary = config.SOURCE_ORDER[0] if config.SOURCE_ORDER else "mirror"
    lines = ["🩺 *Data\\-source health*", "━━━━━━━━━━━━━━━━━━"]
    primary_ok = False
    for entry in report:
        source = md_escape(entry["source"])
        if entry["ok"]:
            if entry["source"] == primary:
                primary_ok = True
                lines.append(f"✅ *{source}* — {entry['jobs']} jobs · primary")
            else:
                lines.append(f"✅ *{source}* — {entry['jobs']} jobs · standby ready")
        elif entry["source"] == primary:
            lines.append(f"❌ *{source}* — {md_escape(_short_error(entry['error']))}")
        else:
            lines.append(
                f"🟡 *{source}* — standby · {md_escape(_short_error(entry['error']))}"
            )
    lines.append("━━━━━━━━━━━━━━━━━━")
    if primary_ok:
        lines.append(
            "✅ *Primary source is healthy* — the bot is fully operational\\."
        )
    else:
        lines.append(
            "⚠️ *Primary source is down* — the bot is using a fallback source\\."
        )
    lines.append(
        "ℹ️ Fallback sources stay on standby and are used automatically if the "
        "primary one fails\\."
    )
    lines.append(
        f"Last success: {md_escape(scraper_status.get('last_success_at') or 'never')} "
        f"via {md_escape(scraper_status.get('last_success_source') or '—')}"
    )
    return "\n".join(lines)


def _short_error(error: str | None) -> str:
    """Compress a raw scraper error into one readable line."""
    if not error:
        return "not reachable"
    low = error.lower()
    if "403" in low:
        return "HTTP 403 (site blocks datacenter IPs)"
    if "reader proxy" in low or "jina" in low:
        return "reader proxy blocked"
    if "zero parseable jobs" in low:
        return "no parseable jobs returned"
    if "http" in low:
        match = re.search(r"HTTP \d{3}", error, re.IGNORECASE)
        return match.group() if match else error[:60]
    return error[:70]


# ------------------------------------------------------------ owner: /users
async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Owner-only list of every subscriber + a jump into their profile."""
    if not _is_owner(update):
        await update.message.reply_text("🚫 Owner-only command.")
        return
    db = _db(context)
    users = await db.all_users()
    if not users:
        await update.message.reply_text("📭 No subscribers yet.")
        return
    context.application.bot_data.setdefault("admin_users", {})[
        update.effective_user.id
    ] = {"page": 0}
    await _render_admin_users(update, context, update.effective_user.id)


async def _render_admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE,
                               owner_id: int, edit: bool = False) -> None:
    db = _db(context)
    users = await db.all_users()
    total_pages = max(1, -(-len(users) // ADMIN_USERS_PAGE))
    state = context.application.bot_data.setdefault("admin_users", {}).setdefault(
        owner_id, {"page": 0}
    )
    state["page"] = min(state.get("page", 0), total_pages - 1)
    page = state["page"]
    chunk = users[page * ADMIN_USERS_PAGE:(page + 1) * ADMIN_USERS_PAGE]
    lines = [
        "👥 *All Subscribers*",
        f"📄 Page {page + 1} / {total_pages} · {len(users)} total",
        "👆 Tap a name to open that profile",
        "━━━━━━━━━━━━━━━━━━",
    ]
    for profile in chunk:
        degrees = ", ".join(profile.degree_labels) or "—"
        lines.append(
            f"• *{md_escape(profile.full_name)}*"
            f"{' @' + md_escape(profile.username) if profile.username else ''}"
            f" · {md_escape(profile.category)} · {md_escape(degrees)}"
        )
    lines.append("━━━━━━━━━━━━━━━━━━")
    markup = admin_users_keyboard(chunk, page, total_pages)
    text = "\n".join(lines)
    if edit and update.callback_query is not None:
        try:
            await update.callback_query.edit_message_text(
                text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=markup,
                disable_web_page_preview=True,
            )
            return
        except Exception:  # noqa: BLE001 - message not editable -> send a new one
            pass
    message = update.effective_message
    if message is not None:
        await message.reply_markdown_v2(
            text, reply_markup=markup, disable_web_page_preview=True,
        )


async def admin_users_callback(update: Update,
                               context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not _is_owner(update):
        await query.answer("🚫 Owner-only command.", show_alert=True)
        return
    parts = query.data.split(":")
    action = parts[1] if len(parts) > 1 else ""
    await query.answer()
    owner_id = query.from_user.id

    if action == "users":
        await _render_admin_users(update, context, owner_id, edit=True)
        return

    if action == "page":
        page_action = parts[2] if len(parts) > 2 else "noop"
        if page_action == "noop":
            return
        state = context.application.bot_data.setdefault("admin_users", {}).setdefault(
            owner_id, {"page": 0}
        )
        state["page"] = max(0, state.get("page", 0) + (1 if page_action == "n" else -1))
        await _render_admin_users(update, context, owner_id, edit=True)
        return

    if action == "prof" and len(parts) > 2:
        user_id = int(parts[2])
        db = _db(context)
        profile = await db.get_user(user_id)
        if profile is None:
            await query.message.reply_text("That user no longer exists.")
            return
        saved = await db.list_saved(user_id)
        saved_lines = "\n".join(
            f"  • {md_escape(item.title[:70])}"
            for item in saved[:10]
        ) or "  • none"
        card = admin_user_card(
            profile,
            saved_count=len(saved),
            extra=f"🔖 *Saved Jobs:*\n{saved_lines}",
        )
        await query.message.reply_markdown_v2(
            card,
            reply_markup=admin_profile_keyboard(profile, len(saved)),
            disable_web_page_preview=True,
        )
        return

    if action == "saved" and len(parts) > 2:
        user_id = int(parts[2])
        saved = await _db(context).list_saved(user_id)
        if not saved:
            await query.message.reply_text("That user has no saved jobs.")
            return
        lines = ["🔖 *Saved Jobs of this subscriber*", "━━━━━━━━━━━━━━━━━━"]
        for item in saved[:25]:
            lines.append(f"• {md_escape(item.title[:80])}")
        await query.message.reply_markdown_v2(
            "\n".join(lines), disable_web_page_preview=True,
        )
        return


async def _alert_duplicate_instance(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Tell the owners that a second instance is eating the updates."""
    app = context.application
    owner_ids: set[int] = app.bot_data.get("owner_chat_ids", set())
    if not owner_ids:
        return
    last = app.bot_data.get("last_duplicate_alert")
    now = __import__("time").monotonic()
    if last is not None and now - last < 1800:
        return
    app.bot_data["last_duplicate_alert"] = now
    text = (
        "🚨 *Duplicate instance detected*\n\n"
        "Another bot instance is polling with the same token, so Telegram is "
        "splitting the updates between them — that is why buttons sometimes "
        "look dead and the bot feels silent\\.\\n\\n"
        "✅ Stop every other copy \\(cloud service, Termux, local run\\) and "
        "keep exactly one running\\."
    )
    for chat_id in owner_ids:
        try:
            await app.bot.send_message(chat_id, text, parse_mode=ParseMode.MARKDOWN_V2)
        except Exception:  # noqa: BLE001
            logger.exception("Could not deliver the duplicate-instance alert")


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
        await _alert_duplicate_instance(context)
        return
    if isinstance(error, (NetworkError, TimedOut)):
        logger.warning("Telegram network hiccup: %s", error)
        return

    logger.exception("Unhandled error while processing update %s", update, exc_info=error)
    if not isinstance(update, Update):
        return
    # A button press must never look dead: stop the spinner and say something.
    if update.callback_query is not None:
        try:
            await update.callback_query.answer(
                "⚠️ Something went wrong - please tap again", show_alert=True
            )
        except Exception:  # noqa: BLE001
            logger.exception("Failed to answer the callback query")
    if update.effective_message:
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
            # A reservation button tapped without a live conversation (after a
            # restart, or on an old keyboard) must still work.
            CallbackQueryHandler(category_chosen, pattern="^cat:"),
        ],
        states={
            S_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, name_received)],
            S_DOB: [MessageHandler(filters.TEXT & ~filters.COMMAND, dob_received)],
            S_CATEGORY: [CallbackQueryHandler(category_chosen, pattern="^cat:")],
            S_DEGREES: [CallbackQueryHandler(degree_chosen, pattern="^deg:")],
            S_DOCUMENTS: [CallbackQueryHandler(document_chosen, pattern="^doc:")],
            S_SECTORS: [CallbackQueryHandler(sector_chosen, pattern="^sec:")],
            S_EDIT_MENU: [CallbackQueryHandler(profile_edit_callback, pattern="^pe:")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
        # Persist the conversation state so a button tapped after a restart
        # (or a redeploy) still works instead of dying silently. Only possible
        # when the application has a persistence attached (see bot/main.py).
        name="onboarding",
        persistent=app.persistence is not None,
    )
    app.add_handler(conversation)

    app.add_handler(CommandHandler("profile", show_profile))
    app.add_handler(CommandHandler("latest", latest))
    app.add_handler(CommandHandler("pause", pause))
    app.add_handler(CommandHandler("resume", resume))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("about", about_command))
    app.add_handler(CommandHandler("admit", admit_cards))
    app.add_handler(CommandHandler("result", results))
    app.add_handler(CommandHandler("contact", contact_owner))
    app.add_handler(CommandHandler("reply", owner_reply))

    app.add_handler(CommandHandler("stats", admin_stats))
    app.add_handler(CommandHandler("broadcast", admin_broadcast))
    app.add_handler(CommandHandler("scrape_now", admin_scrape_now))
    app.add_handler(CommandHandler("sources", admin_sources))
    app.add_handler(CommandHandler("users", admin_users))
    app.add_handler(CommandHandler("webapp", webapp_command))
    app.add_handler(CommandHandler("digest", admin_digest_preview))
    app.add_handler(CommandHandler("channel", admin_channel_test))

    app.add_handler(TypeHandler(Update, track_owner), group=-1)
    app.add_handler(CallbackQueryHandler(menu_handler, pattern="^menu:"))
    # The in-chat job browser (Previous / Next) - registered here so that
    # /latest and /scrape_now pagination actually answers the buttons.
    app.add_handler(CallbackQueryHandler(browser_callback, pattern="^br:"))
    app.add_handler(CallbackQueryHandler(full_text_callback, pattern="^full:"))
    app.add_handler(CallbackQueryHandler(admin_users_callback, pattern="^adm:"))
    # A job tapped in the daily digest -> the full job card
    app.add_handler(CallbackQueryHandler(digest_job_callback, pattern="^dig:"))
    # A setup button that arrives without a live conversation (restart or a
    # duplicate instance) must never be ignored silently.
    app.add_handler(CallbackQueryHandler(orphaned_setup_callback,
                                         pattern="^(cat|deg|doc|sec|pe):"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, fallback_text))
    app.add_error_handler(global_error_handler)

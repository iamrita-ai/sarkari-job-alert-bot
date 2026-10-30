"""Formatted Telegram message cards - all rendered in MarkdownV2.

Rule of thumb: every dynamic value passes through ``md_escape``; static
template literals use pre-escaped MarkdownV2 punctuation.

The v1.4 card shows the *whole* notification: start date, last date, fee
payment date, exam date, admit card, result, total posts, selection process,
application mode, the full qualification text and the documents a candidate
needs. Long texts are clipped on a safe boundary (never inside an escape
sequence) and the complete version stays one tap away.
"""
from __future__ import annotations

from bot import config
from bot.constants import (
    CATEGORY_AGE_RELAXATION,
    CATEGORY_MAP,
    DOCUMENT_MAP,
    QUAL_MAP,
)
from bot.branding import DIVIDER, ICON_ALERT, ICON_SPARK
from bot.models import JobDetail, JobSummary, UserProfile
from bot.utils import bold, code, link, md_escape
NOT_DISCLOSED = "Check official notification"
TELEGRAM_LIMIT = 4096
CAPTION_LIMIT = 1024


def _value(value: str | None) -> str:
    return md_escape(value) if value and value.strip() else md_escape(NOT_DISCLOSED)


def _clip(text: str, limit: int) -> str:
    """Clip to ``limit`` chars without breaking a MarkdownV2 escape pair."""
    if len(text) <= limit:
        return text
    cut = limit - 1
    while cut > 0 and text[cut - 1] == "\\":
        cut -= 1
    return text[:cut].rstrip() + "…"


def _assemble(top: list[str], middle: list[str], bottom: list[str],
              limit: int) -> str:
    """Join the three card zones, clipping the *middle* (the long
    qualification text) so the tail - apply links, PDF, credits - can never
    be pushed out by Telegram's message limit."""
    top_text = "\n".join(top)
    bottom_text = "\n".join(bottom)
    middle_text = "\n".join(middle)
    allowance = limit - len(top_text) - len(bottom_text) - 2
    if allowance < 30:
        middle_text = ""
    elif len(middle_text) > allowance:
        middle_text = _clip(middle_text, allowance)
    parts = [part for part in (top_text, middle_text, bottom_text) if part]
    return "\n".join(parts)


def _age_line(detail: JobDetail, profile: UserProfile, age_info: dict | None) -> str:
    if detail.min_age is None and detail.max_age is None:
        published = md_escape("See notification")
    else:
        published = f"{detail.min_age or '—'} – {detail.max_age or '—'} Yrs"
    line = f"📆 {bold('Age Limit:')} {published}"
    if age_info and age_info.get("user_age") is not None:
        relax = age_info["relaxation"]
        cat = md_escape(CATEGORY_MAP.get(profile.category, profile.category))
        if relax:
            line += (
                f"\n👤 {bold('You:')} {age_info['user_age']} Yrs · {cat} "
                f"\\(\\+{relax} relax → max {age_info['effective_max']}\\)"
            )
        else:
            line += f"\n👤 {bold('You:')} {age_info['user_age']} Yrs · {cat}"
    return line


def _dates_block(detail: JobDetail, labels: dict | None = None) -> list[str]:
    """The important-dates table of the notification."""
    lab = labels or {}
    rows = [
        ("🟢 " + lab.get("start_date", "Apply Online Start Date"), detail.apply_start_date),
        ("🔴 " + lab.get("last_date", "Apply Online Last Date"), detail.apply_last_date),
        ("💳 " + lab.get("fee_date", "Fee Payment Last Date"), detail.fee_last_date),
        ("✏️ " + lab.get("correction_date", "Correction Date"), detail.correction_date),
        ("📝 " + lab.get("exam_date", "Exam Date"), detail.exam_date),
        ("🎫 " + lab.get("admit_card", "Admit Card"), detail.admit_card_date),
        ("🏁 " + lab.get("result_date", "Result Date"), detail.result_date),
    ]
    lines = []
    for label, value in rows:
        if value and value.strip():
            lines.append(f"• {bold(label + ':')} {md_escape(value.strip())}")
    return lines


def _breakdown_line(detail: JobDetail, profile: UserProfile | None) -> str:
    """Category-wise vacancy breakdown, with the user's own category marked."""
    breakdown = detail.vacancy_breakdown or {}
    if not breakdown:
        return ""
    user_category = (profile.category if profile else "") or ""
    bits: list[str] = []
    for label, value in list(breakdown.items())[:8]:
        marker = " ← " + user_category if label.upper().startswith(user_category.upper()) else ""
        bits.append(f"{md_escape(label)} {md_escape(value)}{marker}")
    return " · ".join(bits)


def _state_line(detail: JobDetail) -> str:
    if not detail.states:
        return ""
    from bot.constants import STATE_MAP

    labels = [STATE_MAP[s]["label"] for s in detail.states if s in STATE_MAP]
    return md_escape(", ".join(labels))


def _documents_block(detail: JobDetail, profile: UserProfile | None,
                     labels: dict | None = None) -> list[str]:
    required = detail.documents_required or []
    if not required:
        return []
    lab = labels or {}
    owned = set(profile.documents) if profile else set()
    lines = [f"📎 {bold(lab.get('documents', 'Documents Needed') + ':')}"]
    for key in required:
        label = DOCUMENT_MAP.get(key, {}).get("label", key)
        if not profile:
            lines.append(f"• {md_escape(label)}")
        elif key in owned:
            lines.append(f"• ✅ {md_escape(label)}")
        else:
            lines.append(f"• ❌ {md_escape(label)}")
    return lines


def _hindi_block(detail: JobDetail, profile: UserProfile,
                 age_info: dict | None = None) -> list[str]:
    """Compact Hindi version of the key facts (feature: Hindi + English cards)."""
    from bot.constants import HINDI_LABELS as H

    lines = ["🇮🇳 *हिंदी में देखें*"]
    state = _state_line(detail)
    if state:
        lines.append(f"📍 *राज्य:* {state}")
    if detail.total_posts:
        lines.append(f"👥 *{H['total_posts']}:* {md_escape(detail.total_posts)}")
    if detail.apply_start_date:
        lines.append(f"🟢 *{H['start_date']}:* {md_escape(detail.apply_start_date)}")
    if detail.apply_last_date:
        lines.append(f"🔴 *{H['last_date']}:* {md_escape(detail.apply_last_date)}")
    qualification = detail.qualification or detail.eligibility
    if qualification:
        lines.append(f"🎓 *{H['qualification']}:* {md_escape(qualification[:220])}")
    if detail.fee:
        lines.append(f"💳 *{H['fee']}:* {md_escape(detail.fee)}")
    if detail.min_age or detail.max_age:
        lines.append(
            f"📆 *{H['age_limit']}:* {detail.min_age or '—'} – {detail.max_age or '—'} Yrs"
        )
    if detail.ai_summary_hi:
        lines.append("")
        lines.append(f"🧠 *{H['qualification']}:* {md_escape(detail.ai_summary_hi)}")
    return lines


def job_card(
    job: JobSummary,
    detail: JobDetail | None,
    profile: UserProfile,
    age_info: dict | None = None,
    language: str | None = None,
) -> str:
    """Full MarkdownV2 card for a text message (up to 4096 chars)."""
    detail = detail or JobDetail()
    language = (language or config.CARD_LANGUAGE or "en").lower()
    top = [
        f"{ICON_SPARK} *{config.BRAND_NAME} MATCH — NEW JOB FOR YOU*",
        DIVIDER,
        f"📝 {link(job.title, job.url)}",
    ]
    if detail.organization:
        top.append(f"🏢 *Organisation:* {md_escape(detail.organization)}")
    state = _state_line(detail)
    if state:
        top.append(f"📍 *State:* {state}")
    meta: list[str] = []
    if detail.post_date:
        meta.append(f"📅 *Notification:* {md_escape(detail.post_date)}")
    if detail.total_posts:
        meta.append(f"👥 *Total Posts:* {md_escape(detail.total_posts)}")
    if meta:
        top.append(" · ".join(meta))
    if detail.selection_process:
        top.append(f"🧭 *Selection:* {md_escape(detail.selection_process)}")
    if detail.application_mode:
        top.append(f"💻 *Apply Mode:* {md_escape(detail.application_mode)}")

    date_lines = _dates_block(detail)
    if date_lines:
        top.append(f"🗓 *Important Dates*")
        top.extend(date_lines)

    # --- qualification (full text, exactly as published) ------------------
    middle: list[str] = []
    qualification = detail.qualification or detail.eligibility
    if qualification:
        middle.append(f"🎓 *Qualification:*")
        middle.append(md_escape(qualification.strip()))

    bottom: list[str] = []
    if detail.salary:
        bottom.append(f"💰 *Salary / Pay:* {md_escape(detail.salary)}")
    if detail.fee:
        bottom.append(f"💳 *Application Fee:* {md_escape(detail.fee)}")
    bottom.append(_age_line(detail, profile, age_info))

    breakdown = _breakdown_line(detail, profile)
    if breakdown:
        bottom.append(f"👥 *Posts by category:* {breakdown}")

    doc_lines = _documents_block(detail, profile)
    if doc_lines:
        bottom.extend(doc_lines)

    if detail.ai_summary:
        bottom.append(f"🧠 *In short:* {md_escape(detail.ai_summary)}")

    if language in {"hi", "both"}:
        bottom.append("")
        bottom.extend(_hindi_block(detail, profile, age_info))

    bottom.append(DIVIDER)
    if detail.apply_url:
        bottom.append(f"👉 {link('CLICK HERE TO FILL THE FORM', detail.apply_url)}")
    detail_links = [link("🌐 Full Details", job.url)]
    if detail.notification_pdf:
        detail_links.append(link("📄 Notification PDF", detail.notification_pdf))
    if detail.official_site:
        detail_links.append(link("🏛 Official Website", detail.official_site))
    if detail.short_notice:
        detail_links.append(link("📰 Short Notice", detail.short_notice))
    bottom.append("  ·  ".join(detail_links))
    bottom.append(f"🤖 {md_escape(config.OWNER_HANDLES)}")
    return _assemble(top, middle, bottom, TELEGRAM_LIMIT)


def full_detail_text(job: JobSummary, detail: JobDetail | None) -> str:
    """The complete notification text - sent in chunks by the 'Full
    Notification' button so nothing is lost to the 4096 char limit."""
    detail = detail or JobDetail()
    lines = [
        f"📄 *Full Notification — {md_escape(job.title)}*",
        DIVIDER,
        f"🔗 {link('Open the page', job.url)}",
    ]
    if detail.qualification or detail.eligibility:
        lines.append("")
        lines.append(f"🎓 {bold('Qualification (full text)')}")
        lines.append(md_escape((detail.qualification or detail.eligibility).strip()))
    if detail.important_dates:
        lines.append("")
        lines.append(f"🗓 {bold('Important Dates (as published)')}")
        lines.append(md_escape(detail.important_dates))
    if detail.how_to_apply:
        lines.append("")
        lines.append(f"📝 {bold('How To Apply')}")
        lines.append(md_escape(detail.how_to_apply))
    if detail.age_limit:
        lines.append("")
        lines.append(f"📆 {bold('Age Limit:')} {md_escape(detail.age_limit)}")
    if detail.documents_required:
        labels = [
            DOCUMENT_MAP.get(k, {}).get("label", k) for k in detail.documents_required
        ]
        lines.append(f"📎 {bold('Documents Needed:')} {md_escape(', '.join(labels))}")
    lines.append(DIVIDER)
    lines.append(f"🤖 Managed by {md_escape(config.OWNER_HANDLES)}")
    return "\n".join(lines)


def photo_caption(
    job: JobSummary,
    detail: JobDetail | None,
    profile: UserProfile,
    age_info: dict | None = None,
    language: str | None = None,
) -> str:
    """Compact MarkdownV2 caption - Telegram photo captions are capped at 1024."""
    detail = detail or JobDetail()
    top = [
        f"{ICON_SPARK} *{config.BRAND_NAME} MATCH — NEW JOB FOR YOU*",
        f"📝 {link(job.title, job.url)}",
    ]
    if detail.organization:
        top.append(f"🏢 {md_escape(detail.organization)}")
    if detail.total_posts:
        top.append(f"👥 {md_escape(detail.total_posts)}")
    if detail.apply_start_date:
        top.append(f"🟢 {bold('Start:')} {md_escape(detail.apply_start_date)}")
    if detail.apply_last_date or job.last_date:
        top.append(
            f"🔴 {bold('Last Date:')} "
            f"{md_escape(detail.apply_last_date or job.last_date or '')}"
        )
    middle: list[str] = []
    qualification = detail.qualification or detail.eligibility
    if qualification:
        middle.append(f"🎓 {bold('Qualification:')} {md_escape(qualification)}")
    bottom: list[str] = []
    if detail.fee:
        bottom.append(f"💳 {bold('Fee:')} {md_escape(detail.fee)}")
    if detail.salary:
        bottom.append(f"💰 {bold('Salary:')} {md_escape(detail.salary)}")
    bottom.append(_age_line(detail, profile, age_info))
    if detail.apply_url:
        bottom.append(f"👉 {link('CLICK HERE TO FILL THE FORM', detail.apply_url)}")
    return _assemble(top, middle, bottom, CAPTION_LIMIT)


def profile_card(profile: UserProfile) -> str:
    from bot.utils import calculate_age

    status = "🟢 *Active*" if profile.active else "🔴 *Paused*"
    sectors = "\n".join(f"  • {md_escape(label)}" for label in profile.sector_labels)
    age = calculate_age(profile.dob)
    dob_line = md_escape(profile.dob or "Not set")
    if age is not None:
        dob_line += f" \\({age} Yrs\\)"
    degrees = (
        "\n".join(f"  • {md_escape(label)}" for label in profile.degree_labels)
        or "  • Not set"
    )
    documents = (
        "\n".join(f"  • {md_escape(label)}" for label in profile.document_labels)
        or "  • Not set"
    )
    return (
        "👤 *Your Job Profile*\n"
        f"{DIVIDER}\n"
        f"🧑‍💼 {bold('Name:')} {md_escape(profile.full_name)}\n"
        f"🎂 {bold('D.O.B:')} {dob_line}\n"
        f"🏷️ {bold('Category:')} {md_escape(CATEGORY_MAP.get(profile.category, profile.category))}\n"
        f"🎓 {bold('Highest Qualification:')} {md_escape(QUAL_MAP[profile.qualification]['label'])}\n"
        f"📚 {bold('Degrees You Hold:')}\n{degrees}\n"
        f"📎 {bold('Documents You Have:')}\n{documents}\n"
        f"📂 {bold('Job Preferences:')}\n{sectors}\n"
        f"{DIVIDER}\n"
        f"🔔 {bold('Alerts:')} {status}"
    )


def admin_user_card(profile: UserProfile, saved_count: int = 0,
                    extra: str = "") -> str:
    """Owner-facing view of a subscriber's profile."""
    status = "🟢 Active" if profile.active else "🔴 Paused"
    degrees = ", ".join(profile.degree_labels) or "—"
    documents = ", ".join(profile.document_labels) or "—"
    sectors = ", ".join(profile.sector_labels) or "—"
    return (
        "👤 *Subscriber Profile*\n"
        f"{DIVIDER}\n"
        f"🧑‍💼 {bold('Name:')} {md_escape(profile.full_name)}\n"
        f"🔗 {bold('Username:')} @{md_escape(profile.username or '—')}\n"
        f"🆔 {bold('User ID:')} `{profile.user_id}`\n"
        f"🎂 {bold('D.O.B:')} {md_escape(profile.dob or 'Not set')}\n"
        f"🏷️ {bold('Category:')} {md_escape(CATEGORY_MAP.get(profile.category, profile.category))}\n"
        f"🎓 {bold('Highest Qual:')} {md_escape(QUAL_MAP[profile.qualification]['label'])}\n"
        f"📚 {bold('Degrees:')} {md_escape(degrees)}\n"
        f"📎 {bold('Documents:')} {md_escape(documents)}\n"
        f"📂 {bold('Sectors:')} {md_escape(sectors)}\n"
        f"🔖 {bold('Saved Jobs:')} {saved_count}\n"
        f"🔔 {bold('Alerts:')} {status}\n"
        + (f"{extra}\n" if extra else "")
        + f"{DIVIDER}"
    )


def _job_href(job_id: str, external_url: str, deep_base: str | None) -> str:
    """Deep link back into the bot when possible, else the external page."""
    if deep_base:
        from bot.utils import job_ref

        return deep_base + job_ref(job_id)
    return external_url


def list_page(jobs: list[JobSummary], page: int, total_pages: int,
              heading: str, deep_base: str | None = None) -> str:
    # ``jobs`` is already the slice for this page; browser keeps the page index.
    lines = [
        f"🔔 *{md_escape(heading)}*",
        f"📄 Page {page + 1} / {max(total_pages, 1)}",
        "👆 Tap a job title to open its full card inside this bot",
        DIVIDER,
    ]
    for index, job in enumerate(jobs, start=1):
        date_tag = f" {code(job.last_date)}" if job.last_date else ""
        href = _job_href(job.job_id, job.url, deep_base)
        lines.append(f"{index}\\. {link(job.title, href)}{date_tag}")
    if not jobs:
        lines.append("No vacancies on this page\\.")
    lines.append(DIVIDER)
    lines.append(f"🤖 {md_escape(config.OWNER_HANDLES)}")
    return "\n".join(lines)


def saved_list_card(saved: list, page: int, total_pages: int,
                    deep_base: str | None = None) -> str:
    lines = [
        "🔖 *Your Saved Jobs*",
        f"📄 Page {page + 1} / {max(total_pages, 1)}",
        "👆 Tap a title to reopen the full card",
        DIVIDER,
    ]
    for index, item in enumerate(saved, start=1):
        date_tag = f" {code(item.last_date)}" if item.last_date else ""
        reminder = " ⏰" if item.reminder_date else ""
        href = _job_href(item.job_id, item.url, deep_base)
        lines.append(f"{index}\\. {link(item.title, href)}{date_tag}{reminder}")
    if not saved:
        lines.append(
            "You haven't saved any jobs yet\\. Tap 🔖 on any job card\\."
        )
    lines.append(DIVIDER)
    lines.append(f"🤖 {md_escape(config.OWNER_HANDLES)}")
    return "\n".join(lines)


def welcome_caption() -> str:
    """The /start banner caption - what the bot does and why it is useful."""
    return (
        f"✨ *Welcome to {config.BRAND_NAME}*\n"
        f"{DIVIDER}\n"
        "I keep an eye on the government job portals around the clock and the "
        "moment a vacancy fits *your* profile, the full card lands in your "
        "chat\\.\n\n"
        "💡 *Why this is useful for you*\n"
        "• 🧾 Every new vacancy is checked for you \u2014 never scroll a job "
        "portal again\n"
        "• 🎯 Only the ones that fit your *age, category, degrees and "
        "documents*\n"
        "• 🎫 Admit card, exam date and last\\-date changes reach you first\n"
        "• ⏰ A reminder before every deadline \u2014 nothing slips\n"
        "• 🗂️ Admit cards, results, saved jobs and a daily digest in one place\n"
        "• 💬 A human \\(the owner\\) reads every bug report and suggestion\n\n"
        "Tap the button below to create your profile in 6 quick steps "
        "\\(name, D\\.O\\.B, category, degrees, documents, job choices\\)\\."
    )


def help_text() -> str:
    """A short, friendly guide: what to tap and in which order."""
    return (
        f"ℹ️ *{config.BRAND_NAME} — how to use me*\n"
        f"{DIVIDER}\n"
        "*1\\. Build your profile* \\(one time, about a minute\\)\n"
        "   • /start → name → D\\.O\\.B → category → degrees → documents → "
        "job types\n"
        "   • /edit — change any answer later\n"
        "*2\\. Get matched alerts*\n"
        "   I check the job portals around the clock \\(every 30 minutes by "
        "default\\) and send the full card the moment a vacancy fits your age, "
        "category, degrees and documents\\.\n"
        "*3\\. Browse whenever you want*\n"
        "   • /latest — jobs that match you \\(Next / Previous\\)\n"
        "   • /latest bihar — one state only\n"
        "   • /admit — latest admit cards\n"
        "   • /result — latest results\n"
        "   • type `@<bot_username> railway` in any chat to search inline\n"
        "*4\\. Save and organise*\n"
        "   • /saved — your bookmarked jobs and reminders\n"
        "   • tap 🔖 on any card to save it, ⏰ to set a reminder\n"
        "*5\\. Notifications*\n"
        "   • /pause — stop alerts · /resume — start again\n"
        "   • /profile — see your preferences\n"
        "   • /digest — today\'s summary on demand\n"
        "*6\\. Need a hand?*\n"
        "   • /why — why this bot is useful for *you*\n"
        "   • /contact — report a bug, send a suggestion or offer to help\n"
        "   • /about — bot info and owners\n"
        f"{DIVIDER}\n"
        f"🤖 {config.BRAND_NAME} · managed by {md_escape(config.OWNER_HANDLES)}"
    )


def about_text() -> str:
    return (
        f"📢 *{config.BRAND_NAME}* — Technical Sarkari Job Alert Bot\n"
        f"{DIVIDER}\n"
        f"{config.BRAND_NAME} watches the government job portals around the clock "
        "and pushes personalised Telegram alerts based on your category, age, "
        "degrees, documents and preferred job sectors\\.\n\n"
        "⚙️ Python · python\\-telegram\\-bot v22 · BeautifulSoup · SQLite / MongoDB\n"
        "🔄 Continuous checks · rich job cards · admit cards · results · reminders\n"
        "🧩 Optional web dashboard with the full job list\n\n"
        "👑 *Bot Owners*\n"
        "• @TechnicalSerena\n"
        "• @Xioqui\\_xin\n"
        f"{DIVIDER}\n"
        "_Not affiliated with the job portals\\. Always verify the details in the "
        "official notification before applying\\._"
    )

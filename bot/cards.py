"""Formatted Telegram message cards - all rendered in MarkdownV2.

Rule of thumb: every dynamic value passes through ``md_escape``; static
template literals use pre-escaped MarkdownV2 punctuation.
"""
from __future__ import annotations

from bot import config
from bot.constants import CATEGORY_AGE_RELAXATION, CATEGORY_MAP, QUAL_MAP
from bot.models import JobDetail, JobSummary, UserProfile
from bot.utils import bold, code, link, md_escape

DIVIDER = "━━━━━━━━━━━━━━━━━━"
NOT_DISCLOSED = "Check official notification"


def _value(value: str | None) -> str:
    return md_escape(value) if value and value.strip() else md_escape(NOT_DISCLOSED)


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


def job_card(
    job: JobSummary,
    detail: JobDetail | None,
    profile: UserProfile,
    age_info: dict | None = None,
) -> str:
    """Full MarkdownV2 card for a text message (up to 4096 chars)."""
    detail = detail or JobDetail()
    lines = [
        "🔔 *NEW SARKARI JOB MATCH*",
        DIVIDER,
        f"📝 {link(job.title, job.url)}",
    ]
    if detail.organization:
        lines.append(f"🏢 {bold('Organisation:')} {md_escape(detail.organization)}")
    lines.append(f"🎓 {bold('Qualification:')} {_value(detail.eligibility)}")
    lines.append(f"💰 {bold('Salary / Pay:')} {_value(detail.salary)}")
    lines.append(f"💳 {bold('Application Fee:')} {_value(detail.fee)}")
    lines.append(_age_line(detail, profile, age_info))
    if job.last_date:
        lines.append(f"⏳ {bold('Apply Before:')} {code(job.last_date)}")
    lines.append(DIVIDER)

    if detail.apply_url:
        lines.append(f"👉 {link('CLICK HERE TO FILL FORM', detail.apply_url)}")
    detail_links = [link("🌐 Full Details", job.url)]
    if detail.notification_pdf:
        detail_links.append(link("📄 Notification PDF", detail.notification_pdf))
    lines.append("  ·  ".join(detail_links))
    lines.append(DIVIDER)
    lines.append(f"🤖 Managed by {md_escape(config.OWNER_HANDLES)}")
    return "\n".join(lines)


def photo_caption(
    job: JobSummary,
    detail: JobDetail | None,
    profile: UserProfile,
    age_info: dict | None = None,
) -> str:
    """Compact MarkdownV2 caption - Telegram photo captions are capped at 1024."""
    detail = detail or JobDetail()
    lines = [
        "🔔 *NEW SARKARI JOB MATCH*",
        f"📝 {link(job.title, job.url)}",
    ]
    if detail.organization:
        lines.append(f"🏢 {md_escape(detail.organization)}")
    lines.append(f"🎓 {bold('Eligibility:')} {_value(detail.eligibility)}")
    if detail.fee:
        lines.append(f"💳 {bold('Fee:')} {md_escape(detail.fee)}")
    if detail.salary:
        lines.append(f"💰 {bold('Salary:')} {md_escape(detail.salary)}")
    lines.append(_age_line(detail, profile, age_info))
    if job.last_date:
        lines.append(f"⏳ {bold('Last Date:')} {code(job.last_date)}")
    if detail.apply_url:
        lines.append(f"👉 {link('CLICK HERE TO FILL FORM', detail.apply_url)}")
    text = "\n".join(lines)
    if len(text) > 1024:  # defensive: drop the longest optional line
        text = "\n".join(lines[:-2])
    return text[:1024]


def profile_card(profile: UserProfile) -> str:
    from bot.utils import calculate_age

    status = "🟢 *Active*" if profile.active else "🔴 *Paused*"
    sectors = "\n".join(f"  • {md_escape(label)}" for label in profile.sector_labels)
    age = calculate_age(profile.dob)
    dob_line = md_escape(profile.dob or "Not set")
    if age is not None:
        dob_line += f" \\({age} Yrs\\)"
    return (
        "👤 *Your Job Profile*\n"
        f"{DIVIDER}\n"
        f"🧑‍💼 {bold('Name:')} {md_escape(profile.full_name)}\n"
        f"🎂 {bold('D.O.B:')} {dob_line}\n"
        f"🏷️ {bold('Category:')} {md_escape(CATEGORY_MAP.get(profile.category, profile.category))}\n"
        f"🎓 {bold('Qualification:')} {md_escape(QUAL_MAP[profile.qualification]['label'])}\n"
        f"📂 {bold('Job Preferences:')}\n{sectors}\n"
        f"{DIVIDER}\n"
        f"🔔 {bold('Alerts:')} {status}"
    )


def _job_href(job_id: str, external_url: str, deep_base: str | None) -> str:
    """Deep link back into the bot when possible, else the external page."""
    if deep_base:
        from bot.utils import encode_job_id

        return deep_base + encode_job_id(job_id)
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
    return (
        "🚀 *Welcome to Sarkari Job Alert Bot*\n"
        f"{DIVIDER}\n"
        "I watch Sarkari Result around the clock and message you the moment a "
        "government job matches your profile\\.\n\n"
        "Tap the button below to create your profile in 5 quick steps "
        "\\(name, D\\.O\\.B, category, qualification, job choices\\)\\."
    )


def help_text() -> str:
    return (
        "ℹ️ *How to use this bot*\n"
        f"{DIVIDER}\n"
        "1\\. /start — create your profile: name, D\\.O\\.B, category, "
        "qualification and job sectors\n"
        "2\\. The bot scans Sarkari Result automatically and sends a rich card "
        "the moment a vacancy matches your qualification *and age*\n"
        "3\\. Commands:\n"
        "   • /profile — view saved preferences\n"
        "   • /edit — update your profile\n"
        "   • /latest — browse matching jobs with Next / Previous\n"
        "   • /saved — your bookmarked jobs & reminders\n"
        "   • /pause — stop notifications temporarily\n"
        "   • /resume — turn notifications back on\n"
        "   • /help — this message\n"
        "   • /about — bot info & owners\n"
        "4\\. In any chat, type `@<bot_username> railway` to search jobs inline\n"
        f"{DIVIDER}\n"
        f"🤖 Managed by {md_escape(config.OWNER_HANDLES)}"
    )


def about_text() -> str:
    return (
        "📢 *Sarkari Job Alert Bot*\n"
        f"{DIVIDER}\n"
        "Scrapes the latest government vacancy listings and pushes personalised "
        "Telegram alerts based on your category, age, qualification and preferred "
        "job sectors\\.\n\n"
        "⚙️ Python · python\\-telegram\\-bot v22 · BeautifulSoup · SQLite\n"
        "🔄 Automatic checks around the clock · image alerts · reminders\n\n"
        "👑 *Bot Owners*\n"
        "• @TechnicalSerena\n"
        "• @Xioqui\\_xin\n"
        f"{DIVIDER}\n"
        "_Not affiliated with Sarkari Result\\. Always verify details on the "
        "official notification before applying\\._"
    )

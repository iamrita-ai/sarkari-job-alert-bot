"""Formatted Telegram message cards."""
from __future__ import annotations

import html

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from bot import config
from bot.constants import CATEGORY_MAP, QUAL_MAP
from bot.models import JobDetail, JobSummary, UserProfile


def esc(value: str | None) -> str:
    return html.escape(str(value or "—"))


def _clip(value: str, limit: int) -> str:
    value = value.strip()
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def profile_card(profile: UserProfile) -> str:
    status = "🟢 Active" if profile.active else "🔴 Paused"
    sectors = "\n".join(f"  • {esc(label)}" for label in profile.sector_labels)
    return (
        "👤 <b>Your Job Profile</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🧑‍💼 <b>Name:</b> {esc(profile.full_name)}\n"
        f"🏷️ <b>Category:</b> {esc(CATEGORY_MAP.get(profile.category, profile.category))}\n"
        f"🎓 <b>Qualification:</b> {esc(QUAL_MAP[profile.qualification]['label'])}\n"
        f"📂 <b>Job Preferences:</b>\n{sectors}\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🔔 <b>Alerts:</b> {status}"
    )


def job_card(job: JobSummary, detail: JobDetail | None,
             profile: UserProfile) -> tuple[str, InlineKeyboardMarkup]:
    lines = [
        "🔔 <b>NEW SARKARI JOB MATCH</b>",
        "━━━━━━━━━━━━━━━━━━",
        f"📝 <b>{esc(_clip(job.title, 220))}</b>",
    ]
    if detail and detail.organization:
        lines.append(f"🏢 <b>Organisation:</b> {esc(_clip(detail.organization, 120))}")

    eligibility = detail.eligibility if detail and detail.eligibility else None
    lines.append(
        f"🎓 <b>Eligibility:</b> {esc(_clip(eligibility, 300)) if eligibility else 'Check full notification'}"
    )
    if detail and detail.age_limit:
        lines.append(f"📆 <b>Age Limit:</b> {esc(_clip(detail.age_limit, 160))}")
    if job.last_date:
        lines.append(f"⏳ <b>Apply Before:</b> <code>{esc(job.last_date)}</code>")
    lines.append(
        f"👤 <b>Your Category:</b> {esc(CATEGORY_MAP.get(profile.category, profile.category))}"
        " (relaxation as per official rules)"
    )
    lines.append("━━━━━━━━━━━━━━━━━━")
    lines.append(f"🤖 Managed by {esc(config.OWNER_HANDLES)}")

    buttons: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton("🌐 Full Details", url=job.url)]
    ]
    if detail and detail.apply_url:
        buttons[0].append(
            InlineKeyboardButton("📝 Apply Online", url=detail.apply_url)
        )
    if detail and detail.notification_pdf:
        buttons.append(
            [InlineKeyboardButton("📄 Notification PDF",
                                  url=detail.notification_pdf)]
        )
    return "\n".join(lines), InlineKeyboardMarkup(buttons)


def latest_jobs_card(jobs: list[JobSummary], profile: UserProfile | None) -> str:
    head = "🔔 <b>Latest Matching Jobs</b>\n<i>Tap a title to open the official page</i>\n━━━━━━━━━━━━━━━━━━\n"
    body_lines = []
    for index, job in enumerate(jobs[:10], start=1):
        date_tag = f" <code>({esc(job.last_date)})</code>" if job.last_date else ""
        body_lines.append(
            f"{index}. <a href=\"{esc(job.url)}\">{esc(_clip(job.title, 160))}</a>{date_tag}"
        )
    if not body_lines:
        return head + "No matching vacancies right now. New alerts arrive automatically. 🕒"
    footer = "\n━━━━━━━━━━━━━━━━━━\n🤖 Managed by " + esc(config.OWNER_HANDLES)
    return head + "\n".join(body_lines) + footer


HELP_TEXT = (
    "ℹ️ <b>How to use this bot</b>\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "1. /start — create your profile (name, category, qualification, job choices)\n"
    "2. The bot scans <b>Sarkari Result</b> automatically and sends you a card "
    "the moment a vacancy matching your profile appears.\n"
    "3. Commands:\n"
    "   /profile — view your saved preferences\n"
    "   /edit — update name / category / qualification / sectors\n"
    "   /latest — fetch matching jobs right now\n"
    "   /pause — stop notifications temporarily\n"
    "   /resume — turn notifications back on\n"
    "   /help — this message\n"
    "   /about — bot info & owners\n"
    "━━━━━━━━━━━━━━━━━━\n"
    f"🤖 Managed by {esc(config.OWNER_HANDLES)}"
)

ABOUT_TEXT = (
    "📢 <b>Sarkari Job Alert Bot</b>\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "This bot scrapes the latest government vacancy listings from "
    "SarkariResult.com and pushes personalised Telegram alerts based on your "
    "category, qualification and preferred job sectors.\n\n"
    "⚙️ Built with Python, python-telegram-bot, BeautifulSoup & SQLite.\n"
    "🔄 Checks for new jobs automatically around the clock.\n\n"
    "👑 <b>Bot Owners</b>\n"
    "• @TechnicalSerena\n"
    "• @Xioqui_xin\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "<i>Not affiliated with SarkariResult.com. Always verify details on the "
    "official notification before applying.</i>"
)

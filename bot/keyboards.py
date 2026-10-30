"""Inline keyboards.

Coloured buttons use Bot API ``style`` (PTB 22.7+, Telegram clients after
Feb 2026): PRIMARY = blue, SUCCESS = green, DANGER = red. Older clients
gracefully render the same buttons without colour.

Colour convention used everywhere in the bot:
  * BLUE   - navigation and neutral information
  * GREEN  - positive actions (apply, save, confirm, done, selected items)
  * RED    - destructive or stopping actions (cancel, pause, remove)
"""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import KeyboardButtonStyle

from bot.constants import (
    CATEGORIES,
    CATEGORY_EMOJI,
    DEGREES,
    DOCUMENTS,
    PAGE_SIZE,
    QUALIFICATIONS,
    SECTOR_EMOJI,
    SECTORS,
)
from bot.utils import job_ref

BLUE = KeyboardButtonStyle.PRIMARY
GREEN = KeyboardButtonStyle.SUCCESS
RED = KeyboardButtonStyle.DANGER


def _rows(items: list[InlineKeyboardButton], per_row: int = 2
          ) -> list[list[InlineKeyboardButton]]:
    rows: list[list[InlineKeyboardButton]] = []
    for index in range(0, len(items), per_row):
        rows.append(items[index:index + per_row])
    return rows


# ----------------------------------------------------------- onboarding
def category_keyboard() -> InlineKeyboardMarkup:
    """Reservation categories - plain labels, no emoji (cleaner on mobile)."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            label, callback_data=f"cat:{key}", style=BLUE,
        )]
        for key, label in CATEGORIES
    ])


def resume_setup_keyboard() -> InlineKeyboardMarkup:
    """Shown when a setup button arrives without a live conversation."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Get Started", callback_data="start:begin", style=GREEN)],
        [InlineKeyboardButton("✏️ Edit Profile", callback_data="menu:edit", style=BLUE)],
    ])


def qualification_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"🎓 {q['label']}", callback_data=f"qual:{q['key']}", style=BLUE
        )]
        for q in QUALIFICATIONS
    ])


def degrees_keyboard(selected: set[str]) -> InlineKeyboardMarkup:
    """Multi-select: a person can hold ITI *and* B.Ed, B.Sc *and* M.Com."""
    buttons: list[InlineKeyboardButton] = []
    for degree in DEGREES:
        key = degree["key"]
        is_on = key in selected
        buttons.append(InlineKeyboardButton(
            f"{'✅' if is_on else '⬜'} {degree['label']}",
            callback_data=f"deg:{key}",
            style=GREEN if is_on else BLUE,
        ))
    rows = _rows(buttons, 2)
    rows.append([InlineKeyboardButton(
        "✅ Done — Save Degrees", callback_data="deg:done", style=GREEN
    )])
    return InlineKeyboardMarkup(rows)


def documents_keyboard(selected: set[str]) -> InlineKeyboardMarkup:
    """Multi-select: mark the documents you already own."""
    buttons: list[InlineKeyboardButton] = []
    for document in DOCUMENTS:
        key = document["key"]
        is_on = key in selected
        buttons.append(InlineKeyboardButton(
            f"{'✅' if is_on else '⬜'} {document['label']}",
            callback_data=f"doc:{key}",
            style=GREEN if is_on else BLUE,
        ))
    rows = _rows(buttons, 2)
    rows.append([InlineKeyboardButton(
        "✅ Done — Save Documents", callback_data="doc:done", style=GREEN
    )])
    return InlineKeyboardMarkup(rows)


def sectors_keyboard(selected: set[str]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for sector in SECTORS:
        emoji = SECTOR_EMOJI.get(sector["key"], "🔘")
        state = "✅" if sector["key"] in selected else "⬜"
        button = InlineKeyboardButton(
            f"{state} {emoji} {sector['label']}",
            callback_data=f"sec:{sector['key']}",
            style=GREEN if sector["key"] in selected else BLUE,
        )
        row.append(button)
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(
        "✅ Done — Save Preferences", callback_data="sec:done", style=GREEN
    )])
    return InlineKeyboardMarkup(rows)


def get_started_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🚀 Get Started", callback_data="start:begin", style=GREEN)
    ]])


# ----------------------------------------------------------- profile edit
def profile_edit_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "🧑‍💼 Name", callback_data="pe:name", style=BLUE
        ), InlineKeyboardButton(
            "🎂 Date of Birth", callback_data="pe:dob", style=BLUE
        )],
        [InlineKeyboardButton(
            "🏷️ Reservation Category", callback_data="pe:category", style=BLUE
        ), InlineKeyboardButton(
            "📚 Degrees", callback_data="pe:degrees", style=BLUE
        )],
        [InlineKeyboardButton(
            "📎 Documents", callback_data="pe:documents", style=BLUE
        ), InlineKeyboardButton(
            "📂 Job Sectors", callback_data="pe:sectors", style=BLUE
        )],
        [InlineKeyboardButton(
            "✖ Close", callback_data="pe:close", style=RED
        )],
    ])


# ----------------------------------------------------------- main menu
def main_menu_keyboard(active: bool) -> InlineKeyboardMarkup:
    toggle = (
        ("⏸ Pause Alerts", "menu:pause", RED) if active
        else ("▶️ Resume Alerts", "menu:resume", GREEN)
    )
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "🔔 Latest Matching Jobs", callback_data="menu:latest", style=BLUE
        )],
        [InlineKeyboardButton("✏️ Edit Profile", callback_data="menu:edit", style=BLUE),
         InlineKeyboardButton(toggle[0], callback_data=toggle[1], style=toggle[2])],
        [InlineKeyboardButton(
            "🔍 Search in Any Chat", switch_inline_query="", style=BLUE
        )],
        [InlineKeyboardButton("🎫 Admit Cards", callback_data="menu:admit",
                              style=BLUE),
         InlineKeyboardButton("🏁 Results", callback_data="menu:result",
                              style=BLUE)],
        [InlineKeyboardButton("🔖 Saved Jobs", callback_data="menu:saved", style=BLUE),
         InlineKeyboardButton("ℹ️ Help", callback_data="menu:help", style=BLUE)],
        [InlineKeyboardButton("📢 About", callback_data="menu:about", style=BLUE),
         InlineKeyboardButton(
             "💬 Contact owner", callback_data="menu:contact", style=GREEN
         )],
        [InlineKeyboardButton("💡 Why SERENA?", callback_data="menu:why",
                              style=GREEN)],
    ])


# ----------------------------------------------------------- daily digest
def digest_keyboard(matched, closing=None) -> InlineKeyboardMarkup:
    """Buttons under the daily digest - tapping one opens the full job card."""
    rows: list[list[InlineKeyboardButton]] = []
    for job in list(matched)[:8]:
        encoded = job_ref(job.job_id)
        label = job.title if len(job.title) <= 42 else job.title[:40] + "…"
        rows.append([InlineKeyboardButton(
            f"📋 {label}", callback_data=f"dig:{encoded}", style=BLUE,
        )])
    for item in list(closing or [])[:4]:
        encoded = job_ref(item.job_id)
        label = item.title if len(item.title) <= 42 else item.title[:40] + "…"
        rows.append([InlineKeyboardButton(
            f"⏰ {label}", callback_data=f"dig:{encoded}", style=GREEN,
        )])
    rows.append([InlineKeyboardButton(
        "📂 Browse all jobs", callback_data="menu:latest", style=GREEN
    )])
    return InlineKeyboardMarkup(rows)

# ----------------------------------------------------------- job cards
def job_action_keyboard(job, saved: bool = False) -> InlineKeyboardMarkup:
    encoded = job_ref(job.job_id)
    row_one: list[InlineKeyboardButton] = [
        InlineKeyboardButton("🌐 Full Details", url=job.url, style=BLUE)
    ]
    # Apply URL lives on the detail record; the scheduler/handler injects it
    # by rebuilding this keyboard when a detail is available.
    rows = [row_one]
    save_label = "🔖 Saved ✓" if saved else "🔖 Save Job"
    rows.append([
        InlineKeyboardButton(save_label, callback_data=f"save:{encoded}", style=GREEN),
        InlineKeyboardButton("⏰ Remind Me", callback_data=f"rem:{encoded}", style=BLUE),
    ])
    return InlineKeyboardMarkup(rows)


def job_detail_keyboard(job, detail, saved: bool = False) -> InlineKeyboardMarkup:
    encoded = job_ref(job.job_id)
    row_one: list[InlineKeyboardButton] = []
    if detail and detail.apply_url:
        row_one.append(InlineKeyboardButton(
            "👉 Apply Online", url=detail.apply_url, style=GREEN
        ))
    row_one.append(InlineKeyboardButton("🌐 Full Details", url=job.url, style=BLUE))
    rows = [row_one]
    if detail and detail.notification_pdf:
        rows.append([InlineKeyboardButton(
            "📄 Notification PDF", url=detail.notification_pdf, style=BLUE
        )])
    rows.append([InlineKeyboardButton(
        f"📃 Full Notification Text", callback_data=f"full:{encoded}", style=BLUE
    )])
    save_label = "🔖 Saved ✓" if saved else "🔖 Save Job"
    rows.append([
        InlineKeyboardButton(save_label, callback_data=f"save:{encoded}", style=GREEN),
        InlineKeyboardButton("⏰ Remind Me", callback_data=f"rem:{encoded}", style=BLUE),
    ])
    return InlineKeyboardMarkup(rows)


def reminder_keyboard(job_id: str, has_last_date: bool) -> InlineKeyboardMarkup:
    encoded = job_ref(job_id)
    rows = []
    if has_last_date:
        rows.append([
            InlineKeyboardButton("1 Day Before", callback_data=f"remset:{encoded}:1d",
                                 style=BLUE),
            InlineKeyboardButton("3 Days Before", callback_data=f"remset:{encoded}:3d",
                                 style=BLUE),
        ])
        rows.append([InlineKeyboardButton(
            "On Last Date", callback_data=f"remset:{encoded}:last", style=GREEN
        )])
    rows.append([InlineKeyboardButton(
        "✍️ Custom Date", callback_data=f"remcustom:{encoded}", style=BLUE
    )])
    rows.append([InlineKeyboardButton(
        "✖ Cancel", callback_data=f"remcancel:{encoded}", style=RED
    )])
    return InlineKeyboardMarkup(rows)


# ----------------------------------------------------------- browsers
# Browsers expose ONLY Previous / Next (with a page indicator and Home).
# Job titles in the message body are tappable deep links that reopen the full
# job card inside the bot.
def browse_keyboard(page: int, total_pages: int, page_jobs) -> InlineKeyboardMarkup:
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀ Previous", callback_data="br:p", style=BLUE))
    nav.append(InlineKeyboardButton(f"📄 {page + 1}/{total_pages}",
                                    callback_data="br:noop", style=BLUE))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("Next ▶", callback_data="br:n", style=BLUE))
    return InlineKeyboardMarkup([
        nav,
        [InlineKeyboardButton("🏠 Main Menu", callback_data="br:home", style=GREEN)],
    ])


def back_to_list_keyboard(kind: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("◀ Back to List", callback_data=f"br:back:{kind}", style=BLUE)
    ]])


def saved_browse_keyboard(page: int, total_pages: int, page_items) -> InlineKeyboardMarkup:
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀ Previous", callback_data="sv:p", style=BLUE))
    nav.append(InlineKeyboardButton(f"📄 {page + 1}/{total_pages}",
                                    callback_data="sv:noop", style=BLUE))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("Next ▶", callback_data="sv:n", style=BLUE))
    return InlineKeyboardMarkup([
        nav,
        [InlineKeyboardButton("🏠 Main Menu", callback_data="br:home", style=GREEN)],
    ])


# ----------------------------------------------------------- owner tools
def admin_users_keyboard(users: list, page: int, total_pages: int) -> InlineKeyboardMarkup:
    """Owner-only list of subscribers - each row opens that profile."""
    rows: list[list[InlineKeyboardButton]] = []
    for profile in users:
        label = f"👤 {profile.full_name[:24]}"
        if profile.username:
            label += f" (@{profile.username[:16]})"
        rows.append([InlineKeyboardButton(
            label, callback_data=f"adm:prof:{profile.user_id}", style=BLUE
        )])
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀ Previous", callback_data="adm:page:p",
                                        style=BLUE))
    nav.append(InlineKeyboardButton(f"📄 {page + 1}/{total_pages}",
                                    callback_data="adm:page:noop", style=BLUE))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("Next ▶", callback_data="adm:page:n",
                                        style=BLUE))
    if nav:
        rows.append(nav)
    return InlineKeyboardMarkup(rows)


def admin_profile_keyboard(profile, saved_count: int = 0) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if saved_count:
        rows.append([InlineKeyboardButton(
            f"🔖 Saved Jobs ({saved_count})", callback_data=f"adm:saved:{profile.user_id}",
            style=BLUE
        )])
    rows.append([InlineKeyboardButton(
        "💬 Open Chat", url=f"tg://user?id={profile.user_id}", style=GREEN
    )])
    rows.append([InlineKeyboardButton(
        "◀ Back to Users", callback_data="adm:users", style=RED
    )])
    return InlineKeyboardMarkup(rows)

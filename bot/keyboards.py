"""Inline keyboards.

Coloured buttons use Bot API ``style`` (PTB 22.7+, Telegram clients after
Feb 2026): PRIMARY = blue, SUCCESS = green, DANGER = red. Older clients
gracefully render the same buttons without colour.
"""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import KeyboardButtonStyle

from bot.constants import (
    CATEGORIES,
    CATEGORY_EMOJI,
    PAGE_SIZE,
    QUALIFICATIONS,
    SECTOR_EMOJI,
    SECTORS,
)
from bot.utils import encode_job_id

BLUE = KeyboardButtonStyle.PRIMARY
GREEN = KeyboardButtonStyle.SUCCESS
RED = KeyboardButtonStyle.DANGER


# ----------------------------------------------------------- onboarding
def category_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"{CATEGORY_EMOJI.get(key, '🔘')} {label}",
            callback_data=f"cat:{key}", style=BLUE,
        )]
        for key, label in CATEGORIES
    ])


def qualification_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"🎓 {q['label']}", callback_data=f"qual:{q['key']}", style=BLUE
        )]
        for q in QUALIFICATIONS
    ])


def sectors_keyboard(selected: set[str]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for sector in SECTORS:
        emoji = SECTOR_EMOJI.get(sector["key"], "🔘")
        state = "✅" if sector["key"] in selected else "⬜"
        button = InlineKeyboardButton(
            f"{state} {emoji} {sector['label']}",
            callback_data=f"sec:{sector['key']}",
        )
        if sector["key"] in selected:
            button = InlineKeyboardButton(
                f"{state} {emoji} {sector['label']}",
                callback_data=f"sec:{sector['key']}",
                style=GREEN,
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
        [InlineKeyboardButton("✏️ Edit Profile", callback_data="menu:edit"),
         InlineKeyboardButton(toggle[0], callback_data=toggle[1], style=toggle[2])],
        [InlineKeyboardButton("🔍 Search in Any Chat", switch_inline_query="")],
        [InlineKeyboardButton("🔖 Saved Jobs", callback_data="menu:saved"),
         InlineKeyboardButton("ℹ️ Help", callback_data="menu:help")],
        [InlineKeyboardButton("📢 About", callback_data="menu:about")],
    ])


# ----------------------------------------------------------- job cards
def job_action_keyboard(job, saved: bool = False) -> InlineKeyboardMarkup:
    encoded = encode_job_id(job.job_id)
    row_one: list[InlineKeyboardButton] = [
        InlineKeyboardButton("🌐 Full Details", url=job.url, style=BLUE)
    ]
    # Apply URL lives on the detail record; the scheduler/handler injects it
    # by rebuilding this keyboard when a detail is available.
    rows = [row_one]
    save_label = "🔖 Saved ✓" if saved else "🔖 Save Job"
    rows.append([
        InlineKeyboardButton(save_label, callback_data=f"save:{encoded}", style=BLUE),
        InlineKeyboardButton("⏰ Remind Me", callback_data=f"rem:{encoded}"),
    ])
    return InlineKeyboardMarkup(rows)


def job_detail_keyboard(job, detail, saved: bool = False) -> InlineKeyboardMarkup:
    encoded = encode_job_id(job.job_id)
    row_one: list[InlineKeyboardButton] = []
    if detail and detail.apply_url:
        row_one.append(InlineKeyboardButton(
            "👉 Apply Online", url=detail.apply_url, style=GREEN
        ))
    row_one.append(InlineKeyboardButton("🌐 Full Details", url=job.url, style=BLUE))
    rows = [row_one]
    if detail and detail.notification_pdf:
        rows.append([InlineKeyboardButton(
            "📄 Notification PDF", url=detail.notification_pdf
        )])
    save_label = "🔖 Saved ✓" if saved else "🔖 Save Job"
    rows.append([
        InlineKeyboardButton(save_label, callback_data=f"save:{encoded}", style=BLUE),
        InlineKeyboardButton("⏰ Remind Me", callback_data=f"rem:{encoded}"),
    ])
    return InlineKeyboardMarkup(rows)


def reminder_keyboard(job_id: str, has_last_date: bool) -> InlineKeyboardMarkup:
    encoded = encode_job_id(job_id)
    rows = []
    if has_last_date:
        rows.append([
            InlineKeyboardButton("1 Day Before", callback_data=f"remset:{encoded}:1d"),
            InlineKeyboardButton("3 Days Before", callback_data=f"remset:{encoded}:3d"),
        ])
        rows.append([InlineKeyboardButton(
            "On Last Date", callback_data=f"remset:{encoded}:last", style=RED
        )])
    rows.append([InlineKeyboardButton(
        "✍️ Custom Date", callback_data=f"remcustom:{encoded}", style=BLUE
    )])
    rows.append([InlineKeyboardButton("✖ Cancel", callback_data=f"remcancel:{encoded}")])
    return InlineKeyboardMarkup(rows)


# ----------------------------------------------------------- browsers
def browse_keyboard(page: int, total_pages: int, page_jobs) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    open_row: list[InlineKeyboardButton] = []
    for index, _job in enumerate(page_jobs):
        open_row.append(InlineKeyboardButton(
            str(index + 1), callback_data=f"br:o:{page}:{index}"
        ))
    if open_row:
        rows.append(open_row)
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀ Previous", callback_data="br:p", style=BLUE))
    nav.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="br:noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("Next ▶", callback_data="br:n", style=BLUE))
    rows.append(nav)
    rows.append([InlineKeyboardButton("🏠 Main Menu", callback_data="br:home")])
    return InlineKeyboardMarkup(rows)


def back_to_list_keyboard(kind: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("◀ Back to List", callback_data=f"br:back:{kind}", style=BLUE)
    ]])


def saved_browse_keyboard(page: int, total_pages: int, page_items) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    open_row = [
        InlineKeyboardButton(str(i + 1), callback_data=f"sv:o:{page}:{i}")
        for i, _ in enumerate(page_items)
    ]
    if open_row:
        rows.append(open_row)
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀ Previous", callback_data="sv:p", style=BLUE))
    nav.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="br:noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("Next ▶", callback_data="sv:n", style=BLUE))
    rows.append(nav)
    rows.append([InlineKeyboardButton("🏠 Main Menu", callback_data="br:home")])
    return InlineKeyboardMarkup(rows)

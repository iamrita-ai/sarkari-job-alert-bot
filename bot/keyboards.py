"""Inline keyboards used by the bot's conversations and menus."""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from bot.constants import CATEGORIES, QUALIFICATIONS, SECTORS


def category_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(label, callback_data=f"cat:{key}")]
        for key, label in CATEGORIES
    ]
    return InlineKeyboardMarkup(rows)


def qualification_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(q["label"], callback_data=f"qual:{q['key']}")]
        for q in QUALIFICATIONS
    ]
    return InlineKeyboardMarkup(rows)


def sectors_keyboard(selected: set[str]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for sector in SECTORS:
        tick = "✅ " if sector["key"] in selected else ""
        row.append(
            InlineKeyboardButton(
                f"{tick}{sector['label']}", callback_data=f"sec:{sector['key']}"
            )
        )
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("✅ Done — Save Preferences", callback_data="sec:done")])
    return InlineKeyboardMarkup(rows)


def main_menu_keyboard(active: bool) -> InlineKeyboardMarkup:
    toggle = ("⏸ Pause Alerts", "menu:pause") if active else ("▶️ Resume Alerts", "menu:resume")
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔔 Latest Matching Jobs", callback_data="menu:latest")],
        [InlineKeyboardButton("✏️ Edit Profile", callback_data="menu:edit"),
         InlineKeyboardButton(toggle[0], callback_data=toggle[1])],
        [InlineKeyboardButton("ℹ️ Help", callback_data="menu:help"),
         InlineKeyboardButton("📢 About", callback_data="menu:about")],
    ])

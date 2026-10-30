"""SERENA brand kit - one place for the name, the icons and the dividers.

Keeping the look in a single module makes it easy to re-skin the bot (a new
brand, a new emoji set) without touching every card.
"""
from __future__ import annotations

from bot import config

# --- the name ---------------------------------------------------------------
BRAND: str = config.BRAND_NAME
FULL_NAME: str = f"{config.BRAND_NAME} · Technical Sarkari Job Alert Bot"

# --- section icons ----------------------------------------------------------
ICON_ALERT = "🚨"      # new vacancy
ICON_MATCH = "🎯"      # matched to you
ICON_CARD = "🗂️"      # job card
ICON_TICKET = "🎫"     # admit card
ICON_FLAG = "🏁"       # result
ICON_CLOCK = "⏰"      # deadline / reminder
ICON_BELL = "🔔"       # notifications
ICON_MAG = "🔍"        # search
ICON_BOOK = "📚"       # saved jobs
ICON_CHAT = "💬"       # contact / support
ICON_SPARK = "✨"      # premium accent
ICON_STAR = "⭐️"       # rating / favourite
ICON_SHIELD = "🛡️"     # privacy / safety
ICON_ROCKET = "🚀"     # start / go
ICON_PIN = "📍"        # state
ICON_DOC = "📄"        # document
ICON_CHECK = "✅"
ICON_CROSS = "❌"
ICON_WARN = "⚠️"
ICON_INFO = "ℹ️"
ICON_FIRE = "🔥"

# --- dividers ---------------------------------------------------------------
# A light divider for the compact cards, a heavy one for the big messages.
DIVIDER = "━━━━━━━━━━━━━━━━━━"
DIVIDER_HEAVY = "━━━━━━━━━━━━━━━━━━━━━━━━━━"
DIVIDER_DOTS = "· · · · · · · · · · · · ·"

# --- small helpers ----------------------------------------------------------
def bullets(lines: list[str]) -> str:
    """Render a bullet list (the caller escapes the text)."""
    return "\n".join(f"• {line}" for line in lines)


def stat_line(icon: str, label: str, value: str) -> str:
    """One 'icon label: value' line."""
    return f"{icon} {label}: {value}"


def highlight(text: str) -> str:
    """Make a word stand out (MarkdownV2 bold)."""
    return f"*{text}*"

"""Small shared helpers: MarkdownV2 escaping, dates, age, deep-link encoding."""
from __future__ import annotations

import base64
import re
from datetime import date, datetime

# Every character that must be escaped in Telegram MarkdownV2 text.
_MD_SPECIAL = re.compile(r"([_*\[\]()~`>#+\-=|{}.!\\])")
_DOB_RE = re.compile(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$")
# dd/mm/yyyy as found on vacancy pages
_SLASH_DATE_RE = re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\b")


# ------------------------------------------------------------- MarkdownV2
def md_escape(text: str | None) -> str:
    """Escape dynamic text so it can never break a MarkdownV2 message."""
    if text is None:
        return ""
    return _MD_SPECIAL.sub(r"\\\1", str(text))


def bold(text: str) -> str:
    return f"*{md_escape(text)}*"


def code(text: str) -> str:
    return f"`{md_escape(text)}`"


def link(label: str, url: str | None) -> str:
    """Inline hyperlink. The URL itself is emitted raw (destinations don't
    accept Markdown escaping); the visible label is escaped."""
    if not url:
        return md_escape(label)
    return f"[{md_escape(label)}]({url})"


# ------------------------------------------------------------- dates / age
def parse_dob(text: str) -> date | None:
    """Accept DD/MM/YYYY or DD-MM-YYYY; return None when invalid/impossible."""
    match = _DOB_RE.match(text.strip())
    if not match:
        return None
    day, month, year = (int(part) for part in match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


def dob_to_storage(dob: date) -> str:
    return dob.strftime("%d/%m/%Y")


def calculate_age(dob_text: str | None, on_date: date | None = None) -> int | None:
    if not dob_text:
        return None
    dob = parse_dob(dob_text)
    if dob is None:
        return None
    today = on_date or date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def parse_slash_date(text: str | None) -> date | None:
    """Parse a DD/MM/YYYY string (e.g. a vacancy last date)."""
    if not text:
        return None
    match = _SLASH_DATE_RE.search(text)
    if not match:
        return None
    day, month, year = (int(part) for part in match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


# ------------------------------------------------------------- deep links
def encode_job_id(job_id: str) -> str:
    """URL-safe base64 without padding - valid inside /start payloads."""
    return base64.urlsafe_b64encode(job_id.encode()).rstrip(b"=").decode()


def decode_job_id(payload: str) -> str | None:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", payload):
        return None
    padded = payload + "=" * (-len(payload) % 4)
    try:
        return base64.urlsafe_b64decode(padded).decode()
    except (ValueError, UnicodeDecodeError):
        return None

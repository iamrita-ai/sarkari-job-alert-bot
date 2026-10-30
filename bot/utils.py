"""Small shared helpers: MarkdownV2 escaping, dates, age, deep-link encoding."""
from __future__ import annotations

import base64
import hashlib
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
    """Inline code span.

    A code span cannot contain an escaped backtick, so backticks inside the
    value are replaced by apostrophes before escaping.
    """
    cleaned = str(text).replace("`", "'")
    return f"`{md_escape(cleaned)}`"


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
def job_ref(job_id: str) -> str:
    """A short reference for a job id.

    Telegram allows only 64 bytes of callback data and 64 characters in a
    deep-link payload, while a job id (the notice slug) can be 80+
    characters. The reference is a stable short hash - the database maps it
    back to the job id.
    """
    return hashlib.sha1(job_id.encode("utf-8")).hexdigest()[:12]


def remember_jobs(application, jobs) -> None:  # noqa: ANN001
    """Keep a short-lived map of reference -> job.

    A notice that is newer than the last database sync is not in the
    ``jobs`` table yet. Its buttons (save, reminder, ...) must still work,
    so the freshly fetched jobs are remembered in memory.
    """
    store = application.bot_data.setdefault("job_refs", {})
    for job in jobs:
        store[job_ref(job.job_id)] = job
    if len(store) > 1000:  # keep the map small
        for key in list(store)[:200]:
            store.pop(key, None)


async def resolve_job(application, ref: str):  # noqa: ANN001
    """Resolve a job reference: the live map first, then the database."""
    job = application.bot_data.get("job_refs", {}).get(ref)
    if job is not None:
        return job
    db = application.bot_data.get("db")
    if db is None:
        return None
    return await db.get_job_by_ref(ref)


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

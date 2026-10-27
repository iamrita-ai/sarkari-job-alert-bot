"""Profile -> vacancy matching logic."""
from __future__ import annotations

import re

from bot.constants import QUALIFICATIONS, SECTOR_MAP
from bot.models import JobDetail, JobSummary, UserProfile


def _normalize(text: str) -> str:
    # URL slugs use hyphens - turn them into spaces for keyword matching
    return re.sub(r"[\s\-_]+", " ", text.lower())


def title_matches(profile: UserProfile, job: JobSummary) -> bool:
    """True if any of the user's sectors appears in the title or slug."""
    haystack = _normalize(f"{job.title} {job.url}")
    for sector_key in profile.sectors:
        sector = SECTOR_MAP.get(sector_key)
        if not sector:
            continue
        if any(keyword in haystack for keyword in sector["keywords"]):
            return True
    return False


def detect_required_ranks(text: str) -> list[int]:
    """Education ranks mentioned in an eligibility text (may be several)."""
    low = text.lower()
    ranks: list[int] = []
    for qualification in QUALIFICATIONS:
        for alias in qualification["aliases"]:
            pattern = r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])"
            if re.search(pattern, low):
                ranks.append(qualification["rank"])
                break
    return ranks


def qualification_matches(profile: UserProfile, detail: JobDetail) -> bool:
    """Compare the user's level against the lowest requirement in the notice.

    When the scraper cannot detect any qualification we do NOT block the
    alert - missing a job is worse than an extra notification.
    """
    source = detail.eligibility or detail.raw_text[:3000]
    if not source:
        return True
    required = detect_required_ranks(source)
    if not required:
        return True
    return profile.qual_rank >= min(required)

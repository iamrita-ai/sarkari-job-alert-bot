"""Profile -> vacancy matching logic."""
from __future__ import annotations

import re

from bot.constants import (
    CATEGORY_AGE_RELAXATION,
    DEGREES,
    DOCUMENTS,
    QUALIFICATIONS,
    SECTOR_MAP,
)
from bot.models import JobDetail, JobSummary, UserProfile
from bot.utils import calculate_age


def _normalize(text: str) -> str:
    # URL slugs use hyphens - turn them into spaces for keyword matching
    return re.sub(r"[\s\-_]+", " ", text.lower())


def _alias_hit(low: str, alias: str) -> bool:
    """Whole-word-ish match so 'ba' does not fire inside 'bank'."""
    pattern = r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])"
    return bool(re.search(pattern, low))


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
            if _alias_hit(low, alias):
                ranks.append(qualification["rank"])
                break
    return ranks


def detect_degree_keys(text: str) -> list[str]:
    """Specific degrees mentioned in a notice (B.Ed, ITI, B.Sc Nursing...)."""
    low = text.lower()
    found: list[str] = []
    for degree in DEGREES:
        for alias in degree["aliases"]:
            if _alias_hit(low, alias):
                found.append(degree["key"])
                break
    return found


def detect_documents(text: str) -> list[str]:
    """Documents a notice asks the candidate to carry."""
    low = text.lower()
    found: list[str] = []
    for document in DOCUMENTS:
        for alias in document["aliases"]:
            if _alias_hit(low, alias):
                found.append(document["key"])
                break
    return found


def qualification_matches(profile: UserProfile, detail: JobDetail) -> bool:
    """Compare the user's degrees against the notice.

    A user who picked "ITI + B.Ed" matches a notice that asks for either of
    them, even when the generic rank scale would say "too low". When the
    scraper cannot detect any qualification we do NOT block the alert -
    missing a job is worse than an extra notification.
    """
    source = detail.qualification or detail.eligibility or detail.raw_text[:3000]
    if not source:
        return True

    required_degrees = set(detect_degree_keys(source))
    if required_degrees and set(profile.degrees) & required_degrees:
        return True

    required = detect_required_ranks(source)
    if not required:
        return True
    return profile.qual_rank >= min(required)


def document_gaps(profile: UserProfile, detail: JobDetail) -> list[str]:
    """Documents the notice needs that the user has NOT marked as owned."""
    required = detail.documents_required or detect_documents(
        detail.qualification or detail.eligibility or detail.raw_text[:3000]
    )
    return [key for key in required if key not in profile.documents]



def age_matches(profile: UserProfile, detail: JobDetail) -> tuple[bool, dict]:
    """Check the user's age against min/max with category relaxation.

    Returns ``(eligible, info)`` where info carries the numbers used so the
    card can explain the decision. Missing data never blocks an alert.
    """
    info = {
        "user_age": calculate_age(profile.dob),
        "min_age": detail.min_age,
        "max_age": detail.max_age,
        "relaxation": CATEGORY_AGE_RELAXATION.get(profile.category, 0),
        "effective_max": None,
        "reason": "",
    }
    if info["user_age"] is None or (detail.min_age is None and detail.max_age is None):
        info["reason"] = "age data unavailable"
        return True, info

    effective_max = None
    if detail.max_age is not None:
        effective_max = detail.max_age + info["relaxation"]
        info["effective_max"] = effective_max

    if detail.min_age is not None and info["user_age"] < detail.min_age:
        info["reason"] = "below minimum age"
        return False, info
    if effective_max is not None and info["user_age"] > effective_max:
        info["reason"] = "above maximum age (incl. relaxation)"
        return False, info
    info["reason"] = "within age window"
    return True, info

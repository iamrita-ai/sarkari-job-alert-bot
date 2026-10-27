"""Dataclasses shared across scraper, database and handlers."""
from __future__ import annotations

import dataclasses
import json


@dataclasses.dataclass(slots=True)
class JobSummary:
    """One row from the Sarkari Result latest-jobs listing."""

    job_id: str          # unique slug derived from the URL path
    title: str
    url: str
    last_date: str | None = None


@dataclasses.dataclass(slots=True)
class JobDetail:
    """Parsed contents of an individual vacancy page."""

    eligibility: str = ""
    age_limit: str = ""
    important_dates: str = ""
    organization: str | None = None
    apply_url: str | None = None
    notification_pdf: str | None = None
    image_url: str | None = None
    salary: str = ""
    fee: str = ""
    min_age: int | None = None
    max_age: int | None = None
    raw_text: str = ""

    def to_json(self) -> str:
        return json.dumps(dataclasses.asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, payload: str) -> JobDetail:
        data = json.loads(payload)
        # Forward-compatible: older rows may lack newly added fields
        allowed = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in allowed})


@dataclasses.dataclass(slots=True)
class UserProfile:
    """A subscriber's saved preferences."""

    user_id: int
    username: str | None
    full_name: str
    category: str
    qualification: str
    sectors: list[str]
    dob: str | None = None                 # stored as DD/MM/YYYY
    active: bool = True
    created_at: str = ""
    updated_at: str = ""

    @property
    def qual_rank(self) -> int:
        from bot.constants import QUAL_MAP

        return QUAL_MAP[self.qualification]["rank"]

    @property
    def sector_labels(self) -> list[str]:
        from bot.constants import SECTOR_MAP

        return [SECTOR_MAP[k]["label"] for k in self.sectors if k in SECTOR_MAP]

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass(slots=True)
class SavedJob:
    """A bookmarked vacancy, optionally with a reminder."""

    user_id: int
    job_id: str
    title: str
    url: str
    last_date: str | None
    saved_at: str
    reminder_date: str | None = None      # ISO-8601 UTC instant
    reminded: bool = False

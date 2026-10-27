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
    raw_text: str = ""

    def to_json(self) -> str:
        return json.dumps(dataclasses.asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, payload: str) -> "JobDetail":
        return cls(**json.loads(payload))


@dataclasses.dataclass(slots=True)
class UserProfile:
    """A subscriber's saved preferences."""

    user_id: int
    username: str | None
    full_name: str
    category: str
    qualification: str
    sectors: list[str]
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

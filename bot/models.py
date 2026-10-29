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
    # --- v1.4: full notification features -------------------------------
    exam_name: str = ""              # "Railway RRB Station Master 2026"
    post_date: str = ""              # notification / post published date
    apply_start_date: str = ""       # "Apply Online Start Date"
    apply_last_date: str = ""        # "Apply Online Last Date"
    fee_last_date: str = ""          # "Last Date For Fee Payment"
    correction_date: str = ""        # "Correction Date"
    exam_date: str = ""              # "Exam Date"
    admit_card_date: str = ""        # "Admit Card"
    result_date: str = ""            # "Result Declared Date"
    total_posts: str = ""            # "Total Posts: 1265"
    selection_process: str = ""      # "Mode Of Selection"
    application_mode: str = ""       # "Apply Mode: Online / Offline"
    qualification: str = ""          # FULL qualification text (multi-line)
    how_to_apply: str = ""           # "How To Fill ... Online Form" steps
    documents_required: list[str] = dataclasses.field(default_factory=list)
    official_site: str | None = None
    short_notice: str | None = None
    vacancy_breakdown: dict[str, str] = dataclasses.field(default_factory=dict)
    states: list[str] = dataclasses.field(default_factory=list)
    ai_summary: str = ""                 # optional plain-English summary
    ai_summary_hi: str = ""              # optional Hindi summary

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
    degrees: list[str] = dataclasses.field(default_factory=list)     # multi-select
    documents: list[str] = dataclasses.field(default_factory=list)   # multi-select

    @property
    def qual_rank(self) -> int:
        from bot.constants import QUAL_MAP

        return QUAL_MAP[self.qualification]["rank"]

    @property
    def sector_labels(self) -> list[str]:
        from bot.constants import SECTOR_MAP

        return [SECTOR_MAP[k]["label"] for k in self.sectors if k in SECTOR_MAP]

    @property
    def degree_labels(self) -> list[str]:
        from bot.constants import DEGREE_MAP

        return [DEGREE_MAP[k]["label"] for k in self.degrees if k in DEGREE_MAP]

    @property
    def document_labels(self) -> list[str]:
        from bot.constants import DOCUMENT_MAP

        return [DOCUMENT_MAP[k]["label"] for k in self.documents if k in DOCUMENT_MAP]

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

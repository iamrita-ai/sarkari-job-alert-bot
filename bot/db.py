"""Async SQLite storage (users, jobs, notifications, bookmarks, reminders)."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import aiosqlite

from bot.models import JobDetail, JobSummary, SavedJob, UserProfile

logger = logging.getLogger(__name__)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


async def build_database():
    """Storage factory: SQLite by default, MongoDB when DATABASE_BACKEND=mongodb.

    Both backends expose the identical async method surface.
    """
    from bot import config

    if config.DATABASE_BACKEND == "mongodb":
        from bot.storage_mongo import MongoDatabase

        database = MongoDatabase(config.MONGODB_URI, config.MONGODB_DATABASE)
    else:
        database = Database(config.DATABASE_PATH)
    await database.connect()
    return database


class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        self._db: aiosqlite.Connection | None = None

    # ------------------------------------------------------------------ setup
    async def connect(self) -> None:
        self._db = await aiosqlite.connect(self.path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL;")
        await self._db.execute("PRAGMA foreign_keys=ON;")
        await self._create_schema()
        await self._migrate()
        logger.info("Database ready at %s", self.path)

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    async def _create_schema(self) -> None:
        assert self._db is not None
        await self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id       INTEGER PRIMARY KEY,
                username      TEXT,
                full_name     TEXT NOT NULL,
                category      TEXT NOT NULL,
                qualification TEXT NOT NULL,
                sectors       TEXT NOT NULL,
                dob           TEXT,
                active        INTEGER NOT NULL DEFAULT 1,
                created_at    TEXT NOT NULL,
                updated_at    TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS jobs (
                job_id         TEXT PRIMARY KEY,
                url            TEXT NOT NULL,
                title          TEXT NOT NULL,
                last_date      TEXT,
                first_seen     TEXT NOT NULL,
                detail_fetched INTEGER NOT NULL DEFAULT 0,
                detail_json    TEXT
            );

            CREATE TABLE IF NOT EXISTS notifications (
                user_id INTEGER NOT NULL,
                job_id  TEXT NOT NULL,
                sent_at TEXT NOT NULL,
                PRIMARY KEY (user_id, job_id)
            );

            CREATE TABLE IF NOT EXISTS saved_jobs (
                user_id       INTEGER NOT NULL,
                job_id        TEXT NOT NULL,
                title         TEXT NOT NULL,
                url           TEXT NOT NULL,
                last_date     TEXT,
                saved_at      TEXT NOT NULL,
                reminder_date TEXT,
                reminded      INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, job_id)
            );

            CREATE TABLE IF NOT EXISTS meta (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_jobs_pending
                ON jobs(detail_fetched, first_seen);
            CREATE INDEX IF NOT EXISTS idx_saved_reminders
                ON saved_jobs(reminded, reminder_date);
            """
        )
        await self._db.commit()

    async def _migrate(self) -> None:
        """Add columns introduced after the first release."""
        assert self._db is not None
        async with self._db.execute("PRAGMA table_info(users)") as cur:
            columns = {row["name"] for row in await cur.fetchall()}
        if "dob" not in columns:
            await self._db.execute("ALTER TABLE users ADD COLUMN dob TEXT")
            await self._db.commit()
            logger.info("Migration: added users.dob column")
        for column in ("degrees", "documents"):
            if column not in columns:
                await self._db.execute(
                    f"ALTER TABLE users ADD COLUMN {column} TEXT NOT NULL DEFAULT '[]'"
                )
                await self._db.commit()
                logger.info("Migration: added users.%s column", column)

    # -------------------------------------------------------------------- meta
    async def get_meta(self, key: str, default: str | None = None) -> str | None:
        assert self._db is not None
        async with self._db.execute(
            "SELECT value FROM meta WHERE key = ?", (key,)
        ) as cur:
            row = await cur.fetchone()
        return row["value"] if row else default

    async def set_meta(self, key: str, value: str) -> None:
        assert self._db is not None
        await self._db.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        await self._db.commit()

    # ------------------------------------------------------------------ users
    async def get_user(self, user_id: int) -> UserProfile | None:
        assert self._db is not None
        async with self._db.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
        return self._row_to_profile(row) if row else None

    async def upsert_user(
        self,
        user_id: int,
        username: str | None,
        full_name: str,
        category: str,
        qualification: str,
        sectors: list[str],
        dob: str | None,
        degrees: list[str] | None = None,
        documents: list[str] | None = None,
    ) -> UserProfile:
        assert self._db is not None
        now = _utcnow()
        existing = await self.get_user(user_id)
        created = existing.created_at if existing else now
        if degrees is None:
            degrees = existing.degrees if existing else []
        if documents is None:
            documents = existing.documents if existing else []
        await self._db.execute(
            """
            INSERT INTO users (user_id, username, full_name, category,
                               qualification, sectors, dob, degrees, documents,
                               active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username=excluded.username,
                full_name=excluded.full_name,
                category=excluded.category,
                qualification=excluded.qualification,
                sectors=excluded.sectors,
                dob=excluded.dob,
                degrees=excluded.degrees,
                documents=excluded.documents,
                active=1,
                updated_at=excluded.updated_at
            """,
            (user_id, username, full_name, category, qualification,
             json.dumps(sectors), dob, json.dumps(degrees), json.dumps(documents),
             created, now),
        )
        await self._db.commit()
        profile = await self.get_user(user_id)
        assert profile is not None
        return profile

    async def update_user(self, user_id: int, **fields) -> UserProfile | None:
        """Partial profile update used by the /edit menu."""
        assert self._db is not None
        allowed = {
            "full_name": lambda v: str(v),
            "category": lambda v: str(v),
            "qualification": lambda v: str(v),
            "dob": lambda v: v,
            "sectors": lambda v: json.dumps(list(v)),
            "degrees": lambda v: json.dumps(list(v)),
            "documents": lambda v: json.dumps(list(v)),
            "username": lambda v: v,
        }
        sets: list[str] = []
        values: list = []
        for key, value in fields.items():
            if key not in allowed or value is None:
                continue
            sets.append(f"{key} = ?")
            values.append(allowed[key](value))
        if not sets:
            return await self.get_user(user_id)
        sets.append("updated_at = ?")
        values.append(_utcnow())
        values.append(user_id)
        await self._db.execute(
            f"UPDATE users SET {', '.join(sets)} WHERE user_id = ?", values
        )
        await self._db.commit()
        return await self.get_user(user_id)

    async def set_active(self, user_id: int, active: bool) -> None:
        assert self._db is not None
        await self._db.execute(
            "UPDATE users SET active = ?, updated_at = ? WHERE user_id = ?",
            (1 if active else 0, _utcnow(), user_id),
        )
        await self._db.commit()

    async def all_active_users(self) -> list[UserProfile]:
        assert self._db is not None
        async with self._db.execute(
            "SELECT * FROM users WHERE active = 1"
        ) as cur:
            rows = await cur.fetchall()
        return [self._row_to_profile(r) for r in rows]

    async def all_users(self) -> list[UserProfile]:
        assert self._db is not None
        async with self._db.execute("SELECT * FROM users") as cur:
            rows = await cur.fetchall()
        return [self._row_to_profile(r) for r in rows]

    # ------------------------------------------------------------------- jobs
    async def get_seen_job_ids(self) -> set[str]:
        assert self._db is not None
        async with self._db.execute("SELECT job_id FROM jobs") as cur:
            rows = await cur.fetchall()
        return {r["job_id"] for r in rows}

    async def upsert_jobs(self, jobs: list[JobSummary]) -> None:
        """Insert new listings; existing rows are left untouched."""
        assert self._db is not None
        now = _utcnow()
        await self._db.executemany(
            """
            INSERT OR IGNORE INTO jobs
                (job_id, url, title, last_date, first_seen, detail_fetched)
            VALUES (?, ?, ?, ?, ?, 0)
            """,
            [(j.job_id, j.url, j.title, j.last_date, now) for j in jobs],
        )
        await self._db.commit()

    async def get_pending_jobs(
        self, limit: int, max_age_days: int = 10
    ) -> list[JobSummary]:
        """Jobs whose detail page still needs to be fetched & matched."""
        assert self._db is not None
        async with self._db.execute(
            """
            SELECT job_id, url, title, last_date FROM jobs
            WHERE detail_fetched = 0
              AND first_seen >= datetime('now', ?)
            ORDER BY first_seen ASC
            LIMIT ?
            """,
            (f"-{max_age_days} days", limit),
        ) as cur:
            rows = await cur.fetchall()
        return [
            JobSummary(r["job_id"], r["title"], r["url"], r["last_date"])
            for r in rows
        ]

    async def mark_detail_fetched(
        self, job_id: str, detail: JobDetail | None
    ) -> None:
        assert self._db is not None
        await self._db.execute(
            "UPDATE jobs SET detail_fetched = 1, detail_json = ? WHERE job_id = ?",
            (detail.to_json() if detail else None, job_id),
        )
        await self._db.commit()

    async def get_job_detail(self, job_id: str) -> JobDetail | None:
        assert self._db is not None
        async with self._db.execute(
            "SELECT detail_json FROM jobs WHERE job_id = ?", (job_id,)
        ) as cur:
            row = await cur.fetchone()
        if row and row["detail_json"]:
            return JobDetail.from_json(row["detail_json"])
        return None

    async def get_job(self, job_id: str) -> JobSummary | None:
        assert self._db is not None
        async with self._db.execute(
            "SELECT job_id, url, title, last_date FROM jobs WHERE job_id = ?",
            (job_id,),
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        return JobSummary(row["job_id"], row["title"], row["url"], row["last_date"])

    async def list_jobs(self, limit: int = 100) -> list[JobSummary]:
        assert self._db is not None
        async with self._db.execute(
            "SELECT job_id, url, title, last_date FROM jobs "
            "ORDER BY first_seen DESC LIMIT ?",
            (limit,),
        ) as cur:
            rows = await cur.fetchall()
        return [
            JobSummary(r["job_id"], r["title"], r["url"], r["last_date"])
            for r in rows
        ]

    async def search_jobs(self, keyword: str, limit: int = 20) -> list[JobSummary]:
        assert self._db is not None
        if keyword.strip():
            query = (
                "SELECT job_id, url, title, last_date FROM jobs "
                "WHERE title LIKE ? ORDER BY first_seen DESC LIMIT ?"
            )
            params: tuple = (f"%{keyword.strip()}%", limit)
        else:
            query = (
                "SELECT job_id, url, title, last_date FROM jobs "
                "ORDER BY first_seen DESC LIMIT ?"
            )
            params = (limit,)
        async with self._db.execute(query, params) as cur:
            rows = await cur.fetchall()
        return [
            JobSummary(r["job_id"], r["title"], r["url"], r["last_date"])
            for r in rows
        ]

    async def mark_bootstrap_complete(self) -> None:
        """Consider every currently catalogued job already processed."""
        assert self._db is not None
        await self._db.execute(
            "UPDATE jobs SET detail_fetched = 1 WHERE detail_fetched = 0"
        )
        await self._db.commit()

    # ------------------------------------------------------------ notifications
    async def was_notified(self, user_id: int, job_id: str) -> bool:
        assert self._db is not None
        async with self._db.execute(
            "SELECT 1 FROM notifications WHERE user_id = ? AND job_id = ?",
            (user_id, job_id),
        ) as cur:
            return await cur.fetchone() is not None

    async def mark_notified(self, user_id: int, job_id: str) -> None:
        assert self._db is not None
        await self._db.execute(
            "INSERT OR IGNORE INTO notifications (user_id, job_id, sent_at) "
            "VALUES (?, ?, ?)",
            (user_id, job_id, _utcnow()),
        )
        await self._db.commit()

    async def notification_count(self) -> int:
        assert self._db is not None
        async with self._db.execute(
            "SELECT COUNT(*) AS c FROM notifications"
        ) as cur:
            row = await cur.fetchone()
        return int(row["c"])

    async def job_count(self) -> int:
        assert self._db is not None
        async with self._db.execute("SELECT COUNT(*) AS c FROM jobs") as cur:
            row = await cur.fetchone()
        return int(row["c"])

    # ------------------------------------------------------- bookmarks/reminders
    async def save_job(self, user_id: int, job: JobSummary) -> bool:
        """Bookmark a job. Returns False if it was already saved."""
        assert self._db is not None
        await self._db.execute(
            """
            INSERT OR IGNORE INTO saved_jobs
                (user_id, job_id, title, url, last_date, saved_at, reminded)
            VALUES (?, ?, ?, ?, ?, ?, 0)
            """,
            (user_id, job.job_id, job.title, job.url, job.last_date, _utcnow()),
        )
        await self._db.commit()
        async with self._db.execute(
            "SELECT changes() AS c"
        ) as cur:
            return bool((await cur.fetchone())["c"])

    async def unsave_job(self, user_id: int, job_id: str) -> None:
        assert self._db is not None
        await self._db.execute(
            "DELETE FROM saved_jobs WHERE user_id = ? AND job_id = ?",
            (user_id, job_id),
        )
        await self._db.commit()

    async def is_saved(self, user_id: int, job_id: str) -> bool:
        assert self._db is not None
        async with self._db.execute(
            "SELECT 1 FROM saved_jobs WHERE user_id = ? AND job_id = ?",
            (user_id, job_id),
        ) as cur:
            return await cur.fetchone() is not None

    async def list_saved(self, user_id: int) -> list[SavedJob]:
        assert self._db is not None
        async with self._db.execute(
            "SELECT * FROM saved_jobs WHERE user_id = ? ORDER BY saved_at DESC",
            (user_id,),
        ) as cur:
            rows = await cur.fetchall()
        return [self._row_to_saved(r) for r in rows]

    async def set_reminder(
        self, user_id: int, job_id: str, reminder_iso_utc: str
    ) -> None:
        assert self._db is not None
        await self._db.execute(
            "UPDATE saved_jobs SET reminder_date = ?, reminded = 0 "
            "WHERE user_id = ? AND job_id = ?",
            (reminder_iso_utc, user_id, job_id),
        )
        await self._db.commit()

    async def pending_reminders(self) -> list[SavedJob]:
        assert self._db is not None
        async with self._db.execute(
            "SELECT * FROM saved_jobs WHERE reminded = 0 AND reminder_date IS NOT NULL"
        ) as cur:
            rows = await cur.fetchall()
        return [self._row_to_saved(r) for r in rows]

    async def mark_reminded(self, user_id: int, job_id: str) -> None:
        assert self._db is not None
        await self._db.execute(
            "UPDATE saved_jobs SET reminded = 1 WHERE user_id = ? AND job_id = ?",
            (user_id, job_id),
        )
        await self._db.commit()

    async def saved_count(self, user_id: int) -> int:
        assert self._db is not None
        async with self._db.execute(
            "SELECT COUNT(*) AS c FROM saved_jobs WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
        return int(row["c"])

    # ---------------------------------------------------------------- helpers
    @staticmethod
    def _row_to_profile(row: aiosqlite.Row) -> UserProfile:
        keys = row.keys()
        return UserProfile(
            user_id=row["user_id"],
            username=row["username"],
            full_name=row["full_name"],
            category=row["category"],
            qualification=row["qualification"],
            sectors=json.loads(row["sectors"]),
            dob=row["dob"] if "dob" in keys else None,
            active=bool(row["active"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            degrees=json.loads(row["degrees"]) if "degrees" in keys else [],
            documents=json.loads(row["documents"]) if "documents" in keys else [],
        )

    @staticmethod
    def _row_to_saved(row: aiosqlite.Row) -> SavedJob:
        return SavedJob(
            user_id=row["user_id"],
            job_id=row["job_id"],
            title=row["title"],
            url=row["url"],
            last_date=row["last_date"],
            saved_at=row["saved_at"],
            reminder_date=row["reminder_date"],
            reminded=bool(row["reminded"]),
        )

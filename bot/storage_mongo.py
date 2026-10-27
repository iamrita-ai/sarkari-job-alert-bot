"""Optional MongoDB backend (drop-in replacement for ``bot.db.Database``).

Activate with environment variables::

    DATABASE_BACKEND=mongodb
    MONGODB_URI=mongodb+srv://user:pass@cluster/example?retryWrites=true
    MONGODB_DATABASE=sarkari_job_bot

The extra dependency is NOT installed by default - add ``motor`` (see
requirements-mongo.txt). Every method mirrors the SQLite implementation so the
rest of the bot is storage-agnostic.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

from bot.models import JobDetail, JobSummary, SavedJob, UserProfile

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso() -> str:
    return _utcnow().isoformat(timespec="seconds")


class MongoDatabase:
    def __init__(self, uri: str, database_name: str) -> None:
        if not uri:
            raise SystemExit(
                "DATABASE_BACKEND=mongodb but MONGODB_URI is empty. "
                "Set MONGODB_URI (e.g. a MongoDB Atlas connection string)."
            )
        self.uri = uri
        self.database_name = database_name
        self._client = None
        self._db = None

    # ------------------------------------------------------------------ setup
    async def connect(self) -> None:
        from motor.motor_asyncio import AsyncIOMotorClient

        self._client = AsyncIOMotorClient(self.uri, serverSelectionTimeoutMS=10000)
        # Fail fast on wrong credentials instead of at the first query
        await self._client.admin.command("ping")
        self._db = self._client[self.database_name]
        await self._db["jobs"].create_index("detail_fetched")
        await self._db["jobs"].create_index("first_seen")
        await self._db["saved_jobs"].create_index(
            [("reminded", 1), ("reminder_date", 1)]
        )
        logger.info("MongoDB ready: database '%s'", self.database_name)

    async def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    # -------------------------------------------------------------------- meta
    async def get_meta(self, key: str, default: str | None = None) -> str | None:
        doc = await self._db["meta"].find_one({"_id": key})
        return doc["value"] if doc else default

    async def set_meta(self, key: str, value: str) -> None:
        await self._db["meta"].update_one(
            {"_id": key}, {"$set": {"value": value}}, upsert=True
        )

    # ------------------------------------------------------------------ users
    @staticmethod
    def _profile_from_doc(doc: dict) -> UserProfile:
        return UserProfile(
            user_id=doc["_id"],
            username=doc.get("username"),
            full_name=doc["full_name"],
            category=doc["category"],
            qualification=doc["qualification"],
            sectors=doc.get("sectors", []),
            dob=doc.get("dob"),
            active=bool(doc.get("active", True)),
            created_at=doc.get("created_at", ""),
            updated_at=doc.get("updated_at", ""),
        )

    async def get_user(self, user_id: int) -> UserProfile | None:
        doc = await self._db["users"].find_one({"_id": user_id})
        return self._profile_from_doc(doc) if doc else None

    async def upsert_user(self, user_id, username, full_name, category,
                          qualification, sectors, dob) -> UserProfile:
        now = _iso()
        existing = await self.get_user(user_id)
        created = existing.created_at if existing else now
        await self._db["users"].update_one(
            {"_id": user_id},
            {"$set": {
                "username": username, "full_name": full_name,
                "category": category, "qualification": qualification,
                "sectors": sectors, "dob": dob, "active": True,
                "updated_at": now,
            }, "$setOnInsert": {"_id": user_id, "created_at": created}},
            upsert=True,
        )
        profile = await self.get_user(user_id)
        assert profile is not None
        return profile

    async def set_active(self, user_id: int, active: bool) -> None:
        await self._db["users"].update_one(
            {"_id": user_id}, {"$set": {"active": active, "updated_at": _iso()}}
        )

    async def all_active_users(self) -> list[UserProfile]:
        return [self._profile_from_doc(d)
                async for d in self._db["users"].find({"active": True})]

    async def all_users(self) -> list[UserProfile]:
        return [self._profile_from_doc(d)
                async for d in self._db["users"].find({})]

    # ------------------------------------------------------------------- jobs
    async def get_seen_job_ids(self) -> set[str]:
        return {d["_id"] async for d in self._db["jobs"].find({}, {"_id": 1})}

    async def upsert_jobs(self, jobs: list[JobSummary]) -> None:
        from pymongo import UpdateOne

        now = _utcnow()
        await self._db["jobs"].bulk_write([
            UpdateOne(
                {"_id": job.job_id},
                {"$setOnInsert": {
                    "url": job.url, "title": job.title,
                    "last_date": job.last_date, "first_seen": now,
                    "detail_fetched": False, "detail": None,
                }},
                upsert=True,
            )
            for job in jobs
        ], ordered=False)

    async def get_pending_jobs(self, limit: int, max_age_days: int = 10) -> list[JobSummary]:
        cutoff = _utcnow() - timedelta(days=max_age_days)
        cursor = (
            self._db["jobs"]
            .find({"detail_fetched": False, "first_seen": {"$gte": cutoff}})
            .sort("first_seen", 1).limit(limit)
        )
        return [JobSummary(d["_id"], d["title"], d["url"], d.get("last_date"))
                async for d in cursor]

    async def mark_detail_fetched(self, job_id: str, detail: JobDetail | None) -> None:
        await self._db["jobs"].update_one(
            {"_id": job_id},
            {"$set": {
                "detail_fetched": True,
                "detail": dataclasses_asdict(detail) if detail else None,
            }},
        )

    async def get_job_detail(self, job_id: str) -> JobDetail | None:
        doc = await self._db["jobs"].find_one({"_id": job_id})
        if doc and doc.get("detail"):
            allowed = {f for f in JobDetail.__dataclass_fields__}
            return JobDetail(**{k: v for k, v in doc["detail"].items() if k in allowed})
        return None

    async def get_job(self, job_id: str) -> JobSummary | None:
        d = await self._db["jobs"].find_one({"_id": job_id})
        return JobSummary(d["_id"], d["title"], d["url"], d.get("last_date")) if d else None

    async def list_jobs(self, limit: int = 100) -> list[JobSummary]:
        cursor = self._db["jobs"].find({}).sort("first_seen", -1).limit(limit)
        return [JobSummary(d["_id"], d["title"], d["url"], d.get("last_date"))
                async for d in cursor]

    async def search_jobs(self, keyword: str, limit: int = 20) -> list[JobSummary]:
        query: dict = {}
        if keyword.strip():
            safe = re.escape(keyword.strip())
            query["title"] = {"$regex": safe, "$options": "i"}
        cursor = self._db["jobs"].find(query).sort("first_seen", -1).limit(limit)
        return [JobSummary(d["_id"], d["title"], d["url"], d.get("last_date"))
                async for d in cursor]

    async def mark_bootstrap_complete(self) -> None:
        await self._db["jobs"].update_many(
            {"detail_fetched": False}, {"$set": {"detail_fetched": True}}
        )

    # ------------------------------------------------------------ notifications
    async def was_notified(self, user_id: int, job_id: str) -> bool:
        return await self._db["notifications"].find_one(
            {"_id": f"{user_id}:{job_id}"}
        ) is not None

    async def mark_notified(self, user_id: int, job_id: str) -> None:
        from pymongo.errors import DuplicateKeyError

        try:
            await self._db["notifications"].insert_one({
                "_id": f"{user_id}:{job_id}",
                "user_id": user_id, "job_id": job_id, "sent_at": _iso(),
            })
        except DuplicateKeyError:
            pass

    async def notification_count(self) -> int:
        return await self._db["notifications"].count_documents({})

    async def job_count(self) -> int:
        return await self._db["jobs"].count_documents({})

    # ------------------------------------------------------- bookmarks/reminders
    async def save_job(self, user_id: int, job: JobSummary) -> bool:
        from pymongo.errors import DuplicateKeyError

        try:
            await self._db["saved_jobs"].insert_one({
                "_id": f"{user_id}:{job.job_id}",
                "user_id": user_id, "job_id": job.job_id,
                "title": job.title, "url": job.url, "last_date": job.last_date,
                "saved_at": _iso(), "reminder_date": None, "reminded": False,
            })
            return True
        except DuplicateKeyError:
            return False

    async def unsave_job(self, user_id: int, job_id: str) -> None:
        await self._db["saved_jobs"].delete_one({"_id": f"{user_id}:{job_id}"})

    async def is_saved(self, user_id: int, job_id: str) -> bool:
        return await self._db["saved_jobs"].find_one(
            {"_id": f"{user_id}:{job_id}"}
        ) is not None

    @staticmethod
    def _saved_from_doc(d: dict) -> SavedJob:
        return SavedJob(
            user_id=d["user_id"], job_id=d["job_id"], title=d["title"],
            url=d["url"], last_date=d.get("last_date"), saved_at=d["saved_at"],
            reminder_date=d.get("reminder_date"), reminded=bool(d.get("reminded")),
        )

    async def list_saved(self, user_id: int) -> list[SavedJob]:
        cursor = self._db["saved_jobs"].find(
            {"user_id": user_id}
        ).sort("saved_at", -1)
        return [self._saved_from_doc(d) async for d in cursor]

    async def set_reminder(self, user_id: int, job_id: str,
                           reminder_iso_utc: str) -> None:
        await self._db["saved_jobs"].update_one(
            {"_id": f"{user_id}:{job_id}"},
            {"$set": {"reminder_date": reminder_iso_utc, "reminded": False}},
        )

    async def pending_reminders(self) -> list[SavedJob]:
        cursor = self._db["saved_jobs"].find(
            {"reminded": False, "reminder_date": {"$ne": None}}
        )
        return [self._saved_from_doc(d) async for d in cursor]

    async def mark_reminded(self, user_id: int, job_id: str) -> None:
        await self._db["saved_jobs"].update_one(
            {"_id": f"{user_id}:{job_id}"}, {"$set": {"reminded": True}}
        )

    async def saved_count(self, user_id: int) -> int:
        return await self._db["saved_jobs"].count_documents({"user_id": user_id})


def dataclasses_asdict(detail: JobDetail) -> dict:
    import dataclasses

    return dataclasses.asdict(detail)

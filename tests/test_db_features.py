"""Database: user DOB migration, bookmarks and reminders (no async plugin)."""
import asyncio
import tempfile
from pathlib import Path

from bot.db import Database
from bot.models import JobSummary


def _tmp_db() -> Database:
    path = str(Path(tempfile.mkdtemp()) / "t.db")
    return Database(path)


def test_user_dob_persistence():
    async def scenario():
        db = _tmp_db()
        await db.connect()
        profile = await db.upsert_user(
            1, "tester", "Rahul", "OBC", "graduate", ["railway"], "15/08/2000"
        )
        assert profile.dob == "15/08/2000"
        assert (await db.get_user(1)).dob == "15/08/2000"
        await db.close()

    asyncio.run(scenario())


def test_save_and_reminder_lifecycle():
    async def scenario():
        db = _tmp_db()
        await db.connect()
        await db.upsert_user(1, "u", "Rahul", "UR", "graduate", ["railway"], None)
        job = JobSummary(
            "/railway-x-2026", "Railway X Online Form 2026",
            "https://sarkariresult.com.cm/railway-x-2026/", "25/11/2026",
        )

        assert await db.save_job(1, job) is True
        assert await db.save_job(1, job) is False       # duplicate ignored
        assert await db.is_saved(1, job.job_id) is True
        assert await db.saved_count(1) == 1

        await db.set_reminder(1, job.job_id, "2026-11-24T03:30:00+00:00")
        pending = await db.pending_reminders()
        assert len(pending) == 1
        assert pending[0].reminder_date == "2026-11-24T03:30:00+00:00"

        await db.mark_reminded(1, job.job_id)
        assert await db.pending_reminders() == []

        saved = await db.list_saved(1)
        assert len(saved) == 1 and saved[0].title == job.title

        await db.unsave_job(1, job.job_id)
        assert await db.saved_count(1) == 0
        await db.close()

    asyncio.run(scenario())


def test_job_search_and_listing():
    async def scenario():
        db = _tmp_db()
        await db.connect()
        await db.upsert_jobs([
            JobSummary("/railway-a-2026", "Railway RRB A Online Form 2026",
                       "https://sarkariresult.com.cm/railway-a-2026/", None),
            JobSummary("/sbi-b-2026", "SBI Clerk Online Form 2026",
                       "https://sarkariresult.com.cm/sbi-b-2026/", None),
        ])
        results = await db.search_jobs("railway")
        assert len(results) == 1 and results[0].title.startswith("Railway")
        assert len(await db.list_jobs()) == 2
        fetched = await db.get_job("/sbi-b-2026")
        assert fetched is not None and fetched.url.endswith("/sbi-b-2026/")
        await db.close()

    asyncio.run(scenario())

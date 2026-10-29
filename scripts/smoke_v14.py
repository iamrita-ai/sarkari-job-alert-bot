"""End-to-end smoke test for the v1.4 flows (no network, no real Telegram)."""
import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot import browser, cards, handlers, keyboards, reminders  # noqa: E402
from bot.db import Database  # noqa: E402
from bot.models import JobDetail, JobSummary  # noqa: E402


class FakeMessage:
    def __init__(self):
        self.sent = []
        self.text = None

    async def reply_markdown_v2(self, text, **kwargs):
        self.sent.append(("md", text, kwargs))

    async def reply_text(self, text, **kwargs):
        self.sent.append(("txt", text, kwargs))

    async def reply_photo(self, **kwargs):
        raise RuntimeError("no banner in smoke test")

    async def edit_message_text(self, text, **kwargs):
        self.sent.append(("edit", text, kwargs))


class FakeUser:
    id = 4242
    username = "TechnicalSerena"
    first_name = "Owner"


class FakeQuery:
    def __init__(self, data):
        self.data = data
        self.message = FakeMessage()
        self.answers = []
        self.markup = None
        self.from_user = FakeUser()

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))

    async def edit_message_text(self, text, **kwargs):
        self.message.sent.append(("edit", text, kwargs))

    async def edit_message_reply_markup(self, reply_markup=None, **kwargs):
        self.markup = reply_markup


class FakeUpdate:
    def __init__(self, text=None, callback=None, args=None):
        self.effective_user = FakeUser()
        self.effective_message = FakeMessage()
        self.message = self.effective_message
        self.callback_query = FakeQuery(callback) if callback else None
        self.text = text
        self.args = args
        if text is not None:
            self.message.text = text


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, **kwargs):
        self.sent.append((chat_id, text))


class FakeApp:
    def __init__(self, db):
        self.bot_data = {
            "db": db,
            "bot_username": "jobtestbot",
            "browsers": {},
            "saved_browsers": {},
            "owner_chat_ids": set(),
            "admin_users": {},
        }
        self.bot = FakeBot()


class FakeContext:
    def __init__(self, app):
        self.application = app
        self.user_data = {}

    @property
    def bot(self):
        return self.application.bot


async def main() -> int:
    tmp = tempfile.mkdtemp()
    db = Database(str(Path(tmp) / "smoke.db"))
    await db.connect()
    try:
        return await run_checks(db)
    finally:
        await db.close()


async def run_checks(db) -> int:
    app = FakeApp(db)
    ctx = FakeContext(app)

    # ---------------------------------------------------- onboarding (6 steps)
    up = FakeUpdate(callback="start:begin")
    await handlers.begin_conversation(up, ctx)
    await handlers.name_received(FakeUpdate(text="Smoke Tester"), ctx)
    await handlers.dob_received(FakeUpdate(text="15/08/2000"), ctx)
    await handlers.category_chosen(FakeUpdate(callback="cat:OBC"), ctx)
    await handlers.degree_chosen(FakeUpdate(callback="deg:iti"), ctx)
    await handlers.degree_chosen(FakeUpdate(callback="deg:b_ed"), ctx)
    await handlers.degree_chosen(FakeUpdate(callback="deg:done"), ctx)
    await handlers.document_chosen(FakeUpdate(callback="doc:aadhaar"), ctx)
    await handlers.document_chosen(FakeUpdate(callback="doc:caste_certificate"), ctx)
    await handlers.document_chosen(FakeUpdate(callback="doc:done"), ctx)
    await handlers.sector_chosen(FakeUpdate(callback="sec:railway"), ctx)
    await handlers.sector_chosen(FakeUpdate(callback="sec:done"), ctx)

    profile = await db.get_user(4242)
    assert profile is not None, "profile was not saved"
    assert sorted(profile.degrees) == ["b_ed", "iti"], profile.degrees
    assert sorted(profile.documents) == ["aadhaar", "caste_certificate"]
    assert profile.qualification == "graduate", profile.qualification
    assert profile.sectors == ["railway"]
    print("OK onboarding: degrees/documents/qualification saved")

    # ---------------------------------------------------------- edit menu
    await handlers.edit_profile(FakeUpdate(), ctx)
    await handlers.profile_edit_callback(FakeUpdate(callback="pe:degrees"), ctx)
    await handlers.degree_chosen(FakeUpdate(callback="deg:b_sc"), ctx)
    await handlers.degree_chosen(FakeUpdate(callback="deg:done"), ctx)
    profile = await db.get_user(4242)
    assert sorted(profile.degrees) == ["b_ed", "b_sc", "iti"], profile.degrees
    print("OK edit menu: degrees updated without touching the rest")

    # ------------------------------------------------------------- browser
    jobs = [
        JobSummary(f"/job-{i}-2026/", f"Railway Job {i} 2026",
                   f"https://sarkariresult.com.cm/job-{i}-2026/", "25/11/2026")
        for i in range(14)
    ]
    await browser.open_browser(FakeUpdate(), ctx, 4242, jobs,
                               kind="all", heading="All Catalogued Jobs")
    query = FakeQuery("br:n")
    up = FakeUpdate(callback="br:n")
    await browser.browser_callback(up, ctx)
    assert up.callback_query.message.sent, "Next button produced no output"
    text = up.callback_query.message.sent[-1][1]
    assert "Page 2 / 3" in text, text[:200]
    print("OK browser: Next button moves to page 2")

    # ------------------------------------------------------- full text button
    await db.upsert_jobs([jobs[0]])
    await db.mark_detail_fetched(jobs[0].job_id, JobDetail(
        qualification="Bachelor Degree in any stream",
        apply_start_date="27 October 2026",
        apply_last_date="25 November 2026",
        important_dates="Apply Online Last Date : 25/11/2026",
    ))
    up = FakeUpdate(callback=f"full:{__import__('bot.utils', fromlist=['x']).encode_job_id(jobs[0].job_id)}")
    await handlers.full_text_callback(up, ctx)
    assert up.callback_query.message.sent, "full text button produced nothing"
    assert "Bachelor Degree" in up.callback_query.message.sent[-1][1]
    print("OK full notification text button")

    # ------------------------------------------------------------ admin tools
    up = FakeUpdate()
    await handlers.admin_users(up, ctx)
    assert up.effective_message.sent, "/users produced nothing"
    assert "Smoke Tester" in up.effective_message.sent[-1][1]
    up = FakeUpdate(callback="adm:prof:4242")
    await handlers.admin_users_callback(up, ctx)
    assert "Subscriber Profile" in up.callback_query.message.sent[-1][1]
    print("OK owner /users list + profile redirect")

    # ------------------------------------------------------------- /sources
    report = [
        {"source": "mirror", "ok": True, "jobs": 99, "error": None},
        {"source": "original", "ok": False, "jobs": 0,
         "error": "Could not fetch https://www.sarkariresult.com/latestjob/: HTTP 403"},
        {"source": "original-jina", "ok": False, "jobs": 0,
         "error": "Reader proxy could not reach the source (blocked)"},
    ]
    text = handlers.format_sources_report(
        report, {"last_success_at": "2026-10-29T11:14:17+00:00",
                 "last_success_source": "mirror"})
    assert "standby" in text and "Primary source is healthy" in text
    print("OK /sources report shows fallbacks as standby")

    print("\nSMOKE OK - all v1.4 flows work")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

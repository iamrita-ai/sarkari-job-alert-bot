"""Web dashboard tests (skipped when FastAPI is not installed)."""
import asyncio

import pytest

fastapi = pytest.importorskip("fastapi")

from bot import config  # noqa: E402
from bot.models import JobSummary, UserProfile  # noqa: E402
from bot.webapp import create_app, sign_token, verify_token  # noqa: E402

SECRET = "topsecret-test"


class FakeDB:
    """Minimal async storage stub for the dashboard routes."""

    def __init__(self):
        self.profile = UserProfile(
            user_id=7, username="u", full_name="Rahul", category="OBC",
            qualification="graduate", sectors=["railway"], dob="15/08/2000",
            degrees=["b_ed"], documents=["aadhaar"],
        )
        self.jobs = [
            JobSummary("/railway-new-2026/", "Railway New Job 2026",
                       "https://sarkariresult.com.cm/railway-new-2026/", "30/11/2026"),
        ]

    async def get_user(self, user_id):
        return self.profile if user_id == 7 else None

    async def list_saved(self, user_id):
        return []

    async def search_jobs(self, keyword, limit=20):
        return self.jobs

    async def get_job_detail(self, job_id):
        return None

    async def update_user(self, user_id, **fields):
        for key, value in fields.items():
            setattr(self.profile, key, value)
        return self.profile


class FakeApp:
    def __init__(self):
        self.bot_data = {"db": FakeDB()}


def _client():
    from fastapi.testclient import TestClient

    app = FakeApp()
    return TestClient(create_app(app)), app


@pytest.fixture(autouse=True)
def _web_secret(monkeypatch):
    monkeypatch.setattr(config, "WEB_APP_SECRET", SECRET)


def test_dashboard_requires_a_valid_token():
    client, _ = _client()
    assert "Open" in client.get("/?t=badtoken").text
    token = sign_token(7, SECRET)
    body = client.get(f"/?t={token}").text
    assert "Railway New Job 2026" in body


def test_profile_form_and_save():
    client, app = _client()
    token = sign_token(7, SECRET)
    form = client.get(f"/profile?t={token}").text
    assert "B.Ed" in form
    assert "Aadhaar" in form
    saved = client.post("/profile", data={
        "t": token, "full_name": "Rahul Kumar", "dob": "15/08/2000",
        "category": "SC", "degrees": ["b_ed", "iti"],
        "documents": ["aadhaar"], "sectors": ["railway"],
    })
    assert saved.status_code == 200
    assert "Profile saved" in saved.text
    profile = app.bot_data["db"].profile
    assert profile.full_name == "Rahul Kumar"
    assert profile.category == "SC"
    assert profile.degrees == ["b_ed", "iti"]


def test_tokens_are_signed():
    token = sign_token(7, SECRET)
    assert verify_token(token, SECRET) == 7
    assert verify_token(token, "other-secret") is None
    assert verify_token("7.deadbeef", "topsecret") is None

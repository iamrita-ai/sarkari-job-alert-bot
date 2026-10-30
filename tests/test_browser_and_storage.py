"""Browser keyboard shape, deep links and storage-backend parity."""
import inspect

from bot.cards import list_page, saved_list_card
from bot.db import Database
from bot.keyboards import browse_keyboard, saved_browse_keyboard
from bot.models import JobSummary
from bot.utils import job_ref

JOB = JobSummary("/railway-x-2026", "Railway X Online Form 2026",
                 "https://sarkariresult.com.cm/railway-x-2026/", "25/11/2026")


def test_browser_keyboards_have_only_navigation_buttons():
    for kb in (browse_keyboard(0, 3, [JOB]),
               browse_keyboard(1, 3, [JOB]),
               saved_browse_keyboard(2, 5, [object()])):
        callbacks = [
            b.callback_data for row in kb.inline_keyboard for b in row
        ]
        # No numbered open buttons (br:o: / sv:o:) may exist
        assert not any(c and (c.startswith("br:o:") or c.startswith("sv:o:"))
                       for c in callbacks)
        assert any(c == "br:p" or c == "sv:p" for c in callbacks) or \
               any(c == "br:n" or c == "sv:n" for c in callbacks)
        assert "br:home" in callbacks


def test_first_page_hides_previous_last_page_hides_next():
    first = [b.callback_data for row in browse_keyboard(0, 3, [JOB]).inline_keyboard
             for b in row]
    last = [b.callback_data for row in browse_keyboard(2, 3, [JOB]).inline_keyboard
            for b in row]
    assert "br:p" not in first and "br:n" in first
    assert "br:n" not in last and "br:p" in last


def test_list_page_deep_links_open_the_bot_card():
    base = "https://t.me/jobbot?start=j"
    text = list_page([JOB], 0, 1, "Latest", deep_base=base)
    expected = base + job_ref(JOB.job_id)
    assert f"({expected})" in text
    # The deep link carries a short reference (Telegram allows 64 characters)
    payload = expected.split("start=")[1][1:]
    assert payload == job_ref(JOB.job_id)
    assert len(payload) <= 64

    # Without a bot username the external URL is used
    fallback = list_page([JOB], 0, 1, "Latest")
    assert f"({JOB.url})" in fallback


def test_mongo_backend_matches_sqlite_interface():
    from bot.storage_mongo import MongoDatabase

    sqlite_methods = {
        name for name, _ in inspect.getmembers(Database, inspect.isfunction)
        if not name.startswith("_")
    }
    mongo_methods = {
        name for name, _ in inspect.getmembers(MongoDatabase, inspect.isfunction)
        if not name.startswith("_")
    }
    missing = sqlite_methods - mongo_methods
    assert not missing, f"Mongo backend missing methods: {missing}"

    # motor is imported lazily so the default SQLite deployment has no mongo dep
    import sys
    assert "motor" not in sys.modules


def test_saved_list_renders_deep_links():
    class Saved:
        job_id = "/saved-x-2026"
        title = "Saved Job 2026"
        url = "https://sarkariresult.com.cm/saved-x-2026/"
        last_date = "01/01/2027"
        reminder_date = "2026-12-31T03:30:00+00:00"

    text = saved_list_card([Saved()], 0, 1, "https://t.me/jobbot?start=j")
    assert "⏰" in text
    assert job_ref(Saved.job_id) in text

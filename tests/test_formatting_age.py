"""MarkdownV2 escaping, DOB/age maths, deep links and age-relaxation rules."""
from datetime import date

import pytest

from bot.cards import job_card, photo_caption, profile_card
from bot.matcher import age_matches
from bot.models import JobDetail, JobSummary, UserProfile
from bot.utils import (
    calculate_age,
    decode_job_id,
    encode_job_id,
    md_escape,
    parse_dob,
)


# ------------------------------------------------------------- MarkdownV2
def test_md_escape_covers_every_special_character():
    raw = "_*[]()~`>#+-=|{}.!\\"
    escaped = md_escape(raw)
    # Every special char must be preceded by a backslash
    for char in "_*[]()~`>#+-=|{}.!":
        assert f"\\{char}" in escaped
    assert md_escape(None) == ""


def test_cards_escape_dangerous_user_input():
    profile = UserProfile(
        user_id=1, username="u", full_name="Rahul_Test. 100%!",
        category="OBC", qualification="graduate", sectors=["railway"],
        dob="15/08/2000",
    )
    job = JobSummary("/x/evil-2026/", "B.Ed? *Special* [Recruitment] 2026",
                     "https://sarkariresult.com.cm/evil-2026/", "25/11/2026")
    detail = JobDetail(
        eligibility="Bachelor's (Any Stream)", fee="UR: ₹500/-",
        min_age=20, max_age=33,
        apply_url="https://apply.example.in/x",
    )
    text = job_card(job, detail, profile, {"user_age": 26, "relaxation": 3,
                                           "effective_max": 36, "min_age": 20,
                                           "max_age": 33, "reason": "ok"})
    # Raw title markup must be neutralised with backslashes
    assert "B\\.Ed?" in text
    assert "\\*Special\\*" in text
    assert "\\[Recruitment\\]" in text
    # Entities we deliberately create stay intact
    assert "*NEW SARKARI JOB MATCH*" in text
    assert "[CLICK HERE TO FILL FORM]" in text
    assert len(text) <= 4096

    # User-controlled name is escaped on the profile card
    pc = profile_card(profile)
    assert "Rahul\\_Test\\." in pc and "100%\\!" in pc

    caption = photo_caption(job, detail, profile)
    assert len(caption) <= 1024


def test_profile_card_shows_dob_and_age():
    profile = UserProfile(
        user_id=1, username=None, full_name="Asha", category="SC",
        qualification="twelfth", sectors=["banking"], dob="03/04/2003",
    )
    card = profile_card(profile)
    assert "03/04/2003" in card
    assert str(calculate_age("03/04/2003")) in card


# ------------------------------------------------------------- dates
def test_dob_parsing_and_validation():
    assert parse_dob("15/08/2000") == date(2000, 8, 15)
    assert parse_dob("15-08-2000") == date(2000, 8, 15)
    assert parse_dob("31/02/2000") is None      # impossible date
    assert parse_dob("15.08.2000") is None      # wrong separator
    assert parse_dob("") is None


def test_age_calculation():
    # Fixed reference date so the test never ages out
    assert calculate_age("15/08/2000", on_date=date(2026, 10, 27)) == 26
    assert calculate_age("27/12/2000", on_date=date(2026, 10, 27)) == 25
    assert calculate_age(None) is None


# ------------------------------------------------------------- deep links
def test_job_id_roundtrip_and_guard():
    for job_id in ["/railway-rrb-station-master-2026",
                   "/2026/some-deep/slug/",
                   "/x-y_z-2026/"]:
        encoded = encode_job_id(job_id)
        assert encoded.isascii() and "/" not in encoded and "=" not in encoded
        assert decode_job_id(encoded) == job_id
    assert decode_job_id("bad payload!!") is None


# ------------------------------------------------------------- age matching
def _profile(dob: str, category: str) -> UserProfile:
    return UserProfile(
        user_id=1, username=None, full_name="T", category=category,
        qualification="graduate", sectors=["railway"], dob=dob,
    )


def test_age_match_with_category_relaxation():
    # 35 year old OBC candidate, max age 33 -> +3 relaxation allows up to 36
    obc = _profile("01/01/1991", "OBC")
    detail = JobDetail(min_age=20, max_age=33)
    ok, info = age_matches(obc, detail)
    assert ok is True and info["effective_max"] == 36 and info["relaxation"] == 3

    # Same candidate as UR (no relaxation) -> rejected
    ur = _profile("01/01/1991", "UR")
    ok, info = age_matches(ur, detail)
    assert ok is False and "above maximum" in info["reason"]

    # SC gets +5
    sc = _profile("01/01/1989", "SC")  # 37 years old, max 33 + 5 = 38
    ok, info = age_matches(sc, detail)
    assert ok is True and info["effective_max"] == 38

    # Too young
    youngster = _profile("01/01/2012", "UR")  # 14 years old
    ok, info = age_matches(youngster, detail)
    assert ok is False and "minimum" in info["reason"]


def test_age_match_degrades_gracefully_without_data():
    profile = _profile("01/01/2000", "UR")
    ok, info = age_matches(profile, JobDetail())  # no age data at all
    assert ok is True

    no_dob = _profile("", "UR")
    ok, _ = age_matches(no_dob, JobDetail(min_age=18, max_age=30))
    assert ok is True  # never block on missing DOB

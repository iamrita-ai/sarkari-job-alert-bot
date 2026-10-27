"""Tests for profile -> vacancy matching."""
from bot.matcher import detect_required_ranks, qualification_matches, title_matches
from bot.models import JobDetail, JobSummary, UserProfile


def make_profile(qualification: str, sectors: list[str]) -> UserProfile:
    return UserProfile(
        user_id=1,
        username="tester",
        full_name="Test User",
        category="OBC",
        qualification=qualification,
        sectors=sectors,
        active=True,
        created_at="",
        updated_at="",
    )


def make_job(title: str, url: str | None = None) -> JobSummary:
    slug = title.lower().replace(" ", "-")
    return JobSummary(
        job_id=f"/2026/{slug}/",
        title=title,
        url=url or f"https://www.sarkariresult.com/2026/{slug}/",
    )


def test_title_sector_matching():
    railway_fan = make_profile("graduate", ["railway"])
    rrb = make_job("Railway RRB Station Master Online Form 2026")
    lic = make_job("LIC HFL Apprentice Online Form 2026")

    assert title_matches(railway_fan, rrb) is True
    assert title_matches(railway_fan, lic) is False

    multi = make_profile("graduate", ["banking", "apprentice"])
    assert title_matches(multi, lic) is True


def test_qualification_rank_detection():
    assert 6 in detect_required_ranks("Bachelor Degree in Any Stream")
    ranks = detect_required_ranks("Candidate must be 10th Pass and hold an ITI certificate")
    assert 2 in ranks and 4 in ranks
    assert detect_required_ranks("some unrelated paragraph") == []


def test_qualification_gate():
    graduate = make_profile("graduate", ["railway"])
    tenth_pass = make_profile("tenth", ["railway"])
    degree_job = JobDetail(
        eligibility="Bachelor Degree in Any Stream from a recognised university",
        raw_text="Bachelor Degree in Any Stream",
    )

    assert qualification_matches(graduate, degree_job) is True
    assert qualification_matches(tenth_pass, degree_job) is False

    # Unknown / unparseable eligibility must not block the alert
    assert qualification_matches(tenth_pass, JobDetail(eligibility="", raw_text="")) is True

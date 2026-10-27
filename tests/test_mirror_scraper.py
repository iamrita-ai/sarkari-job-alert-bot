"""Tests for the sarkariresult.com.cm mirror parsers and Jina error detection."""
import pytest

from bot.models import JobSummary
from bot.scraper import (
    ScraperError,
    parse_listing_markdown,
    parse_mirror_detail_html,
    parse_mirror_listing_html,
)
from bot.scraper import parse_detail_markdown

FIXTURES = __import__("pathlib").Path(__file__).parent / "fixtures"


def test_mirror_listing_filters_and_dates():
    html = (FIXTURES / "mirror_listing_sample.html").read_text(encoding="utf-8")
    jobs = parse_mirror_listing_html(
        html, "https://sarkariresult.com.cm/latest-jobs/"
    )

    # 5 vacancy anchors; nav/section/social/utility links filtered out
    slugs = {j.job_id for j in jobs}
    assert slugs == {
        "/railway-rrb-station-master-2026",
        "/rrb-ntpc-inter-level-07-2026",
        "/bpsc-school-teacher-tre-4-0-2026",
        "/mpesb-group-3-sub-engineer-2026",
        "/sib-junior-officer-operations-2026",
    }
    assert not any("latest-jobs" in s or "contact" in s or "latest-posts" in s for s in slugs)

    by_id = {j.job_id: j for j in jobs}
    rrb = by_id["/railway-rrb-station-master-2026"]
    assert rrb.last_date == "25/11/2026"          # "25 November 2026" normalized
    assert rrb.url.startswith("https://sarkariresult.com.cm/")
    assert "Last Date" not in rrb.title
    # "Last Date Today" has no parseable date -> None, not a crash
    assert by_id["/mpesb-group-3-sub-engineer-2026"].last_date is None
    # Date-extended post without any date -> None
    assert by_id["/bpsc-school-teacher-tre-4-0-2026"].last_date is None
    # http scheme links are accepted and normalized
    assert by_id["/sib-junior-officer-operations-2026"].url.startswith("http://")


def test_mirror_detail_parsing():
    html = (FIXTURES / "mirror_detail_sample.html").read_text(encoding="utf-8")
    detail = parse_mirror_detail_html(
        html, "https://sarkariresult.com.cm/railway-rrb-station-master-2026/"
    )

    assert "bachelor degree" in detail.eligibility.lower()
    assert "20 years" in detail.age_limit.lower()
    assert "33 years" in detail.age_limit.lower()
    assert "important dates" in detail.important_dates.lower()
    assert detail.organization == "Railway RRB Station Master Online Form 2026"

    # Apply portal is the first external link under "Apply Online Link"
    assert detail.apply_url == "https://www.rrbapply.gov.in/#/auth/landing"
    # PDF detected even though the URL does not END in .pdf
    assert detail.notification_pdf and ".pdf" in detail.notification_pdf
    # Social/app/internal links never picked as apply URL
    assert "t.me" not in detail.apply_url
    assert "play.google" not in detail.apply_url
    assert "wp-content" not in detail.apply_url
    assert len(detail.raw_text) <= 4000

    # New v1.2 fields
    assert detail.min_age == 20 and detail.max_age == 33
    assert "500" in detail.fee and "250" in detail.fee
    assert "Pay Level 6" in detail.salary
    assert detail.image_url == (
        "https://sarkariresult.com.cm/wp-content/uploads/2026/10/station-master-2026.jpg"
    )


def test_jina_cloudfront_error_is_raised_not_empty():
    blocked = (FIXTURES / "jina_blocked_sample.md").read_text(encoding="utf-8")
    with pytest.raises(ScraperError):
        parse_listing_markdown(blocked, "https://www.sarkariresult.com/latestjob/")
    with pytest.raises(ScraperError):
        parse_detail_markdown(blocked, "https://www.sarkariresult.com/2026/x/")


def test_mirror_detail_degrades_gracefully():
    # Minimal page - parser must return empties rather than crash
    detail = parse_mirror_detail_html(
        "<html><body><div class='entry-content'><p>Some notice</p></div></body></html>",
        "https://sarkariresult.com.cm/whatever-2026/",
    )
    assert isinstance(detail.eligibility, str) and detail.eligibility == ""
    assert detail.apply_url is None and detail.notification_pdf is None
    assert JobSummary  # import sanity

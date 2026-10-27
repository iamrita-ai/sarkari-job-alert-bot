"""Offline parser tests - no network access required."""
from pathlib import Path

from bot.scraper import parse_detail_markdown, parse_listing_markdown

FIXTURES = Path(__file__).parent / "fixtures"


def test_listing_markdown_parses_jobs():
    markdown = (FIXTURES / "listing_sample.md").read_text(encoding="utf-8")
    jobs = parse_listing_markdown(markdown, "https://www.sarkariresult.com/latestjob/")

    # 8 vacancy links; navigation / section links must be filtered out
    assert len(jobs) == 8

    by_id = {job.job_id: job for job in jobs}
    isro = by_id["/2026/isro-ursc-technician-driver-04-26"]
    assert isro.last_date == "13/11/2026"
    assert "Last Date" not in isro.title
    assert isro.title.startswith("ISRO URSC Technician")

    # Listing without an inline last date -> None instead of crashing
    upsssc = by_id["/2026/upsssc-lower-pcs-26-exam-oct26"]
    assert upsssc.last_date is None
    assert upsssc.url.endswith("/")

    # Section-prefixed URLs are supported
    assert "/bihar/bpsc-tre-4-2026" in by_id
    assert "/railway/nta-ugc-net-december2026" in by_id


def test_detail_markdown_extracts_eligibility_and_links():
    markdown = (FIXTURES / "detail_sample.md").read_text(encoding="utf-8")
    detail = parse_detail_markdown(
        markdown, "https://www.sarkariresult.com/2026/rrb-station-master-08-26/"
    )

    assert "bachelor degree" in detail.eligibility.lower()
    assert "20 years" in detail.age_limit.lower()
    assert "33 years" in detail.age_limit.lower()

    # Escaped markdown hash must be restored, social links skipped
    assert detail.apply_url == "https://www.rrbapply.gov.in/#/auth/home"
    assert detail.notification_pdf is not None
    assert detail.notification_pdf.endswith(".pdf")
    assert detail.organization and "Railway RRB Station Master" in detail.organization
    assert "t.me" not in (detail.apply_url or "")
    assert len(detail.raw_text) <= 4000

"""Sarkari Result scraper.

Two transport modes are supported:

* ``html``     - direct request with a full browser header set / HTTP-2
* ``markdown`` - fallback through the r.jina.ai reader when CloudFront
                 returns 403 to the hosting provider's IP range

Parsers are pure functions so they can be unit-tested offline with saved
fixtures. Sarkari Result occasionally changes its markup - all selectors
live in this single module to make maintenance easy.
"""
from __future__ import annotations

import asyncio
import logging
import random
import re
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from bot import config
from bot.models import JobDetail, JobSummary

logger = logging.getLogger(__name__)


class ScraperError(RuntimeError):
    """Raised when a page cannot be retrieved through any transport."""


# Job detail URLs look like https://www.sarkariresult.com/2026/some-slug/
JOB_HREF_RE = re.compile(
    r"^https?://(www\.)?sarkariresult\.com/[a-z0-9\-]+/[a-z0-9\-]+/?$", re.IGNORECASE
)
# Site sections that are definitely not vacancy pages
SEGMENT_BLOCKLIST = {
    "latestjob", "results", "result", "admit-card", "answer-key", "syllabus",
    "admission", "contact", "about", "privacy-policy", "disclaimer", "page",
    "category", "tag", "author", "feed", "app", "tools", "mobile-app",
    "important-links",
}
YEAR_RE = re.compile(r"20\d{2}")
LAST_DATE_RE = re.compile(r"last date\s*:?\s*(\d{2}/\d{2}/\d{4})", re.IGNORECASE)
MD_LINK_RE = re.compile(
    r"\[([^\]]+)\]\((https?://[^)\s]+)(?:\s+\"[^\"]*\")?\)"
)
SOCIAL_HOSTS = {
    "t.me", "telegram.me", "whatsapp.com", "wa.me", "instagram.com",
    "youtube.com", "youtu.be", "x.com", "twitter.com", "facebook.com",
    "play.google.com", "apps.apple.com", "itunes.apple.com", "flaticon.com",
    "sarkariresultportal.com",
}


# --------------------------------------------------------------------- helpers
def _clean(text: str) -> str:
    return " ".join(text.split())


def _unescape_md(text: str) -> str:
    return text.replace("\\|", " ").replace("\\#", "#").replace("\\_", "_").strip()


def _is_job_link(url: str, text: str) -> bool:
    if not JOB_HREF_RE.match(url):
        return False
    segments = [s for s in urlparse(url).path.split("/") if s]
    if not segments or segments[0] in SEGMENT_BLOCKLIST:
        return False
    if len(text) < 12 or not YEAR_RE.search(text):
        return False
    return True


def _summarise(url: str, text: str) -> JobSummary | None:
    text = _clean(_unescape_md(text))
    if not _is_job_link(url, text):
        return None
    last_date = None
    if match := LAST_DATE_RE.search(text):
        last_date = match.group(1)
    # Drop the "| Last Date : .." suffix from the human readable title
    title = re.split(r"\s*[\\|]?\s*Last Date", text, flags=re.IGNORECASE)[0]
    title = _clean(title.strip(" |"))
    job_id = urlparse(url).path.rstrip("/")
    return JobSummary(job_id=job_id, title=title, url=url, last_date=last_date)


# ------------------------------------------------------------- listing parse
def parse_listing_html(html: str, base_url: str) -> list[JobSummary]:
    soup = BeautifulSoup(html, "lxml")
    container = (
        soup.select_one("#content")
        or soup.select_one("main")
        or soup.select_one("article")
        or soup.select_one(".entry-content")
        or soup
    )
    jobs: dict[str, JobSummary] = {}
    for anchor in container.select('a[href]'):
        href = urljoin(base_url, anchor.get("href", "").split("#")[0])
        text = anchor.get_text(" ", strip=True)
        summary = _summarise(href, text)
        if summary and summary.job_id not in jobs:
            jobs[summary.job_id] = summary
    return list(jobs.values())


def parse_listing_markdown(markdown: str, base_url: str) -> list[JobSummary]:
    jobs: dict[str, JobSummary] = {}
    for raw_text, raw_url in MD_LINK_RE.findall(markdown):
        href = urljoin(base_url, _unescape_md(raw_url).split("#")[0])
        summary = _summarise(href, raw_text)
        if summary and summary.job_id not in jobs:
            jobs[summary.job_id] = summary
    return list(jobs.values())


# -------------------------------------------------------------- detail parse
def _markdown_to_text_and_links(markdown: str) -> tuple[str, list[tuple[str, str]]]:
    links = [
        (_clean(_unescape_md(text)), _unescape_md(url))
        for text, url in MD_LINK_RE.findall(markdown)
    ]
    text = MD_LINK_RE.sub(lambda m: m.group(1), markdown)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)       # images
    text = text.replace("**", "").replace("##", "")
    text = re.sub(r"[#`*_>]", "", text)
    text = text.replace("\\|", " ").replace("|", " ")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines), links


def _html_to_text_and_links(html: str) -> tuple[str, list[tuple[str, str]]]:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    lines = [
        line.strip()
        for line in soup.get_text("\n").splitlines()
        if line.strip()
    ]
    links = [
        (a.get_text(" ", strip=True), a["href"])
        for a in soup.find_all("a", href=True)
    ]
    return "\n".join(lines), links


def _extract(text: str, patterns: list[str], limit: int) -> str:
    for pattern in patterns:
        if match := re.search(pattern, text, flags=re.IGNORECASE):
            return _clean(match.group(0))[:limit]
    return ""


_QUAL_LINE_RE = re.compile(
    r"bachelor|degree|10th|12th|10\+2|iti|diploma|graduat|intermediate|"
    r"high school|matric|b\.tech|b\.e\b|bba|bca|nursing|viii|8th|"
    r"master'?s?\s+degree|post[\s-]?graduat|\bmba\b|\bmca\b|\bm\.tech\b",
    re.IGNORECASE,
)


def _extract_eligibility(text: str) -> str:
    """Pick the line that actually states a qualification, not a table header."""
    lines = text.splitlines()
    candidates = [
        line for line in lines
        if re.search(r"eligib|qualification", line, re.IGNORECASE)
        and _QUAL_LINE_RE.search(line)
    ]
    if not candidates:
        candidates = [line for line in lines if _QUAL_LINE_RE.search(line)]
    if candidates:
        return _clean(candidates[0])[:600]
    return _extract(text, [r"eligibility[^\n]{0,500}"], limit=600)


def _extract_age(text: str) -> str:
    lines = text.splitlines()
    min_max = [
        line for line in lines
        if re.search(r"(?:minimum|maximum)\s*age", line, re.IGNORECASE)
    ][:2]
    if min_max:
        return " | ".join(_clean(line) for line in min_max)[:220]
    return _extract(text, [r"age limit[^\n]{0,140}"], limit=220)


def _extract_dates(text: str) -> str:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if re.search(r"important dates", line, re.IGNORECASE):
            block = " ".join(lines[index:index + 4])
            return _clean(block)[:350]
    return ""


def _pick_apply_url(links: list[tuple[str, str]]) -> tuple[str | None, str | None]:
    apply_url: str | None = None
    pdf_url: str | None = None
    external: list[tuple[str, str]] = []

    for label, href in links:
        host = (urlparse(href).hostname or "").lower().replace("www.", "")
        if href.lower().split("?")[0].endswith(".pdf"):
            pdf_url = pdf_url or href
        if not host or host.endswith("sarkariresult.com") or host in SOCIAL_HOSTS:
            continue
        external.append((label, href))

    for label, href in external:
        if re.search(r"apply|click here|online|register", label, re.IGNORECASE):
            apply_url = href
            break
    if apply_url is None and external:
        apply_url = external[0][1]
    return apply_url, pdf_url


def _build_detail(text: str, links: list[tuple[str, str]], url: str) -> JobDetail:
    organization = None
    head = "\n".join(text.splitlines()[:6])
    if match := re.search(
        r"(.+?)\s+(?:online form|recruitment|notification|exam|bharti)\b",
        head, flags=re.IGNORECASE,
    ):
        organization = _clean(match.group(1))[:120] or None

    eligibility = _extract_eligibility(text)
    age_limit = _extract_age(text)
    important_dates = _extract_dates(text)
    apply_url, pdf_url = _pick_apply_url(links)

    return JobDetail(
        eligibility=eligibility,
        age_limit=age_limit,
        important_dates=important_dates,
        organization=organization,
        apply_url=apply_url,
        notification_pdf=pdf_url,
        raw_text=text[:4000],
    )


def parse_detail_html(html: str, url: str) -> JobDetail:
    text, links = _html_to_text_and_links(html)
    return _build_detail(text, links, url)


def parse_detail_markdown(markdown: str, url: str) -> JobDetail:
    text, links = _markdown_to_text_and_links(markdown)
    return _build_detail(text, links, url)


# ------------------------------------------------------------------- scraper
class SarkariScraper:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            http2=True,
            follow_redirects=True,
            timeout=config.REQUEST_TIMEOUT,
            trust_env=True,  # honours HTTPS_PROXY if the host needs a proxy
            headers={
                "User-Agent": config.USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-IN,en;q=0.9,hi;q=0.8",
                "Referer": "https://www.sarkariresult.com/",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
            },
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _fetch_via_jina(self, url: str) -> tuple[str, str]:
        jina_url = "https://r.jina.ai/" + url
        headers = {"X-Return-Format": "markdown"}
        if config.JINA_API_KEY:
            headers["Authorization"] = f"Bearer {config.JINA_API_KEY}"
        logger.warning("Direct fetch failed, trying reader proxy for %s", url)
        response = await self._client.get(jina_url, headers=headers)
        response.raise_for_status()
        if not response.text.strip():
            raise ScraperError(f"Empty reader response for {url}")
        return "markdown", response.text

    async def fetch(self, url: str) -> tuple[str, str]:
        """Return ``(format, content)`` where format is html or markdown."""
        last_error: Exception | None = None
        for attempt in range(1, config.MAX_RETRIES + 1):
            try:
                response = await self._client.get(url)
                if response.status_code == 200 and response.text.strip():
                    return "html", response.text
                last_error = ScraperError(
                    f"HTTP {response.status_code} for {url}"
                )
                logger.warning("Attempt %d failed: %s", attempt, last_error)
            except httpx.HTTPError as exc:
                last_error = exc
                logger.warning("Attempt %d error for %s: %s", attempt, url, exc)
            await asyncio.sleep(min(2 ** attempt, 10) + random.uniform(0, 0.8))

        if config.USE_JINA_FALLBACK:
            try:
                return await self._fetch_via_jina(url)
            except httpx.HTTPError as exc:
                last_error = ScraperError(f"Reader proxy also failed: {exc}")
        raise ScraperError(f"Could not fetch {url}: {last_error}")

    async def fetch_latest_jobs(self) -> list[JobSummary]:
        merged: dict[str, JobSummary] = {}
        for listing_url in config.LISTING_URLS:
            try:
                fmt, content = await self.fetch(listing_url)
            except ScraperError:
                logger.exception("Listing fetch failed for %s", listing_url)
                continue
            if fmt == "html":
                jobs = parse_listing_html(content, listing_url)
            else:
                jobs = parse_listing_markdown(content, listing_url)
            logger.info("Fetched %d jobs from %s", len(jobs), listing_url)
            for job in jobs:
                merged.setdefault(job.job_id, job)
        return list(merged.values())

    async def fetch_job_detail(self, url: str) -> JobDetail:
        fmt, content = await self.fetch(url)
        if fmt == "html":
            return parse_detail_html(content, url)
        return parse_detail_markdown(content, url)

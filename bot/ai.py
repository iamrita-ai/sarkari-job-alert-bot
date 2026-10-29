"""Optional AI summaries (Groq, free tier) - never required, never fatal.

The bot works exactly the same without a key; with one, the long eligibility
text is turned into three plain lines (and optionally Hindi).

Free key: https://console.groq.com/keys  ->  GROQ_API_KEY=...
"""
from __future__ import annotations

import hashlib
import logging

import httpx

from bot import config

logger = logging.getLogger(__name__)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

EN_PROMPT = (
    "Summarise this Indian government job eligibility note in 2 short, simple "
    "lines for a job seeker. State who can apply, the minimum qualification "
    "and any special condition (experience, age, certificates). Plain text "
    "only, no markdown, no bullet symbols, no headings.\n\n"
)

HI_PROMPT = (
    "इस भारतीय सरकारी नौकरी के पात्रता नोटिस को 2 सरल पंक्तियों में हिंदी में "
    "समझाएँ। बताएँ कि कौन आवेदन कर सकता है, न्यूनतम योग्यता क्या है और कोई "
    "विशेष शर्त (अनुभव, आयु, प्रमाण पत्र) क्या है। केवल सादा टेक्स्ट, कोई "
    "मार्कडाउन या बुलेट नहीं।\n\n"
)

# In-memory cache: sha1(text+language) -> summary
_cache: dict[str, str] = {}


def enabled() -> bool:
    return bool(config.AI_SUMMARY_ENABLED and config.GROQ_API_KEY)


async def summarise(text: str, language: str | None = None) -> str:
    """Return a short plain-text summary (empty string when unavailable)."""
    if not enabled() or not text or not text.strip():
        return ""
    language = (language or config.AI_SUMMARY_LANGUAGE or "en").lower()
    key = hashlib.sha1(f"{language}:{text}".encode()).hexdigest()
    if key in _cache:
        return _cache[key]

    prompt = HI_PROMPT if language.startswith("hi") else EN_PROMPT
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.post(
                GROQ_URL,
                headers={
                    "Authorization": f"Bearer {config.GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": config.GROQ_MODEL,
                    "temperature": 0.2,
                    "max_tokens": 180,
                    "messages": [{"role": "user", "content": prompt + text.strip()[:4000]}],
                },
            )
            response.raise_for_status()
            data = response.json()
            summary = (data["choices"][0]["message"]["content"] or "").strip()
    except Exception as exc:  # noqa: BLE001 - AI is a bonus, never a blocker
        logger.warning("AI summary failed: %s", exc)
        return ""

    summary = " ".join(summary.split())[:400]
    if summary:
        _cache[key] = summary
    return summary


def clear_cache() -> None:
    _cache.clear()

"""Strict MarkdownV2 linter - catches unescaped reserved characters.

Telegram MarkdownV2 reserves: _ * [ ] ( ) ~ ` > # + - = | { } . ! and the
backslash. Every reserved character outside inline-code spans and link URLs
must be preceded by a backslash. A single unescaped '.' makes the whole
sendMessage/sendPhoto call fail with 400 Bad Request - exactly the bug that
broke /start in production.
"""
from bot.cards import (
    about_text,
    help_text,
    job_card,
    list_page,
    photo_caption,
    profile_card,
    saved_list_card,
    welcome_caption,
)
from bot.models import JobDetail, JobSummary, UserProfile

RESERVED = set("_*[]()~`>#+-=|{}.!\\")


def lint_markdown_v2(text: str) -> list[str]:
    """Return human-readable violations (empty list = valid).

    State machine that understands MarkdownV2 entities: *bold*, _italic_,
    __underline__, ~strike~, ||spoiler||, `code` and [label](url) links.
    Only the entity delimiters themselves are exempt; every other reserved
    character inside an entity must still be backslash-escaped.
    """
    violations: list[str] = []
    i, n = 0, len(text)
    state = "normal"
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""

        if state == "code":
            if ch == "`":
                ticks = 1
                while i + ticks < n and text[i + ticks] == "`" and ticks < 3:
                    ticks += 1
                state = "normal"
                i += ticks
                continue
            i += 1
            continue

        if ch == "\\":
            if i + 1 >= n:
                violations.append("dangling backslash at end")
                break
            i += 2
            continue

        if ch == "`":
            state = "code"
            i += 1
            continue

        if state == "normal":
            if ch == "*":
                state = "bold"
            elif ch == "_" and nxt == "_":
                state = "underline"; i += 2; continue
            elif ch == "_":
                state = "italic"
            elif ch == "~":
                state = "strike"
            elif ch == "|" and nxt == "|":
                state = "spoiler"; i += 2; continue
            elif ch == "[":
                close = text.find("](", i)
                if close == -1:
                    violations.append(f"unmatched '[' at {i}")
                else:
                    violations.extend(
                        f"link label: {v}"
                        for v in lint_markdown_v2(text[i + 1:close])
                    )
                    url_end = text.find(")", close + 2)
                    if url_end == -1:
                        violations.append("link missing closing ')'")
                        return violations
                    i = url_end + 1
                    continue
            elif ch in RESERVED:
                violations.append(
                    f"unescaped {ch!r} at {i}: ...{text[max(0, i-15):i+15]!r}"
                )
        else:  # inside an emphasis entity: only its delimiter exits
            if (
                (state == "bold" and ch == "*")
                or (state == "italic" and ch == "_")
                or (state == "underline" and ch == "_" and nxt == "_")
                or (state == "strike" and ch == "~")
                or (state == "spoiler" and ch == "|" and nxt == "|")
            ):
                if state == "underline":
                    i += 2; state = "normal"; continue
                if state == "spoiler":
                    i += 2; state = "normal"; continue
                state = "normal"
            elif ch in RESERVED:
                violations.append(
                    f"unescaped {ch!r} inside {state} at {i}: "
                    f"...{text[max(0, i-15):i+15]!r}"
                )
        i += 1

    if state == "code":
        violations.append("unterminated inline code span")
    elif state != "normal":
        violations.append(f"unterminated {state} entity")
    return violations


JOB = JobSummary("/railway-x-2026", "Railway X Online Form 2026",
                 "https://sarkariresult.com.cm/railway-x-2026/", "25/11/2026")
DETAIL = JobDetail(
    eligibility="Bachelor's Degree (Any Stream)", fee="UR: ₹500/-",
    salary="Pay Level 6", min_age=20, max_age=33,
    apply_url="https://apply.example.in/x",
    notification_pdf="https://x/a.pdf", image_url="https://x/i.jpg",
)
PROFILE = UserProfile(1, "u", "Rahul_T. 100%!", "OBC", "graduate",
                      ["railway"], "15/08/2000")
AGE_INFO = {"user_age": 26, "min_age": 20, "max_age": 33, "relaxation": 3,
            "effective_max": 36, "reason": "ok"}


def test_all_static_cards_are_valid_markdown_v2():
    samples = {
        "welcome": welcome_caption(),
        "help": help_text().replace("@<bot_username>", "@jobbot"),
        "about": about_text(),
        "job_card": job_card(JOB, DETAIL, PROFILE, AGE_INFO),
        "photo_caption": photo_caption(JOB, DETAIL, PROFILE, AGE_INFO),
        "profile": profile_card(PROFILE),
        "list_page": list_page([JOB], 0, 3, "Latest Matching Jobs"),
        "saved_list": saved_list_card([
            type("S", (), {"job_id": "/saved-x-2026", "title": "T.",
                           "url": "https://x", "last_date": "01/01/2027",
                           "reminder_date": "2026-12-31"})()
        ], 0, 1),
        "list_deep_link": list_page([JOB], 0, 3, "Latest",
                                    "https://t.me/jobbot?start=j"),
        "job_card_no_detail": job_card(JOB, None, PROFILE, None),
    }
    failures = {name: issues for name, text in samples.items()
                if (issues := lint_markdown_v2(text))}
    assert not failures, failures

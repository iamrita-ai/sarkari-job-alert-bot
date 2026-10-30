"""Optional web dashboard (FastAPI) - a phone-friendly page for the profile
and the latest vacancies.

Enable it with ``ENABLE_WEB_APP=true`` and ``WEB_APP_SECRET=<random>``
(``pip install -r requirements-web.txt``). The bot hands every user a signed
link (``/webapp``) - no login, no password database.
"""
from __future__ import annotations

import hashlib
import hmac
import logging

from bot import config
from bot.constants import (
    CATEGORIES,
    CATEGORY_MAP,
    DEGREES,
    DEGREE_MAP,
    DOCUMENTS,
    QUAL_MAP,
    SECTORS,
    STATES,
)

logger = logging.getLogger(__name__)

# FastAPI is an OPTIONAL dependency (requirements-web.txt). The module must
# still import without it, because bot/handlers.py uses sign_token().
try:  # pragma: no cover - depends on the environment
    from fastapi import FastAPI, Form, Request
    from fastapi.responses import HTMLResponse

    FASTAPI_AVAILABLE = True
except ImportError:  # pragma: no cover
    FASTAPI_AVAILABLE = False
    FastAPI = Form = Request = HTMLResponse = None  # type: ignore[assignment]

CSS = """
body{font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;background:#0f172a;
color:#e2e8f0;margin:0;padding:16px}
a{color:#7dd3fc;text-decoration:none}
.card{background:#1e293b;border-radius:14px;padding:14px;margin-bottom:12px}
h1{font-size:20px}h2{font-size:16px;margin:0 0 8px}
.muted{color:#94a3b8;font-size:13px}
.chip{display:inline-block;background:#334155;border-radius:999px;padding:3px 10px;
margin:3px 4px 3px 0;font-size:13px}
.chip.on{background:#16a34a;color:#fff}
input,select,textarea{width:100%;padding:9px;border-radius:9px;border:1px solid #334155;
background:#0b1220;color:#e2e8f0;margin:6px 0 10px;box-sizing:border-box}
button{background:#2563eb;color:#fff;border:0;border-radius:9px;padding:10px 16px;
font-size:15px;cursor:pointer}
label{display:block;font-size:13px;color:#94a3b8;margin-top:10px}
"""


def sign_token(user_id: int, secret: str) -> str:
    if not secret:
        return ""
    digest = hmac.new(secret.encode(), str(user_id).encode(), hashlib.sha256).hexdigest()
    return f"{user_id}.{digest[:32]}"


def verify_token(token: str, secret: str) -> int | None:
    if not token or not secret or "." not in token:
        return None
    raw, _, signature = token.partition(".")
    try:
        user_id = int(raw)
    except ValueError:
        return None
    expected = sign_token(user_id, secret)
    if hmac.compare_digest(expected, token):
        return user_id
    return None


def _html(text: str | None) -> str:
    """Escape text for safe use inside the dashboard HTML."""
    if text is None:
        return ""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _page(title: str, body: str) -> str:
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{title}</title><style>{CSS}</style></head><body>{body}</body></html>"
    )


def _chips(name: str, options, selected) -> str:
    out = []
    for key, label in options:
        on = " on" if key in selected else ""
        out.append(
            f"<label class='chip{on}'><input type='checkbox' name='{name}' "
            f"value='{key}' style='width:auto;display:inline' "
            f"{'checked' if on else ''}> {label}</label>"
        )
    return "".join(out)


def create_app(application):  # noqa: ANN001
    """Build the FastAPI application (optional dependency)."""
    if not FASTAPI_AVAILABLE:
        raise RuntimeError(
            "FastAPI is not installed - run: pip install -r requirements-web.txt"
        )

    api = FastAPI(title="Sarkari Job Alert", docs_url=None, redoc_url=None)
    db = application.bot_data["db"]

    async def current_user(request: Request) -> int | None:
        return verify_token(request.query_params.get("t", ""), config.WEB_APP_SECRET)

    @api.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request):
        user_id = await current_user(request)
        if user_id is None:
            return _page("Sarkari Job Alert", """
                <div class='card'><h1>Sarkari Job Alert</h1>
                <p class='muted'>Open the personal link the bot sent you
                (/webapp) to see your profile and the latest vacancies.</p></div>""")
        profile = await db.get_user(user_id)
        token = request.query_params.get("t", "")
        query = (request.query_params.get("q") or "").strip()
        state = (request.query_params.get("state") or "").strip()
        jobs = await db.search_jobs(query, limit=60)
        if state:
            filtered = []
            for job in jobs:
                detail = await db.get_job_detail(job.job_id)
                if detail and state in (detail.states or []):
                    filtered.append(job)
            jobs = filtered
        rows = []
        for job in jobs[:40]:
            date_tag = f" · {job.last_date}" if job.last_date else ""
            rows.append(
                f"<div class='card'><a href='{job.url}' target='_blank'>"
                f"{_html(job.title)}</a>"
                f"<div class='muted'>{_html(job.url.split('/')[2])}{date_tag}</div></div>"
            )
        body = [
            "<h1>Sarkari Job Alert</h1>",
            "<div class='card'><h2>Latest vacancies</h2>",
            "<form method='get'><input type='hidden' name='t' value='"
            f"{token}'>",
            "<input name='q' placeholder='Search (railway, bpsc, teacher…)' value='"
            f"{query}'>",
            "<select name='state'><option value=''>All states</option>",
        ]
        for state_def in STATES:
            sel = " selected" if state == state_def["key"] else ""
            body.append(f"<option value='{state_def['key']}'{sel}>"
                        f"{state_def['label']}</option>")
        body.append("</select><button type='submit'>Filter</button></form>")
        body.extend(rows or ["<p class='muted'>Nothing found.</p>"])
        body.append("</div>")
        if profile:
            body.append(
                "<div class='card'><h2>Your profile</h2>"
                f"<p class='muted'>{_html(profile.full_name)} · "
                f"{_html(profile.category)} · "
                f"{_html(', '.join(profile.degree_labels) or 'no degrees yet')}</p>"
                f"<a href='/profile?t={token}'>✏️ Edit profile</a> · "
                f"<a href='/saved?t={token}'>🔖 Saved jobs</a></div>"
            )
        return _page("Sarkari Job Alert", "".join(body))

    @api.get("/health")
    async def health():
        """The platform health check - the dashboard replaces the tiny
        stdlib health server when it owns the port."""
        return {
            "status": "ok",
            "service": "serena-bot",
            "web_app": True,
        }

    @api.get("/profile", response_class=HTMLResponse)
    async def profile_form(request: Request):
        user_id = await current_user(request)
        if user_id is None:
            return _page("Profile", "<div class='card'>Open the link from the bot."
                                         "</div>")
        token = request.query_params.get("t", "")
        profile = await db.get_user(user_id)
        if profile is None:
            return _page("Profile", "<div class='card'>No profile yet - send "
                                     "/start in the bot.</div>")
        body = [
            "<h1>Edit profile</h1><div class='card'><form method='post'>",
            f"<input type='hidden' name='t' value='{token}'>",
            "<label>Name</label><input name='full_name' value='"
            f"{_html(profile.full_name)}'>",
            "<label>Date of birth (DD/MM/YYYY)</label><input name='dob' value='"
            f"{_html(profile.dob or '')}'>",
            "<label>Category</label><select name='category'>",
        ]
        for key, label in CATEGORIES:
            sel = " selected" if profile.category == key else ""
            body.append(f"<option value='{key}'{sel}>{label}</option>")
        body.append("</select>")
        body.append("<label>Degrees you hold</label>")
        body.append(_chips("degrees", [(d["key"], d["label"]) for d in DEGREES],
                           set(profile.degrees)))
        body.append("<label>Documents you own</label>")
        body.append(_chips("documents", [(d["key"], d["label"]) for d in DOCUMENTS],
                           set(profile.documents)))
        body.append("<label>Job sectors</label>")
        body.append(_chips("sectors", [(s["key"], s["label"]) for s in SECTORS],
                           set(profile.sectors)))
        body.append("<button type='submit'>Save profile</button></form></div>")
        return _page("Edit profile", "".join(body))

    @api.post("/profile", response_class=HTMLResponse)
    async def profile_save(
            request: Request,
            t: str = Form(""),
            full_name: str = Form(""),
            dob: str = Form(""),
            category: str = Form("UR"),
            degrees: list[str] = Form([]),
            documents: list[str] = Form([]),
            sectors: list[str] = Form([]),
    ):
        user_id = verify_token(t, config.WEB_APP_SECRET)
        if user_id is None:
            return _page("Profile", "<div class='card'>Invalid link.</div>")
        profile = await db.get_user(user_id)
        if profile is None:
            return _page("Profile", "<div class='card'>No profile yet.</div>")
        best_rank, best_key = -1, profile.qualification
        for key in degrees:
            degree = DEGREE_MAP.get(key)
            if not degree or key == "other":
                continue
            rank = QUAL_MAP[degree["qual_key"]]["rank"]
            if rank > best_rank:
                best_rank, best_key = rank, degree["qual_key"]
        await db.update_user(
            user_id,
            full_name=full_name.strip()[:64] or profile.full_name,
            dob=dob.strip() or profile.dob,
            category=category if category in CATEGORY_MAP else profile.category,
            qualification=best_key,
            degrees=degrees,
            documents=documents,
            sectors=sectors or profile.sectors,
        )
        return _page("Saved", f"<div class='card'><h2>✅ Profile saved</h2>"
                              "<a href='/?t=" + t + "'>← Back to jobs</a></div>")

    @api.get("/saved", response_class=HTMLResponse)
    async def saved_jobs(request: Request):
        user_id = await current_user(request)
        if user_id is None:
            return _page("Saved", "<div class='card'>Open the link from the bot."
                                  "</div>")
        token = request.query_params.get("t", "")
        items = await db.list_saved(user_id)
        rows = [
            f"<div class='card'><a href='{item.url}' target='_blank'>"
            f"{_html(item.title)}</a>"
            f"<div class='muted'>{_html(item.last_date or '')}</div></div>"
            for item in items
        ]
        body = ("<h1>Saved jobs</h1>" + "".join(rows or
               ["<div class='card muted'>Nothing saved yet.</div>"]) +
               f"<a href='/?t={token}'>← Back to jobs</a>")
        return _page("Saved jobs", body)

    return api


def start_web_app(application) -> None:  # noqa: ANN001
    """Run the dashboard in a background thread (uvicorn)."""
    import threading

    import uvicorn

    api = create_app(application)

    class _Server(uvicorn.Server):
        def install_signal_handlers(self) -> None:  # pragma: no cover
            return

    port = config.WEB_APP_PORT or config.PORT
    config_ = uvicorn.Config(api, host="0.0.0.0", port=port,
                             log_level="warning")
    server = _Server(config_)
    thread = threading.Thread(target=server.run, daemon=True,
                              name="sarkari-webapp")
    thread.start()
    logger.info("Web dashboard running on port %s", port)

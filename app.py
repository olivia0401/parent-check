# Flask app for 爸妈求证 (Parent Check) - CS50x final project.
#
# Language is kept in the session and switched with ?lang=zh / ?lang=en. All
# the actual wording lives in translations.py - the DB only ever stores
# language-neutral codes, so old history entries still render correctly if you
# switch language later.

import os
import secrets
import sqlite3
import time
from collections import deque
from contextlib import closing
from datetime import datetime

from flask import Flask, redirect, render_template, request, session, url_for

from fetch_url import fetch_article, is_url
from helpers import analyze_content, build_view
from regions import current_region, current_region_code
from translations import TRANSLATIONS

app = Flask(__name__)
# In production (Render sets RENDER) a missing SECRET_KEY is a hard error -
# locally we just fall back to a dev key.
_secret = os.environ.get("SECRET_KEY")
if not _secret:
    if os.environ.get("RENDER"):
        raise RuntimeError("SECRET_KEY must be set in production")
    _secret = "dev-only-key-not-for-production"
app.secret_key = _secret

# SameSite=Lax also helps with CSRF (cookie isn't sent on cross-site POSTs).
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=bool(os.environ.get("RENDER")),
)

DB_PATH = os.path.join(os.path.dirname(__file__), "parent_check.db")

MAX_CONTENT = 5000  # cap on submitted text length

# Crude in-memory rate limit per IP. Resets on restart and only works per
# worker - good enough for one gunicorn worker, not for a real multi-worker
# setup (would need Redis or a proxy-level limiter).
RATE_LIMIT = 30
RATE_WINDOW = 60
_rate_hits = {}  # ip -> deque of timestamps

# source options shown on the home page form (labels live in translations.py)
SOURCE_CODES = ["health_article", "supplement_ad", "suspicious_msg", "other"]


def get_db():
    """Open a connection to the SQLite database with row access by column name."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create the table from schema.sql if it does not exist yet."""
    schema = os.path.join(os.path.dirname(__file__), "schema.sql")
    with open(schema, "r", encoding="utf-8") as f:
        sql = f.read()
    with closing(get_db()) as conn:
        conn.executescript(sql)
        conn.commit()


# Run on import, not just __main__ - gunicorn never executes the block below.
init_db()

# Optional Gemini step. Stays off (None) unless GEMINI_API_KEY is set, in which
# case the app just runs on the rule-based checks like before.
_llm = None
_rag_zh = None
_rag_en = None


def _init_ai():
    """Set up the Gemini client and the zh/en knowledge bases, if configured."""
    global _llm, _rag_zh, _rag_en
    try:
        from ai.llm_client import LLMClient
        from ai.rag_engine import ScamRAGEngine

        _llm = LLMClient()
        if not _llm.available:
            return

        data_dir = os.path.dirname(__file__)
        _rag_zh = ScamRAGEngine(DB_PATH, _llm, "zh")
        _rag_en = ScamRAGEngine(DB_PATH, _llm, "en")

        # only does anything the first time - table stays populated after
        _rag_zh.seed_if_empty(os.path.join(data_dir, "data", "scams_zh.json"))
        _rag_en.seed_if_empty(os.path.join(data_dir, "data", "scams_en.json"))
    except Exception as e:
        app.logger.warning("AI init failed (continuing without AI): %s", e)


_init_ai()


def current_lang():
    """Return the active language code, defaulting to Chinese."""
    return session.get("lang", "zh")


def current_uid():
    """Random per-browser id stored in the session cookie, so each visitor
    only ever sees their own history. No accounts, no names."""
    if "uid" not in session:
        session.permanent = True
        session["uid"] = secrets.token_hex(16)
    return session["uid"]


def csrf_token():
    """A per-session token used to protect our POST forms against CSRF."""
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return session["csrf"]


@app.before_request
def remember_language():
    """If the request asks to switch language (?lang=...), store the choice."""
    lang = request.args.get("lang")
    if lang in TRANSLATIONS:
        session["lang"] = lang


@app.before_request
def rate_limit():
    """Throttle POSTs per client IP to deter batch abuse of the service."""
    if request.method != "POST":
        return None
    fwd = request.headers.get("X-Forwarded-For", request.remote_addr) or "?"
    ip = fwd.split(",")[0].strip()
    now = time.time()
    if len(_rate_hits) > 5000:  # bound memory
        _rate_hits.clear()
    hits = _rate_hits.setdefault(ip, deque())
    while hits and now - hits[0] > RATE_WINDOW:
        hits.popleft()
    if len(hits) >= RATE_LIMIT:
        app.logger.warning("rate limit hit for %s", ip)
        return "Too many requests, please slow down.", 429
    hits.append(now)
    return None


@app.before_request
def csrf_protect():
    """Reject POSTs whose CSRF token doesn't match the session's."""
    if request.method == "POST":
        sent = request.form.get("csrf_token", "")
        if not sent or sent != session.get("csrf"):
            return "Bad request (invalid CSRF token).", 400


@app.context_processor
def inject_translations():
    """Make `t`, `lang`, region config and the CSRF token available everywhere."""
    lang = current_lang()
    return {
        "t": TRANSLATIONS[lang],
        "lang": lang,
        "region": current_region(),
        "region_code": current_region_code(),
        "csrf_token": csrf_token(),
    }


@app.route("/")
def index():
    """Home page with the input form."""
    return render_template("index.html", sources=SOURCE_CODES)


@app.route("/check", methods=["POST"])
def check():
    """Analyze submitted text, store the result, and show the result page."""
    content = (request.form.get("content") or "").strip()[:MAX_CONTENT]
    source = request.form.get("source") or "other"
    if source not in SOURCE_CODES:  # only accept known source codes
        source = "other"

    if not content:
        return redirect(url_for("index"))

    # If the user pasted a URL, fetch the article text first.
    fetched_title = ""
    if is_url(content):
        t_lang = TRANSLATIONS[current_lang()]
        fetch = fetch_article(content)
        if fetch["ok"]:
            fetched_title = fetch.get("title", "")
            content = fetch["text"]
        else:
            error_key = {
                "timeout":    "url_error_timeout",
                "no_content": "url_error_no_content",
                "unsafe_url": "url_error_unsafe",
            }.get(fetch["error"], "url_error_generic")
            return render_template(
                "index.html",
                sources=SOURCE_CODES,
                url_error=t_lang[error_key],
                prefill=request.form.get("content", ""),
            )

    result = analyze_content(content, source)

    # Optional second opinion from Gemini. Stays None if it's not configured
    # or anything goes wrong - the rule-based result is used as-is then.
    lang = current_lang()
    ai_result = None
    if _llm and _llm.available:
        from ai import agent as ai_agent
        rag = _rag_zh if lang == "zh" else _rag_en
        ai_result = ai_agent.analyze(content, lang, result["risk"], _llm, rag)

    if ai_result:
        # can only push the risk level up, never down
        result["risk"] = ai_result["ai_risk"]

    # Store the verdict/category/matched signals, but not the original text -
    # it might contain personal info the user pasted in.
    with closing(get_db()) as conn:
        cur = conn.execute(
            """INSERT INTO checks
               (created_at, source, risk, category, reasons, helpful, user_token)
               VALUES (?, ?, ?, ?, ?, NULL, ?)""",
            (
                datetime.now().strftime("%Y-%m-%d %H:%M"),
                source,
                result["risk"],
                result["category"],
                "\n".join(result["reasons"]),
                current_uid(),
            ),
        )
        conn.commit()
        check_id = cur.lastrowid

    # log the verdict for debugging, never the text someone submitted
    app.logger.info(
        "check verdict=%s category=%s source=%s ai=%s",
        result["risk"],
        result["category"],
        source,
        "yes" if ai_result else "no",
    )

    t = TRANSLATIONS[lang]
    view = build_view(t, result["risk"], result["category"], result["reasons"], source)

    return render_template(
        "result.html",
        check_id=check_id,
        source=source,
        risk=result["risk"],
        category=result["category"],
        reasons=view["reasons"],
        summary=view["summary"],
        advice=view["advice"],
        child_message=view["child_message"],
        ai_reason=ai_result["reason"] if ai_result else "",
        ai_advice=ai_result["advice"] if ai_result else "",
        actions=ai_result["actions"] if ai_result else [],
        emergency_number=current_region()["hotline"],
        fetched_title=fetched_title,
    )


@app.route("/history")
def history():
    """Show all past checks, newest first."""
    with closing(get_db()) as conn:
        rows = conn.execute(
            "SELECT id, created_at, source, risk FROM checks WHERE user_token = ? ORDER BY id DESC",
            (current_uid(),),
        ).fetchall()
    return render_template("history.html", rows=rows)


@app.route("/history/<int:check_id>")
def detail(check_id):
    """Show the full detail of one past check, rendered in the current language."""
    with closing(get_db()) as conn:
        row = conn.execute(
            "SELECT * FROM checks WHERE id = ? AND user_token = ?",
            (check_id, current_uid()),
        ).fetchone()
    if row is None:
        return redirect(url_for("history"))

    reasons = row["reasons"].split("\n") if row["reasons"] else []
    t = TRANSLATIONS[current_lang()]
    view = build_view(t, row["risk"], row["category"], reasons, row["source"])

    return render_template(
        "detail.html",
        row=row,
        reasons=view["reasons"],
        summary=view["summary"],
        advice=view["advice"],
        child_message=view["child_message"],
    )


@app.route("/history/clear", methods=["POST"])
def clear_history():
    """Delete this browser's saved history from the server."""
    with closing(get_db()) as conn:
        conn.execute("DELETE FROM checks WHERE user_token = ?", (current_uid(),))
        conn.commit()
    return redirect(url_for("history"))


@app.route("/feedback/<int:check_id>", methods=["POST"])
def feedback(check_id):
    """Record whether a past check was helpful."""
    value = 1 if request.form.get("helpful") == "yes" else 0
    with closing(get_db()) as conn:
        conn.execute(
            "UPDATE checks SET helpful = ? WHERE id = ? AND user_token = ?",
            (value, check_id, current_uid()),
        )
        conn.commit()
    return redirect(url_for("detail", check_id=check_id))


@app.route("/about")
def about():
    """Scope and disclaimer page."""
    return render_template("about.html")


@app.route("/privacy")
def privacy():
    """Plain-language, region-aware privacy policy."""
    return render_template("privacy.html")


if __name__ == "__main__":
    init_db()
    app.run(debug=True)

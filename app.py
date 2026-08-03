# Flask app for 爸妈求证 (Parent Check) - CS50x final project.
#
# Language is kept in the session and switched with ?lang=zh / ?lang=en. All
# the actual wording lives in translations.py - the DB only ever stores
# language-neutral codes, so old history entries still render correctly if you
# switch language later.

import os
import secrets

from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from flask_cors import CORS

import db
import observability
import ocr
import repo
from fetch_url import fetch_article, is_url
from helpers import analyze_content, build_view
from ratelimit import RateLimiter
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

# Structured logging + tracing + Prometheus /metrics (degrades if libs absent).
observability.setup(app, db.engine)

# SameSite=Lax also helps with CSRF (cookie isn't sent on cross-site POSTs).
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=bool(os.environ.get("RENDER")),
)

# The Next.js frontend runs on its own origin and calls /api/*. Allow just
# that origin (set FRONTEND_ORIGIN in production; defaults to the dev server).
FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "http://localhost:3000")
CORS(app, resources={r"/api/*": {"origins": FRONTEND_ORIGIN}})

MAX_CONTENT = 5000  # cap on submitted text length

# Rate limit per IP, enforced across all workers via Redis (falls back to an
# in-process window if REDIS_URL is unset/unreachable - see ratelimit.py).
RATE_LIMIT = 30
RATE_WINDOW = 60
_limiter = RateLimiter(RATE_LIMIT, RATE_WINDOW)

# source options shown on the home page form (labels live in translations.py)
SOURCE_CODES = ["health_article", "supplement_ad", "suspicious_msg", "other"]


# Run on import, not just __main__ - gunicorn never executes the block below.
# Enables pgvector and creates tables/indexes if they don't exist yet.
db.init_db()

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
        _rag_zh = ScamRAGEngine(_llm, "zh")
        _rag_en = ScamRAGEngine(_llm, "en")

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
    if not _limiter.allow(ip):
        app.logger.warning("rate limit hit for %s", ip)
        return "Too many requests, please slow down.", 429
    return None


@app.before_request
def csrf_protect():
    """Reject POSTs whose CSRF token doesn't match the session's."""
    if request.method == "POST":
        # The JSON API is stateless and cross-origin (no cookies, no session),
        # so the form CSRF token doesn't apply. It's guarded instead by the
        # CORS allow-list above and the per-IP rate limit below.
        if request.path.startswith("/api/"):
            return None
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
        # Public base URL for absolute og:/twitter: links (empty in local dev).
        "site_url": os.environ.get("SITE_URL", "").rstrip("/"),
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

    return _render_check(content, source, fetched_title)


def _render_check(content, source, fetched_title="", ocr_text=""):
    """
    Shared core for the HTML routes: run the pipeline on `content`, store the
    verdict and render the result page. Used by /check (text / URL) and
    /check-image (screenshot OCR), so they behave identically: rule engine ->
    optional LangGraph AI second opinion (raises risk only) -> stored result.
    `ocr_text` is shown on the result page when the content came from an image.
    """
    result = analyze_content(content, source)

    # Optional second opinion from Gemini. Stays None if it's not configured
    # or anything goes wrong - the rule-based result is used as-is then.
    lang = current_lang()
    ai_result = None
    if _llm and _llm.available:
        # LangGraph state-machine agent; prompt/parse helpers live in agent.py.
        from ai import agent_graph as ai_agent
        rag = _rag_zh if lang == "zh" else _rag_en
        ai_result = ai_agent.analyze(content, lang, result["risk"], _llm, rag)

    if ai_result:
        # can only push the risk level up, never down
        result["risk"] = ai_result["ai_risk"]

    # Store the verdict/category/matched signals, but not the original text -
    # it might contain personal info the user pasted in.
    check_id = repo.create_check(
        source=source,
        risk=result["risk"],
        category=result["category"],
        reasons=result["reasons"],
        user_token=current_uid(),
    )

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
        ocr_text=ocr_text,
    )


@app.route("/check-image", methods=["POST"])
def check_image():
    """
    OCR an uploaded screenshot, then run the exact same check as /check.

    Mirrors the URL flow: just as a pasted link is fetched to text before
    analysis, an uploaded image is OCR'd to text first. On any OCR failure it
    re-renders the home page with a friendly message (same slot as url_error).
    """
    source = request.form.get("source") or "suspicious_msg"
    if source not in SOURCE_CODES:
        source = "suspicious_msg"

    file = request.files.get("image")
    if file is None or not file.filename:
        return redirect(url_for("index"))

    image_bytes = file.read(ocr.MAX_BYTES + 1)
    ocr_result = ocr.extract_text(image_bytes, file.mimetype, _llm)
    if not ocr_result["ok"]:
        error_key = {
            "unsupported": "image_error_unsupported",
            "too_large":   "image_error_too_large",
            "no_text":     "image_error_no_text",
        }.get(ocr_result["error"], "image_error_failed")
        return render_template(
            "index.html",
            sources=SOURCE_CODES,
            url_error=TRANSLATIONS[current_lang()][error_key],
        )

    content = ocr_result["text"].strip()[:MAX_CONTENT]
    app.logger.info(
        "check-image ocr_engine=%s chars=%d", ocr_result["engine"], len(content)
    )
    return _render_check(content, source, ocr_text=content)


def _analyze_json(content, source, lang, fetched_title=""):
    """
    Shared core for the JSON API: run the pipeline on `content` and return the
    verdict as a Flask JSON response. Used by both /api/check (text / URL) and
    /api/check-image (screenshot OCR), so they stay behaviourally identical:
    rule engine -> optional LangGraph AI second opinion (raises risk only) ->
    view builder.
    """
    result = analyze_content(content, source)

    ai_result = None
    if _llm and _llm.available:
        from ai import agent_graph as ai_agent
        rag = _rag_zh if lang == "zh" else _rag_en
        ai_result = ai_agent.analyze(content, lang, result["risk"], _llm, rag)
    if ai_result:
        result["risk"] = ai_result["ai_risk"]  # only ever raises the risk

    app.logger.info(
        "api check verdict=%s category=%s source=%s ai=%s",
        result["risk"], result["category"], source, "yes" if ai_result else "no",
    )

    t = TRANSLATIONS[lang]
    view = build_view(t, result["risk"], result["category"], result["reasons"], source)

    return jsonify({
        "risk": result["risk"],
        "category": result["category"],
        "reasons": view["reasons"],
        "summary": view["summary"],
        "advice": view["advice"],
        "child_message": view["child_message"],
        "ai_reason": ai_result["reason"] if ai_result else "",
        "ai_advice": ai_result["advice"] if ai_result else "",
        "ai_tools": ai_result.get("tools_called", []) if ai_result else [],
        "actions": ai_result["actions"] if ai_result else [],
        "emergency_number": current_region()["hotline"],
        "fetched_title": fetched_title,
        "used_ai": bool(ai_result),
    })


@app.route("/api/check", methods=["POST"])
def api_check():
    """
    JSON API consumed by the Next.js frontend.

    Stateless by design: it analyses the submitted text and returns the verdict
    as JSON, with no session, no stored history and no CSRF token. Language and
    source come from the request body instead of the session cookie. It reuses
    the exact same pipeline as the HTML /check route: rule engine → optional
    LangGraph AI second opinion (which can only raise the risk) → view builder.
    """
    data = request.get_json(silent=True) or {}
    content = (data.get("content") or "").strip()[:MAX_CONTENT]
    source = data.get("source") or "other"
    if source not in SOURCE_CODES:
        source = "other"
    lang = data.get("lang") if data.get("lang") in TRANSLATIONS else "zh"

    if not content:
        return jsonify({"error": "empty_content"}), 400

    # If the user pasted a URL, fetch the article text first (same as /check).
    fetched_title = ""
    if is_url(content):
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
            return jsonify({"error": "url_fetch_failed",
                            "message": TRANSLATIONS[lang][error_key]}), 400

    return _analyze_json(content, source, lang, fetched_title)


@app.route("/api/check-image", methods=["POST"])
def api_check_image():
    """
    JSON API for screenshot checks, consumed by the Next.js frontend.

    The user uploads an image (multipart/form-data) of a suspicious message,
    email or ad; we OCR the text out of it, then run the exact same pipeline as
    /api/check. This mirrors how a pasted URL is fetched to text before
    analysis - the image is just another way to arrive at `content`.
    """
    source = request.form.get("source") or "suspicious_msg"
    if source not in SOURCE_CODES:
        source = "suspicious_msg"
    req_lang = request.form.get("lang")
    lang = req_lang if req_lang in TRANSLATIONS else "zh"

    file = request.files.get("image")
    if file is None or not file.filename:
        return jsonify({"error": "empty_image"}), 400

    # Read at most one byte past the cap - enough for ocr.extract_text to reject
    # oversized uploads without pulling a huge file fully into memory.
    image_bytes = file.read(ocr.MAX_BYTES + 1)
    ocr_result = ocr.extract_text(image_bytes, file.mimetype, _llm)
    if not ocr_result["ok"]:
        error_key = {
            "unsupported": "image_error_unsupported",
            "too_large":   "image_error_too_large",
            "no_text":     "image_error_no_text",
        }.get(ocr_result["error"], "image_error_failed")
        return jsonify({"error": "image_ocr_failed",
                        "message": TRANSLATIONS[lang][error_key]}), 400

    content = ocr_result["text"].strip()[:MAX_CONTENT]
    app.logger.info(
        "api check-image ocr_engine=%s chars=%d", ocr_result["engine"], len(content)
    )
    return _analyze_json(content, source, lang)


@app.route("/history")
def history():
    """Show all past checks, newest first."""
    rows = repo.list_checks(current_uid())
    return render_template("history.html", rows=rows)


@app.route("/history/<int:check_id>")
def detail(check_id):
    """Show the full detail of one past check, rendered in the current language."""
    row = repo.get_check(check_id, current_uid())
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
    repo.clear_history(current_uid())
    return redirect(url_for("history"))


@app.route("/feedback/<int:check_id>", methods=["POST"])
def feedback(check_id):
    """Record whether a past check was helpful."""
    value = 1 if request.form.get("helpful") == "yes" else 0
    repo.set_feedback(check_id, current_uid(), value)
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
    db.init_db()
    app.run(debug=True)

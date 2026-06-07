# app.py
# Flask web application for "爸妈求证" (Parent Check).
# CS50x final project. Covers Week 6 (Python), 7 (SQL), 8 (HTML/CSS), 9 (Flask).
#
# Bilingual (Chinese / English): the chosen language is kept in the session and
# can be switched with ?lang=zh / ?lang=en. All wording lives in translations.py;
# the database only stores language-neutral codes.
#
# Routes:
#   GET  /              home + input form
#   POST /check         analyze the submitted text, save it, show the result
#   GET  /history       list of past checks
#   GET  /history/<id>  detail of one past check
#   POST /feedback/<id> record whether a past check was helpful
#   GET  /about         scope / disclaimer page

import os
import secrets
import sqlite3
from datetime import datetime

from flask import Flask, redirect, render_template, request, session, url_for

from helpers import analyze_content, build_view
from regions import current_region, current_region_code
from translations import TRANSLATIONS

app = Flask(__name__)
# In production (Render) the secret key is supplied via an environment variable;
# the fallback is only for local development.
app.secret_key = os.environ.get("SECRET_KEY", "parent-check-dev-key")

# Session-cookie hardening. SameSite=Lax also mitigates CSRF on our POST forms
# (the cookie isn't sent on cross-site POSTs). Secure is enabled in production
# (HTTPS); local dev over http has no SECRET_KEY set, so it stays off there.
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=bool(os.environ.get("SECRET_KEY")),
)

DB_PATH = os.path.join(os.path.dirname(__file__), "parent_check.db")

# Cap on submitted text — prevents oversized requests and keeps the DB tidy.
MAX_CONTENT = 5000

# Content-source codes shown on the form (labels come from translations.py).
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
    conn = get_db()
    conn.executescript(sql)
    conn.commit()
    conn.close()


# Make sure the table exists as soon as the module is imported. This matters in
# production: Render runs the app with gunicorn, which never executes the
# __main__ block below, so we cannot rely on that to create the database.
init_db()


def current_lang():
    """Return the active language code, defaulting to Chinese."""
    return session.get("lang", "zh")


def current_uid():
    """An anonymous per-browser id (kept in the signed session cookie) so each
    visitor only ever sees their own history. No name or account is involved."""
    if "uid" not in session:
        session.permanent = True
        session["uid"] = secrets.token_hex(16)
    return session["uid"]


@app.before_request
def remember_language():
    """If the request asks to switch language (?lang=...), store the choice."""
    lang = request.args.get("lang")
    if lang in TRANSLATIONS:
        session["lang"] = lang


@app.context_processor
def inject_translations():
    """Make `t`, `lang` and the region config available in every template."""
    lang = current_lang()
    return {
        "t": TRANSLATIONS[lang],
        "lang": lang,
        "region": current_region(),
        "region_code": current_region_code(),
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

    if not content:
        return redirect(url_for("index"))

    result = analyze_content(content, source)

    # Save this check to the database (Week 7: INSERT with parameters).
    # Data minimisation: we store the verdict, category, matched signals and time
    # — but NOT the original text the user pasted, which may contain personal data.
    conn = get_db()
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
    conn.close()

    # Turn the stored codes into words in the current language.
    t = TRANSLATIONS[current_lang()]
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
    )


@app.route("/history")
def history():
    """Show all past checks, newest first."""
    conn = get_db()
    rows = conn.execute(
        "SELECT id, created_at, source, risk FROM checks WHERE user_token = ? ORDER BY id DESC",
        (current_uid(),),
    ).fetchall()
    conn.close()
    return render_template("history.html", rows=rows)


@app.route("/history/<int:check_id>")
def detail(check_id):
    """Show the full detail of one past check, rendered in the current language."""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM checks WHERE id = ? AND user_token = ?", (check_id, current_uid())
    ).fetchone()
    conn.close()
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


@app.route("/feedback/<int:check_id>", methods=["POST"])
def feedback(check_id):
    """Record whether a past check was helpful (a small learning loop)."""
    value = 1 if request.form.get("helpful") == "yes" else 0
    conn = get_db()
    conn.execute(
        "UPDATE checks SET helpful = ? WHERE id = ? AND user_token = ?",
        (value, check_id, current_uid()),
    )
    conn.commit()
    conn.close()
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

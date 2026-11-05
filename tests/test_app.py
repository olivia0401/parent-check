# run with: python -m pytest -q

import pytest

import app as app_module
from helpers import analyze_content

# judgement logic


def risk(text, source="other"):
    return analyze_content(text, source)["risk"]


def test_scam_is_danger():
    assert risk("点击链接输入验证码并转账", "suspicious_msg") == "danger"


def test_uk_scam_url_is_danger():
    assert (
        risk("Royal Mail: pay at http://royalmail-redelivery.com", "suspicious_msg")
        == "danger"
    )


def test_impersonation_without_keywords_is_danger():
    # caught by the semantic layer, not by a single keyword
    assert (
        risk("妈，我换了新号码，急用，先帮我打一点过来", "suspicious_msg") == "danger"
    )


def test_health_rumour_is_caution():
    assert risk("这款保健品包治百病，无副作用", "supplement_ad") == "caution"


def test_benign_is_ok():
    assert risk("月季花叶子发黄怎么办？") == "ok"


def test_no_false_positive_pin_inside_word():
    # "pin" must not match inside "shopping" (word-boundary matching)
    assert risk("I love shopping for clothes at the weekend") == "ok"


def test_no_false_positive_remote_control():
    assert risk("I bought a new remote control for the TV") == "ok"


def test_never_returns_safe():
    # the only verdicts are ok / caution / danger — never "safe"
    for text in ["hello", "转账验证码", "保健品根治"]:
        assert analyze_content(text)["risk"] in {"ok", "caution", "danger"}


# routes


@pytest.fixture
def client():
    return app_module.app.test_client()


def test_home_ok(client):
    assert client.get("/").status_code == 200


def test_privacy_ok(client):
    assert client.get("/privacy").status_code == 200


def test_check_requires_csrf(client):
    # POST without a CSRF token is rejected
    r = client.post("/check", data={"content": "x", "source": "other"})
    assert r.status_code == 400


def test_check_with_csrf_works(client):
    with client.session_transaction() as s:
        s["csrf"] = "tok"
    r = client.post(
        "/check",
        data={
            "content": "点击链接验证码转账",
            "source": "suspicious_msg",
            "csrf_token": "tok",
        },
    )
    assert r.status_code == 200


def test_history_is_isolated_per_browser():
    a = app_module.app.test_client()
    b = app_module.app.test_client()
    with a.session_transaction() as s:
        s["csrf"] = "tok"
    a.post(
        "/check",
        data={"content": "转账验证码", "source": "suspicious_msg", "csrf_token": "tok"},
    )
    # b is a different browser/session → must not see a's record
    assert b.get("/history/1").status_code == 404


@pytest.mark.parametrize("lang", ["zh", "en"])
@pytest.mark.parametrize("text", ["转账验证码", "月季花叶子发黄怎么办？"])
def test_owner_can_open_saved_history_and_submit_feedback(client, lang, text):
    # Use the real ORM record: an anonymous visitor's redirect would miss the bug.
    import repo

    client.get(f"/history?lang={lang}")
    with client.session_transaction() as session:
        token = session["uid"]
        session["csrf"] = "history-test-token"
    verdict = analyze_content(text, "other")
    check_id = repo.create_check(
        "other", verdict["risk"], verdict["category"], verdict["reasons"], token
    )
    response = client.get(f"/history/{check_id}")
    assert response.status_code == 200
    assert f"/feedback/{check_id}".encode() in response.data

    outsider = app_module.app.test_client()
    assert outsider.get(f"/history/{check_id}").status_code == 404
    response = client.post(
        f"/feedback/{check_id}",
        data={"helpful": "yes", "csrf_token": "history-test-token"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert repo.get_check(check_id, token).helpful == 1

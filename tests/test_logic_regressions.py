"""Cross-module regressions reproduced by the repository review."""

import io
import json
import time
from types import SimpleNamespace

import pytest
from PIL import Image, PngImagePlugin

import app as app_module
import blocklist
import ocr
import semantic
from ai import agent_graph, llm_trace, tools
from ai.agent import build_analysis_prompt
from ai.verifier import build_verifier_prompt
from helpers import analyze_content
from ratelimit import RateLimiter
from translations import TRANSLATIONS


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(app_module, "_limiter", RateLimiter(1000, 60, fail_closed=False))
    monkeypatch.setattr(app_module, "_llm", None)
    return app_module.app.test_client()


@pytest.mark.parametrize("lang", ["zh", "en"])
def test_ai_escalation_matches_api_html_and_private_history(client, monkeypatch, lang):
    monkeypatch.setattr(app_module, "_llm", SimpleNamespace(available=True))
    monkeypatch.setattr(
        agent_graph,
        "analyze",
        lambda *args: {
            "ai_risk": "danger",
            "reason": "PRIVATE_AI_REASON",
            "advice": "PRIVATE_AI_ADVICE",
            "actions": [],
            "tools_called": [],
        },
    )
    response = client.post("/api/check", json={"content": "hello", "lang": lang})
    body = response.get_json()
    assert body["risk"] == "danger" and body["category"] == "mixed"
    assert body["summary"] == TRANSLATIONS[lang]["summary"]["mixed"]
    assert body["advice"] and TRANSLATIONS[lang]["reason_ai"] in body["reasons"]
    with client.session_transaction() as state:
        state.update(lang=lang, csrf="token")
    response = client.post("/check", data={"content": "hello", "csrf_token": "token"})
    assert response.status_code == 200 and b"PRIVATE_AI_REASON" in response.data
    with client.session_transaction() as state:
        owner = state["uid"]
    row = app_module.repo.list_checks(owner)[0]
    assert row.category == "mixed" and row.risk == "danger"
    assert row.reasons == "ai_escalation"
    detail = client.get(f"/history/{row.id}")
    assert TRANSLATIONS[lang]["reason_ai"] in detail.get_data(as_text=True)
    assert b"PRIVATE_AI_REASON" not in detail.data  # no free-form personal AI text stored


def test_ai_cannot_lower_the_deterministic_floor(client, monkeypatch):
    monkeypatch.setattr(app_module, "_llm", SimpleNamespace(available=True))
    monkeypatch.setattr(
        agent_graph,
        "analyze",
        lambda *args: {
            "ai_risk": "ok",
            "reason": "",
            "advice": "",
            "actions": [],
        },
    )
    assert client.post("/api/check", json={"content": "转账验证码"}).get_json()["risk"] == "danger"


@pytest.mark.parametrize("route", ["/api/check", "/check"])
def test_original_and_redirect_urls_survive_a_benign_body(client, monkeypatch, route):
    monkeypatch.setattr(
        app_module,
        "fetch_article",
        lambda url: {
            "ok": True,
            "text": "A pleasant article about growing flowers in the garden.",
            "title": "Garden",
            "urls": [url, "https://hmrc-refund.net:443/article"],
        },
    )
    if route == "/check":
        with client.session_transaction() as state:
            state["csrf"] = "token"
        response = client.post(
            route, data={"content": "https://example.com/", "csrf_token": "token"}
        )
        with client.session_transaction() as state:
            row = app_module.repo.list_checks(state["uid"])[0]
        assert row.risk == "danger" and "hmrc-refund.net" in row.reasons
    else:
        response = client.post(route, json={"content": "https://example.com/"})
        assert response.get_json()["risk"] == "danger"
    assert response.status_code == 200


@pytest.mark.parametrize("suffix", ["", ":443", ".", ":443?x=y"])
def test_blocklisted_host_normalizes_ports_and_trailing_dot(suffix):
    score, reasons = blocklist.check(f"See https://hmrc-refund.net{suffix}/")
    assert score == 3 and reasons == ["hmrc-refund.net"]


def test_subdomain_match_has_a_domain_boundary():
    assert blocklist.check("https://login.hmrc-refund.net/")[0] == 3
    assert blocklist.check("https://nothmrc-refund.net/")[0] == 0
    assert blocklist.check("https://hmrc-refund.net.attacker.com/")[0] == 0
    assert blocklist.check('Read "https://hmrc-refund.net"')[0] == 3


def test_tld_alone_does_not_classify_a_normal_domain_as_high_risk():
    assert analyze_content("Read https://www.gov.cn/news")["risk"] == "caution"


def test_english_money_signals_have_word_boundaries():
    assert semantic.escalate("Hi mum, I urgently need my wireless headphones.")[0] == 0
    assert semantic.escalate("Hi mum, urgently wire some money.")[0] >= 3
    assert semantic.escalate("妈，新号码，急用钱请打一点过来")[0] >= 3


@pytest.mark.parametrize(
    "message",
    [
        "记住，不要把银行验证码发给任何人。",
        "请勿将密码告诉陌生人。",
        "我们周末一起吃火锅吧，记得带身份证。",
        "出门记得携带好身份证。",
    ],
)
def test_protective_notices_and_carrying_id_are_not_disclosure_requests(message):
    assert analyze_content(message)["risk"] == "ok"


@pytest.mark.parametrize(
    "message",
    [
        "不要把验证码发给任何人，但现在请发给我。",
        "记住，不要把银行验证码发给任何人。现在点击链接输入验证码并转账。",
        "记得带身份证，拍照发给我。",
        "记得带身份证，发到这里。",
        "请勿将密码告诉陌生人，登录 https://hmrc-refund.net 核实。",
    ],
)
def test_a_protective_prefix_cannot_hide_the_following_scam_request(message):
    assert analyze_content(message)["risk"] == "danger"


def test_both_agents_receive_tail_evidence_at_the_input_limit():
    content = "x" * 4987 + "TAIL_EVIDENCE"
    assert len(content) <= app_module.MAX_CONTENT
    assert "TAIL_EVIDENCE" in build_analysis_prompt(content, "en")
    assert "TAIL_EVIDENCE" in build_verifier_prompt(content, "zh", {"ai_risk": "ok"})


@pytest.mark.parametrize("lang", ["zh", "en"])
def test_region_not_language_selects_number_rules(lang):
    result = tools.execute_check_phone("Call 159", lang, region="uk")
    assert result["found"] and result["numbers"][0]["number"] == "159"


@pytest.mark.parametrize("phone", ["13800138000", "+8613800138000", "8613800138000"])
def test_china_mobile_with_or_without_country_prefix(phone):
    assert tools.classify_phone(phone, "en", region="cn") == "China mobile"


def test_each_duplicate_tool_invocation_receives_its_own_reply(monkeypatch):
    class Rag:
        def retrieve_similar(self, text, **kwargs):
            if text == "slow":
                time.sleep(0.15)
            return []

    monkeypatch.setattr(tools, "TOOL_TIMEOUT_S", 0.04)
    result = tools.run_tools_parallel(
        [
            {"name": "query_knowledge_base", "id": "first", "args": {"text": "fast"}},
            {"name": "query_knowledge_base", "id": "second", "args": {"text": "slow"}},
        ],
        Rag(),
        "en",
        "hello",
    )
    assert len(result) == 2
    assert result[0]["id"] == "first" and result[0]["response"]["found"] is False
    assert result[1]["id"] == "second" and result[1]["response"] == {"error": "timeout"}


def test_tool_error_messages_cannot_reach_the_model():
    class Rag:
        def retrieve_similar(self, *args, **kwargs):
            raise RuntimeError("PRIVATE_DATABASE_MARKER")

    result = tools.run_tools_parallel(
        [{"name": "query_knowledge_base", "args": {}}], Rag(), "en", "hi"
    )
    assert result[0]["response"] == {"error": "tool_failed"}
    assert "PRIVATE_DATABASE_MARKER" not in json.dumps(result)


@pytest.mark.parametrize("args", [None, [], {"text": []}, {"text": "x" * 5001}])
def test_tool_arguments_are_validated(args):
    result = tools.run_tools_parallel(
        [{"name": "check_phone_numbers", "args": args}], None, "en", "hi"
    )
    assert result[0]["response"] == {"error": "invalid_tool_arguments"}


def test_verifier_exception_preserves_the_analyst_escalation():
    class LLM:
        available = True

        def generate_with_tools(self, *args):
            return {"type": "text", "text": '{"risk":"CAUTION", "reason":"Analyst evidence"}'}

        def generate(self, *args, **kwargs):
            raise RuntimeError("private verifier error")

    result = agent_graph.analyze("hello", "en", "ok", LLM(), None)
    assert result["ai_risk"] == "caution" and result["reason"] == "Analyst evidence"


def test_invalid_image_never_reaches_a_provider():
    provider = SimpleNamespace(
        available=True, read_image_text=lambda *args: pytest.fail("Invalid image sent")
    )
    assert ocr.extract_text(b"not an image", "image/png", provider)["error"] == "unsupported"


def test_image_mime_pixels_and_metadata_are_checked(monkeypatch):
    image = io.BytesIO()
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("Comment", "PRIVATE_IMAGE_METADATA")
    Image.new("RGBA", (16, 16), (0, 0, 0, 0)).save(image, format="PNG", pnginfo=metadata)

    class Provider:
        available = True

        def read_image_text(self, content, mime):
            with Image.open(io.BytesIO(content)) as decoded:
                assert not decoded.info and decoded.getpixel((0, 0)) == (255, 255, 255)
            return "Extracted text"

    assert ocr.extract_text(image.getvalue(), "image/png", Provider())["ok"]
    assert ocr.extract_text(image.getvalue(), "image/jpeg", Provider())["error"] == "unsupported"
    monkeypatch.setattr(ocr, "MAX_PIXELS", 8)
    assert ocr.extract_text(image.getvalue(), "image/png", Provider())["error"] == "too_large"


def test_trace_does_not_store_user_content_by_default(monkeypatch):
    captured = {}
    observation = SimpleNamespace(update=lambda **kwargs: captured.update(kwargs), end=lambda: None)
    monkeypatch.setattr(
        llm_trace,
        "_client_or_none",
        lambda: SimpleNamespace(start_observation=lambda **kw: observation),
    )
    monkeypatch.delenv("LANGFUSE_CAPTURE_CONTENT", raising=False)
    llm_trace.log_generation("test", "PRIVATE_USER_INPUT", "PRIVATE_OUTPUT", model="test")
    assert "input" not in captured and "output" not in captured


def test_metrics_cannot_be_reached_through_a_public_proxy(client):
    assert client.get("/metrics").status_code == 200
    assert client.get("/metrics", headers={"X-Forwarded-For": "93.184.216.34"}).status_code == 404
    assert client.get("/metrics", headers={"X-Forwarded-For": "127.0.0.1"}).status_code == 404

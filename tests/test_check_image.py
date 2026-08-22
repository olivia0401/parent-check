# End-to-end tests for the screenshot path (/api/check-image), with OCR mocked.
#
# The image route is deliberately just "OCR -> the exact same pipeline as text".
# These tests lock that promise in: whatever text OCR extracts, the image route
# must return the identical verdict as pasting that same text into /api/check.
# OCR itself (Gemini vision / Azure) needs a live key and is covered separately;
# here we monkeypatch ocr.extract_text so the wiring is tested deterministically.
#
# The app initializes its isolated test database on the first request. The pure
# OCR-layer logic lives in tests/test_ocr.py and needs no DB.

import io

import pytest

import app as app_module


@pytest.fixture
def client():
    return app_module.app.test_client()


def _png_upload():
    return {"image": (io.BytesIO(b"\x89PNG\r\n\x1a\nfake"), "shot.png")}


def _mock_ocr(monkeypatch, result):
    monkeypatch.setattr(app_module.ocr, "extract_text", lambda *a, **k: result)


def _verdict_for_text(client, text, source="suspicious_msg", lang="zh"):
    r = client.post("/api/check", json={"content": text, "source": source, "lang": lang})
    assert r.status_code == 200
    return r.get_json()


@pytest.mark.parametrize(
    "text",
    [
        "您的医保账户异常，请点击链接完成认证，需要输入身份证和验证码。",  # zh scam
        "HMRC: you are due a tax refund. Verify your bank details at http://hmrc-refund.net",  # en scam
        "今晚一起去公园散步吗？",  # benign
        "这款保健品包治百病，无副作用，限时优惠。",  # health caution
    ],
)
def test_image_verdict_matches_pasted_text(client, monkeypatch, text):
    """The screenshot route must agree with the text route on the same content."""
    _mock_ocr(monkeypatch, {"ok": True, "text": text, "engine": "gemini"})
    r = client.post(
        "/api/check-image",
        data={**_png_upload(), "source": "suspicious_msg", "lang": "zh"},
        content_type="multipart/form-data",
    )
    assert r.status_code == 200
    from_image = r.get_json()
    from_text = _verdict_for_text(client, text)
    assert from_image["risk"] == from_text["risk"]
    assert from_image["category"] == from_text["category"]


def test_scam_screenshot_is_flagged(client, monkeypatch):
    scam = "【公安局】您涉嫌洗钱，请把资金转入安全账户自证清白。"
    _mock_ocr(monkeypatch, {"ok": True, "text": scam, "engine": "gemini"})
    r = client.post(
        "/api/check-image",
        data={**_png_upload(), "source": "suspicious_msg", "lang": "zh"},
        content_type="multipart/form-data",
    )
    assert r.status_code == 200
    assert r.get_json()["risk"] == "danger"


def test_empty_image_is_400(client):
    r = client.post("/api/check-image", data={"source": "suspicious_msg"},
                    content_type="multipart/form-data")
    assert r.status_code == 400
    assert r.get_json()["error"] == "empty_image"


@pytest.mark.parametrize("err", ["unsupported", "too_large", "no_text", "failed"])
def test_ocr_failure_maps_to_friendly_400(client, monkeypatch, err):
    _mock_ocr(monkeypatch, {"ok": False, "error": err})
    r = client.post(
        "/api/check-image",
        data={**_png_upload(), "source": "suspicious_msg", "lang": "zh"},
        content_type="multipart/form-data",
    )
    assert r.status_code == 400
    body = r.get_json()
    assert body["error"] == "image_ocr_failed"
    assert body["message"]  # a translated, user-facing message is present

from core import guard
from core import selectors


def test_selectors_have_core_constants():
    assert selectors.CHAT_URL.startswith("https://www.douyin.com/chat")
    assert selectors.CHAT_INPUT_SELECTOR == 'div[contenteditable="true"]'
    assert selectors.QR_CODE_SELECTOR == "#animate_qrcode_container"
    assert "操作频繁" in selectors.RISK_TEXT_MARKERS


def test_guard_uses_selectors():
    assert guard.RATE_LIMIT_KEYWORDS == selectors.RISK_TEXT_MARKERS

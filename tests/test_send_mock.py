from core import automation


class MockLocator:
    def __init__(self, count=1, box=None, text=""):
        self._count = count
        self._box = box if box is not None else {"x": 400, "y": 50, "width": 100, "height": 30}
        self._text = text
        self.first = self

    def count(self):
        return self._count

    def bounding_box(self):
        return self._box

    def is_visible(self):
        return True

    def inner_text(self):
        return self._text

    def wait_for(self, state=None, timeout=None):
        return None

    def click(self, **kwargs):
        return self

    def fill(self, value):
        return None

    def nth(self, index):
        return self


class MockPage:
    def __init__(self, input_locator=None):
        self._input = input_locator or MockLocator()
        self.keyboard = MockKeyboard()

    def locator(self, selector):
        return self._input

    def get_by_text(self, text, exact=False):
        return MockLocator(count=0)

    def get_by_placeholder(self, text, exact=False):
        return MockLocator(count=0)


class MockKeyboard:
    def press(self, key):
        return None

    def type(self, text, delay=0):
        return None


def test_send_message_dry_run_no_send(monkeypatch):
    monkeypatch.setattr(automation, "detect_rate_limit", lambda page: None)
    monkeypatch.setattr(automation, "_type_and_send", lambda page, box, text: None)
    status, why = automation._send_message(MockPage(), "🔥", dry_run=True)
    assert status == "ok" and why == "dry-run"


def test_send_message_success_when_input_cleared(monkeypatch):
    monkeypatch.setattr(automation, "detect_rate_limit", lambda page: None)
    monkeypatch.setattr(automation, "_type_and_send", lambda page, box, text: True)
    monkeypatch.setattr(automation, "_wait_input_cleared", lambda box, text, wait=8: True)
    status, _ = automation._send_message(MockPage(), "🔥", dry_run=False)
    assert status == "ok"


def test_send_message_failed_on_rate_limit(monkeypatch):
    monkeypatch.setattr(automation, "detect_rate_limit", lambda page: "安全验证")
    status, why = automation._send_message(MockPage(), "🔥", dry_run=False)
    assert status == "failed" and why == "发送前检测到验证提示"


def test_send_message_uncertain_when_input_stays(monkeypatch):
    monkeypatch.setattr(automation, "detect_rate_limit", lambda page: None)
    monkeypatch.setattr(automation, "_type_and_send", lambda page, box, text: True)
    monkeypatch.setattr(automation, "_wait_input_cleared", lambda box, text, wait=8: False)
    status, why = automation._send_message(MockPage(), "🔥", dry_run=False)
    assert status == "uncertain"
    assert "未清空" in why


def test_send_to_contact_failed_when_locate_fails(monkeypatch):
    monkeypatch.setattr(automation, "_locate_contact", lambda page, name: False)
    status, _ = automation.send_to_contact(MockPage(), "甲", "🔥", dry_run=False)
    assert status == "failed"


def test_send_consumer_maps_result_and_risk(monkeypatch):
    monkeypatch.setattr(automation, "send_to_contact", lambda page, name, text, dry: ("failed", "发送失败"))
    monkeypatch.setattr(automation, "detect_rate_limit", lambda page: "操作频繁")
    monkeypatch.setattr(
        automation, "ledger",
        type("FakeLedger", (), {
            "confirm_join": lambda *a, **k: None,
            "update_send_result": lambda *a, **k: None,
            "mark_no_consumer_conversation": lambda *a, **k: None,
        })(),
    )
    result = {"ok": [], "failed": [], "uncertain": [], "skipped": [], "rate_limited": False, "risk_detected": False}
    automation._send_consumer(MockPage(), {"display_name": "甲", "channel": "consumer"}, "🔥", False, result, "default")
    assert result["failed"] and result["rate_limited"] is True and result["risk_detected"] is True


def test_risk_marker_detected():
    from core.guard import detect_rate_limit

    class RiskPage:
        def get_by_text(self, text, exact=False):
            return MockLocator(count=1 if text == "安全验证" else 0)

    assert detect_rate_limit(RiskPage()) == "安全验证"


def test_next_gap_within_range():
    # §36 随机延迟范围：相邻好友之间等待秒数应落在 [gap_min, gap_max]
    values = [automation._next_gap(6, 12) for _ in range(200)]
    assert all(6 <= v <= 12 for v in values)

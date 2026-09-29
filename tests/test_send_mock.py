from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from core import automation, ledger


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


def _sent_ok_entry(name: str) -> dict:
    today = datetime.now().astimezone().date().isoformat()
    return {
        "display_name": name,
        "has_conversation": True,
        "last_send_ok": True,
        "last_sent_at": f"{today}T08:00:00+08:00",
    }


def test_run_send_skips_contacts_already_sent_today(monkeypatch):
    entries = [_sent_ok_entry("甲"), _sent_ok_entry("乙")]

    @contextmanager
    def _no_browser(*_args, **_kwargs):
        raise AssertionError("全员今日已发送时不应打开浏览器")
        yield

    monkeypatch.setattr(automation, "get_valid_state_path", lambda _aid: Path("state.json"))
    monkeypatch.setattr(automation.ledger, "get_selected", lambda _aid: entries)
    monkeypatch.setattr(automation, "open_browser", _no_browser)

    result = automation.run_send(account_id="default")

    assert result["ok"] == []
    assert [s["name"] for s in result["skipped"]] == ["甲", "乙"]
    assert all("今日已成功发送" in s["reason"] for s in result["skipped"])


def test_run_send_dry_run_does_not_skip_sent_contacts(monkeypatch):
    entries = [_sent_ok_entry("甲"), _sent_ok_entry("乙")]
    processed: list[str] = []

    @contextmanager
    def _fake_browser(*_args, **_kwargs):
        yield None, None, None, object()

    monkeypatch.setattr(automation, "get_valid_state_path", lambda _aid: Path("state.json"))
    monkeypatch.setattr(automation.ledger, "get_selected", lambda _aid: entries)
    monkeypatch.setattr(automation, "open_browser", _fake_browser)
    monkeypatch.setattr(automation, "_open_chat_page", lambda _page: True)
    monkeypatch.setattr(automation.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(automation, "check_login", lambda _page: (True, "ok"))
    monkeypatch.setattr(automation, "refresh_authenticated_state", lambda _ctx, _state: True)
    monkeypatch.setattr(
        automation,
        "_send_consumer",
        lambda _page, entry, _msg, _dry, _result, _aid=None: processed.append(entry["display_name"]),
    )

    result = automation.run_send(dry_run=True, account_id="default")

    assert processed == ["甲", "乙"]
    assert result["skipped"] == []


def test_run_send_real_run_processes_only_unsent_contacts(monkeypatch):
    failed_today = {
        "display_name": "乙",
        "has_conversation": True,
        "last_send_ok": False,
        "last_sent_at": f"{datetime.now().astimezone().date().isoformat()}T09:00:00+08:00",
    }
    entries = [_sent_ok_entry("甲"), failed_today]
    processed: list[str] = []

    @contextmanager
    def _fake_browser(*_args, **_kwargs):
        yield None, None, None, object()

    monkeypatch.setattr(automation, "get_valid_state_path", lambda _aid: Path("state.json"))
    monkeypatch.setattr(automation.ledger, "get_selected", lambda _aid: entries)
    monkeypatch.setattr(automation, "open_browser", _fake_browser)
    monkeypatch.setattr(automation, "_open_chat_page", lambda _page: True)
    monkeypatch.setattr(automation.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(automation, "check_login", lambda _page: (True, "ok"))
    monkeypatch.setattr(automation, "refresh_authenticated_state", lambda _ctx, _state: True)
    monkeypatch.setattr(
        automation,
        "_send_consumer",
        lambda _page, entry, _msg, _dry, _result, _aid=None: processed.append(entry["display_name"]),
    )

    result = automation.run_send(account_id="default")

    assert processed == ["乙"]
    assert [s["name"] for s in result["skipped"]] == ["甲"]


def test_compute_pending_excludes_already_sent_today(monkeypatch):
    stale_ok = {
        "display_name": "丙",
        "has_conversation": True,
        "last_send_ok": True,
        "last_sent_at": "2020-01-01T08:00:00+08:00",
    }
    entries = [_sent_ok_entry("甲"), {"display_name": "乙", "has_conversation": True}, stale_ok]
    monkeypatch.setattr(automation.ledger, "get_selected", lambda _aid: entries)

    pending = automation.compute_pending({"allow_first_message": False}, account_id="default")

    assert [p["display_name"] for p in pending] == ["乙", "丙"]


def test_update_send_result_records_ok_flag():
    ledger.import_config_friends(["去重测试甲"], "default")

    ledger.update_send_result("去重测试甲", True, at="2026-09-29T08:00:00+08:00", account_id="default")
    entry = next(e for e in ledger.load_ledger("default") if e["display_name"] == "去重测试甲")
    assert entry["last_send_ok"] is True
    assert entry["last_sent_at"] == "2026-09-29T08:00:00+08:00"

    ledger.update_send_result("去重测试甲", False, at="2026-09-29T09:00:00+08:00", account_id="default")
    entry = next(e for e in ledger.load_ledger("default") if e["display_name"] == "去重测试甲")
    assert entry["last_send_ok"] is False
    assert entry["last_sent_at"] == "2026-09-29T09:00:00+08:00"

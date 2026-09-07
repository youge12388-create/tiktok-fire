from core import login_session
import threading


class _QrLocator:
    def __init__(self, image: bytes | None = b"png-bytes", fail: bool = False):
        self.image = image
        self.fail = fail
        self.calls: list[dict] = []

    def screenshot(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError("screenshot unavailable")
        return self.image


def test_qrcode_data_url_is_reused_without_screenshot():
    locator = _QrLocator()
    source = "data:image/png;base64,already-encoded"

    assert login_session._qrcode_locator_to_data_url(locator, source) == source
    assert locator.calls == []


def test_remote_qrcode_is_converted_from_browser_element():
    locator = _QrLocator(b"qr-png")

    result = login_session._qrcode_locator_to_data_url(locator, "https://example.test/qr.png")

    assert result == "data:image/png;base64,cXItcG5n"
    assert locator.calls == [{"type": "png", "timeout": 5000}]


def test_qrcode_keeps_encoded_source_fallback_when_screenshot_fails():
    locator = _QrLocator(fail=True)
    encoded_source = "aGVsbG8="

    assert login_session._qrcode_locator_to_data_url(locator, encoded_source) == "data:image/png;base64,aGVsbG8="


class _NoQrPage:
    main_frame = object()
    frames = [main_frame]

    def locator(self, _selector):
        raise RuntimeError("not present")

    def wait_for_timeout(self, _timeout):
        pass

    def screenshot(self, **_kwargs):
        return b"page-png"


def test_missing_qrcode_keeps_full_page_screenshot_fallback():
    assert login_session._wait_and_extract_qrcode(_NoQrPage(), timeout_ms=0) == "data:image/png;base64,cGFnZS1wbmc="


class _ProfilePage:
    def __init__(self, nickname="抖音昵称"):
        self.nickname = nickname
        self.url = ""

    def goto(self, url, **_kwargs):
        self.url = url

    def wait_for_timeout(self, _timeout):
        pass

    def evaluate(self, script):
        assert script == login_session._PROFILE_NICKNAME_JS
        return self.nickname


def test_profile_nickname_is_read_from_self_profile():
    page = _ProfilePage()

    assert login_session._extract_profile_nickname(page) == "抖音昵称"
    assert page.url == login_session.PROFILE_URL


def test_profile_nickname_failure_does_not_break_login():
    class _BrokenPage:
        def goto(self, *_args, **_kwargs):
            raise RuntimeError("page changed")

    assert login_session._extract_profile_nickname(_BrokenPage()) == ""


def test_old_cleanup_cannot_remove_replacement_session(monkeypatch):
    replacement = {
        "session_id": "new-session",
        "status": "waiting_scan",
        "message": "等待扫码",
        "qrcode": "",
        "error": "",
    }
    monkeypatch.setitem(login_session._sessions, "acc_1", replacement)

    login_session._cleanup_session("acc_1", "old-session")

    assert login_session._sessions["acc_1"] is replacement


def test_old_watchdog_cannot_expire_replacement_session(monkeypatch):
    replacement = {
        "session_id": "new-session",
        "status": "waiting_scan",
        "message": "等待扫码",
        "qrcode": "",
        "error": "",
    }
    flag = threading.Event()
    monkeypatch.setitem(login_session._sessions, "acc_1", replacement)
    monkeypatch.setitem(login_session._stop_flags, "acc_1", flag)
    released: list[tuple[str, str]] = []
    monkeypatch.setattr(login_session, "_release_slot_once", lambda aid, sid: released.append((aid, sid)))

    login_session._hard_expire("acc_1", "old-session")

    assert replacement["status"] == "waiting_scan"
    assert not flag.is_set()
    assert released == []


def test_old_session_cannot_save_state_after_replacement(monkeypatch):
    replacement = {"session_id": "new-session", "status": "waiting_scan"}
    monkeypatch.setitem(login_session._sessions, "acc_1", replacement)
    saved: list[bool] = []
    monkeypatch.setattr(login_session, "_save_state", lambda *_args: saved.append(True))

    assert login_session._save_state_if_current(object(), "acc_1", "old-session") is False
    assert saved == []


def test_expired_session_cannot_update_nickname(monkeypatch):
    flag = threading.Event()
    flag.set()
    monkeypatch.setitem(
        login_session._sessions,
        "acc_1",
        {"session_id": "old-session", "status": "expired"},
    )
    monkeypatch.setitem(login_session._stop_flags, "acc_1", flag)
    updated: list[str] = []
    monkeypatch.setattr(
        login_session,
        "update_runtime",
        lambda _aid, **fields: updated.append(fields["douyin_nickname"]),
    )

    assert login_session._update_nickname_if_current("acc_1", "old-session", "旧昵称") is False
    assert updated == []

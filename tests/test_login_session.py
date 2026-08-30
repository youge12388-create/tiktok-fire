from core import login_session


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

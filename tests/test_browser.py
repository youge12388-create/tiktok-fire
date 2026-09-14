import os
import shutil
import uuid
from pathlib import Path

import pytest

from core import browser


class _FakePage:
    def close(self):
        pass


class _FakeContext:
    def __init__(self, browser_handle):
        self.browser = browser_handle
        self.closed = False
        self.pages = []
        self.storage_state_path = None

    def new_page(self):
        page = _FakePage()
        self.pages.append(page)
        return page

    def set_storage_state(self, path):
        self.storage_state_path = path

    def close(self):
        self.closed = True


class _FakeBrowser:
    version = "138.0.1"

    def __init__(self):
        self.closed = False
        self.context_kwargs = None

    def close(self):
        self.closed = True

    def new_context(self, **kwargs):
        self.context_kwargs = kwargs
        return _FakeContext(self)


class _FakeChromium:
    def __init__(self, *, persistent_error=None):
        self.persistent_error = persistent_error
        self.persistent_kwargs = None
        self.persistent_context = None
        self.ephemeral_browser = None

    def launch(self, **_kwargs):
        return _FakeBrowser()

    def launch_persistent_context(self, profile, **kwargs):
        self.persistent_kwargs = {"profile": profile, **kwargs}
        if self.persistent_error:
            raise self.persistent_error
        self.persistent_context = _FakeContext(_FakeBrowser())
        return self.persistent_context


class _FakePlaywright:
    def __init__(self, chromium):
        self.chromium = chromium


class _PlaywrightFactory:
    def __init__(self, playwright):
        self.playwright = playwright

    def start(self):
        return self.playwright


@pytest.fixture
def browser_state_path():
    root = Path(os.environ["DOUYIN_DATA_DIR"]) / "browser-tests" / uuid.uuid4().hex
    root.mkdir(parents=True)
    path = root / "state.json"
    try:
        yield path
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_open_browser_uses_per_account_persistent_profile(monkeypatch, browser_state_path):
    chromium = _FakeChromium()
    playwright = _FakePlaywright(chromium)
    monkeypatch.setattr(browser, "sync_playwright", lambda: _PlaywrightFactory(playwright))
    monkeypatch.setattr(browser, "_apply_stealth", lambda _page: None)
    profile = browser_state_path.parent / "profile"
    monkeypatch.setattr(browser, "account_browser_profile_path", lambda _account_id: profile)
    state = browser_state_path
    state.write_text('{"cookies": [], "origins": []}', encoding="utf-8")

    with browser.open_browser(state_path=state, account_id="profile-test") as (_p, _b, context, _page):
        assert context is chromium.persistent_context

    assert chromium.persistent_kwargs["profile"] == str(profile)
    assert chromium.persistent_context.storage_state_path == str(state)
    assert chromium.persistent_context.closed is True
    assert (profile / browser._PROFILE_STATE_MARKER).read_text(encoding="ascii") == str(state.stat().st_mtime_ns)

    # The profile has already consumed this exact snapshot; a newer profile
    # session must not be overwritten by the same old file on next launch.
    with browser.open_browser(state_path=state, account_id="profile-test") as (_p, _b, context, _page):
        assert context.storage_state_path is None


def test_open_browser_falls_back_to_snapshot_when_profile_is_unusable(monkeypatch, browser_state_path):
    chromium = _FakeChromium(persistent_error=RuntimeError("profile is corrupt"))
    playwright = _FakePlaywright(chromium)
    monkeypatch.setattr(browser, "sync_playwright", lambda: _PlaywrightFactory(playwright))
    monkeypatch.setattr(browser, "_apply_stealth", lambda _page: None)
    profile = browser_state_path.parent / "profile"
    monkeypatch.setattr(browser, "account_browser_profile_path", lambda _account_id: profile)
    state = browser_state_path
    state.write_text('{"cookies": [], "origins": []}', encoding="utf-8")

    with browser.open_browser(state_path=state, account_id="profile-fallback") as (_p, _b, context, _page):
        assert context is not chromium.persistent_context
        assert context.storage_state_path == str(state)

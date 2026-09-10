import json
import os
import shutil
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from core import session_state


@pytest.fixture
def state_dir():
    root = Path(os.environ["DOUYIN_DATA_DIR"]) / "session-state-tests"
    path = root / uuid.uuid4().hex
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


class _Context:
    def __init__(self, state: dict):
        self.state = state

    def storage_state(self):
        return self.state


def _state(value: str = "cookie-value") -> dict:
    return {
        "cookies": [
            {
                "name": "sessionid",
                "value": value,
                "domain": ".douyin.com",
                "path": "/",
            }
        ],
        "origins": [],
    }


def test_concurrent_state_writes_use_unique_temp_files(state_dir, monkeypatch):
    target = state_dir / "state.json"
    replace_sources = []
    real_replace = session_state.os.replace

    def tracked_replace(source, destination):
        replace_sources.append(source)
        real_replace(source, destination)

    monkeypatch.setattr(session_state.os, "replace", tracked_replace)

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [
            pool.submit(session_state.write_storage_state, target, _state(str(index)))
            for index in range(16)
        ]
        for future in futures:
            future.result()

    assert len(replace_sources) == 16
    assert len({str(path) for path in replace_sources}) == 16
    assert session_state.read_storage_state(target, require_login_cookie=True) is not None
    assert list(state_dir.glob("state.json.*.tmp")) == []


def test_failed_replace_preserves_existing_state_and_cleans_temp(state_dir, monkeypatch):
    target = state_dir / "state.json"
    session_state.write_storage_state(target, _state("old"))

    def fail_replace(_source, _destination):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(session_state.os, "replace", fail_replace)

    with pytest.raises(OSError, match="simulated"):
        session_state.write_storage_state(target, _state("new"))

    assert json.loads(target.read_text(encoding="utf-8"))["cookies"][0]["value"] == "old"
    assert list(state_dir.glob("state.json.*.tmp")) == []


def test_missing_data_directory_during_temp_create_retries_and_preserves_atomicity(state_dir, monkeypatch):
    target = state_dir / "state.json"
    session_state.write_storage_state(target, _state("old"))
    real_open = Path.open
    temp_open_attempts = 0

    def missing_once(path, mode="r", *args, **kwargs):
        nonlocal temp_open_attempts
        if mode == "x" and path.name.startswith("state.json.") and path.name.endswith(".tmp"):
            temp_open_attempts += 1
            if temp_open_attempts == 1:
                raise FileNotFoundError(2, "No such file or directory", str(path))
        return real_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(session_state.Path, "open", missing_once)

    session_state.write_storage_state(target, _state("new"))

    assert temp_open_attempts == 2
    assert json.loads(target.read_text(encoding="utf-8"))["cookies"][0]["value"] == "new"
    assert list(state_dir.glob("state.json.*.tmp")) == []


def test_persistently_missing_data_directory_keeps_existing_state_and_returns_diagnostic(state_dir, monkeypatch):
    target = state_dir / "state.json"
    session_state.write_storage_state(target, _state("old"))
    real_open = Path.open
    temp_open_attempts = 0

    def always_missing(path, mode="r", *args, **kwargs):
        nonlocal temp_open_attempts
        if mode == "x" and path.name.startswith("state.json.") and path.name.endswith(".tmp"):
            temp_open_attempts += 1
            raise FileNotFoundError(2, "No such file or directory", str(path))
        return real_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(session_state.Path, "open", always_missing)

    with pytest.raises(session_state.StorageStateUnavailableError, match="登录态无法保存：数据目录不可用"):
        session_state.write_storage_state(target, _state("new"))

    assert temp_open_attempts == session_state._WRITE_ATTEMPTS
    assert json.loads(target.read_text(encoding="utf-8"))["cookies"][0]["value"] == "old"
    assert list(state_dir.glob("state.json.*.tmp")) == []


def test_context_without_login_cookie_does_not_overwrite_existing_state(state_dir):
    target = state_dir / "state.json"
    session_state.write_storage_state(target, _state("old"))
    context = _Context({"cookies": [], "origins": []})

    assert session_state.persist_context_state(context, target) is False
    assert json.loads(target.read_text(encoding="utf-8"))["cookies"][0]["value"] == "old"


def test_context_refresh_replaces_state_after_login_is_confirmed(state_dir):
    target = state_dir / "state.json"
    session_state.write_storage_state(target, _state("old"))

    assert session_state.persist_context_state(_Context(_state("refreshed")), target) is True
    assert json.loads(target.read_text(encoding="utf-8"))["cookies"][0]["value"] == "refreshed"


def test_invalid_storage_state_is_rejected_without_touching_existing_file(state_dir):
    target = state_dir / "state.json"
    session_state.write_storage_state(target, _state("old"))

    with pytest.raises(ValueError, match="cookies/origins"):
        session_state.write_storage_state(target, {"cookies": {}, "origins": []})

    assert json.loads(target.read_text(encoding="utf-8"))["cookies"][0]["value"] == "old"

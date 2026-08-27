"""§36 API 参数校验：未知账号 404、非法配置 400、同账号忙碌 409。"""

from core import accounts
from services.state import acquire_lock, lock_for

PWD = "T3st-Strong-Passw0rd!"


def _login(client):
    client.post("/api/v1/auth/login", json={"username": "admin", "password": PWD})


def _new_account(name: str) -> str:
    return accounts.create_account(name=name, device="")["id"]


def _cleanup(aid: str) -> None:
    accounts.remove_account(aid)


def test_task_unknown_account_404(client):
    _login(client)
    assert client.get("/api/v1/accounts/nope/spark-task").status_code == 404


def test_task_bad_schedule_400(client):
    _login(client)
    aid = _new_account("bad-schedule")
    try:
        r = client.put(f"/api/v1/accounts/{aid}/spark-task", json={"config": {"schedule_time": "99:00"}})
        assert r.status_code == 400
    finally:
        _cleanup(aid)


def test_task_unknown_config_400(client):
    _login(client)
    aid = _new_account("bad-config")
    try:
        r = client.put(f"/api/v1/accounts/{aid}/spark-task", json={"config": {"nope": 1}})
        assert r.status_code == 400
    finally:
        _cleanup(aid)


def test_sync_contacts_409_when_account_busy(client):
    _login(client)
    aid = _new_account("busy")
    assert acquire_lock(aid) is True
    try:
        r = client.post(f"/api/v1/accounts/{aid}/contacts/sync")
        assert r.status_code == 409
    finally:
        lk = lock_for(aid)
        if lk.locked():
            lk.release()
        _cleanup(aid)

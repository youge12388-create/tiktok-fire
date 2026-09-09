from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from api.deps import CSRFMiddleware
from api import auth as auth_api


def test_health_is_public(client):
    r = client.get("/api/v1/system/health")
    assert r.status_code == 200
    assert r.json()["ready"] is True
    assert r.json()["checks"] == {"database": True, "scheduler": True}
    assert client.get("/api/v1/system/health/live").json()["ok"] is True


def test_unauthenticated_protected(client):
    assert client.get("/api/v1/accounts").status_code == 401
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/runs").status_code == 401


def test_login_wrong_password_rejected(client):
    r = client.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"})
    assert r.status_code == 401


def test_login_unicode_input_returns_auth_error_not_server_error(client):
    r = client.post("/api/v1/auth/login", json={"username": "游sir", "password": "错误密码"})
    assert r.status_code == 401


def test_login_rate_limit_keeps_block_for_configured_duration(client, monkeypatch):
    auth_api._login_failures.clear()
    auth_api._login_blocked_until.clear()
    now = 1000.0
    monkeypatch.setattr(auth_api.time, "monotonic", lambda: now)
    for _ in range(auth_api._LOGIN_MAX_FAILURES):
        assert client.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"}).status_code == 429
    monkeypatch.setattr(auth_api.time, "monotonic", lambda: now + auth_api._LOGIN_WINDOW_SECONDS + 1)
    assert client.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"}).status_code == 429
    monkeypatch.setattr(auth_api.time, "monotonic", lambda: now + auth_api._LOGIN_BLOCK_SECONDS + 1)
    assert client.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"}).status_code == 401
    auth_api._login_failures.clear()
    auth_api._login_blocked_until.clear()


def test_login_logout_me_cycle(client):
    pwd = "T3st-Strong-Passw0rd!"
    r = client.post("/api/v1/auth/login", json={"username": "admin", "password": pwd})
    assert r.status_code == 200 and r.json().get("ok") is True
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 200 and r.json()["username"] == "admin"
    r = client.post("/api/v1/auth/logout")
    assert r.status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401


def test_authenticated_can_access_runs(client):
    pwd = "T3st-Strong-Passw0rd!"
    client.post("/api/v1/auth/login", json={"username": "admin", "password": pwd})
    r = client.get("/api/v1/runs")
    assert r.status_code == 200 and "items" in r.json()


def test_notification_status_and_test_require_login(client):
    assert client.get("/api/v1/system/notifications/status").status_code == 401
    assert client.post("/api/v1/system/notifications/test").status_code == 401


def test_authenticated_admin_can_send_notification_test(client, monkeypatch):
    from api import system as system_api

    client.post("/api/v1/auth/login", json={"username": "admin", "password": "T3st-Strong-Passw0rd!"})
    monkeypatch.setattr(system_api.notification_service, "dingtalk_configured", lambda: True)
    monkeypatch.setattr(
        system_api.notification_service,
        "send_test_notification",
        lambda: (True, "测试消息已发送，请在钉钉群中确认收到"),
    )

    status = client.get("/api/v1/system/notifications/status")
    sent = client.post("/api/v1/system/notifications/test")

    assert status.status_code == 200
    assert status.json() == {"dingtalk": {"configured": True}}
    assert sent.status_code == 200
    assert sent.json()["ok"] is True


def test_notification_test_returns_actionable_configuration_error(client, monkeypatch):
    from api import system as system_api

    client.post("/api/v1/auth/login", json={"username": "admin", "password": "T3st-Strong-Passw0rd!"})
    monkeypatch.setattr(system_api.notification_service, "dingtalk_configured", lambda: False)
    monkeypatch.setattr(
        system_api.notification_service,
        "send_test_notification",
        lambda: (False, "钉钉告警未完整配置"),
    )

    response = client.post("/api/v1/system/notifications/test")

    assert response.status_code == 400
    assert response.json()["detail"] == "钉钉告警未完整配置"


def test_csrf_uses_configured_session_cookie_name():
    mini_app = FastAPI()

    @mini_app.post("/login")
    def login(request: Request):
        request.session["admin"] = "admin"
        return {"ok": True}

    @mini_app.post("/write")
    def write():
        return {"ok": True}

    mini_app.add_middleware(
        SessionMiddleware,
        secret_key="0123456789abcdef0123456789abcdef",
        session_cookie="douyin_fire_session",
    )
    mini_app.add_middleware(CSRFMiddleware, session_cookie="douyin_fire_session")

    with TestClient(mini_app) as mini_client:
        assert mini_client.post("/login").status_code == 200
        response = mini_client.post("/write", headers={"Origin": "https://evil.example"})

    assert response.status_code == 403

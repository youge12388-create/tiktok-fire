from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from api.deps import CSRFMiddleware


def test_health_is_public(client):
    r = client.get("/api/v1/system/health")
    assert r.status_code == 200


def test_unauthenticated_protected(client):
    assert client.get("/api/v1/accounts").status_code == 401
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/runs").status_code == 401


def test_login_wrong_password_rejected(client):
    r = client.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"})
    assert r.status_code == 401


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

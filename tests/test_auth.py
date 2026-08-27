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

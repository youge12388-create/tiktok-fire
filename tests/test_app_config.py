import app_config


def test_security_ok_with_strong_env():
    assert app_config.security_problems() == []


def test_weak_password_flagged():
    original = app_config.ADMIN_PASSWORD
    try:
        app_config.ADMIN_PASSWORD = "123456"
        assert any("过弱" in p for p in app_config.security_problems())
    finally:
        app_config.ADMIN_PASSWORD = original


def test_missing_secret_flagged():
    original = app_config.SESSION_SECRET
    try:
        app_config.SESSION_SECRET = ""
        assert any("SESSION_SECRET" in p for p in app_config.security_problems())
    finally:
        app_config.SESSION_SECRET = original


def test_weak_default_passwords_all_flagged():
    original = app_config.ADMIN_PASSWORD
    try:
        for weak in app_config.WEAK_PASSWORDS:
            if not weak:
                continue
            app_config.ADMIN_PASSWORD = weak
            assert any("过弱" in p for p in app_config.security_problems()), weak
    finally:
        app_config.ADMIN_PASSWORD = original

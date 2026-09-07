from pathlib import PurePosixPath

import deploy_to_server


def test_archive_filter_excludes_credentials_runtime_data_and_agent_artifacts():
    excluded_paths = (
        ".env",
        "state.json",
        "data/state.json",
        ".agent/credentials.local.md",
        ".tmp/build.log",
        ".impeccable/preview.png",
        "nested/.env",
        "nested/state.json",
        "runtime.json.123.456.tmp",
        "server.pid",
        "debug.log",
    )

    assert all(
        deploy_to_server.should_exclude_from_archive(PurePosixPath(path))
        for path in excluded_paths
    )


def test_archive_filter_keeps_deployable_source_and_env_template():
    included_paths = ("app.py", "deploy/deploy.sh", ".env.example", "frontend/src/main.ts")

    assert all(
        not deploy_to_server.should_exclude_from_archive(PurePosixPath(path))
        for path in included_paths
    )


def test_dockerignore_excludes_sensitive_and_temporary_content_at_any_depth():
    rules = {
        line.strip()
        for line in (deploy_to_server.BASE_DIR / ".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }

    assert {".env", "state.json", "data/", ".agent/", ".tmp/", ".impeccable/", "logs/"} <= rules
    assert {"*.tmp", "*.pid", "*.log", "*.log.*"} <= rules
    assert {"**/.env", "**/state.json", "**/data/", "**/.agent/", "**/.tmp/", "**/.impeccable/"} <= rules
    assert "**/logs/" in rules


def test_legacy_deploy_script_uses_current_authentication_variables():
    script = (deploy_to_server.BASE_DIR / "deploy" / "deploy.sh").read_text(encoding="utf-8")

    assert "ADMIN_PASSWORD" in script
    assert "SESSION_SECRET" in script
    assert "AUTH_TOKEN=" not in script
    assert "security_problems" in script


def test_legacy_deploy_script_does_not_kill_unrelated_processes():
    script = (deploy_to_server.BASE_DIR / "deploy" / "deploy.sh").read_text(encoding="utf-8")

    assert 'pkill -9 -f "python.*app.py"' not in script
    assert "fuser -k -9 8000/tcp" not in script


def test_remote_deployer_does_not_advertise_private_app_port():
    script = (deploy_to_server.BASE_DIR / "deploy_to_server.py").read_text(encoding="utf-8")

    assert "http://{server_ip}:8000" not in script
    assert "ADMIN_USERNAME / ADMIN_PASSWORD" in script

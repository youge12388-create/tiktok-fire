"""Douyin Cloud Streak V1 · FastAPI 入口。

瘦身为：创建 app + 安全配置 fail-fast + 单实例锁 + 调度器 + 挂载 /api/v1 +
托管前端构建产物（frontend/dist）。抖音自动化逻辑全部收敛在 core/ 与 services/。
"""

from __future__ import annotations

import json
import logging
import os
import socket
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from api import api_router
from api.deps import CSRFMiddleware
from app_config import (
    COOKIE_SECURE,
    DATA_DIR,
    HOST,
    PORT,
    SESSION_COOKIE_NAME,
    SESSION_COOKIE_PATH,
    SESSION_MAX_AGE,
    SESSION_SECRET,
    security_problems,
)
from core import accounts, scheduler
from core.runtime import setup_logging
from db import init_db
from services.task_runtime import _scheduled_run, start_harvest_creator

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
FRONTEND_DIST = BASE_DIR / "frontend" / "dist"
PID_PATH = DATA_DIR / "server.pid"

logger = setup_logging()

# ── 安全配置 fail-fast ─────────────────────────────────────────────────────
problems = security_problems()
if problems:
    for problem in problems:
        logger.error(problem)
    raise SystemExit("安全配置错误：" + "；".join(problems))


# ── 单实例锁（防止旧实例 scheduler 残留重复发送）────────────────────────────
def _pid_alive(pid: int) -> bool:
    if os.name == "nt":
        try:
            import subprocess

            r = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return str(pid) in r.stdout and "python" in r.stdout.lower()
        except Exception:
            return False
    try:
        import os

        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _proc_identity(pid: int | None = None) -> tuple[str, str]:
    pid = pid if pid is not None else os.getpid()
    start = ""
    if os.name == "posix":
        try:
            fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
            start = fields[19]
        except (OSError, IndexError):
            start = ""
    return socket.gethostname(), start


def _acquire_instance_lock() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    cur_host, cur_start = _proc_identity()
    if PID_PATH.exists():
        old_pid = None
        old_host, old_start = "", ""
        try:
            raw = json.loads(PID_PATH.read_text().strip())
            old_pid = int(raw["pid"])
            old_host = str(raw.get("host", ""))
            old_start = str(raw.get("start", ""))
        except (ValueError, OSError, KeyError, TypeError):
            old_pid = None
        if old_pid:
            if old_host and old_host != cur_host:
                logger.info("发现其他容器/主机（%s）的残留锁（PID %s），可安全接管", old_host, old_pid)
            elif _pid_alive(old_pid) and old_start and _proc_identity(old_pid)[1] == old_start:
                logger.error("检测到已有实例在运行（PID %s），拒绝启动", old_pid)
                raise SystemExit(f"已有实例在运行（PID {old_pid}），请先停止旧实例")
            else:
                logger.info("旧实例锁已失效（PID %s），可安全接管", old_pid)
    PID_PATH.write_text(
        json.dumps({"pid": os.getpid(), "host": cur_host, "start": cur_start}),
        encoding="utf-8",
    )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _acquire_instance_lock()
    init_db()
    try:
        accounts.list_accounts()
        scheduler.configure(
            _scheduled_run,
            harvest_func=lambda account_id: start_harvest_creator(account_id),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("调度器启动失败: %s", exc)
    yield
    scheduler.shutdown()
    try:
        PID_PATH.unlink(missing_ok=True)
    except Exception:
        pass


app = FastAPI(title="Douyin Cloud Streak", lifespan=lifespan)

app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    session_cookie=SESSION_COOKIE_NAME,
    path=SESSION_COOKIE_PATH,
    same_site="lax",
    https_only=COOKIE_SECURE,
    max_age=SESSION_MAX_AGE,
)
app.add_middleware(CSRFMiddleware, session_cookie=SESSION_COOKIE_NAME)

app.include_router(api_router)

app.mount("/avatars", StaticFiles(directory=DATA_DIR / "avatars", check_dir=False), name="avatars")

if FRONTEND_DIST.exists() and (FRONTEND_DIST / "index.html").exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
else:

    @app.get("/", include_in_schema=False)
    def index_fallback() -> HTMLResponse:
        return HTMLResponse(
            "<!doctype html><html><body><h3>前端尚未构建</h3>"
            "<p>请进入 frontend/ 目录执行 <code>npm install</code> 后 <code>npm run build</code>，"
            "或本地开发使用 <code>npm run dev</code> 并代理 <code>/api</code> 到本服务。</p></body></html>"
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host=HOST, port=PORT, reload=False)

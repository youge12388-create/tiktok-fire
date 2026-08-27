"""认证依赖与 CSRF 防护。"""

from __future__ import annotations

from urllib.parse import urlparse

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def require_admin(request: Request) -> str:
    """要求已登录，返回管理员用户名。未登录返回 401。"""
    admin = request.session.get("admin")
    if not admin:
        raise HTTPException(status_code=401, detail="未登录或会话已失效")
    return str(admin)


class CSRFMiddleware(BaseHTTPMiddleware):
    """对携带会话 Cookie 的状态变更请求做 Origin / Sec-Fetch-Site 校验。"""

    async def dispatch(self, request: Request, call_next):
        if request.method in UNSAFE_METHODS and request.cookies.get("session"):
            site = request.headers.get("sec-fetch-site")
            origin = request.headers.get("origin")
            host = request.headers.get("host", "")
            if site and site not in ("same-origin", "none"):
                return JSONResponse({"detail": "CSRF 校验失败，请求来源非法"}, status_code=403)
            if origin:
                parsed = urlparse(origin)
                if parsed.netloc and not _host_matches(parsed.netloc, host):
                    return JSONResponse({"detail": "CSRF 校验失败，请求来源非法"}, status_code=403)
        return await call_next(request)


def _host_matches(origin_netloc: str, host: str) -> bool:
    o_host = origin_netloc.rsplit("@", 1)[-1].split(":", 1)[0]
    r_host = host.rsplit("@", 1)[-1].split(":", 1)[0]
    return o_host == r_host

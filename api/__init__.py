"""HTTP API 层：统一挂载 /api/v1。"""

from fastapi import APIRouter

from . import accounts, auth, contacts, runs, system, tasks

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(accounts.router)
api_router.include_router(contacts.router)
api_router.include_router(tasks.router)
api_router.include_router(runs.router)
api_router.include_router(system.router)

__all__ = ["api_router"]

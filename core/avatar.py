"""抖音好友头像本地化缓存。

抖音网页版头像 URL 带签名参数，过期后无法再访问。
同步联系人时把头像下载到本地 data/avatars/<account_id>/<hash>.<ext>，
前端通过 /avatars/... 访问本地文件，长期有效。
"""

from __future__ import annotations

import hashlib
import logging
import threading
from pathlib import Path

import requests

from .config import DEFAULT_ACCOUNT_ID, DATA_DIR

logger = logging.getLogger("douyin-cloud-streak")

_TIMEOUT = 12
_FILE_LOCKS: dict[str, threading.Lock] = {}
_FILE_LOCKS_GUARD = threading.Lock()


def _file_lock(key: str) -> threading.Lock:
    with _FILE_LOCKS_GUARD:
        lock = _FILE_LOCKS.get(key)
        if lock is None:
            lock = _FILE_LOCKS[key] = threading.Lock()
        return lock


def avatar_dir(account_id: str | None = None) -> Path:
    return DATA_DIR / "avatars" / (account_id or DEFAULT_ACCOUNT_ID)


def _public_url(account_id: str, fname: str) -> str:
    return f"/avatars/{account_id}/{fname}"


def fetch_and_save_avatar(url: str, account_id: str | None = None) -> str | None:
    """下载头像到本地，返回可公开访问的相对路径；失败返回 None。

    URL 为空或下载失败时不抛异常，保证同步流程不受影响。
    """
    if not url or not isinstance(url, str):
        return None
    aid = account_id or DEFAULT_ACCOUNT_ID
    try:
        ext = Path(url.split("?")[0]).suffix.lower()
        if ext not in (".jpg", ".jpeg", ".png", ".webp"):
            ext = ".jpg"
        fname = f"{hashlib.md5(url.encode('utf-8')).hexdigest()[:16]}{ext}"
        d = avatar_dir(aid)
        fp = d / fname
        if fp.exists() and fp.stat().st_size > 0:
            return _public_url(aid, fname)
        with _file_lock(f"{aid}:{fname}"):
            if fp.exists() and fp.stat().st_size > 0:
                return _public_url(aid, fname)
            d.mkdir(parents=True, exist_ok=True)
            r = requests.get(url, timeout=_TIMEOUT, headers={"Referer": "https://www.douyin.com/"})
            r.raise_for_status()
            tmp = fp.with_suffix(fp.suffix + ".tmp")
            tmp.write_bytes(r.content)
            tmp.replace(fp)
        logger.info("[%s] 头像已缓存: %s", aid, fname)
        return _public_url(aid, fname)
    except Exception as e:
        logger.warning("[%s] 头像下载失败: %s", aid, str(e)[:120])
        return None

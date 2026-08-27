"""共享防护：限流关键词与安全验证浮层检测。"""

from __future__ import annotations

from .selectors import RISK_TEXT_MARKERS

RATE_LIMIT_KEYWORDS = RISK_TEXT_MARKERS


def detect_rate_limit(page) -> str | None:
    """扫描页面上可见的限流/验证提示，命中返回关键词，未命中返回 None。"""
    for kw in RATE_LIMIT_KEYWORDS:
        try:
            loc = page.get_by_text(kw, exact=False)
            for i in range(loc.count()):
                box = loc.nth(i).bounding_box()
                if box:  # 可见才计，避免匹配到隐藏节点
                    return kw
        except Exception:
            continue
    return None

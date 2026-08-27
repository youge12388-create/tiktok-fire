"""业务服务层：隔离 Web API 与抖音自动化核心。"""

from .douyin import DouyinService, douyin

__all__ = ["DouyinService", "douyin"]

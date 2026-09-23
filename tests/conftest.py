import os
from pathlib import Path

# 在导入任何项目模块前，把数据目录与安全环境变量重定向到测试目录
_TMP_DATA = Path(__file__).resolve().parent / "_tmp_data"
_TMP_DATA.mkdir(parents=True, exist_ok=True)
os.environ["DOUYIN_DATA_DIR"] = str(_TMP_DATA)
os.environ["ADMIN_PASSWORD"] = "T3st-Strong-Passw0rd!"
os.environ["SESSION_SECRET"] = "0123456789abcdef0123456789abcdef"
# 测试绝不能把掉线告警发到真实钉钉群。先占位为空串即可屏蔽 .env：
# load_dotenv(override=False) 只补齐缺失的键，不会覆盖这里已存在的键。
os.environ["DINGTALK_WEBHOOK_URL"] = ""
os.environ["DINGTALK_SECRET"] = ""

import pytest
from fastapi.testclient import TestClient

import app as app_module
from db import init_db
from services import settings_service

# 网页端保存的机器人配置同样要隔离，避免读到本机或上次测试留下的真实 settings.json。
settings_service.SETTINGS_PATH = _TMP_DATA / "settings-isolated" / "settings.json"

init_db()


@pytest.fixture
def client():
    with TestClient(app_module.app) as c:
        yield c

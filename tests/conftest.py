import os
from pathlib import Path

# 在导入任何项目模块前，把数据目录与安全环境变量重定向到测试目录
_TMP_DATA = Path(__file__).resolve().parent / "_tmp_data"
_TMP_DATA.mkdir(parents=True, exist_ok=True)
os.environ["DOUYIN_DATA_DIR"] = str(_TMP_DATA)
os.environ["ADMIN_PASSWORD"] = "T3st-Strong-Passw0rd!"
os.environ["SESSION_SECRET"] = "0123456789abcdef0123456789abcdef"

import pytest
from fastapi.testclient import TestClient

import app as app_module
from db import init_db

init_db()


@pytest.fixture
def client():
    with TestClient(app_module.app) as c:
        yield c

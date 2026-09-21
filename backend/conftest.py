"""测试环境准备：每次测试用独立的 test.db，跑完自动清空。"""
import os
import sys
import pytest

# 【关键】在导入 database/main 之前，把数据库指向 test.db
os.environ["ZHIENG_DB"] = "test.db"
sys.path.insert(0, os.path.dirname(__file__))

from fastapi.testclient import TestClient
import database
import main

TEST_DB = os.path.join(os.path.dirname(__file__), "test.db")


@pytest.fixture
def client():
    # 每个用例前：删掉 test.db，重建
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    database.init_db()
    return TestClient(main.app)
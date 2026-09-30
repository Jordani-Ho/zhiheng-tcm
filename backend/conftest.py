"""测试环境准备：每次测试用独立的 test.db，跑完自动清空。"""
import os
import sys
import pytest

# 【关键】在导入 database/main 之前，把数据库指向 test.db
os.environ["ZHIENG_DB"] = "test.db"
# 【Epic 1 新增】模板接口默认关闭（设计 §5.2 第 5 条：`TEMPLATE_API_ENABLED` 默认 off、分批放量）；
# 测试统一打开，需要验「关闭态」的用例自行 monkeypatch 成 off（test_templates.py 覆盖）。
os.environ["TEMPLATE_API_ENABLED"] = "on"
# 【Epic 2 新增】智能體階段總閘（設計 §4.5-⑥ 文件清單的「conftest.py 改 1 行」）：與上一行同款理由 ——
# flag 真相源在服務層（`agent_stage_service.agent_stage_enabled()`，默認 off），測試統一打開；
# 需要驗「關閉態」的用例自行 monkeypatch 成 off（含 404 `agent_stage_disabled` 與 flag off 逐字節一致，
# test_agent_stage.py 的 ⑨/⑪/⑫ 組已用 monkeypatch.delenv 覆蓋）。
os.environ["AGENT_STAGE_ENABLED"] = "on"
sys.path.insert(0, os.path.dirname(__file__))

from fastapi.testclient import TestClient
import database
import main
import migrations_runner

TEST_DB = os.path.join(os.path.dirname(__file__), "test.db")


@pytest.fixture
def client():
    # 每个用例前：删掉 test.db，重建
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    database.init_db()
    # 【Epic 1 新增】templates 表由 alembic 迁移创建（init_db() 不再建它），
    # 让 pytest 与生产走同一条迁移路径；失败只打日志、不阻塞存量用例（批复 1）。
    migrations_runner.run_upgrade()
    return TestClient(main.app)

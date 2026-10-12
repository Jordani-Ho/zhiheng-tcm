"""内测场景 1「老师入社区」的守护测试。

被测：`POST /api/teachers/onboard`（`backend/teacher_service.py`）。
对齐：内测场景 1（老师入社区）+ D-051。

纪律（照 `test_referral_api.py` 既有先例）：
· 每个用例在 `tmp_path` 下自建独立 SQLite，**绝不碰 `backend/zhiheng.db`**；
· 迁移跑真实的 `run_upgrade("head")`，与生产同一条路径。

背景（为什么需要这个端点）：
`teachers` 表原先只有 `database.init_db()` 的种子数据（`database.py:409`），
全库**没有任何「创建老师」的函数或端点** —— 老师是写死的种子，不是「入社区」进来的。
"""
import importlib
import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BACKEND_DIR)

import migrations_runner


def _setup_client(tmp_path, monkeypatch, lineage_enabled=True):
    """最小 FastAPI app：挂 teacher_service.router + 隔离 DB。

    与 `test_referral_api._setup_client` 的关键差异（教训留档）：
    `run_upgrade("head")` **只建迁移管的表**；而 `teachers` 是 `database.init_db()`
    建的（迁移链里没有它）。故本夹具必须 **先 `init_db()` 再 `run_upgrade("head")`** ——
    与生产启动路径（`main.py` 里 init_db 后跑迁移运行器）一致，否则 `teachers` 不存在。
    """
    db = tmp_path / "test_onboard.db"
    assert migrations_runner.run_upgrade("head", db_file=str(db)) is True

    import database
    monkeypatch.setattr(database, "DB_PATH", str(db))
    database.init_db()  # teachers / patients 等由 init_db 建，不属迁移链

    import lineage_service
    import teacher_service
    importlib.reload(lineage_service)
    importlib.reload(teacher_service)

    if lineage_enabled:
        monkeypatch.setenv("LINEAGE_ENABLED", "on")
    else:
        monkeypatch.delenv("LINEAGE_ENABLED", raising=False)

    app = FastAPI()
    app.include_router(teacher_service.router)
    return TestClient(app), database


def _teacher_row(db, name):
    conn = db.get_connection()
    try:
        return conn.execute("SELECT * FROM teachers WHERE name = ?", (name,)).fetchone()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 主路径
# ---------------------------------------------------------------------------
def test_onboard_creates_teacher_and_lineage(tmp_path, monkeypatch):
    """场景 1：老师入社区 → teachers 行 + 该老师的默认师门，两者同时建成。"""
    client, db = _setup_client(tmp_path, monkeypatch)

    resp = client.post("/api/teachers/onboard", json={
        "name": "王医生", "teacher_id": "王医生", "description": "内科"})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["teacher_created"] is True
    assert body["teacher"]["name"] == "王医生"
    assert body["teacher"]["status"] == "active"
    # 师门同时建成，且 id 走既有推导规则 lin-<slug>
    assert body["lineage_created"] is True
    assert body["lineage"]["id"].startswith("lin-")
    assert body["lineage"]["owner_teacher_name"] == "王医生"
    assert body["warnings"] == []

    # 真实落库（不看接口投影）
    row = _teacher_row(db, "王医生")
    assert row is not None
    assert row["description"] == "内科"


def test_onboard_is_idempotent(tmp_path, monkeypatch):
    """幂等：重复提交同一老师 → 200 且两个 created 都是 false，不建第二行。

    照 `lineage_service.create_lineage` 的先例（重复开山门 → 200 + 既有行，不 409）：
    阶段一老师端没有切换器，409 会造成「自己把自己锁住」的困惑。
    """
    client, db = _setup_client(tmp_path, monkeypatch)
    payload = {"name": "王医生", "teacher_id": "王医生"}

    first = client.post("/api/teachers/onboard", json=payload)
    second = client.post("/api/teachers/onboard", json=payload)

    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["teacher_created"] is True
    assert second.json()["teacher_created"] is False
    assert second.json()["lineage_created"] is False

    conn = db.get_connection()
    try:
        n = conn.execute("SELECT COUNT(*) FROM teachers WHERE name = ?", ("王医生",)).fetchone()[0]
        m = conn.execute("SELECT COUNT(*) FROM lineage WHERE owner_teacher_name = ?", ("王医生",)).fetchone()[0]
    finally:
        conn.close()
    assert n == 1, "不得建第二行老师"
    assert m == 1, "一师一门：不得建第二个师门"


# ---------------------------------------------------------------------------
# 边界
# ---------------------------------------------------------------------------
def test_onboard_empty_name_returns_400(tmp_path, monkeypatch):
    client, _ = _setup_client(tmp_path, monkeypatch)
    resp = client.post("/api/teachers/onboard", json={"name": "   "})
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "teacher_name_required"


def test_onboard_identity_mismatch_returns_409(tmp_path, monkeypatch):
    """双因子不一致 → 409（沿 lineage_service.require_teacher_identity 的既有口径）。"""
    client, _ = _setup_client(tmp_path, monkeypatch)
    resp = client.post("/api/teachers/onboard", json={"name": "李医生", "teacher_id": "别人"})
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"] == "teacher_name_taken_by_other"


def test_onboard_lineage_flag_off_still_creates_teacher(tmp_path, monkeypatch):
    """师门旗标 off → **老师行仍建成**，师门步骤如实进 warnings（不吞、不伪装成功）。

    这条是内测的关键韧性：入社区不该因为一个旁路旗标而整体失败。
    """
    client, db = _setup_client(tmp_path, monkeypatch, lineage_enabled=False)

    resp = client.post("/api/teachers/onboard", json={"name": "赵医生", "teacher_id": "赵医生"})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["teacher_created"] is True, "老师行必须建成"
    assert body["lineage"] is None
    assert body["lineage_created"] is False
    assert body["warnings"], "师门未建成必须如实上报，不得静默成功"
    assert _teacher_row(db, "赵医生") is not None


def test_onboard_teacher_visible_in_teacher_list(tmp_path, monkeypatch):
    """入社区后，老师出现在既有 `GET /api/teachers` 的数据源里（沿用既有查询，不另立投影）。"""
    client, db = _setup_client(tmp_path, monkeypatch)
    client.post("/api/teachers/onboard", json={"name": "钱医生", "teacher_id": "钱医生"})

    names = [t["name"] for t in db.get_teachers()]
    assert "钱医生" in names

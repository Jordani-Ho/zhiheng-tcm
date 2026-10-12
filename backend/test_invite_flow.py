"""内测场景 2「邀请 ≥3 学生」的守护测试。

被测：`POST /api/invites` → `POST /api/invites/accept` → `GET /api/teacher-patients`
对齐：内测场景 2 + D-052。

**本文件存在的理由（回归守护）**：
`accept_invite()` 原先写 `patient_teachers` 时**不写 `lineage_id` 列**，而
`get_teacher_patients()` 在 `LINEAGE_ENABLED=on` 时强制 `pt.lineage_id = ?`
（`database.py:470-471`）→ 邀请入社区的学生**在老师端学生列表里查不出来**
（HTTP 200 但返回 `[]`），下游按师门过滤的读点一并失明。
本文件钉住「邀请 3 个学生 → 老师端看得到 3 个」这条内测主路径。

夹具口径（照 `test_agent_stage.py` / `test_teacher_onboard.py` 既有先例）：
用 conftest 的 `client`（= `TestClient(main.app)`，路由齐全），DB 由 conftest
指向独立 `backend/test.db` 并在每个用例前重建 —— **绝不碰 `backend/zhiheng.db`**。
"""
import os
import sys

import pytest

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BACKEND_DIR)

import database
import lineage_service


@pytest.fixture
def lineage_on(monkeypatch):
    """内测主路径要求师门隔离已启用（`LINEAGE_ENABLED=on`）。"""
    monkeypatch.setenv("LINEAGE_ENABLED", "on")
    yield


def _onboard(client, name):
    resp = client.post("/api/teachers/onboard", json={"name": name, "teacher_id": name})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _issue_and_accept(client, teacher, student):
    code = client.post("/api/invites", json={"teacher_name": teacher}).json()["code"]
    resp = client.post("/api/invites/accept", json={"code": code, "student_name": student})
    assert resp.status_code == 200, resp.text
    return code


# ---------------------------------------------------------------------------
# 核心回归
# ---------------------------------------------------------------------------
def test_invite_three_students_visible_to_teacher(client, lineage_on):
    """**核心回归**：邀请 3 个学生 → 老师端学生列表返回 3 个。

    这条若失败，内测场景 2 不成立：学生「入社区成功了」，但老师看不到任何学生
    （HTTP 200 + 返回 []，比报错更难发现）。
    """
    _onboard(client, "王医生")
    lineage_id = lineage_service.default_lineage_id("王医生")

    for i in (1, 2, 3):
        _issue_and_accept(client, "王医生", "学生%d" % i)

    resp = client.get(
        "/api/teacher-patients", params={"teacher_name": "王医生", "lineage_id": lineage_id}
    )
    assert resp.status_code == 200, resp.text
    names = [s["name"] for s in resp.json()]
    assert len(names) == 3, "邀请入社区的学生必须在老师端可见（原缺陷：返回 []）"
    assert set(names) == {"学生1", "学生2", "学生3"}


def test_accept_invite_writes_lineage_id_column(client, lineage_on):
    """机制层：`patient_teachers.lineage_id` 必须被写入且等于一师一门推导值。

    直接查列（不看接口投影）—— 这条是本缺陷的根因面，必须单独钉住。
    """
    _onboard(client, "王医生")
    _issue_and_accept(client, "王医生", "学生甲")

    expected = lineage_service.default_lineage_id("王医生")
    conn = database.get_connection()
    try:
        row = conn.execute(
            "SELECT lineage_id FROM patient_teachers WHERE patient_name = ?",
            ("学生甲",),
        ).fetchone()
    finally:
        conn.close()

    assert row is not None, "师生关系必须建立"
    assert row["lineage_id"] == expected, (
        "invite 入社区必须写 lineage_id（原缺此列 -> NULL/空串 -> 老师端查不到）"
    )


def test_accept_invite_does_not_duplicate_relation(client, lineage_on):
    """同一学生重复加入同一老师：不重复建行（既有 IntegrityError 兜底行为，一并钉住）。"""
    _onboard(client, "王医生")
    _issue_and_accept(client, "王医生", "学生乙")
    _issue_and_accept(client, "王医生", "学生乙")

    conn = database.get_connection()
    try:
        n = conn.execute(
            "SELECT COUNT(*) FROM patient_teachers WHERE patient_name = ?", ("学生乙",)
        ).fetchone()[0]
    finally:
        conn.close()
    assert n == 1, "同一师生关系不得重复建行"


def test_invite_requires_teacher_name(client, lineage_on):
    """边界：发码缺 `teacher_name` → 422（pydantic 必填），不是 500。"""
    resp = client.post("/api/invites", json={})
    assert resp.status_code == 422


def test_accept_bad_code_returns_error_not_crash(client, lineage_on):
    """边界：不存在的邀请码 → 不炸（既有实现返回 error 体，不抛异常）。"""
    resp = client.post("/api/invites/accept", json={"code": "ZHI-NOPE00", "student_name": "学生丙"})
    assert resp.status_code == 200
    assert "error" in resp.json()

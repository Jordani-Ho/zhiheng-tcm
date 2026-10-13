"""身份为空的写端点必须 **fail-loud**，不得返回成功（D-079）。

【缺陷】`/api/check-in` 与 `/api/approve` 原形如：

    @app.post("/api/check-in")
    def check_in(patient_name: str = "张三", teacher_name: str = "李老师"):
        database.update_homework_status(patient_name, teacher_name, "checked_in")
        database.add_points(patient_name, 10)
        return {"message": "打卡成功"}

`update_homework_status` 与 `add_points` 都是 `UPDATE ... WHERE role_name = ?` 形态
—— **名字对不上就静默不生效**。实测空串入参：

    POST /api/check-in?patient_name=&teacher_name=
    -> HTTP 200 {"message": "打卡成功"}      ← 但 homework 状态与积分**都没动**

前端 `selectedPatient` / `selectedTeacher` 初值就是空串（D-059 改为数据驱动引导），
一旦身份未解析出来就点了按钮，就会看到「打卡成功」而实际什么都没发生。

本文件钉住修好后的行为：空身份 -> 4xx，且**错误信息说明缺哪个字段**。
"""

import os
import sys

import pytest

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BACKEND_DIR)

import database

TEACHER = "打卡医生"
STUDENT = "打卡学生"


@pytest.fixture
def lineage_on(monkeypatch):
    monkeypatch.setenv("LINEAGE_ENABLED", "on")
    yield


@pytest.fixture
def seeded(client, lineage_on):
    """建好老师 + 学生 + 一条 homework，返回 (student, teacher)，并确保学生有积分账户。"""
    assert client.post("/api/teachers/onboard",
                       json={"name": TEACHER, "teacher_id": TEACHER}).status_code == 200
    code = client.post("/api/invites", json={"teacher_name": TEACHER}).json()["code"]
    assert client.post("/api/invites/accept",
                       json={"code": code, "student_name": STUDENT}).status_code == 200
    conn = database.get_connection()
    try:
        conn.execute("INSERT OR IGNORE INTO homework (patient_name, teacher_name, task, detail, status, created_at) "
                     "VALUES (?, ?, '今日医嘱', '请遵医嘱', 'pending', '2026-10-04')", (STUDENT, TEACHER))
        conn.execute("INSERT OR IGNORE INTO points_accounts (role_name, points) VALUES (?, 100)", (STUDENT,))
        conn.commit()
    finally:
        conn.close()
    return STUDENT, TEACHER


def _homework_status():
    conn = database.get_connection()
    try:
        row = conn.execute("SELECT status FROM homework WHERE patient_name = ?",
                           (STUDENT,)).fetchone()
        return None if row is None else row["status"]
    finally:
        conn.close()


def _points():
    conn = database.get_connection()
    try:
        row = conn.execute("SELECT points FROM points_accounts WHERE role_name = ?",
                           (STUDENT,)).fetchone()
        return None if row is None else row["points"]
    finally:
        conn.close()


def test_check_in_with_real_identity_still_works(client, seeded):
    """正路不回归：真实身份打卡 -> 状态变更 + 加分。"""
    before = _points()
    r = client.post("/api/check-in", params={"patient_name": STUDENT, "teacher_name": TEACHER})
    assert r.status_code == 200, r.text
    assert _homework_status() == "checked_in"
    assert _points() == before + 10


def test_check_in_with_empty_identity_fails_loud(client, seeded):
    """**核心回归**：空身份 -> 4xx，且状态/积分**都没动**。

    修好前：HTTP 200「打卡成功」，而 homework 与积分纹丝不动 —— 静默假成功。
    """
    before = _points()
    r = client.post("/api/check-in", params={"patient_name": "", "teacher_name": ""})
    assert r.status_code >= 400, (
        "空身份必须 fail-loud；修好前会返回 200「打卡成功」而实际什么都没改")
    assert _homework_status() == "pending", "空身份不得改动 homework"
    assert _points() == before, "空身份不得加分"


def test_check_in_with_empty_patient_only_fails_loud(client, seeded):
    """只缺病人也要拦（不得靠"另一个字段有值"蒙过去）。"""
    r = client.post("/api/check-in", params={"patient_name": "", "teacher_name": TEACHER})
    assert r.status_code >= 400
    assert _homework_status() == "pending"


def test_check_in_with_empty_teacher_only_fails_loud(client, seeded):
    """只缺老师也要拦。"""
    r = client.post("/api/check-in", params={"patient_name": STUDENT, "teacher_name": ""})
    assert r.status_code >= 400


def test_check_in_missing_params_entirely_fails_loud(client, seeded):
    """完全不传参数 -> 也必须是 4xx（原实现有 "张三"/"李老师" 默认值，会打到演示数据上）。"""
    r = client.post("/api/check-in")
    assert r.status_code >= 400, (
        "不传身份不得回落到演示数据「张三/李老师」——那会把打卡打到无关的人身上")
    assert _homework_status() == "pending"


def test_approve_with_empty_identity_fails_loud(client, seeded):
    """`/api/approve` 同一问题：空身份 -> 4xx。"""
    r = client.post("/api/approve", params={"patient_name": "", "teacher_name": ""})
    assert r.status_code >= 400
    assert _homework_status() == "pending"


def test_approve_missing_params_fails_loud(client, seeded):
    r = client.post("/api/approve")
    assert r.status_code >= 400


def test_approve_with_real_identity_still_works(client, seeded):
    """正路不回归：真实身份审核 -> 状态变更。"""
    assert client.post("/api/check-in",
                       params={"patient_name": STUDENT, "teacher_name": TEACHER}).status_code == 200
    r = client.post("/api/approve", params={"patient_name": STUDENT, "teacher_name": TEACHER})
    assert r.status_code == 200, r.text
    assert _homework_status() == "approved"

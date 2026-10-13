"""签字 / 积分归属的老师必须是**实际操作的那位**，不得写死（D-074）。

【缺陷】`backend/main.py` 原在四处把老师名写死为演示老师「李老师」：
  · L481  `if role == "李老师"`        —— `get_role_data` 的角色判定
  · L831  `transfer_points(patient_name, "李老师", 50)` —— 签字时扣分对象
  · L1030 `get_points("李老师")`       —— `/api/points` 的 teacher_points

实测（flag 全开，新老师「新医生王」签字一张自己的草案）：

    签字后账户:  {'张三': 100, '李四': 100, '李老师': 550, '学生A': 50}
    学生A    -> 50     ← 得 50（正确）
    新医生王  -> 无账户  ← **实际签字的老师，一分未扣**
    李老师    -> 550    ← 多了 50（原 500）—— **从没参与签字**

叠加效应：`transfer_points` 用 `UPDATE`，账户不存在时**静默不生效**
→ 分数凭空产生、账目不平，而接口照样返回「积分已支付」。

本文件钉住**修好后的行为**：积分归属与读取都跟随实际老师。
"""

import os
import sys

import pytest

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BACKEND_DIR)

import database
import lineage_service

T1 = "积分医生甲"
T2 = "积分医生乙"
STUDENT = "积分学生"


@pytest.fixture
def lineage_on(monkeypatch):
    """内测主路径要求师门隔离已启用。

    注：`conftest.py` 统一开了 TEMPLATE_API_ENABLED / AGENT_STAGE_ENABLED，但**没开**
    `LINEAGE_ENABLED`（需要验「关闭态」的用例自行 monkeypatch）。此处显式打开。
    （`test_core_loop.py` 有同名 fixture；两处各自定义，避免改动 conftest 影响存量用例。）
    """
    monkeypatch.setenv("LINEAGE_ENABLED", "on")
    yield lineage_service.default_lineage_id(T1)


@pytest.fixture
def teacher_with_student(client, lineage_on, monkeypatch):
    """入社区 + 邀请学生 + 转写生成草案，返回草案 id。

    ⚠️ `client` fixture 会删库重建，而 `lineage_on` 的 monkeypatch 在**模块导入后**才生效
    —— 故本 fixture 内**再次显式设置** LINEAGE_ENABLED，确保转写时的 flag 状态确定。
    转写必须带 `lineage_id`（flag on 时的契约，见 D-054），否则 400 `lineage_required`。
    """
    monkeypatch.setenv("LINEAGE_ENABLED", "on")

    def _setup(teacher: str):
        assert client.post("/api/teachers/onboard",
                           json={"name": teacher, "teacher_id": teacher}).status_code == 200
        code = client.post("/api/invites", json={"teacher_name": teacher}).json()["code"]
        assert client.post("/api/invites/accept",
                           json={"code": code, "student_name": STUDENT}).status_code == 200
        lin = database._derived_lineage_id(teacher)
        r = client.post("/api/transcribe", json={
            "patient_name": STUDENT, "teacher_name": teacher,
            "content": "头痛三天", "data_type": "text", "lineage_id": lin,
        })
        assert r.status_code == 200, r.text
        drafts = database.get_drafts(teacher_name=teacher, lineage_id=lin)
        assert drafts, "草案应已生成"
        return drafts[0]["id"]
    return _setup


def _points(role_name):
    conn = database.get_connection()
    try:
        row = conn.execute("SELECT points FROM points_accounts WHERE role_name = ?",
                           (role_name,)).fetchone()
        return None if row is None else row["points"]
    finally:
        conn.close()


def _ensure_account(role_name, points):
    conn = database.get_connection()
    try:
        conn.execute("INSERT OR IGNORE INTO points_accounts (role_name, points) VALUES (?, ?)",
                     (role_name, points))
        conn.commit()
    finally:
        conn.close()


def test_sign_moves_points_from_patient_to_actual_teacher(client, teacher_with_student):
    """**核心回归**：签字后积分从**学生**流向**草案所属老师**。

    `transfer_points(from_role=patient_name, to_role=<老师>, 50)`
    —— 方向是「学生完成学习 → 老师获得回报」。

    修好前：受方写死「李老师」-> 新医生王的账户纹丝不动（实测 500 不变），
    而从未参与签字的「李老师」凭空 +50（实测 500 -> 550）。
    """
    draft_id = teacher_with_student(T1)
    _ensure_account(T1, 500)
    _ensure_account(STUDENT, 100)

    seeded_before = _points("李老师")
    teacher_before = _points(T1)
    student_before = _points(STUDENT)

    resp = client.post("/api/drafts/%s/sign" % draft_id,
                       json={"final_plan": "桂枝汤", "final_content": "病历"})
    assert resp.status_code == 200, resp.text
    assert "error" not in resp.json()

    assert _points(T1) == teacher_before + 50, (
        "实际签字的老师必须 +50（修好前是「李老师」被加分）")
    assert _points(STUDENT) == student_before - 50, "学生必须被扣 50"
    assert _points("李老师") == seeded_before, (
        "演示老师「李老师」不得被动到 —— 它没参与这次签字")


def test_sign_credits_the_teacher(client, teacher_with_student):
    """签字后老师得 50（方向：学生 -> 老师）。"""
    draft_id = teacher_with_student(T1)
    _ensure_account(T1, 500)
    _ensure_account(STUDENT, 100)

    resp = client.post("/api/drafts/%s/sign" % draft_id,
                       json={"final_plan": "桂枝汤", "final_content": "病历"})
    assert resp.status_code == 200
    assert _points(T1) == 550
    assert _points(STUDENT) == 50


def test_two_teachers_are_credited_independently(client, teacher_with_student):
    """两位老师各自签字 —— 各得各的，不互相串（「去单例锁」在积分上的体现）。"""
    d1 = teacher_with_student(T1)
    d2 = teacher_with_student(T2)
    _ensure_account(T1, 500)
    _ensure_account(T2, 500)
    _ensure_account(STUDENT, 100)

    assert client.post("/api/drafts/%s/sign" % d1,
                       json={"final_plan": "方一", "final_content": "c1"}).status_code == 200
    assert client.post("/api/drafts/%s/sign" % d2,
                       json={"final_plan": "方二", "final_content": "c2"}).status_code == 200

    assert _points(T1) == 550
    assert _points(T2) == 550


def test_points_endpoint_reads_the_requested_teacher(client, teacher_with_student):
    """/api/points?teacher_name=X 必须返回**X**的积分，不是「李老师」的。

    修好前：无论问谁，teacher_points 都返回「李老师」的分数。
    """
    teacher_with_student(T1)
    _ensure_account(T1, 321)
    seeded = _points("李老师")

    body = client.get("/api/points", params={"patient_name": STUDENT,
                                             "teacher_name": T1}).json()
    assert body["teacher_points"] == 321, (
        "应返回查询老师（%s）的积分；修好前恒返回「李老师」的 %s" % (T1, seeded))
    assert body["patient_points"] == _points(STUDENT)


def test_points_endpoint_without_teacher_name_still_works(client):
    """/api/points 不传 teacher_name 时仍可用（向后兼容，回落到既有默认）。"""
    resp = client.get("/api/points", params={"patient_name": STUDENT})
    assert resp.status_code == 200
    body = resp.json()
    assert "teacher_points" in body and "patient_points" in body

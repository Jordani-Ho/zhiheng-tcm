"""内测核心闭环 + 接诊四路径的守护测试（D-053 / D-054）。

覆盖两批内测阻塞缺陷的回归：

**A. 写路径漏写 `lineage_id`（D-054）**
Epic 4 给**读路径**加了 `lineage_id = ?` 过滤（flag on 时），但四条写入路径漏写该列
→ **刚写入的行立刻查不到**。症状全是「接口返回成功、列表却为空」：
  · `transcriptions` → `/api/transcribe` 报「转述失败」
  · `drafts`         → 报「草案已生成」但草案列表空
  · `patient_records`/`homework` → 报「签字成功已归档」但病历与随访皆空

**B. 接诊四路径（D-053）**
`appointments.is_remote` 列早已存在，但 `AppointmentInput` 没有该字段、`create_appointment`
也不写该列 → **场景 4「远程诊断」用接口造不出来**。同时预约层两处时间戳硬编码。

夹具口径：用 conftest 的 `client`（`TestClient(main.app)`，路由齐全），
DB 指向独立 `backend/test.db` —— **绝不碰 `backend/zhiheng.db`**。
"""
import os
import sys
from datetime import datetime

import pytest

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BACKEND_DIR)

import database
import lineage_service

TEACHER = "内测老师甲"
STUDENT = "内测学生甲"
LINEAGE_FLAG = "LINEAGE_ENABLED"


@pytest.fixture
def lineage_on(monkeypatch):
    """内测主路径要求师门隔离已启用。"""
    monkeypatch.setenv(LINEAGE_FLAG, "on")
    yield lineage_service.default_lineage_id(TEACHER)


def _setup_teacher_and_student(client):
    """老师入社区 + 邀请 1 名学生（内测场景 1、2）。"""
    assert client.post("/api/teachers/onboard",
                       json={"name": TEACHER, "teacher_id": TEACHER}).status_code == 200
    code = client.post("/api/invites", json={"teacher_name": TEACHER}).json()["code"]
    assert client.post("/api/invites/accept",
                       json={"code": code, "student_name": STUDENT}).status_code == 200


def _column(conn, sql, params=()):
    row = conn.execute(sql, params).fetchone()
    return None if row is None else row[0]


# ---------------------------------------------------------------------------
# A. 写路径 lineage_id 回填
# ---------------------------------------------------------------------------
def test_transcribe_chain_visible_under_lineage(client, lineage_on):
    """**核心回归**：转写 → 草案 → 签字 → 病历 + 随访，flag on 时全链可查。

    这是内测核心闭环的端到端守卫。任一条断言失败，内测第一天就会出现
    「接口全成功、界面全空白」。
    """
    lin = lineage_on
    _setup_teacher_and_student(client)

    # ① 转写（非预约面诊入口）
    resp = client.post("/api/transcribe", json={
        "patient_name": STUDENT, "teacher_name": TEACHER,
        "content": "头疼三天，怕冷", "data_type": "text", "lineage_id": lin})
    assert resp.status_code == 200, resp.text
    assert "转述失败" not in str(resp.json()), (
        "转写落库后立刻查不到 = transcriptions 漏写 lineage_id（D-054）")

    # ② 草案
    drafts = database.get_drafts(teacher_name=TEACHER, lineage_id=lin)
    assert len(drafts) == 1, "草案列表为空 = drafts 漏写 lineage_id（D-054）"
    draft_id = drafts[0]["id"]

    # ③ 签字
    resp = client.post("/api/drafts/%s/sign" % draft_id, json={
        "final_plan": "桂枝汤加减", "teacher_name": TEACHER, "lineage_id": lin})
    assert resp.status_code == 200, resp.text

    # ④ 病历（历史表）
    records = database.get_patient_records(patient_name=STUDENT, teacher_name=TEACHER, lineage_id=lin)
    assert len(records) == 1, "病历为空 = patient_records 漏写 lineage_id（D-054）"
    assert records[0]["final_plan"] == "桂枝汤加减"

    # ⑤ 随访作业（`get_homework` 返回单条 dict 或 None）
    hw = database.get_homework(STUDENT, TEACHER, lineage_id=lin)
    assert hw is not None, "随访为空 = homework 漏写 lineage_id（D-054）"
    assert "桂枝汤加减" in hw["task"]


def test_each_write_path_writes_lineage_id(client, lineage_on):
    """机制层：四条写入路径必须各自把 `lineage_id` 落成推导值（直接查列，不看接口投影）。

    与上一条的区别：上条验「查得到」，本条验「列本身正确」——
    即使未来读路径容错，这条也能独立钉住写入侧的完整性。

    ⚠️ **顺序约束**：`sign_draft` 既有行为是**删除**转写行与草案行（`:1029-1030`），
    故 `transcriptions` 的断言必须在签字**之前**做，否则查到的是已被删掉的行（Forever None）。
    """
    lin = lineage_on
    _setup_teacher_and_student(client)
    client.post("/api/transcribe", json={
        "patient_name": STUDENT, "teacher_name": TEACHER,
        "content": "咳嗽", "data_type": "text", "lineage_id": lin})

    conn = database.get_connection()
    try:
        assert _column(conn, "SELECT lineage_id FROM patient_teachers WHERE patient_name = ?",
                       (STUDENT,)) == lin, "accept_invite 未写 lineage_id（D-052）"
        # 签字前查 —— 签字会删除转写行
        assert _column(conn, "SELECT lineage_id FROM transcriptions WHERE patient_name = ?",
                       (STUDENT,)) == lin, "insert_transcription 未写 lineage_id（D-054）"
    finally:
        conn.close()

    drafts = database.get_drafts(teacher_name=TEACHER, lineage_id=lin)
    assert len(drafts) == 1
    client.post("/api/drafts/%s/sign" % drafts[0]["id"], json={
        "final_plan": "止嗽散", "teacher_name": TEACHER, "lineage_id": lin})

    conn = database.get_connection()
    try:
        assert _column(conn, "SELECT lineage_id FROM patient_records WHERE patient_name = ?",
                       (STUDENT,)) == lin, "sign_draft 未写 patient_records.lineage_id（D-054）"
        assert _column(conn, "SELECT lineage_id FROM homework WHERE patient_name = ?",
                       (STUDENT,)) == lin, "sign_draft 未写 homework.lineage_id（D-054）"
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# B. 接诊四路径
# ---------------------------------------------------------------------------
def _make_appointment(client, student, time_str, is_remote=None):
    payload = {
        "patient_name": student, "teacher_name": TEACHER, "initiator": "student",
        "scheduled_date": "2026-12-01", "scheduled_time": time_str, "reason": "复诊",
    }
    if is_remote is not None:
        payload["is_remote"] = is_remote
    return client.post("/api/appointments", json=payload)


def test_appointment_onsite_defaults_to_not_remote(client, lineage_on):
    """场景 3：预约面诊 —— 不传 `is_remote` 时落库为 0（当面诊疗）。"""
    _setup_teacher_and_student(client)
    assert _make_appointment(client, STUDENT, "09:00").status_code == 200

    conn = database.get_connection()
    try:
        assert _column(conn, "SELECT is_remote FROM appointments WHERE scheduled_time = ?",
                       ("09:00",)) == 0
    finally:
        conn.close()


def test_appointment_remote_persists_flag(client, lineage_on):
    """**场景 4**：预约远程诊断 —— `is_remote=True` 必须落库为 1。

    修复前 `AppointmentInput` 没有该字段、`create_appointment` 也不写该列
    → 不论怎么传，所有预约恒为 `0=面诊`，远程诊断造不出来。
    """
    _setup_teacher_and_student(client)
    assert _make_appointment(client, STUDENT, "10:00", is_remote=True).status_code == 200

    conn = database.get_connection()
    try:
        assert _column(conn, "SELECT is_remote FROM appointments WHERE scheduled_time = ?",
                       ("10:00",)) == 1, "远程诊断未落库 is_remote=1（D-053）"
    finally:
        conn.close()


def test_walk_in_visit_needs_no_appointment(client, lineage_on):
    """非预约面诊 / 非预约远程：接诊链**不依赖预约**。

    这条钉住一个架构事实：`/api/generate-draft` 只收 `transcript_id`，
    从不要求就诊会话 —— 故「非预约」两条路径本来就不需要新建实体。
    """
    lin = lineage_on
    _setup_teacher_and_student(client)

    # 完全不开预约，直接接诊
    resp = client.post("/api/transcribe", json={
        "patient_name": STUDENT, "teacher_name": TEACHER,
        "content": "直接来诊", "data_type": "text", "lineage_id": lin})
    assert resp.status_code == 200, resp.text

    drafts = database.get_drafts(teacher_name=TEACHER, lineage_id=lin)
    assert len(drafts) == 1, "非预约接诊必须能独立走通（不依赖 appointments）"

    conn = database.get_connection()
    try:
        n = _column(conn, "SELECT COUNT(*) FROM appointments")
    finally:
        conn.close()
    assert n == 0, "非预约路径不得凭空产生预约记录"


def test_student_send_reaches_teacher(client, lineage_on):
    """**核心闭环入口守护（D-076）**：学生「确认发送」→ 老师端能看到草案。

    这是内测目标的第一个环节（录音/AI整理 → 病历草案 → 老师签字）。
    前端 `handleConfirmSend` 原先**不带 lineage_id** 且**不检查响应**
    → flag on 时 400，而界面照样清空输入、装作发送成功 → 老师端什么都没有。

    本用例从**学生侧解析 lineage** 出发（复现前端 `deriveCurrentLineageId` 的学生端规则：
    在 `/api/student-lineages` 里找 `teacher_name == 当前老师 && status == 'active' && lineage_id` 非空），
    再走转写，最后断言**老师端**能查到该草案。
    """
    lin = lineage_on
    _setup_teacher_and_student(client)

    # 学生侧：解析出「当前咨询老师」对应的活跃师门（前端 deriveCurrentLineageId 的学生端分支）
    sl = client.get("/api/student-lineages", params={"student_name": STUDENT})
    assert sl.status_code == 200, sl.text
    rows = sl.json().get("student_lineages")
    assert isinstance(rows, list), "形状应为 {student_lineages: [...]}（前端按此消费）"
    mine = [r for r in rows
            if r.get("teacher_name") == TEACHER and r.get("status") == "active" and r.get("lineage_id")]
    assert mine, "学生刚加入的师门应可解析出 lineage_id"
    student_lineage = mine[0]["lineage_id"]

    # 学生发送
    r = client.post("/api/transcribe", json={
        "patient_name": STUDENT, "teacher_name": TEACHER,
        "content": "学生自述：头痛三天", "data_type": "text",
        "lineage_id": student_lineage})
    assert r.status_code == 200, r.text

    # 老师端能看到草案（这才是「送达」的定义）
    drafts = database.get_drafts(teacher_name=TEACHER, lineage_id=lin)
    assert len(drafts) == 1, "老师端应能看到学生刚发送的内容生成的草案"
    assert drafts[0]["patient_name"] == STUDENT


def test_walk_in_onsite_entry_requires_lineage_id(client, lineage_on):
    """**D-076 契约钉**：老师现场录入（非预约面诊兜底）的 `/api/transcribe` **必须带 lineage_id**。

    背景：前端兜底 `createDraftViaTranscribe` 原先不带该字段 → flag on 时 400，
    而它**不检查响应** → 老师看到「落库失败：没能生成病历草案，无法签字」，
    内测场景 3「非预约面诊」在老师现场录入这条路上直接不可用。

    本用例把两端契约各自钉住（前端侧另有 vitest `draftFlow.test.ts`）：
      · 缺 lineage_id / 空串 → 400 `lineage_required`（**不许退化为全量**）
      · 带合法 lineage_id → 200，且草案随即生成
    """
    lin = lineage_on
    _setup_teacher_and_student(client)
    onsite = "【老师现场录入】\n学生姓名：%s\n就诊时间：2026年10月4日" % STUDENT

    # ① 缺字段 -> 400，且错误码明确
    r = client.post("/api/transcribe", json={
        "patient_name": STUDENT, "teacher_name": TEACHER,
        "content": onsite, "data_type": "text"})
    assert r.status_code == 400, "缺 lineage_id 必须 fail-loud（§5.2 漏改必 4xx）"
    assert r.json()["detail"]["error"] == "lineage_required"

    # ② 空串同样 400（空不得被当成"未启用"）
    r = client.post("/api/transcribe", json={
        "patient_name": STUDENT, "teacher_name": TEACHER,
        "content": onsite, "data_type": "text", "lineage_id": ""})
    assert r.status_code == 400

    # ③ 带上合法 id -> 成功，且草案已生成（这才是前端兜底该走的形态）
    r = client.post("/api/transcribe", json={
        "patient_name": STUDENT, "teacher_name": TEACHER,
        "content": onsite, "data_type": "text", "lineage_id": lin})
    assert r.status_code == 200, r.text
    assert "转述失败" not in str(r.json())

    drafts = database.get_drafts(teacher_name=TEACHER, lineage_id=lin)
    assert len(drafts) == 1, "现场录入后应生成草案，老师才能继续签字"


def test_appointment_timestamps_are_real(client, lineage_on):
    """时间戳必须是真实时间（原 `created_at` 硬编码 2026-09-21、`confirmed_at` 硬编码 2026-09-20）。

    用「年份与当前年份一致」做判据：不依赖精确时刻，也不会因为跨天而 flaky。
    """
    _setup_teacher_and_student(client)
    assert _make_appointment(client, STUDENT, "11:00").status_code == 200

    conn = database.get_connection()
    try:
        created_at = _column(conn, "SELECT created_at FROM appointments WHERE scheduled_time = ?",
                             ("11:00",))
        appt_id = _column(conn, "SELECT id FROM appointments WHERE scheduled_time = ?", ("11:00",))
    finally:
        conn.close()

    assert created_at, "created_at 不得为空"
    assert str(datetime.now().year) in str(created_at), (
        "created_at 是硬编码旧日期（原为 '2026-09-21'），不是真实时间")

    assert client.post("/api/appointments/%s/confirm" % appt_id).status_code == 200
    conn = database.get_connection()
    try:
        confirmed_at = _column(conn, "SELECT confirmed_at FROM appointments WHERE id = ?", (appt_id,))
    finally:
        conn.close()
    assert str(datetime.now().year) in str(confirmed_at), (
        "confirmed_at 是硬编码旧日期（原为 '2026-09-20'），不是真实时间")

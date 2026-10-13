"""内测验收旅程（D-081）—— 把 `team/INTERNAL-TEST-CHECKLIST.md` §3.1 的验收表**编码成自动化测试**。

【为什么要这条】前几轮反复出现的缺陷都是「**接口返回成功、界面却什么都没变**」
（D-074 积分算错人、D-076/D-078 `lineage_id` 缺失导致 400、D-079 空身份假成功）。
这类缺陷**不会让任何单元测试失败**，只看单个端点也都"正常"。

真正能抓住它们的，是**把完整旅程跑一遍、并逐环节断言"状态真的变了"**。
本文件就是这件事：不测单个端点，测**一条真实内测路径从入社区到学生看到随访**。

【覆盖的内测场景】
  场景 1 老师入社区
  场景 2 邀请 ≥3 学生入社区
  场景 3 面诊：预约面诊 / 非预约面诊
  场景 4 远程诊断：预约远程 / 非预约远程
  核心闭环：转写 → 草案 → 老师签字 → 学生见档案与随访

【另加】两位老师**数据不串**（D-070 是前端侧的串台；本用例钉后端侧隔离）。
"""

import os
import sys

import pytest

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BACKEND_DIR)

import database
import lineage_service


def _id(x):
    return ("".join(ch for ch in x if ch.isascii() and ch.isalnum()) or "T")[:12]


TEACHER_A = "旅程医生A"
TEACHER_B = "旅程医生B"
STUDENTS_A = ["旅程学生A1", "旅程学生A2", "旅程学生A3"]
STUDENT_B = "旅程学生B1"


@pytest.fixture
def lineage_on(monkeypatch):
    monkeypatch.setenv("LINEAGE_ENABLED", "on")
    yield
    # 交给 pytest 的 monkeypatch 还原


def _onboard(client, teacher):
    r = client.post("/api/teachers/onboard", json={"name": teacher, "teacher_id": teacher})
    assert r.status_code == 200, r.text
    return r.json()


def _invite_and_join(client, teacher, student):
    """场景 2：发邀请码 → 学生持码入社区。返回邀请码。"""
    r = client.post("/api/invites", json={"teacher_name": teacher})
    assert r.status_code == 200, r.text
    code = r.json()["code"]
    r = client.post("/api/invites/accept", json={"code": code, "student_name": student})
    assert r.status_code == 200, r.text
    assert not r.json().get("error"), r.json()
    return code


def test_full_internal_test_journey(client, lineage_on):
    """**一条走完的旅程**：两师各 3 学生，四场景 + 核心闭环，逐环节断言「状态真的变了」。"""
    lin_a = lineage_service.default_lineage_id(TEACHER_A)
    lin_b = lineage_service.default_lineage_id(TEACHER_B)

    # ---------- 场景 1：老师入社区（两位，验证多老师不是单例） ----------
    info_a = _onboard(client, TEACHER_A)
    info_b = _onboard(client, TEACHER_B)
    assert info_a["teacher_created"] is True
    assert info_a["lineage"]["id"] == lin_a, "入社区应同时建成该老师的师门"
    assert info_b["lineage"]["id"] == lin_b
    assert lin_a != lin_b, "两位老师必须是不同师门"

    # 幂等：重复入社区不重复创建
    again = _onboard(client, TEACHER_A)
    assert again["teacher_created"] is False

    # ---------- 场景 2：邀请 >=3 学生 ----------
    for s in STUDENTS_A:
        _invite_and_join(client, TEACHER_A, s)
    _invite_and_join(client, TEACHER_B, STUDENT_B)

    # 老师端学生列表（这是「邀请成功」的真正定义：老师看得见）
    tp_a = client.get("/api/teacher-patients",
                      params={"teacher_name": TEACHER_A, "lineage_id": lin_a})
    assert tp_a.status_code == 200, tp_a.text
    assert {x["name"] for x in tp_a.json()} >= set(STUDENTS_A), "老师 A 应看到自己全部 3 名学生"

    tp_b = client.get("/api/teacher-patients",
                      params={"teacher_name": TEACHER_B, "lineage_id": lin_b})
    assert {x["name"] for x in tp_b.json()} == {STUDENT_B}

    # ---------- 数据隔离：A 看不到 B 的学生，反之亦然 ----------
    assert STUDENT_B not in {x["name"] for x in tp_a.json()}
    assert not (set(STUDENTS_A) & {x["name"] for x in tp_b.json()})

    # ---------- 场景 3/4：面诊（预约）与远程（预约） ----------
    s0 = STUDENTS_A[0]
    for time_str, is_remote in (("09:00", False), ("10:00", True)):
        r = client.post("/api/appointments", json={
            "patient_name": s0, "teacher_name": TEACHER_A, "initiator": "student",
            "scheduled_date": "2026-12-01", "scheduled_time": time_str,
            "reason": "复诊", "is_remote": is_remote,
        })
        assert r.status_code == 200, r.text

    conn = database.get_connection()
    try:
        rows = {r["scheduled_time"]: r["is_remote"] for r in conn.execute(
            "SELECT scheduled_time, is_remote FROM appointments WHERE teacher_name = ?", (TEACHER_A,))}
    finally:
        conn.close()
    assert rows == {"09:00": 0, "10:00": 1}, "预约面诊=0 / 预约远程=1 必须落库正确"

    # ---------- 场景 3/4：非预约（直接接诊，不建预约） ----------
    before_appts = len(rows)
    r = client.post("/api/transcribe", json={
        "patient_name": s0, "teacher_name": TEACHER_A, "content": "非预约直接来诊：头痛",
        "data_type": "text", "lineage_id": lin_a})
    assert r.status_code == 200, r.text
    conn = database.get_connection()
    try:
        after_appts = conn.execute("SELECT COUNT(*) c FROM appointments WHERE teacher_name = ?",
                                   (TEACHER_A,)).fetchone()["c"]
    finally:
        conn.close()
    assert after_appts == before_appts, "非预约接诊不得凭空产生预约记录"

    # ---------- 核心闭环：转写 → 草案 → 签字 → 病历 + 随访 ----------
    # 注：s0 在场景 3/4 里做过一次「非预约转写」→ 已有一条草案；本步**签它**，
    # 不假设"只有一条草案"（每次转写各生成一条，属既有设计）。
    drafts = database.get_drafts(teacher_name=TEACHER_A, lineage_id=lin_a)
    assert drafts, "转写后老师端应能看到草案（这是「送达」的定义）"
    target = [d for d in drafts if d["patient_name"] == s0][0]
    assert "非预约直接来诊" in target["content"], "应能拿到该学生刚转写的那条草案"

    r = client.post("/api/drafts/%s/sign" % target["id"], json={
        "final_plan": "桂枝汤加减", "final_content": "完整病历：头痛三天，怕冷"})
    assert r.status_code == 200, r.text
    assert not r.json().get("error"), r.json()

    # ⚠️ 落库口径（**既有设计，勿按直觉改**）：
    #   · `patient_records.final_plan` 存的是 `final_content`（完整病历）；
    #     传了 final_content 时 final_plan 不再进该列（见 database.sign_draft 的
    #     `patient_record_content = final_content if final_content else final_plan`）
    #   · `homework.task` 用的才是 `final_plan`（"今日医嘱：<final_plan>"）
    #   早期 byte-exact 用例（test_agent_stage.py）已钉住该行为。
    records = database.get_patient_records(patient_name=s0, teacher_name=TEACHER_A, lineage_id=lin_a)
    assert len(records) == 1, "签字后病历必须可查（D-054 的回归点）"
    assert records[0]["final_plan"] == "完整病历：头痛三天，怕冷", "病历列存 final_content（既有设计）"
    assert "非预约直接来诊" in str(records[0]["ai_draft"]), "AI 原稿应保留 drafted 内容"

    hw = database.get_homework(s0, TEACHER_A, lineage_id=lin_a)
    assert hw is not None, "签字后必须生成随访作业"
    assert "桂枝汤加减" in hw["task"], "随访任务用的是 final_plan（既有设计）"

    # ---------- 学生见随访：role-data 应显示该作业 ----------
    # 字段口径（实测）：学生端 `task` = 作业任务本人（"今日医嘱：…"），`detail` = 执行说明
    rd = client.get("/api/role-data", params={
        "role": "学生", "patient_name": s0, "teacher_name": TEACHER_A, "lineage_id": lin_a})
    assert rd.status_code == 200, rd.text
    assert "桂枝汤" in str(rd.json().get("task")), "学生端 task 应显示自己的随访医嘱"

    # ---------- 学生打卡 → 老师待审核 → 老师审核 ----------
    r = client.post("/api/check-in", params={"patient_name": s0, "teacher_name": TEACHER_A})
    assert r.status_code == 200, r.text
    assert database.get_homework(s0, TEACHER_A, lineage_id=lin_a)["status"] == "checked_in"

    rd_t = client.get("/api/role-data", params={
        "role": TEACHER_A, "patient_name": s0, "teacher_name": TEACHER_A, "lineage_id": lin_a})
    assert rd_t.status_code == 200, rd_t.text
    assert rd_t.json()["task"] == "待审核", "老师端应看到待审核"
    assert "已打卡" in str(rd_t.json().get("detail"))

    r = client.post("/api/approve", params={"patient_name": s0, "teacher_name": TEACHER_A})
    assert r.status_code == 200, r.text
    assert database.get_homework(s0, TEACHER_A, lineage_id=lin_a)["status"] == "approved"

    # ---------- 闭环收尾：另一位学生也走一遍（证明不是"只能走一次"） ----------
    s1 = STUDENTS_A[1]
    r = client.post("/api/transcribe", json={
        "patient_name": s1, "teacher_name": TEACHER_A, "content": "学生自述：咳嗽两天",
        "data_type": "text", "lineage_id": lin_a})
    assert r.status_code == 200, r.text
    d1 = [d for d in database.get_drafts(teacher_name=TEACHER_A, lineage_id=lin_a)
          if d["patient_name"] == s1]
    assert d1, "第二位学生同样应生成草案"
    assert client.post("/api/drafts/%s/sign" % d1[0]["id"], json={
        "final_plan": "止嗽散", "final_content": "咳嗽两天"}).status_code == 200
    assert len(database.get_patient_records(patient_name=s1, teacher_name=TEACHER_A,
                                            lineage_id=lin_a)) == 1

    # ---------- 老师隔离：A 的病历里不应出现 B 的学生 ----------
    recs_a = database.get_patient_records(teacher_name=TEACHER_A, lineage_id=lin_a)
    assert {r["patient_name"] for r in recs_a} == {s0, s1}
    recs_b = database.get_patient_records(teacher_name=TEACHER_B, lineage_id=lin_b)
    assert recs_b == [], "老师 B 没有任何签字，不应看到别人师门的病历"


def test_each_scenario_fails_loud_without_lineage(client, lineage_on):
    """**契约面**：四场景的关键端点缺 `lineage_id` 时必须 4xx，不得静默退化。

    前几轮的缺陷全是"漏传 lineage_id"（D-054 / D-076 / D-078），
    本用例把所有相关端点一次性钉住 —— 以后新增端点漏了，这里会先响。
    """
    lin = lineage_service.default_lineage_id(TEACHER_A)
    _onboard(client, TEACHER_A)
    _invite_and_join(client, TEACHER_A, STUDENTS_A[0])
    s = STUDENTS_A[0]

    # 转写（学生发送 / 老师现场录入都走它）
    r = client.post("/api/transcribe", json={
        "patient_name": s, "teacher_name": TEACHER_A, "content": "x", "data_type": "text"})
    assert r.status_code == 400 and r.json()["detail"]["error"] == "lineage_required"

    # 老师端学生列表
    r = client.get("/api/teacher-patients", params={"teacher_name": TEACHER_A})
    assert r.status_code == 400, "老师端读点缺 lineage_id 必须 4xx（不得退化为全量）"

    # 草案列表
    r = client.get("/api/drafts", params={"teacher_name": TEACHER_A})
    assert r.status_code == 400

    # 病历
    r = client.get("/api/patient-records", params={"teacher_name": TEACHER_A})
    assert r.status_code == 400

    # 补上 lineage_id 后全部可用（避免"一律 400"的假阳性）
    assert client.get("/api/teacher-patients",
                      params={"teacher_name": TEACHER_A, "lineage_id": lin}).status_code == 200
    assert client.get("/api/drafts",
                      params={"teacher_name": TEACHER_A, "lineage_id": lin}).status_code == 200

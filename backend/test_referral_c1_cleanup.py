"""P-102 · C1 引荐链清理的守护（D-089）。

【背景】学生引荐亲友（C1）是**活的越权面**：`POST /api/referral/student` 可被学生调用
创建引荐记录，并带一套「年度额度 3 位」的配额闸。而白皮书 v2.1 §4.1.1 逐字：

> 「引荐**不是**『审核资格』，是『我愿意为他背书』」

**额度是一种审核**，与宪法冲突（INSTR-02 §1.1）。且 `§4.3.1` 只定义引荐「单向、一次性」——
是逐次语义，**不是年度配额**。

【本次清理的 8 删 + 1 迁移】
  1. `referral_service.create_student_referral`          删
  2. `database.REFERRAL_ANNUAL_QUOTA`                    删
  3. `database.count_referrals_by_referrer_in_year`      删
  4. `database.REFERRAL_REFERRER_TYPES`                  去 'STUDENT'
  5. `database.REFERRAL_REFEREE_TYPES`                   去 'STUDENT'/'DEPENDENT'
  6. `referral_api` 的 `POST /api/referral/student` 等   删
  7. `test_referral_api.py` 的 4 条学生引荐测试          删（见 §7 注）
  8. 前端学生引荐 UI                                     ✅ 已核实无需施工
  9. 新迁移 `0009`                                       清理白名单 + 删函数

【本文件是**新增的守护**】原来那 4 条测试是「验学生引荐能用」——与清理方向相反，
删掉后没有任何用例能防止它**被重新加回来**。故本文件钉住：
  · 端点已不存在（404，而非 200）
  · 白名单里不再有 STUDENT / DEPENDENT
  · 额度常量与额度函数已不存在
  · **老师引荐老师仍正常**（避免清理误伤正路）
"""

import os
import sys

import pytest

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BACKEND_DIR)

import database
import migrations_runner
import referral_service


@pytest.fixture
def referral_on(monkeypatch):
    monkeypatch.setenv("REFERRAL_ENABLED", "on")
    yield


@pytest.fixture
def db():
    """每个用例前重建 test.db（照 `test_learning.db` / `test_agent_stage.db` 同款前置）：
    删库 → `init_db()` → alembic 迁移。返回 `database` 模块本身。"""
    if os.path.exists(database.DB_PATH):
        os.remove(database.DB_PATH)
    database.init_db()
    migrations_runner.run_upgrade()
    return database


# ---------------------------------------------------------------------------
# 1. 端点已下线
# ---------------------------------------------------------------------------
def test_student_referral_endpoint_is_gone(client, referral_on):
    """`POST /api/referral/student` 必须**不可用**，不得仍是 200。

    修好前：该端点 200 + 返回 referral_id —— 学生可以凭空建引荐记录（越权面）。

    ⚠️ 期望状态码是 **404 或 405**，原因：`/api/referral/{referral_id}` 是参数路由，
    会把字面量 "student" 当作 `referral_id` 匹配 —— 于是 POST 落到「路径存在但方法不允许」
    → **405**；若参数路由不存在则会是 404。**两者都证明"学生引荐端点已下线"**，
    故断言 `in (404, 405)`；关键否定条件是**不得为 200**（那才是越权面复活）。
    """
    r = client.post("/api/referral/student", json={
        "referrer_id": "S-001", "referee_id": "C-001", "referee_type": "STUDENT"})
    assert r.status_code in (404, 405), (
        "学生引荐端点必须已下线（404/405）；实际 %s —— 若为 200 说明 C1 越权面又回来了"
        % r.status_code)


def test_student_path_does_not_leak_through_param_route(client, referral_on):
    """`GET /api/referral/student` 会被参数路由吃掉 —— 必须 404，**不得吐出任何记录**。

    这是"端点已删"的**真正安全边界**：参数路由会把 "student" 当 referral_id，
    若 `get_referral` 对未知 id 返回 None 之外的任何东西，就会意外暴露数据。
    """
    r = client.get("/api/referral/student")
    assert r.status_code == 404, (
        "以 'student' 为 referral_id 查询必须 404；实际 %s" % r.status_code)


# ---------------------------------------------------------------------------
# 2. 白名单收窄
# ---------------------------------------------------------------------------
def test_referrer_types_exclude_student():
    """`REFERRAL_REFERRER_TYPES` 不得含 'STUDENT'（引荐人只能是老师）。"""
    assert "STUDENT" not in database.REFERRAL_REFERRER_TYPES
    assert "TEACHER" in database.REFERRAL_REFERRER_TYPES


def test_referee_types_exclude_student_and_dependent():
    """`REFERRAL_REFEREE_TYPES` 不得含 'STUDENT' / 'DEPENDENT'（师生引荐已去掉）。"""
    assert "STUDENT" not in database.REFERRAL_REFEREE_TYPES
    assert "DEPENDENT" not in database.REFERRAL_REFEREE_TYPES
    assert "TEACHER" in database.REFERRAL_REFEREE_TYPES


def test_insert_rejects_student_referrer(db):
    """底线：即便有人绕过 API 直接调库层，也**不能**用 STUDENT 当引荐人。"""
    with pytest.raises(ValueError):
        db.insert_referral_chain(referrer_id="S-001", referrer_type="STUDENT",
                                 referee_id="T-001", referee_type="TEACHER")


def test_insert_rejects_dependent_referee(db):
    """DEPENDENT 同样被拒（它只服务学生引荐亲友，已随之删除）。"""
    with pytest.raises(ValueError):
        db.insert_referral_chain(referrer_id="T-001", referrer_type="TEACHER",
                                 referee_id="C-001", referee_type="DEPENDENT")


# ---------------------------------------------------------------------------
# 3. 额度相关死代码已清
# ---------------------------------------------------------------------------
def test_annual_quota_constant_is_gone():
    """`REFERRAL_ANNUAL_QUOTA` 已删（额度与宪法 §4.1.1「不是审核资格」冲突）。"""
    assert not hasattr(database, "REFERRAL_ANNUAL_QUOTA"), (
        "年度额度常量必须已删除 —— 它是「给背书动作装配额闸」的载体")


def test_quota_counter_is_gone():
    """`count_referrals_by_referrer_in_year` 已删（唯一用途是额度校验）。"""
    assert not hasattr(database, "count_referrals_by_referrer_in_year")


def test_student_referral_service_function_is_gone():
    """服务层 `create_student_referral` 已删。"""
    assert not hasattr(referral_service, "create_student_referral")


def test_annual_count_wrapper_is_gone():
    """`get_annual_referral_count` 已删 —— 它只封装「额度计数」，随之成为死代码。

    核实依据：全仓检索该符号，**除定义处外零引用**（无调用方、无测试）。
    """
    assert not hasattr(referral_service, "get_annual_referral_count")


# ---------------------------------------------------------------------------
# 4. 正路不被误伤
# ---------------------------------------------------------------------------
def test_teacher_referral_still_works(client, referral_on):
    """**老师引荐老师必须照常工作** —— 清理只针对学生引荐，不得误伤 M1 正路。"""
    r = client.post("/api/referral/teacher", json={
        "referrer_id": "T-001", "referee_id": "T-002", "referral_reason": "同门推荐"})
    assert r.status_code == 200, r.text
    rid = r.json().get("referral_id")
    assert rid, r.json()

    # 注：`GET /api/referral/{referral_id}` 的路径参数是**引荐 id**，不是 agent id
    # （双向链查询是另一个端点 `GET /api/referral/chain/{agent_id}`）。
    got = client.get("/api/referral/%s" % rid)
    assert got.status_code == 200, got.text
    assert got.json().get("referrer_type") == "TEACHER"

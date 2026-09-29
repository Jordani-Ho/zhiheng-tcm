"""【Epic 2】智能体五阶段 —— database.py 新增库函数的守护测试（§8 step 2.1：只覆盖 DB 层）

对齐：docs/epic2-agent-stage-design-v1.md §1.2 / §1.3 / §3.4–§3.6 / §4.2 / §7.1-①⑥，
以及 CTO 2026-09-28 的五项裁决（双闸门 / 服务层 flag / 不回落 content / 钩子两态 / 不吞 sqlite3.Error）。

本文件**只测 DB 层**（§6 的服务层与接口层用例在 step 3–4 于本文件继续追加）：
    ① 9 个新函数齐备 + 白名单 ↔ 0003 建表列一致 + 「审计表只增」；
    ② 状态表：无行 → None、upsert 幂等、局部更新不清零、白名单拦截、JSON 列中文不转义；
    ③ 审计表：只增写入 + 倒序 + limit 口径 + 必填 event_type；
    ④ 配置表：无行 → None、单行覆写、全局行与老师行互不影响；
    ⑤ 升级请示：去重查询、与既有 agent_tasks 通道字段同构、既有读写函数零改动可读；
    ⑥ 行动日志：新行能被既有 get_agent_action_log（工作台区块直接读的函数）读到；
    ⑦ 裁决⑤ 守正：表未就绪时 sqlite3.Error **冒泡**，不得被吞成 None / 空列表；
    ⑧ step 1 种子（存量老师状态行 / 全局配置行）↔ 本步新读函数 互通。

运行方式（Windows，串行；见 pytest.ini）：
    cd backend
    ..\\venv\\Scripts\\python.exe -m pytest test_agent_stage.py -v
"""
import json
import os
import sqlite3

import pytest

import database
import migrations_runner

TEACHER = "阶段测试老师甲"
OTHER_TEACHER = "阶段测试老师乙"

# 【重要】测试老师名必须避开「存量老师」名（如 init_db() 的演示老师「李老师」）：
# 0003 迁移会给迁移时已存在的每位老师各种一行 agent_stage_state（§7.1-② 存量不降级，
# stage='learning'），所以用存量老师名做「无行 → None」的用例会必然失败。
SEEDED_TEACHER = "李老师"

# §4.2 定的 action_data 形状（注意：目标阶段键是 "to"，不是 "to_stage"）
ACTION_DATA = {
    "action": "upgrade_agent_stage",
    "from": "learning",
    "to": "apprentice",
    "metrics": {"approved_rate": 0.92, "samples": 12},
    "config_source": {"layer": "teacher", "teacher_name": TEACHER},
}


@pytest.fixture
def db():
    """每个用例前重建 test.db（与 conftest.client 同款，只是不建 TestClient）：
    删库 → init_db() → alembic 迁移（templates / agent_stage* 三张表都走生产同一条迁移路径）。

    之所以不复用 conftest.client：DB 层用例不需要 HTTP，也不该被接口层的鉴权 / 启动钩子影响。
    """
    if os.path.exists(database.DB_PATH):
        os.remove(database.DB_PATH)
    database.init_db()
    migrations_runner.run_upgrade()
    return database


# ============ ① 存在性 / 白名单一致性 / 「只增」守护 ============

def test_agent_stage_functions_all_exist():
    """§4.2 的 8 个函数 + 补的 insert_agent_action_log（§4.5-① / §7.1-⑥）必须齐备。"""
    for name in (
        "get_agent_stage_state", "upsert_agent_stage_state",
        "insert_agent_stage_log", "get_agent_stage_logs",
        "get_agent_stage_config_row", "upsert_agent_stage_config",
        "find_pending_upgrade_task", "insert_agent_stage_upgrade_task",
        "insert_agent_action_log",
    ):
        assert callable(getattr(database, name, None)), "缺少库函数：%s" % name


def test_agent_stage_log_has_no_update_or_delete_function():
    """§1.3「只增」：库层不得存在任何改写阶段审计的函数（防线在代码层，不靠约定）。"""
    offenders = [
        name for name in dir(database)
        if "agent_stage_log" in name and name.startswith(("update_", "delete_", "set_", "clear_"))
    ]
    assert offenders == [], "阶段审计表出现了写改函数：%s" % offenders


def test_whitelists_match_migration_0003_columns(db):
    """白名单 ↔ 0003 建表列 逐列一致（列名漂移立刻红）。"""
    conn = database.get_connection()
    state_columns = {row["name"] for row in conn.execute("PRAGMA table_info('agent_stage_state')")}
    log_columns = {row["name"] for row in conn.execute("PRAGMA table_info('agent_stage_log')")}
    conn.close()

    assert set(database.AGENT_STAGE_STATE_UPSERT_FIELDS) | {"teacher_name"} == state_columns
    assert set(database.AGENT_STAGE_LOG_INSERT_FIELDS) | {"id", "teacher_name", "event_type"} == log_columns


# ============ ② 状态表 agent_stage_state ============

def test_stage_state_absent_returns_none_without_creating_row(db):
    assert db.get_agent_stage_state(TEACHER) is None
    conn = db.get_connection()
    count = conn.execute(
        "SELECT COUNT(*) FROM agent_stage_state WHERE teacher_name = ?", (TEACHER,)
    ).fetchone()[0]
    conn.close()
    assert count == 0, "「无行」不得被悄悄塞成默认行（§1.2：兜底属服务层）"


def test_upsert_stage_state_insert_then_read_roundtrip(db):
    db.upsert_agent_stage_state(
        TEACHER,
        lineage_id="lin-001", stage="apprentice", stage_since="2026-09-28T09:00:00",
        stage_source="manual", last_evaluated_at="2026-09-28T09:00:00",
        last_metrics_json={"approved_rate": 0.9, "样本": 5},
    )
    row = db.get_agent_stage_state(TEACHER)
    assert row["stage"] == "apprentice"
    assert row["lineage_id"] == "lin-001"
    assert row["stage_since"] == "2026-09-28T09:00:00"
    assert row["stage_source"] == "manual"
    assert row["updated_at"], "updated_at 未传时应自动补当前时间"
    assert json.loads(row["last_metrics_json"])["approved_rate"] == 0.9
    assert "样本" in row["last_metrics_json"], "json 列必须 ensure_ascii=False（中文不转义）"


def test_upsert_stage_state_is_idempotent_and_keeps_single_row(db):
    db.upsert_agent_stage_state(TEACHER, stage="observation", stage_since="T1")
    db.upsert_agent_stage_state(TEACHER, stage="learning", stage_since="T2")
    conn = db.get_connection()
    count = conn.execute(
        "SELECT COUNT(*) FROM agent_stage_state WHERE teacher_name = ?", (TEACHER,)
    ).fetchone()[0]
    conn.close()
    assert count == 1, "反复 upsert 必须始终只有一行"
    assert db.get_agent_stage_state(TEACHER)["stage"] == "learning"


def test_upsert_stage_state_partial_update_does_not_clear_other_columns(db):
    """只传变化字段时，其余列必须保持原值（不得被隐式清零/重置为建表默认值）。"""
    db.upsert_agent_stage_state(
        TEACHER, stage="learning", last_metrics_json={"approved": 3},
        pending_stage="apprentice", pending_task_id=7,
    )
    db.upsert_agent_stage_state(TEACHER, stage="apprentice")

    row = db.get_agent_stage_state(TEACHER)
    assert row["stage"] == "apprentice"
    assert json.loads(row["last_metrics_json"]) == {"approved": 3}
    assert row["pending_stage"] == "apprentice"
    assert row["pending_task_id"] == 7


def test_upsert_stage_state_rejects_unknown_field_before_writing(db):
    with pytest.raises(ValueError):
        db.upsert_agent_stage_state(TEACHER, stage_typo="apprentice")
    assert db.get_agent_stage_state(TEACHER) is None, "白名单拦截必须发生在写库之前"


def test_stage_state_is_isolated_per_teacher(db):
    db.upsert_agent_stage_state(TEACHER, stage="learning")
    assert db.get_agent_stage_state(TEACHER)["stage"] == "learning"
    assert db.get_agent_stage_state(OTHER_TEACHER) is None


# ============ ③ 审计表 agent_stage_log ============

def test_stage_log_append_returns_id_and_reads_back_desc(db):
    first = db.insert_agent_stage_log(
        TEACHER, "stage_upgraded", from_stage="learning", to_stage="apprentice",
        capability="draft", task_id=11, detail="达标升级", metrics_json={"approved_rate": 0.9},
    )
    second = db.insert_agent_stage_log(TEACHER, "config_changed", detail="老师手动改了配置")

    assert isinstance(first, int) and isinstance(second, int) and second > first

    logs = db.get_agent_stage_logs(TEACHER)
    assert [row["id"] for row in logs] == [second, first], "created_at DESC、同秒按 id DESC"
    assert logs[0]["event_type"] == "config_changed"
    assert logs[0]["created_at"], "created_at 未传时应自动补当前时间"
    assert logs[1]["from_stage"] == "learning" and logs[1]["to_stage"] == "apprentice"
    assert logs[1]["capability"] == "draft" and logs[1]["task_id"] == 11
    assert json.loads(logs[1]["metrics_json"])["approved_rate"] == 0.9


def test_stage_log_requires_event_type_and_rejects_unknown_field(db):
    with pytest.raises(ValueError):
        db.insert_agent_stage_log(TEACHER, "")
    with pytest.raises(ValueError):
        db.insert_agent_stage_log(TEACHER, "stage_upgraded", stage_typo="x")
    assert db.get_agent_stage_logs(TEACHER) == [], "被拒的写入不得留下任何行"


def test_stage_log_limit_normalization_and_scope(db):
    db.insert_agent_stage_log(TEACHER, "stage_upgraded")
    db.insert_agent_stage_log(TEACHER, "stage_demoted")
    db.insert_agent_stage_log(OTHER_TEACHER, "stage_upgraded")

    assert len(db.get_agent_stage_logs(TEACHER)) == 2
    assert len(db.get_agent_stage_logs(TEACHER, limit=1)) == 1
    # limit 口径与 get_agent_action_log 逐字一致：None / 非正数 → 默认 20
    assert len(db.get_agent_stage_logs(TEACHER, limit=None)) == 2
    assert len(db.get_agent_stage_logs(TEACHER, limit=0)) == 2
    assert db.get_agent_stage_logs(OTHER_TEACHER)[0]["id"] > 0
    assert db.get_agent_stage_logs("") == [], "空 teacher_name 不查库（与既有只读函数同款）"


# ============ ④ 配置表 agent_stage_config ============

def test_stage_config_row_absent_then_upsert_roundtrip(db):
    assert db.get_agent_stage_config_row(TEACHER) is None

    db.upsert_agent_stage_config(TEACHER, {"default_stage": "learning", "说明": "老师手动指定"})
    row = db.get_agent_stage_config_row(TEACHER)
    assert json.loads(row["config_json"])["default_stage"] == "learning"
    assert "说明" in row["config_json"], "json 列必须 ensure_ascii=False（中文不转义）"
    assert row["updated_at"], "updated_at 应写入当前时间"


def test_stage_config_global_row_and_teacher_row_are_independent(db):
    db.upsert_agent_stage_config("", {"default_stage": "observation"})   # 全局默认行（§3.5）
    db.upsert_agent_stage_config(TEACHER, {"default_stage": "learning"})

    assert json.loads(db.get_agent_stage_config_row("")["config_json"])["default_stage"] == "observation"
    assert json.loads(db.get_agent_stage_config_row(TEACHER)["config_json"])["default_stage"] == "learning"

    db.upsert_agent_stage_config(TEACHER, {"default_stage": "apprentice"})   # 覆写：仍只有一行
    conn = db.get_connection()
    count = conn.execute(
        "SELECT COUNT(*) FROM agent_stage_config WHERE teacher_name = ?", (TEACHER,)
    ).fetchone()[0]
    conn.close()
    assert count == 1
    assert json.loads(db.get_agent_stage_config_row(TEACHER)["config_json"])["default_stage"] == "apprentice"


# ============ ⑤ 升级推荐请示（复用既有 agent_tasks 通道）============

def _insert_care_task(teacher_name):
    """按 scan_silent_students 的字段集（category='student'、action=send_care_notice）裸插一行。

    用途：验证升级请示查询**不会误命中别的请示类型**。
    """
    conn = database.get_connection()
    conn.execute(
        "INSERT INTO agent_tasks (teacher_name, task_type, category, title, content, action_data, status, created_at) "
        "VALUES (?, 'request', 'student', ?, ?, ?, 'pending', ?)",
        (teacher_name, "小明已沉默 35 天", "是否发送关怀通知？",
         json.dumps({"action": "send_care_notice", "patient_name": "小明", "template": "care"}, ensure_ascii=False),
         "2026-09-28T09:00:00"),
    )
    conn.commit()
    conn.close()


def test_find_pending_upgrade_task_returns_none_when_absent_or_other_kind(db):
    assert db.find_pending_upgrade_task(TEACHER) is None

    _insert_care_task(TEACHER)
    assert db.find_pending_upgrade_task(TEACHER) is None, "沉默关怀请示不得被误判成升级请示"
    assert db.find_pending_upgrade_task(OTHER_TEACHER) is None, "查询必须限定在本老师范围内"


def test_find_pending_upgrade_task_hit_returns_parsed_action(db):
    task_id = db.insert_agent_stage_upgrade_task(TEACHER, "建议升级：见习期", "各指标已达标", ACTION_DATA)

    found = db.find_pending_upgrade_task(TEACHER)
    assert found is not None and found["id"] == task_id
    assert found["status"] == "pending"
    assert found["action"]["action"] == "upgrade_agent_stage"
    assert found["action"]["from"] == "learning" and found["action"]["to"] == "apprentice"

    # 再写一条后，去重查询取最新一条（去重决策由服务层依据它做，§3.6）
    second = db.insert_agent_stage_upgrade_task(TEACHER, "建议升级：见习期", "再次推荐", ACTION_DATA)
    assert db.find_pending_upgrade_task(TEACHER)["id"] == second


def test_upgrade_task_row_is_compatible_with_existing_channel(db):
    """新请示行必须与既有 agent_tasks 通道同构 → 既有前端 / GET / approve / reject 零改动可读可处理。"""
    task_id = db.insert_agent_stage_upgrade_task(TEACHER, "建议升级：见习期", "各指标已达标", ACTION_DATA)

    conn = db.get_connection()
    row = conn.execute("SELECT * FROM agent_tasks WHERE id = ?", (task_id,)).fetchone()
    conn.close()
    assert row["teacher_name"] == TEACHER
    assert row["task_type"] == "request" and row["category"] == "agent"
    assert row["status"] == "pending" and row["created_at"]
    assert row["resolved_at"] is None
    assert json.loads(row["action_data"]) == ACTION_DATA, "action_data 往返必须逐字段保真（含嵌套）"

    tasks = db.get_agent_tasks(TEACHER, status="pending")   # 既有读取函数，一字未改即可读到
    assert [t["id"] for t in tasks] == [task_id]
    assert tasks[0]["action"]["to"] == "apprentice"


def test_find_pending_upgrade_task_ignores_resolved_tasks(db):
    task_id = db.insert_agent_stage_upgrade_task(TEACHER, "建议升级：见习期", "各指标已达标", ACTION_DATA)
    db.resolve_agent_task(task_id, "approved")            # 既有函数：处理后不再是 pending

    assert db.find_pending_upgrade_task(TEACHER) is None
    assert db.get_agent_action_log(TEACHER)[0]["action"] == "approve", "既有决策留痕行为不变"

    db.insert_agent_stage_upgrade_task(OTHER_TEACHER, "建议升级：见习期", "各指标已达标", ACTION_DATA)
    assert db.find_pending_upgrade_task(TEACHER) is None
    assert db.find_pending_upgrade_task(OTHER_TEACHER) is not None


# ============ ⑥ 行动日志（工作台「行动日志」区块）============

def test_insert_agent_action_log_is_visible_to_existing_reader(db):
    log_id = db.insert_agent_action_log(TEACHER, "stage_upgraded", "已由「学习期」升为「见习期」", task_id=0)

    rows = db.get_agent_action_log(TEACHER)     # 既有函数：工作台该区块直接读它，零改动
    assert rows[0]["id"] == log_id
    assert rows[0]["action"] == "stage_upgraded"
    assert "学习期" in rows[0]["detail"]
    assert rows[0]["task_id"] == 0
    assert rows[0]["created_at"]


def test_insert_agent_action_log_accepts_explicit_time(db):
    log_id = db.insert_agent_action_log(TEACHER, "stage_demoted", "冷却中", created_at="2026-09-28T10:00:00")
    conn = db.get_connection()
    row = conn.execute("SELECT * FROM agent_action_log WHERE id = ?", (log_id,)).fetchone()
    conn.close()
    assert row["created_at"] == "2026-09-28T10:00:00"
    assert row["task_id"] == 0, "task_id 缺省为 0（非请示类节点）"


# ============ ⑦ 裁决⑤ 守正：表未就绪时 sqlite3.Error 冒泡 ============

def test_store_errors_propagate_when_tables_missing(monkeypatch, tmp_path):
    """表未就绪（0003 未跑）时不得被吞成 None / [] / 静默成功 —— 服务层与接口层靠它映射 503。"""
    empty_db = tmp_path / "empty.db"
    sqlite3.connect(str(empty_db)).close()          # 空库：只有文件、没有表
    monkeypatch.setattr(database, "DB_PATH", str(empty_db))

    with pytest.raises(sqlite3.Error):
        database.get_agent_stage_state(TEACHER)
    with pytest.raises(sqlite3.Error):
        database.get_agent_stage_logs(TEACHER)
    with pytest.raises(sqlite3.Error):
        database.get_agent_stage_config_row(TEACHER)
    with pytest.raises(sqlite3.Error):
        database.find_pending_upgrade_task(TEACHER)
    with pytest.raises(sqlite3.Error):
        database.upsert_agent_stage_state(TEACHER, stage="learning")
    with pytest.raises(sqlite3.Error):
        database.insert_agent_stage_log(TEACHER, "stage_upgraded")
    with pytest.raises(sqlite3.Error):
        database.upsert_agent_stage_config(TEACHER, "{}")
    with pytest.raises(sqlite3.Error):
        database.insert_agent_stage_upgrade_task(TEACHER, "t", "c", ACTION_DATA)
    with pytest.raises(sqlite3.Error):
        database.insert_agent_action_log(TEACHER, "stage_upgraded", "d")


# ============ ⑧ step 1 种子 ↔ step 2 读函数 互通 ============

def test_migration_seeded_existing_teacher_is_readable(db):
    """0003 给存量老师的种子行（§7.1-②：stage='learning'，存量不降级）必须能被新读函数直接读到。

    这条同时守住了两个文件之间的契约：迁移写的列名 / 值与库函数读的口径一致。
    """
    row = db.get_agent_stage_state(SEEDED_TEACHER)
    assert row is not None, "迁移应给存量老师各种一行状态"
    assert row["stage"] == "learning"
    assert row["stage_source"] == "default"


def test_migration_seeded_global_config_row_is_readable(db):
    """0003 种下的全局配置行（teacher_name=''、config_json='{}'）必须能被新读函数读到。"""
    row = db.get_agent_stage_config_row("")
    assert row is not None
    assert json.loads(row["config_json"]) == {}


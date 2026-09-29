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
    ⑨ 【§4.2 改 1】insert_draft 快照写入：四分支逐条 + **flag off 逐字节比对**（基线 = 改动前实测捕获，
       非手抄）+ 快照对老师编辑不可变；
    ⑩ 总闸契约：`agent_stage_service.agent_stage_enabled()` 的取值语义（默认 off）、闸门两态降级，
       以及**依赖方向**的源码级守护（`database` → 服务层的 import 恒在函数体内，不得动态绕开）
       + §2.1 禁止 import 清单（服务层永不 import 六个禁忌符号）—— 「服务层对 database 零 import」
       的反向硬断言已按 CTO 批复② 于 step 2.4 删除（§4.5-① 允许服务层 import database）；
    ⑪ 【§4.2 改 2 / 施工步骤 2.3】`sign_draft` 快照进历史表（双闸门 + 空快照回落 content）+ **改动前
       逐字节基线**守护 + best-effort 钩子 `on_draft_signed` 三态（不存在→静默 / 存在→调用一次 /
       抛异常→只打 warn）+「同一个 flag 闸门与同一个列探测只许一份实现」的行为级与源码级守护
       （CTO step 2.3 追加要求 1–3）。
    ⑫ 【§4.2 改 3 / 施工步骤 2.4】`resolve_agent_task` 升级确认钩子：flag off **逐字节基线**守护
       （基线 = 13 组用例的改动前实测捕获，非手抄）+ 既有返回值 / 学生类请示分支 / 空与坏
       `action_data` / 任务不存在全部一字不改 + 钩子三态（缺席→静默 / 在场→按
       `(teacher_name, to, task_id)` 调用一次 / 抛异常→只打 warn 且**不回滚**老师已落定的决策）
       + 「只有一个两态调用器」与「调用点不判 flag」的源码级守护（CTO step 2.4 追加要求 1–4）。

运行方式（Windows，串行；见 pytest.ini）：
    cd backend
    ..\\venv\\Scripts\\python.exe -m pytest test_agent_stage.py -v
"""
import json
import os
import re
import sqlite3
import sys

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


# ============ ⑨ 【§4.2 改 1】insert_draft：双闸门 + 四分支 + flag off 逐字节 ============
#
# 基线来源：本步改动**之前**用同一套 Recorder 实测捕获（只写 %TEMP% 临时库，不碰 zhiheng.db），
# 断言口径 = 把 insert_draft 实际发给 SQLite 的 **(SQL 文本, 参数) 全序列**逐字节比对 —— 不是
# 「语义等价」而是「一字不变」。入参固定为 (1, "张三", "李老师", "AI 原稿")，与捕获时同一组。

_BASELINE_FLAG_OFF_WITH_TEMPLATE_REFS = [
    ("PRAGMA table_info('drafts')", ()),
    ("INSERT INTO drafts (transcript_id, patient_name, teacher_name, content, signed, template_id, template_version) VALUES (?, ?, ?, ?, ?, ?, ?)",
     (1, "张三", "李老师", "AI 原稿", 0, 0, 0)),
    ("UPDATE transcriptions SET processed = 1 WHERE id = ?", (1,)),
]

_BASELINE_FLAG_OFF_LEGACY = [
    ("PRAGMA table_info('drafts')", ()),
    ("INSERT INTO drafts (transcript_id, patient_name, teacher_name, content, signed) VALUES (?, ?, ?, ?, ?)",
     (1, "张三", "李老师", "AI 原稿", 0)),
    ("UPDATE transcriptions SET processed = 1 WHERE id = ?", (1,)),
]

_LEGACY_DRAFTS_DDL = (
    "CREATE TABLE drafts (id INTEGER PRIMARY KEY AUTOINCREMENT, transcript_id INTEGER, patient_name TEXT, "
    "teacher_name TEXT, content TEXT, signed INTEGER DEFAULT 0, created_at TEXT DEFAULT '')"
)
_SNAPSHOT_ONLY_DRAFTS_DDL = (
    "CREATE TABLE drafts (id INTEGER PRIMARY KEY AUTOINCREMENT, transcript_id INTEGER, patient_name TEXT, "
    "teacher_name TEXT, content TEXT, signed INTEGER DEFAULT 0, created_at TEXT DEFAULT '', "
    "ai_original_content TEXT DEFAULT '')"
)


class _RecordingConnection:
    """把 `get_connection()` 包一层，录下被测函数实际执行的每一条 (SQL, 参数)。

    `record_cursor=True` 时连 `conn.cursor().execute(...)` 一起录：`resolve_agent_task`（改 3）走
    cursor，而 `insert_draft` / `sign_draft` 走 `conn.execute` —— 故 ⑨ / ⑪ 保持默认 False，
    录制口径与那两组基线逐字节一致，本步不触碰它们的断言。
    """

    def __init__(self, conn, record_cursor=False):
        self.__dict__["_conn"] = conn
        self.__dict__["calls"] = []
        self.__dict__["_record_cursor"] = record_cursor

    def execute(self, sql, params=()):
        self.__dict__["calls"].append((sql, params))
        return self.__dict__["_conn"].execute(sql, params)

    def cursor(self):
        cur = self.__dict__["_conn"].cursor()
        if not self.__dict__["_record_cursor"]:
            return cur
        return _RecordingCursor(cur, self.__dict__["calls"])

    def __getattr__(self, name):
        return getattr(self.__dict__["_conn"], name)


class _RecordingCursor:
    """录 `cursor.execute`（写进同一个 calls 列表，保持语句先后次序）。"""

    def __init__(self, cur, calls):
        self.__dict__["_cur"] = cur
        self.__dict__["_calls"] = calls

    def execute(self, sql, params=()):
        self.__dict__["_calls"].append((sql, params))
        return self.__dict__["_cur"].execute(sql, params)

    def __getattr__(self, name):
        return getattr(self.__dict__["_cur"], name)


@pytest.fixture
def sql_log(monkeypatch):
    """录下被测函数执行的全部语句（返回 list[_RecordingConnection]）。"""
    real = database.get_connection
    connections = []

    def wrapper():
        conn = _RecordingConnection(real())
        connections.append(conn)
        return conn

    monkeypatch.setattr(database, "get_connection", wrapper)
    return connections


@pytest.fixture
def task_sql_log(monkeypatch):
    """⑫ 组专用：连 `cursor.execute` 一起录（`resolve_agent_task` 走的是 cursor）。"""
    real = database.get_connection
    connections = []

    def wrapper():
        conn = _RecordingConnection(real(), record_cursor=True)
        connections.append(conn)
        return conn

    monkeypatch.setattr(database, "get_connection", wrapper)
    return connections


def _all_calls(connections):
    calls = []
    for conn in connections:
        calls.extend(conn.calls)
    return calls


def _insert_call(connections):
    """取出记录里的那条 INSERT（用于断言分支列集与参数）。"""
    return [c for c in _all_calls(connections) if c[0].startswith("INSERT INTO drafts")][0]


@pytest.fixture
def legacy_db(monkeypatch, tmp_path):
    """模拟「迁移 0002 / 0003 都没跑」的老库：`drafts` 只有最早的 5 列。"""
    return _raw_db(monkeypatch, tmp_path, "legacy.db", _LEGACY_DRAFTS_DDL)


def _raw_db(monkeypatch, tmp_path, filename, drafts_ddl):
    path = tmp_path / filename
    conn = sqlite3.connect(str(path))
    conn.execute(drafts_ddl)
    conn.execute("CREATE TABLE transcriptions (id INTEGER PRIMARY KEY, processed INTEGER DEFAULT 0)")
    conn.commit()
    conn.close()
    monkeypatch.setattr(database, "DB_PATH", str(path))
    return database


def test_insert_draft_flag_off_is_byte_identical_with_template_refs(db, sql_log, monkeypatch):
    """分支②（今天真实路径 · §5.5-① / 裁决①）：flag off 时「探测 + INSERT + UPDATE」逐字节不变。"""
    monkeypatch.delenv("AGENT_STAGE_ENABLED", raising=False)

    draft_id = db.insert_draft(1, "张三", "李老师", "AI 原稿")

    assert _all_calls(sql_log) == _BASELINE_FLAG_OFF_WITH_TEMPLATE_REFS
    assert draft_id == 1


def test_insert_draft_flag_off_is_byte_identical_on_legacy_db(legacy_db, sql_log, monkeypatch):
    """分支④（老库无模板引用列）：flag off 时逐字节不变，老库永远走原 5 列。"""
    monkeypatch.delenv("AGENT_STAGE_ENABLED", raising=False)

    draft_id = legacy_db.insert_draft(1, "张三", "李老师", "AI 原稿")

    assert _all_calls(sql_log) == _BASELINE_FLAG_OFF_LEGACY
    assert draft_id == 1


def test_insert_draft_flag_on_legacy_db_still_uses_original_sql(legacy_db, sql_log, monkeypatch):
    """双闸门的另一半：列还没就位 → 即使 flag on，**写入语句**仍与原 SQL 逐字节相同。

    与 flag off 的唯一差别：多发一条**只读**的列探测 PRAGMA（`_drafts_supports_ai_original`）。
    INSERT / UPDATE 的文本与参数一字不变 → 老库不可能被写坏（INSERT 里绝不出现不存在的列）。
    """
    monkeypatch.setenv("AGENT_STAGE_ENABLED", "on")

    legacy_db.insert_draft(1, "张三", "李老师", "AI 原稿")

    calls = _all_calls(sql_log)
    writes = [c for c in calls if not c[0].startswith("PRAGMA")]
    probes = [c for c in calls if c[0].startswith("PRAGMA")]
    assert writes == _BASELINE_FLAG_OFF_LEGACY[1:], "INSERT + UPDATE 逐字节不变"
    assert probes == [("PRAGMA table_info('drafts')", ()), ("PRAGMA table_info('drafts')", ())]
    assert "ai_original_content" not in writes[0][0]


def test_insert_draft_flag_off_leaves_snapshot_column_empty(db, monkeypatch):
    """flag off：既有 7 列语义一字不改，快照列保持迁移默认值 ''（§5.5-① 断言口径之一）。"""
    monkeypatch.delenv("AGENT_STAGE_ENABLED", raising=False)

    draft_id = db.insert_draft(1, "张三", "李老师", "AI 原稿", template_id=7, template_version=2)

    conn = db.get_connection()
    row = conn.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()
    conn.close()
    assert row["content"] == "AI 原稿"
    assert row["template_id"] == 7 and row["template_version"] == 2
    assert row["ai_original_content"] == ""


def test_insert_draft_flag_on_writes_immutable_snapshot(db, sql_log, monkeypatch):
    """分支①（flag on 且两列都就位）：同一份 `content` 同时写进快照列（§4.2 改 1）。"""
    monkeypatch.setenv("AGENT_STAGE_ENABLED", "on")

    draft_id = db.insert_draft(1, "张三", "李老师", "AI 原稿", template_id=7, template_version=2)

    insert_sql, insert_params = _insert_call(sql_log)
    assert "template_id, template_version, ai_original_content" in insert_sql
    assert insert_params == (1, "张三", "李老师", "AI 原稿", 0, 7, 2, "AI 原稿")

    conn = db.get_connection()
    row = conn.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()
    conn.close()
    assert row["ai_original_content"] == "AI 原稿"
    assert row["signed"] == 0


def test_insert_draft_flag_on_writes_snapshot_even_without_template(db, monkeypatch):
    """分支①的另一半：无模板生成（`template_id=0`）也要写快照 —— ② 指标基准不依赖模板。"""
    monkeypatch.setenv("AGENT_STAGE_ENABLED", "on")

    draft_id = db.insert_draft(1, "张三", "李老师", "AI 原稿")

    conn = db.get_connection()
    row = conn.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()
    conn.close()
    assert row["ai_original_content"] == "AI 原稿"
    assert row["template_id"] == 0 and row["template_version"] == 0


def test_insert_draft_branch_snapshot_without_template_refs(monkeypatch, tmp_path, sql_log):
    """分支③（防御性）：`drafts` 有快照列但**无**模板引用列。

    标准迁移链（0003 的 down_revision = 0002）下不可达，但两个探测彼此独立且各自可能因表结构被手工
    改动而为假 —— 这条守住「任何组合都不抛 OperationalError」，即四分支矩阵的完备性。
    """
    odd_db = _raw_db(monkeypatch, tmp_path, "snapshot_only.db", _SNAPSHOT_ONLY_DRAFTS_DDL)
    monkeypatch.setenv("AGENT_STAGE_ENABLED", "on")

    draft_id = odd_db.insert_draft(1, "张三", "李老师", "AI 原稿")

    insert_sql, insert_params = _insert_call(sql_log)
    assert "template_id" not in insert_sql
    assert "ai_original_content" in insert_sql
    assert insert_params == (1, "张三", "李老师", "AI 原稿", 0, "AI 原稿")

    conn = odd_db.get_connection()
    row = conn.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()
    conn.close()
    assert row["ai_original_content"] == "AI 原稿"


def test_snapshot_survives_teacher_edit(db, monkeypatch):
    """§3.3 纪律：快照 = 生成时刻的 content，此后老师编辑**只改 content**，快照一字不变（② 的基准）。"""
    monkeypatch.setenv("AGENT_STAGE_ENABLED", "on")
    draft_id = db.insert_draft(1, "张三", "李老师", "AI 原稿", template_id=7, template_version=2)

    db.update_draft_content(draft_id, "老师改后的内容")

    conn = db.get_connection()
    row = conn.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()
    conn.close()
    assert row["content"] == "老师改后的内容"
    assert row["ai_original_content"] == "AI 原稿"


# ============ ⑩ 总闸契约：取值语义 / 两态降级 / 零循环依赖 ============

def test_agent_stage_flag_semantics(monkeypatch):
    """§4.5-① flag 判定：默认 **off**，取值语义与 `TEMPLATE_API_ENABLED` 逐字同款（去空格 + 小写）。"""
    import agent_stage_service

    monkeypatch.delenv("AGENT_STAGE_ENABLED", raising=False)
    assert agent_stage_service.agent_stage_enabled() is False, "未设置 = off（默认关）"

    for value in ("on", "ON", " 1 ", "true", "Yes"):
        monkeypatch.setenv("AGENT_STAGE_ENABLED", value)
        assert agent_stage_service.agent_stage_enabled() is True, value

    for value in ("off", "", "0", "no", "enabled", "on!"):
        monkeypatch.setenv("AGENT_STAGE_ENABLED", value)
        assert agent_stage_service.agent_stage_enabled() is False, value


def test_snapshot_gate_two_state(monkeypatch, capsys):
    """裁决④「两态」纪律：服务层缺失 / 无该函数 → 静默 off；闸门自己抛异常 → 打 warn 后按 off。

    两种情形都**不得冒泡**（否则会打断既有生成 / 签字链路）—— 这是「不吞 sqlite3.Error」（裁决⑤）
    的例外边界：吞的是**闸门读取**异常，不是库异常。
    """
    import agent_stage_service

    monkeypatch.setenv("AGENT_STAGE_ENABLED", "on")
    assert database._agent_stage_snapshot_enabled() is True

    monkeypatch.delattr(agent_stage_service, "agent_stage_enabled", raising=False)
    assert database._agent_stage_snapshot_enabled() is False, "函数不存在 → 静默 off"

    def boom():
        raise RuntimeError("env 读坏了")

    monkeypatch.setattr(agent_stage_service, "agent_stage_enabled", boom, raising=False)
    assert database._agent_stage_snapshot_enabled() is False, "闸门抛异常 → 按 off"
    assert "[warn]" in capsys.readouterr().out, "异常按 off 处理时必须留痕"

    monkeypatch.setitem(sys.modules, "agent_stage_service", None)   # 模拟模块不可导入
    assert database._agent_stage_snapshot_enabled() is False, "服务层缺失 → 静默 off"


def test_snapshot_gate_emits_no_sql_when_flag_off(monkeypatch, sql_log):
    """flag off 的「零影响」可验证口径：闸门**一条 SQL 都不发**（连列的 PRAGMA 都不探）。

    说明（避免误解）：延迟 import 只能避免「循环依赖」，**不能避免模块被加载** —— 无论 flag 取值，
    `database` 都会 import 一次 `agent_stage_service`（纯常量 + 一个 env 判读函数，零 DB、零副作用）。
    要守的硬指标是「既有链路的执行语句序列逐字节不变」（见 ⑨ 组两条比对用例）与「闸门零 SQL」。
    """
    monkeypatch.setenv("AGENT_STAGE_ENABLED", "off")
    conn = database.get_connection()

    gate = database._agent_stage_snapshot_enabled() and database._drafts_supports_ai_original(conn)
    conn.close()

    assert gate is False
    assert _all_calls(sql_log) == [], "flag off 时闸门不得发任何 SQL（短路必须发生在列探测之前）"


_FORBIDDEN_SERVICE_IMPORTS = (
    "create_prescription",
    "sanitize_prescription_items",
    "batch_deduct_herbs",
    "sign_draft",
    "update_draft_content",
    "save_prescription",
)


def _service_source():
    path = os.path.join(os.path.dirname(os.path.abspath(database.__file__)), "agent_stage_service.py")
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _service_imports_and_database_attrs(source):
    """AST 口径：抽出**真实**的 import 名与 `database.<属性>` 访问。

    必须用 AST 才能把「docstring / 注释里提到 `database.sign_draft()`」和「代码里真的碰它」分开 ——
    本文件头部就写着 §2.1 禁止清单、交接说明里也会引用这些函数名（口径是「提到可以、import 不行」）。
    """
    import ast

    tree = ast.parse(source)
    imported = set()
    attributes = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[-1])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported.add(alias.name)
        elif (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                and node.value.id == "database"):
            attributes.add(node.attr)
    return imported, attributes


def test_database_to_service_import_stays_inside_function_bodies():
    """依赖方向守护（CTO 2026-09-28 批复②修正版）。

    真正的红线是**方向与时机**：`database` → `agent_stage_service` 的依赖必须恒在**函数体内**
    （模块级 import 会与 `agent_stage_service` 形成循环依赖），且不得用 `__import__` /
    `importlib.import_module` 动态绕开源码级守护。

    「服务层对 `database` 零 import」的反向硬断言已按批复②**删除**：设计 §4.5-① **允许**服务层
    import `database`（只调 §4.2 的 8 个新函数 + 只读函数），step 3 落地时它会正常 import，旧断言
    会误红。服务层侧的守护改为「永不 import 六个禁忌符号」（见下一条用例）。
    """
    with open(os.path.abspath(database.__file__), encoding="utf-8") as fh:
        db_source = fh.read()

    # 锚定**第 0 列**：缩进的（函数体内）延迟 import 是设计要求，不算违规
    assert not re.search(r"(?m)^(?:import\s+agent_stage_service\b|from\s+agent_stage_service\b)", db_source), \
        "服务层必须只在函数体内延迟 import（模块级 = 循环依赖）"
    assert "import_module(" not in db_source and "__import__(" not in db_source, \
        "不得用动态 import 绕过源码级守护"
    assert "agent_stage_service" not in vars(database), "运行期也不得把服务层模块绑进 database 命名空间"

    service_source = _service_source()
    assert "import_module(" not in service_source and "__import__(" not in service_source, \
        "服务层同样不得用动态 import 绕开守护"


def test_service_module_never_imports_forbidden_symbols():
    """§2.1 三条铁律（AI 永不诊断 / 永不开方 / 永不签字）的代码级保证：禁止 import 清单。

    口径（AST 精确判定）：**import 名**与 `database.<符号>` **属性访问**一律不许出现；文档 / 注释里
    「提到」这些名字是允许的（本文件头部就列着这份清单）。step 3 起服务层可以 import `database`，
    但绝不碰这六个符号。
    """
    imported, attributes = _service_imports_and_database_attrs(_service_source())
    for symbol in _FORBIDDEN_SERVICE_IMPORTS:
        assert symbol not in imported, f"服务层不得 import 禁忌符号 {symbol}"
        assert symbol not in attributes, f"服务层不得访问 database.{symbol}"

# ============ ⑪ 【§4.2 改 2】sign_draft：快照进历史表 + best-effort 钩子 ============
#
# 基线来源（＝ CTO 要求 3 的「专门用例」）：本步改动**之前**用同一套 Recorder 实测捕获，两种库形态
# （老 `patient_records` / 已迁 `patient_records`）捕获结果**逐字节相同**，留档于
# %TEMP%\epic2_sign_baseline_before.txt。断言口径同 ⑨：把 sign_draft 实际发给 SQLite 的
# (SQL 文本, 参数) 全序列逐字节比对 —— 唯一非确定性参数 `datetime.now().isoformat()` 归一为 "<NOW>"。

_ISO_NOW_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?$")
_TRANSCRIPT_ID = 77


def _sign_fixture_draft(db):
    """造一条待签字草案（transcript_id 固定 77，便于与基线逐字节比对）。"""
    return db.insert_draft(_TRANSCRIPT_ID, "张三", TEACHER, "AI 原稿")


def _normalized_calls(connections):
    """录制到的 (SQL, 参数) 全序列；时间戳参数归一为 "<NOW>"。"""
    return [
        (sql, tuple("<NOW>" if isinstance(p, str) and _ISO_NOW_RE.match(p) else p for p in params))
        for sql, params in _all_calls(connections)
    ]


def _sign_draft_baseline(draft_id):
    """改动前实测捕获的 sign_draft 语句序列（flag off）。"""
    return [
        ("SELECT * FROM drafts WHERE id = ?", (draft_id,)),
        ("INSERT INTO patient_records (patient_name, teacher_name, ai_draft, final_plan, doctor, visit_at) "
         "VALUES (?, ?, ?, ?, ?, ?)",
         ("张三", TEACHER, "AI 原稿", "完整病历", TEACHER, "<NOW>")),
        ("INSERT INTO homework (patient_name, teacher_name, task, detail, status, created_at) "
         "VALUES (?, ?, ?, ?, ?, ?)",
         ("张三", TEACHER, "今日医嘱：最终方案", "请严格遵医嘱执行", "pending", "2026-09-19")),
        ("DELETE FROM transcriptions WHERE id = ?", (_TRANSCRIPT_ID,)),
        ("DELETE FROM drafts WHERE id = ?", (draft_id,)),
    ]


def _patient_record_insert_call(connections):
    """取出记录里的那条 patient_records INSERT（用于断言分支列集）。"""
    return [c for c in _all_calls(connections) if c[0].startswith("INSERT INTO patient_records")][0]


def test_sign_draft_flag_off_is_byte_identical(db, sql_log, monkeypatch):
    """【要求 3】flag off：sign_draft 的语句序列 + 参数与改动前**逐字节一致**（基线 = 实测捕获）。

    这是 §5.1 红线①（flag off = 逐字节 1:1 / 零副作用）在签字链路上的硬门槛：既有 6 列 INSERT 的
    SQL 文本、参数顺序、`UPDATE transcriptions` / `DELETE` 两条收尾语句、以及返回值全部不变。
    """
    monkeypatch.setenv("AGENT_STAGE_ENABLED", "off")
    draft_id = _sign_fixture_draft(db)
    sql_log.clear()                                   # 只录「签字」这一段

    got = db.sign_draft(draft_id, "最终方案", "完整病历")

    assert got == "张三", "返回值语义不变（§5.1 红线③）"
    assert _normalized_calls(sql_log) == _sign_draft_baseline(draft_id)

    conn = db.get_connection()
    drafts_left = conn.execute("SELECT COUNT(*) AS c FROM drafts WHERE id = ?", (draft_id,)).fetchone()["c"]
    row = conn.execute("SELECT * FROM patient_records ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    assert drafts_left == 0, "草案行照样被删（既有行为不变）"
    assert row["ai_original_text"] == "", "flag off 不写快照列，保持迁移默认值 ''（§5.5-①）"
    assert row["ai_draft"] == "AI 原稿" and row["final_plan"] == "完整病历", "既有字段语义不变"


def test_sign_draft_flag_on_writes_ai_original_text(db, sql_log, monkeypatch):
    """改 2a 正路：flag on 且 `patient_records.ai_original_text` 就位 → 快照随签字进历史表。

    守护的是**不回落 content**（CTO 裁决③）：草案落库后老师把 `content` 改成终稿，进历史表的
    `ai_original_text` 必须仍是**生成时刻的快照**（否则学习轨迹 ① 会把「改过」误记成「零修改」）。
    """
    monkeypatch.setenv("AGENT_STAGE_ENABLED", "on")
    draft_id = _sign_fixture_draft(db)                       # 快照 = "AI 原稿"
    db.update_draft_content(draft_id, "老师改过的终稿")       # 只动 content，快照不可变
    sql_log.clear()

    assert db.sign_draft(draft_id, "最终方案", "完整病历") == "张三"

    sql, _params = _patient_record_insert_call(sql_log)
    assert "ai_original_text" in sql, "列就位 + flag on → 追加写快照列"

    conn = db.get_connection()
    row = conn.execute("SELECT * FROM patient_records ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    assert row["ai_original_text"] == "AI 原稿", "历史表拿到的必须是快照，不是老师改后的 content"
    assert row["ai_draft"] == "老师改过的终稿", "既有字段 ai_draft 仍是签字时刻的 content"


def test_sign_draft_falls_back_to_content_when_snapshot_empty(db, monkeypatch):
    """快照为空 → 回落 `content`（设计 §4.2 改 2a 原文；「无快照」时才借用，绝不用它顶替真快照）。

    空快照的现实来源：该草案落库时 flag 关（或迁移前的老草案，§1.4 不删列）。此时落 content 优于
    留空 —— 留空会让历史表永久丢掉这条学习样本。
    """
    monkeypatch.setenv("AGENT_STAGE_ENABLED", "off")
    draft_id = _sign_fixture_draft(db)                       # 快照保持 ''

    conn = db.get_connection()
    snapshot = conn.execute("SELECT ai_original_content FROM drafts WHERE id = ?", (draft_id,)).fetchone()["ai_original_content"]
    conn.close()
    assert snapshot == "", "前置条件：草案快照为空（flag off 时落库）"

    monkeypatch.setenv("AGENT_STAGE_ENABLED", "on")          # 签字时 flag 已打开
    db.sign_draft(draft_id, "最终方案", "完整病历")

    conn = db.get_connection()
    row = conn.execute("SELECT * FROM patient_records ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    assert row["ai_original_text"] == "AI 原稿", "快照为空 → 回落 content"


_LEGACY_PATIENT_RECORDS_DDL = (
    "CREATE TABLE patient_records (id INTEGER PRIMARY KEY AUTOINCREMENT, patient_name TEXT, teacher_name TEXT, "
    "ai_draft TEXT, final_plan TEXT, doctor TEXT, visit_at TEXT DEFAULT '')"
)


@pytest.fixture
def legacy_full_db(monkeypatch, tmp_path):
    """老库形态：`drafts` 只有 5 列 + `patient_records` 没有 `ai_original_text`（迁移 0002 / 0003 都没跑）。"""
    path = tmp_path / "legacy_full.db"
    conn = sqlite3.connect(str(path))
    conn.execute(_LEGACY_DRAFTS_DDL)
    conn.execute(_LEGACY_PATIENT_RECORDS_DDL)
    conn.execute("CREATE TABLE transcriptions (id INTEGER PRIMARY KEY, processed INTEGER DEFAULT 0)")
    conn.execute("CREATE TABLE homework (id INTEGER PRIMARY KEY AUTOINCREMENT, patient_name TEXT, "
                 "teacher_name TEXT, task TEXT, detail TEXT, status TEXT, created_at TEXT DEFAULT '')")
    conn.commit()
    conn.close()
    monkeypatch.setattr(database, "DB_PATH", str(path))
    return database


def test_sign_draft_flag_on_legacy_db_still_uses_original_sql(legacy_full_db, sql_log, monkeypatch):
    """双闸门的第二道：flag 已 on 但列未就位（老库）→ 仍走原 6 列 SQL，序列与 flag off 基线一致。"""
    monkeypatch.setenv("AGENT_STAGE_ENABLED", "on")
    draft_id = _sign_fixture_draft(legacy_full_db)
    sql_log.clear()

    assert legacy_full_db.sign_draft(draft_id, "最终方案", "完整病历") == "张三"

    sql, _params = _patient_record_insert_call(sql_log)
    assert "ai_original_text" not in sql, "列未就位 → 必须走原 6 列 SQL"

    calls = _normalized_calls(sql_log)
    assert calls[1] == ("PRAGMA table_info('patient_records')", ()), "flag on 时必须真的探到列（第二道闸门）"
    assert [c for c in calls if not c[0].startswith("PRAGMA")] == _sign_draft_baseline(draft_id), \
        "除那一次列探测外，语句序列与 flag off 基线逐字节一致"


def test_sign_draft_hook_absent_is_silent_noop(db, monkeypatch, capsys):
    """【要求 2 · 态一】`on_draft_signed` 不存在（step 2.3 的今天）→ **静默** no-op：零输出、零影响。"""
    import agent_stage_service

    monkeypatch.setenv("AGENT_STAGE_ENABLED", "on")           # 即使 flag on，函数不存在也必须静默
    monkeypatch.delattr(agent_stage_service, "on_draft_signed", raising=False)
    draft_id = _sign_fixture_draft(db)

    assert db.sign_draft(draft_id, "最终方案") == "张三"
    assert database._call_agent_stage_hook("on_draft_signed", TEACHER) is False
    monkeypatch.setitem(sys.modules, "agent_stage_service", None)     # 服务层整个不可导入
    assert database._call_agent_stage_hook("on_draft_signed", TEACHER) is False
    assert capsys.readouterr().out == "", "「无该函数 / 模块不可导入」必须完全静默（不得打 warn）"


def test_sign_draft_hook_present_is_called_once_with_teacher_name(db, monkeypatch):
    """【要求 2 · 态二】钩子存在 → 以 `draft["teacher_name"]` 调用**一次**；返回值仍不变。

    注意（step 3 交接）：调用点**不判 flag** —— 设计 §4.2 改 2b 的代码形状就是无条件 try 调用，
    「flag off → 不算指标」由钩子自身首行闸门负责（见 `agent_stage_enabled()` docstring 的交接说明）。
    """
    import agent_stage_service

    seen = []
    monkeypatch.setenv("AGENT_STAGE_ENABLED", "off")           # 故意 flag off：转发照发，闸门在服务层
    monkeypatch.setattr(agent_stage_service, "on_draft_signed", seen.append, raising=False)
    draft_id = _sign_fixture_draft(db)

    assert db.sign_draft(draft_id, "最终方案") == "张三"
    assert seen == [TEACHER]


def test_sign_draft_hook_exception_only_warns(db, monkeypatch, capsys):
    """【要求 2 · 态三】钩子存在但抛异常 → 打一行 warn、**绝不冒泡**；签字已提交、返回值不变。"""
    import agent_stage_service

    def boom(teacher_name):
        raise RuntimeError("评估炸了")

    monkeypatch.setenv("AGENT_STAGE_ENABLED", "off")          # 本用例与 flag 取值无关：显式固定，不依赖环境
    monkeypatch.setattr(agent_stage_service, "on_draft_signed", boom, raising=False)
    draft_id = _sign_fixture_draft(db)

    assert db.sign_draft(draft_id, "最终方案", "完整病历") == "张三", "异常不得冒泡、返回值不变"

    out = capsys.readouterr().out
    assert "[warn]" in out and "on_draft_signed" in out, "失败必须留痕且留名"

    conn = db.get_connection()
    drafts_left = conn.execute("SELECT COUNT(*) AS c FROM drafts WHERE id = ?", (draft_id,)).fetchone()["c"]
    records = conn.execute("SELECT COUNT(*) AS c FROM patient_records").fetchone()["c"]
    conn.close()
    assert drafts_left == 0 and records >= 1, "钩子失败不影响签字落库 / 删草案"


def test_sign_draft_hook_runs_after_commit(db, monkeypatch):
    """改 2b 的位置纪律：钩子在 **commit + close 之后**调用（评估失败不可能回滚签字）。"""
    import agent_stage_service

    seen = {}

    def hook(teacher_name):
        conn = db.get_connection()                            # 另开一条连接观察「已提交」状态
        seen["drafts"] = conn.execute(
            "SELECT COUNT(*) AS c FROM drafts WHERE patient_name = ?", ("张三",)).fetchone()["c"]
        seen["records"] = conn.execute("SELECT COUNT(*) AS c FROM patient_records").fetchone()["c"]
        conn.close()

    monkeypatch.setenv("AGENT_STAGE_ENABLED", "off")          # 本用例与 flag 取值无关：显式固定，不依赖环境
    monkeypatch.setattr(agent_stage_service, "on_draft_signed", hook, raising=False)
    draft_id = _sign_fixture_draft(db)
    db.sign_draft(draft_id, "最终方案")

    assert seen["drafts"] == 0, "钩子执行时草案行已被提交删除"
    assert seen["records"] >= 1, "钩子执行时病历已提交落库"


def test_single_flag_gate_and_probe_helpers_are_shared(db, monkeypatch):
    """【要求 1】两个快照写入点必须共用**同一个**闸门函数与**同一个**列探测实现（不得各写一份）。"""
    calls = []
    real_gate = database._agent_stage_snapshot_enabled
    real_probe = database._table_has_columns

    def gate_spy():
        calls.append("gate")
        return real_gate()

    def probe_spy(conn, table, columns):
        calls.append(f"probe:{table}")
        return real_probe(conn, table, columns)

    monkeypatch.setenv("AGENT_STAGE_ENABLED", "on")
    monkeypatch.setattr(database, "_agent_stage_snapshot_enabled", gate_spy)
    monkeypatch.setattr(database, "_table_has_columns", probe_spy)

    draft_id = _sign_fixture_draft(db)                        # insert_draft：闸门 1 次 + 草案列探测 1 次
    db.sign_draft(draft_id, "最终方案")                        # sign_draft：闸门 1 次 + 历史表列探测 1 次

    assert calls.count("gate") == 2, "两个写入点各过一次**同一个**闸门（不得存在第二份 flag 判断）"
    assert calls.count("probe:drafts") == 1 and calls.count("probe:patient_records") == 1, \
        "两个快照列探测共用唯一实现 _table_has_columns"


def test_database_module_never_imports_agent_stage_service_at_module_level():
    """【要求 1 · 源码级】`database.py` 对服务层的依赖恒为**函数内延迟 import**（模块级 = 循环依赖）。"""
    source_path = os.path.join(os.path.dirname(os.path.abspath(database.__file__)), "database.py")
    with open(source_path, encoding="utf-8") as fh:
        source = fh.read()

    assert not re.search(r"(?m)^(?:import|from)\s+agent_stage_service", source), "模块级 import = 循环依赖"
    lazy = re.findall(r"(?m)^(\s+)import agent_stage_service\s*$", source)
    assert len(lazy) >= 2, "延迟 import 至少两处：闸门 `_agent_stage_snapshot_enabled` + 钩子转发 `_call_agent_stage_hook`"



# ============ ⑫ 【§4.2 改 3 / 施工步骤 2.4】resolve_agent_task：升级确认钩子 ============
#
# 基线来源（＝ CTO 要求 3 的「专门用例」）：本步改动**之前**用同一套 Recorder 实测捕获，
# 一次跑完 13 组：flag off/on × approved/rejected（升级请示）、学生类 deduct_herbs / send_care_notice、
# 空 action_data、坏 JSON、缺 to、任务不存在 —— 留档于 %TEMP%\epic2_resolve_baseline_before.txt，
# 改动后又用**同一版脚本**跑了一次逐行比对（%TEMP%\epic2_resolve_baseline_after.txt）。
# 口径：把实际发给 SQLite 的 (SQL 文本, 参数) 全序列逐条比对 ——
#   · SQL 归一化空白（`agent_action_log` 的 INSERT 在源码里是多行字面量）；
#   · 唯一非确定性参数 `datetime.now().isoformat()` 归一为 "<NOW>"；
#   · 返回值 / 任务状态 / 行动日志一并断言（要求 2 的「一字不改」包含返回值）。

_RESOLVE_TASK_ID = 1
_TITLE_UPGRADE = "升级请示"
_TITLE_UPGRADE_NO_TO = "升级请示（无 to）"
_TITLE_DEDUCT = "扣减请示"
_TITLE_NOTICE = "关怀请示"
_TITLE_EMPTY = "空 action_data"
_TITLE_BAD_JSON = "坏 JSON 请示"
_TITLE_NON_DICT = "非对象 JSON"

_TASK_UPGRADE = json.dumps(
    {"action": "upgrade_agent_stage", "from": "learning", "to": "apprentice",
     "metrics": {"approved_rate": 0.92, "samples": 12}},
    ensure_ascii=False,
)
_TASK_UPGRADE_NO_TO = json.dumps({"action": "upgrade_agent_stage"}, ensure_ascii=False)
_TASK_DEDUCT = json.dumps({"action": "deduct_herbs", "patient_name": "张三"}, ensure_ascii=False)
_TASK_NOTICE = json.dumps({"action": "send_care_notice", "patient_name": "张三"}, ensure_ascii=False)
_TASK_BAD_JSON = "{不是 JSON"


def _seed_agent_task(action_data, title, teacher=TEACHER, status="pending"):
    """种一条待处理请示（用**裸 sqlite3**，绕开 Recorder → 被测函数的语句序列从零开始录）。

    每个用例都是新库（`db` fixture），故任务 id 恒为 `_RESOLVE_TASK_ID`。
    """
    conn = sqlite3.connect(database.DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        "INSERT INTO agent_tasks (teacher_name, task_type, category, title, content, action_data, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (teacher, "upgrade", "stage", title, "内容", action_data, status, "2026-09-28T10:00:00"),
    )
    task_id = cur.lastrowid
    conn.commit()
    conn.close()
    return task_id


def _read_agent_task(task_id):
    """读回任务行 + 该老师的行动日志（同样走裸 sqlite3，不污染录制）。"""
    conn = sqlite3.connect(database.DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM agent_tasks WHERE id = ?", (task_id,)).fetchone()
    logs = conn.execute(
        "SELECT action, detail FROM agent_action_log WHERE teacher_name = ? ORDER BY id", (TEACHER,)
    ).fetchall()
    conn.close()
    return row, [(r["action"], r["detail"]) for r in logs]


def _task_calls(connections):
    """⑫ 组口径的录制结果：全部语句（含 cursor.execute），SQL 归一空白 + 时间戳归一 "<NOW>"。"""
    return [
        (" ".join(sql.split()),
         tuple("<NOW>" if isinstance(p, str) and _ISO_NOW_RE.match(p) else p for p in (params or ())))
        for sql, params in _all_calls(connections)
    ]


def _resolve_baseline(decision, title, notice_patient=None):
    """改动前实测捕获的 resolve_agent_task 语句序列（flag off，逐条与留档文件一致）。"""
    calls = [
        ("SELECT * FROM agent_tasks WHERE id = ?", (_RESOLVE_TASK_ID,)),
        ("UPDATE agent_tasks SET status = ?, resolved_at = ? WHERE id = ?",
         (decision, "<NOW>", _RESOLVE_TASK_ID)),
        ("INSERT INTO agent_action_log (teacher_name, task_id, action, detail, created_at) VALUES (?, ?, ?, ?, ?)",
         (TEACHER, _RESOLVE_TASK_ID, "approve" if decision == "approved" else "reject",
          ("老师确认执行：" if decision == "approved" else "老师忽略：") + title, "<NOW>")),
    ]
    if notice_patient is not None:
        calls.append(
            ("INSERT INTO agent_action_log (teacher_name, task_id, action, detail, created_at) "
             "VALUES (?, ?, 'send_notice', ?, ?)",
             (TEACHER, _RESOLVE_TASK_ID, f"已发送关怀通知给 {notice_patient}", "<NOW>"))
        )
    return calls


def _install_fake_hooks(monkeypatch, boom=None):
    """给服务层挂两个**假钩子**（只记录参数、零 SQL）→ ⑫ 组语句断言在任何施工步骤都成立。

    `boom` 指定哪个钩子抛异常（用于「抛异常 → 只打 warn、不回滚决策」用例）。
    """
    import agent_stage_service

    calls = []

    def apply_upgrade_confirmation(teacher_name, to_stage, task_id):
        calls.append(("apply_upgrade_confirmation", teacher_name, to_stage, task_id))
        if boom == "apply_upgrade_confirmation":
            raise RuntimeError("服务层炸了")

    def decline_upgrade(teacher_name, task_id):
        calls.append(("decline_upgrade", teacher_name, task_id))
        if boom == "decline_upgrade":
            raise RuntimeError("服务层炸了")

    monkeypatch.setattr(agent_stage_service, "apply_upgrade_confirmation", apply_upgrade_confirmation, raising=False)
    monkeypatch.setattr(agent_stage_service, "decline_upgrade", decline_upgrade, raising=False)
    return calls


def test_resolve_agent_task_flag_off_upgrade_approved_is_byte_identical(db, task_sql_log, monkeypatch):
    """要求 3（专门用例）：flag off + 升级请示被确认 → 语句序列 / 参数 / 返回值逐字节不变。"""
    monkeypatch.delenv("AGENT_STAGE_ENABLED", raising=False)
    task_id = _seed_agent_task(_TASK_UPGRADE, _TITLE_UPGRADE)

    result = db.resolve_agent_task(task_id, "approved")

    assert _task_calls(task_sql_log) == _resolve_baseline("approved", _TITLE_UPGRADE)
    assert result == {"message": "已处理", "status": "approved"}
    row, logs = _read_agent_task(task_id)
    assert row["status"] == "approved" and row["resolved_at"]
    assert logs == [("approve", f"老师确认执行：{_TITLE_UPGRADE}")]


def test_resolve_agent_task_flag_off_upgrade_rejected_is_byte_identical(db, task_sql_log, monkeypatch):
    """要求 3：同一口径的 rejected 分支（改 3 的 `decline_upgrade` 路径）。"""
    monkeypatch.delenv("AGENT_STAGE_ENABLED", raising=False)
    task_id = _seed_agent_task(_TASK_UPGRADE, _TITLE_UPGRADE)

    result = db.resolve_agent_task(task_id, "rejected")

    assert _task_calls(task_sql_log) == _resolve_baseline("rejected", _TITLE_UPGRADE)
    assert result == {"message": "已处理", "status": "rejected"}
    row, logs = _read_agent_task(task_id)
    assert row["status"] == "rejected"
    assert logs == [("reject", f"老师忽略：{_TITLE_UPGRADE}")]


def test_resolve_agent_task_flag_on_with_absent_hook_is_identical_to_flag_off(db, task_sql_log, monkeypatch, capsys):
    """态一（与改 2b 同口径）：服务层**没有**该钩子 → 静默 no-op，且本段代码在 flag on 下也发零条 SQL。

    用 `delattr` 模拟「服务层尚未实现」—— step 3 起钩子会真实存在，故不写成「flag on 就是基线」，
    那时的等价用例是挂**假钩子**（见下面的 upgrade_approved / upgrade_rejected 两条）。
    """
    import agent_stage_service

    monkeypatch.setenv("AGENT_STAGE_ENABLED", "on")
    monkeypatch.delattr(agent_stage_service, "apply_upgrade_confirmation", raising=False)
    task_id = _seed_agent_task(_TASK_UPGRADE, _TITLE_UPGRADE)

    result = db.resolve_agent_task(task_id, "approved")

    assert _task_calls(task_sql_log) == _resolve_baseline("approved", _TITLE_UPGRADE)
    assert result == {"message": "已处理", "status": "approved"}
    assert capsys.readouterr().out == "", "态一必须完全静默（缺失不算异常）"


def test_resolve_agent_task_student_notice_branch_unchanged(db, task_sql_log, monkeypatch):
    """要求 2：学生类请示 `send_care_notice` 分支（多一条发送日志）一字不改，且不误触发升级钩子。"""
    monkeypatch.delenv("AGENT_STAGE_ENABLED", raising=False)
    calls = _install_fake_hooks(monkeypatch)
    task_id = _seed_agent_task(_TASK_NOTICE, _TITLE_NOTICE)

    result = db.resolve_agent_task(task_id, "approved")

    assert _task_calls(task_sql_log) == _resolve_baseline("approved", _TITLE_NOTICE, notice_patient="张三")
    assert result == {"message": "已处理", "status": "approved"}
    assert calls == [], "action != upgrade_agent_stage → 升级钩子一次都不许调"


def test_resolve_agent_task_student_deduct_branch_unchanged(db, task_sql_log, monkeypatch):
    """要求 2：学生类请示 `deduct_herbs` 分支（无附加日志）一字不改、返回值一字不改。"""
    monkeypatch.delenv("AGENT_STAGE_ENABLED", raising=False)
    calls = _install_fake_hooks(monkeypatch)
    task_id = _seed_agent_task(_TASK_DEDUCT, _TITLE_DEDUCT)

    result = db.resolve_agent_task(task_id, "approved")

    assert _task_calls(task_sql_log) == _resolve_baseline("approved", _TITLE_DEDUCT)
    assert result == {"message": "已处理", "status": "approved"}
    assert calls == []


def test_resolve_agent_task_missing_task_is_untouched(db, task_sql_log, monkeypatch):
    """任务不存在：仍返回 None、仍只发那一条 SELECT、不触发任何钩子。"""
    monkeypatch.delenv("AGENT_STAGE_ENABLED", raising=False)
    calls = _install_fake_hooks(monkeypatch)

    result = db.resolve_agent_task(999999, "approved")

    assert result is None
    assert _task_calls(task_sql_log) == [("SELECT * FROM agent_tasks WHERE id = ?", (999999,))]
    assert calls == []


@pytest.mark.parametrize("decision", ["approved", "rejected"])
@pytest.mark.parametrize("action_data,title", [("", _TITLE_EMPTY), (_TASK_BAD_JSON, _TITLE_BAD_JSON)])
def test_resolve_agent_task_malformed_action_data_never_raises(db, task_sql_log, monkeypatch,
                                                              action_data, title, decision):
    """§4.2 改 3「整段包 try/except」：空 / 坏 `action_data` 下仍按原语义落定，绝不冒泡（4 组）。

    同时守住「改 3 段落的解析失败也不许影响返回值」—— 与既有 approved 分支里那段同款防御。
    """
    monkeypatch.delenv("AGENT_STAGE_ENABLED", raising=False)
    task_id = _seed_agent_task(action_data, title)

    result = db.resolve_agent_task(task_id, decision)

    assert _task_calls(task_sql_log) == _resolve_baseline(decision, title)
    assert result == {"message": "已处理", "status": decision}


def test_resolve_agent_task_rejected_with_non_dict_action_data_stays_unchanged(db, task_sql_log, monkeypatch):
    """非对象 JSON（数组 / 字符串 / 数字）+ rejected：**不许**因改 3 新增的那次解析而冒泡。

    改动前 rejected 路径根本不解析 `action_data`，所以期望序列与 rejected 基线严格同构；本形态未列入
    改动前 13 组留档（那里只有空 / 坏 JSON），由 `isinstance` 守卫 + 本条用例直接守住 —— 没有它就会
    是本步引入的回归。
    注：approved 路径遇到同类脏数据在改动前就会在 `action.get(...)` 那一行抛 AttributeError，
    本步不改变它（不属改 3 范围，此处仅作既有行为记录）。
    """
    monkeypatch.delenv("AGENT_STAGE_ENABLED", raising=False)
    calls = _install_fake_hooks(monkeypatch)
    task_id = _seed_agent_task("[1, 2, 3]", _TITLE_NON_DICT)

    result = db.resolve_agent_task(task_id, "rejected")

    assert _task_calls(task_sql_log) == _resolve_baseline("rejected", _TITLE_NON_DICT)
    assert result == {"message": "已处理", "status": "rejected"}
    assert calls == []


def test_resolve_agent_task_upgrade_approved_calls_apply_hook_with_to_stage(db, task_sql_log, monkeypatch):
    """改 3 主路径（✅确认）：`apply_upgrade_confirmation(teacher_name, to, task_id)` 恰好一次。"""
    monkeypatch.delenv("AGENT_STAGE_ENABLED", raising=False)
    calls = _install_fake_hooks(monkeypatch)
    task_id = _seed_agent_task(_TASK_UPGRADE, _TITLE_UPGRADE)

    result = db.resolve_agent_task(task_id, "approved")

    assert calls == [("apply_upgrade_confirmation", TEACHER, "apprentice", task_id)]
    assert _task_calls(task_sql_log) == _resolve_baseline("approved", _TITLE_UPGRADE), \
        "假钩子零 SQL → 语句序列仍与改动前基线逐条一致"
    assert result == {"message": "已处理", "status": "approved"}


def test_resolve_agent_task_upgrade_rejected_calls_decline_hook(db, monkeypatch):
    """改 3 另一条路径（❌忽略）：`decline_upgrade(teacher_name, task_id)` 恰好一次（不调 apply）。"""
    monkeypatch.delenv("AGENT_STAGE_ENABLED", raising=False)
    calls = _install_fake_hooks(monkeypatch)
    task_id = _seed_agent_task(_TASK_UPGRADE, _TITLE_UPGRADE)

    result = db.resolve_agent_task(task_id, "rejected")

    assert calls == [("decline_upgrade", TEACHER, task_id)]
    assert result == {"message": "已处理", "status": "rejected"}


def test_resolve_agent_task_upgrade_without_to_passes_none(db, monkeypatch):
    """韧性：`action_data` 缺 `to` 键 → 仍转发（`to_stage=None`），合法性由服务层校验，库层不擅自跳过。"""
    monkeypatch.delenv("AGENT_STAGE_ENABLED", raising=False)
    calls = _install_fake_hooks(monkeypatch)
    task_id = _seed_agent_task(_TASK_UPGRADE_NO_TO, _TITLE_UPGRADE_NO_TO)

    result = db.resolve_agent_task(task_id, "approved")

    assert calls == [("apply_upgrade_confirmation", TEACHER, None, task_id)]
    assert result == {"message": "已处理", "status": "approved"}


def test_resolve_agent_task_hook_runs_even_when_flag_off(db, monkeypatch):
    """CTO 批复①：调用点**不判 flag** —— flag off 下库层照样转发，算不算指标由服务层首行自闸门决定。"""
    monkeypatch.setenv("AGENT_STAGE_ENABLED", "off")
    calls = _install_fake_hooks(monkeypatch)
    task_id = _seed_agent_task(_TASK_UPGRADE, _TITLE_UPGRADE)

    db.resolve_agent_task(task_id, "approved")

    assert calls == [("apply_upgrade_confirmation", TEACHER, "apprentice", task_id)]


def test_resolve_agent_task_hook_exception_only_warns(db, task_sql_log, monkeypatch, capsys):
    """态二（与改 2b 同口径）：钩子抛异常 → 只 print warn；决策已落定（不回滚）、不冒泡、返回值不变。"""
    monkeypatch.delenv("AGENT_STAGE_ENABLED", raising=False)
    _install_fake_hooks(monkeypatch, boom="apply_upgrade_confirmation")
    task_id = _seed_agent_task(_TASK_UPGRADE, _TITLE_UPGRADE)

    result = db.resolve_agent_task(task_id, "approved")

    out = capsys.readouterr().out
    assert "[warn]" in out and "apply_upgrade_confirmation" in out

    assert result == {"message": "已处理", "status": "approved"}
    assert _task_calls(task_sql_log) == _resolve_baseline("approved", _TITLE_UPGRADE)
    row, logs = _read_agent_task(task_id)
    assert row["status"] == "approved", "钩子炸了也必须保持老师已确认的状态（commit 在前）"
    assert logs == [("approve", f"老师确认执行：{_TITLE_UPGRADE}")]


def test_resolve_agent_task_hook_runs_after_commit(db, monkeypatch):
    """时序：钩子在 `commit` **之后**被调用 —— 钩子内另开连接已能看到「任务已落定 + 行动日志已写」。"""
    import agent_stage_service

    monkeypatch.delenv("AGENT_STAGE_ENABLED", raising=False)
    task_id = _seed_agent_task(_TASK_UPGRADE, _TITLE_UPGRADE)
    observed = {}

    def apply_upgrade_confirmation(teacher_name, to_stage, got_task_id):
        conn = sqlite3.connect(database.DB_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT status FROM agent_tasks WHERE id = ?", (got_task_id,)).fetchone()
        log_count = conn.execute(
            "SELECT COUNT(*) AS n FROM agent_action_log WHERE task_id = ?", (got_task_id,)
        ).fetchone()["n"]
        conn.close()
        observed["status"] = row["status"]
        observed["log_count"] = log_count

    monkeypatch.setattr(agent_stage_service, "apply_upgrade_confirmation", apply_upgrade_confirmation, raising=False)

    db.resolve_agent_task(task_id, "approved")

    assert observed == {"status": "approved", "log_count": 1}


def test_resolve_agent_task_reuses_single_two_state_caller():
    """要求 1 / 4（源码级）：改 3 只许**复用** `_call_agent_stage_hook()`。

    不 import 服务层、不判 flag、不出现第二份两态实现 —— 与改 2b 同一口径。
    """
    import inspect

    source = inspect.getsource(database.resolve_agent_task)

    # 只数**真实调用**：注释 / docstring 里写的是 `_call_agent_stage_hook()`，括号后紧跟反引号 → 不计入
    assert source.count('_call_agent_stage_hook("') == 2, "approved / rejected 各一次，且都走同一个调用器"
    assert "import agent_stage_service" not in source, "库层不得直接 import 服务层（延迟 import 在调用器里）"
    assert "agent_stage_enabled" not in source, "调用点不判 flag（批复①）"
    assert "except Exception" in source, "action_data 解析必须有防御（§4.2 改 3「整段包 try/except」）"

    assert inspect.getsource(database).count("def _call_agent_stage_hook(") == 1, \
        "两态实现只许一份（改 2b / 改 3 共用同一个调用器）"


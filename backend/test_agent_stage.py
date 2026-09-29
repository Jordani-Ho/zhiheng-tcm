"""【Epic 2】智能体五阶段 —— database.py 新增库函数的守护测试（§8 step 2.1：只覆盖 DB 层）

对齐：docs/epic2-agent-stage-design-v1.md §1.2 / §1.3 / §3.4–§3.6 / §4.2 / §7.1-①⑥，
以及 CTO 2026-09-28 的五项裁决（双闸门 / 服务层 flag / 不回落 content / 钩子两态 / 不吞 sqlite3.Error）。

本文件**从 DB 层起测**（服务层用例自施工步骤 3.1 起在本文件继续追加，见 ⑬ 组；接口层用例属 step 4）：
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

    ⑬ 【施工步骤 3.1】服务层**骨架**：`agent_stage_store_ready()`（0003 三表齐备 → True；缺一 / 空库 /
       库文件不在 / 表被改名 / 库不可读 → False；异常吞成 False、绝不建库写库、**不读 flag**、
       **只看 0003 三表不看 0004 两列**）+ `AgentStageError` 的四键形状（code / msg / errors /
       warnings 与统一错误体一一对应，且不与 `TemplateError` 混链）。本组**不**断言状态机符号
       （`current_stage` / `require_capability` / `evaluate` / 三个钩子 …）的缺席 —— 它们属 3.2–3.4。

    ⑭ 【施工步骤 3.2】配置链 + 阶段真值读取：`DEFAULT_STAGE_CONFIG`（§3.5 键表逐字）/
       `load_stage_config`（§3.4 四层读取链：内置默认 ← 全局行 ← 老师行 ← env 白名单；行缺失 /
       JSON 损坏 / 库异常三种态都降级不抛；非法值整份回落内置默认）/ `validate_stage_config`
       （§3.4 第 5 条：返回 `(ok, errors[{path,msg}])`，**只拦不清**，`default_stage` 不得高于
       learning）+ `current_stage` / `describe_stage`（§1.5 四条路径，fail-closed 到 default_stage）
       + 「读数零写入 / 只发 SELECT」「不读 flag」。**零接线**：本组只用直接调用验证行为。
    ⑮ 【施工步骤 3.3】**唯一能力闸门** `require_capability`（§2.2 / §2.3）：白名单**默认拒绝**
       （枚举外一律拒 = §2.1 三不铁律的代码级形态，任何配置都不得解锁）+ `CAPABILITY_MATRIX`
       **逐格**判定（五阶段 × 五能力 25 格逐格钉住 + 与设计文档 §2.3 表格交叉核对）+ flag off 时
       只放行 §2.3 的既有能力例外（零 DB 访问 / 零审计）+ `matrix_enforced=False` 只放宽 §2.5
       逐项枚举的三个新能力（放行也写反向事件 `permission_relaxed`）+ 拒绝**同点**写
       `permission_denied` 审计（stage / capability / 时间）且写失败不改判定 + 库坏了不抛。
       **返回 bool、拒绝不抛**（403 的抛出点属 step 4 接口层）。**零接线**，且不改 ⑭ 组一行。
    ⑯ 【施工步骤 3.4-a】**指标层**：`compute_template_match`（§3.2 ①）+ `compute_modification_consistency`
       （§3.3 ②）+ 库层只读样本原语 `database.get_draft_samples`（批复 C-1：窗口 + 类型过滤 + LIMIT）：
       样本集合与三类排除计数（`skipped_no_template` / `skipped_stale_template` / `skipped_empty`）+
       铁律违规样本（AI 填了 `teacher` 段 → 该样本 `match = 0.0`）+ **空集语义 `value is None` ≠ 0**
       （CTO 硬约束 2：空值既不是 0 分、也不可能「通过」任何阈值）+ 权重 / 截断 / 窗口 / 上限
       **全部来自 `cfg`**（不硬编码）+ **全程只读**（只发 SELECT / PRAGMA，五张表零写入，flag off 照算）
       + 缺列 / 读库异常都降级不抛 + 严格 LCS 的回归用例。`evaluate` / 三个钩子 /
       `get_agent_stage_log_stats`（§6.3-27 的 ③ 占位键亦同）属 **3.4-b**，本组**不**断言它们的缺席
       —— 与 ⑬ ⑭ ⑮ 组同一纪律。


运行方式（Windows，串行；见 pytest.ini）：
    cd backend
    ..\\venv\\Scripts\\python.exe -m pytest test_agent_stage.py -v
"""
import json
import os
import re
import sqlite3
import sys
from datetime import datetime

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


# ============ ⑬ 【施工步骤 3.1】服务层骨架：存储就绪探针 + 服务层错误类型 ============
#
# 本步只收两个**行为完整且可验证**的服务层符号（CTO 放行 3.1 的要求 1–3）：
#   ① `agent_stage_service.agent_stage_store_ready()`：0003 三表齐备 → True，否则 False；异常吞成
#      False、绝不建库 / 建表 / 写入、**不读 flag**、只看 0003 三表**不看** 0004 两列；
#   ② `agent_stage_service.AgentStageError`：code / msg / errors / warnings 四键 = 统一错误体形状。
# 本组**不**断言状态机符号（`current_stage` / `require_capability` / `evaluate` / 三个钩子 …）的缺席：
# 它们属施工步骤 3.2–3.4，用一条「现在必须不存在」的用例会把后续子步的落地顺序锁死。


def _copy_tested_db(monkeypatch, tmp_path, filename):
    """把当前 test.db（已迁移到 head）复制一份为可随意改坏的同构库，并把 DB_PATH 指过去。

    用 `sqlite3.Connection.backup()` 而非复制文件：上一条连接可能仍持有库文件，backup 拿到的
    一定是一致快照（本文件既有的 `_raw_db()` 是「从零造老库」，这里要的是「完整库的副本」）。
    """
    target = os.path.join(str(tmp_path), filename)
    src = sqlite3.connect(database.DB_PATH)
    try:
        dst = sqlite3.connect(target)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    monkeypatch.setattr(database, "DB_PATH", target)
    return target


def _drop_table(path, table):
    conn = sqlite3.connect(path)
    conn.execute("DROP TABLE %s" % table)
    conn.commit()
    conn.close()


def _table_names(path):
    conn = sqlite3.connect(path)
    try:
        return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()


def test_service_store_ready_true_after_full_migration(db):
    """三表齐备（迁移到 head）→ True；探针本身**零副作用**（跑前跑后的表集合一致）。"""
    import agent_stage_service

    before = _table_names(database.DB_PATH)

    assert agent_stage_service.agent_stage_store_ready() is True

    assert _table_names(database.DB_PATH) == before, "探针不得建表 / 删表 / 改名（纯只读）"


def test_service_store_ready_probe_only_reads_sqlite_master(db, sql_log):
    """行为级守护「绝不建库 / 建表 / 写入」：全程只发**一条**只读查询。"""
    import agent_stage_service

    assert agent_stage_service.agent_stage_store_ready() is True

    assert _all_calls(sql_log) == [(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name IN (?, ?, ?)",
        agent_stage_service.AGENT_STAGE_STORE_TABLES,
    )], "探针只许发这一条只读语句（零 DDL / 零写入 / 零 PRAGMA）"


def test_service_store_tables_constant_matches_migration_0003():
    """`AGENT_STAGE_STORE_TABLES` ↔ 迁移 0003 的 `CREATE TABLE IF NOT EXISTS <名>` 逐名对得上。

    与 ① 组「白名单 ↔ 0003 建表列一致」同一手法：常量是探针的唯一真相源，表名一漂移就会把
    「已就位」误判成 503（或反之），所以直接拿迁移源码交叉断言，不靠人眼。
    """
    import agent_stage_service

    path = os.path.join(os.path.dirname(os.path.abspath(database.__file__)),
                        "alembic", "versions", "0003_add_agent_stage.py")
    with open(path, encoding="utf-8") as fh:
        declared = set(re.findall(r"CREATE TABLE IF NOT EXISTS\s+(\w+)", fh.read()))

    assert len(agent_stage_service.AGENT_STAGE_STORE_TABLES) == 3
    assert set(agent_stage_service.AGENT_STAGE_STORE_TABLES) == declared, \
        "探针常量与 0003 建表语句不一致：常量=%s 迁移=%s" % (
            sorted(agent_stage_service.AGENT_STAGE_STORE_TABLES), sorted(declared))


@pytest.mark.parametrize("table", ["agent_stage_state", "agent_stage_config", "agent_stage_log"])
def test_service_store_ready_requires_each_of_the_three_tables(db, monkeypatch, tmp_path, table):
    """三张表**缺一即 False**（参数化覆盖每一张，防「只看其中一张」的假实现）。"""
    import agent_stage_service

    assert agent_stage_service.agent_stage_store_ready() is True, "前置：完整库必须 True"

    path = _copy_tested_db(monkeypatch, tmp_path, "missing_%s.db" % table)
    _drop_table(path, table)

    assert agent_stage_service.agent_stage_store_ready() is False


def test_service_store_ready_false_on_empty_db_without_raising(monkeypatch, tmp_path):
    """0003 未跑（文件在、表不在）→ False 且**不抛**（接口层靠它映射 503；抛出去就变 500）。"""
    import agent_stage_service

    empty = os.path.join(str(tmp_path), "empty_probe.db")
    sqlite3.connect(empty).close()                 # 只造文件、不建表（与 ⑦ 组同款）
    monkeypatch.setattr(database, "DB_PATH", empty)

    assert agent_stage_service.agent_stage_store_ready() is False
    assert _table_names(empty) == set(), "探针不得顺手建表"


def test_service_store_ready_false_when_db_file_missing(monkeypatch, tmp_path):
    """库文件不存在（误删 / 路径写错）→ 同样 False、不抛。

    口径注：`sqlite3.connect()` 会落地一个 0 字节文件 —— 这是 Epic 1 `template_store_ready()` 的
    既有行为，故本条只断言「False + 不抛」，不把「不得创建文件」当红线（见本步 docstring 第 3 条）。
    """
    import agent_stage_service

    monkeypatch.setattr(database, "DB_PATH", os.path.join(str(tmp_path), "never_created.db"))

    assert agent_stage_service.agent_stage_store_ready() is False


def test_service_store_ready_ignores_0004_columns(monkeypatch, tmp_path):
    """口径②：库只迁到 0003（`patient_records` 尚无 0004 两个引用列）→ **仍为 True**。

    「存储就绪」= 0003 三表；0004 两列只是 ① 指标的追加快照（缺列时按 `template_id = 0` 计入
    `skipped_no_template`，§3.2）。若把 0004 绑进 503，就把「少一个指标基准」升级成「阶段功能
    整体不可用」—— 这条用真实库形态把这个分界线钉住。
    """
    import agent_stage_service

    scratch = os.path.join(str(tmp_path), "rev_0003.db")
    monkeypatch.setattr(database, "DB_PATH", scratch)
    database.init_db()
    assert migrations_runner.run_upgrade("0003_add_agent_stage", db_file=scratch) is True

    conn = database.get_connection()
    try:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info('patient_records')")}
    finally:
        conn.close()
    assert "template_id" not in columns and "template_version" not in columns, \
        "前置：该库只迁到 0003，0004 的两个引用列必须还不存在"

    assert agent_stage_service.agent_stage_store_ready() is True


def test_service_store_ready_mirrors_template_store_ready(db, monkeypatch, tmp_path):
    """与 Epic 1 先例同口径：同一库形态下两个探针返回同一个布尔（本探针的模板就是它）。"""
    import agent_stage_service
    import template_service

    assert agent_stage_service.agent_stage_store_ready() is True
    assert template_service.template_store_ready() is True

    path = _copy_tested_db(monkeypatch, tmp_path, "mirror.db")
    _drop_table(path, "agent_stage_state")
    _drop_table(path, "templates")

    assert agent_stage_service.agent_stage_store_ready() is False
    assert template_service.template_store_ready() is False


def test_service_store_ready_is_independent_of_flag(db, monkeypatch):
    """口径①：探针**不读 flag** —— off / on / 未设置三种取值下结论必须一致（要求 3 的一部分）。"""
    import agent_stage_service

    for value in ("off", "on", None):
        if value is None:
            monkeypatch.delenv("AGENT_STAGE_ENABLED", raising=False)
        else:
            monkeypatch.setenv("AGENT_STAGE_ENABLED", value)
        assert agent_stage_service.agent_stage_store_ready() is True


def test_agent_stage_error_shape_is_unified_error_body():
    """`AgentStageError` 四键 = 统一错误体 `{error, msg, errors, warnings}`；不与 Epic 1 错误类混链。"""
    import agent_stage_service
    import template_service

    exc = agent_stage_service.AgentStageError(
        "stage_config_invalid", "閾值配置非法",
        errors=[{"path": "min_samples", "msg": "不在 [1, max_samples]"}])

    assert isinstance(exc, Exception)
    assert str(exc) == "閾值配置非法" == exc.msg
    assert set(vars(exc)) == {"code", "msg", "errors", "warnings"}, \
        "四键必须齐备（接口层按 detail 直出，不必判断某键是否存在）"
    assert exc.errors == [{"path": "min_samples", "msg": "不在 [1, max_samples]"}]
    assert exc.warnings == []

    # 缺省口径：None → 空列表（detail 里不允许出现 null）
    bare = agent_stage_service.AgentStageError("stage_forbidden", "智能體當前為「學習期」")
    assert bare.errors == [] and bare.warnings == []

    # 浅拷贝：抛错方持有的 list 之后再改，不影响异常对象（接口层改 detail 也不会回写异常）
    given = [{"path": "a", "msg": "b"}]
    copied = agent_stage_service.AgentStageError("stage_config_invalid", "x", errors=given)
    given.append({"path": "c", "msg": "d"})
    assert len(copied.errors) == 1

    # 与 Epic 1 的错误类「同构 + 各加一对」，但不是同一条继承链（互不复用 / Epic 1 零改动）
    ref = template_service.TemplateError("templates_disabled", "模板接口未啟用")
    assert set(vars(ref)) == {"code", "msg"}
    assert not issubclass(agent_stage_service.AgentStageError, template_service.TemplateError)


# ============ ⑭ 【施工步骤 3.2】配置链 + 阶段真值读取 ============
#
# CTO 2026-09-28 放行 step 3.2 的六条约束，本组逐条落地（约束 5 的「flag off 逐字节不变」由既有
# ⑨ ⑪ ⑫ 组的改动前基线与本组的「零写入 / 只发 SELECT / 不读 flag」用例共同保证）：
#   ① 配置链三符号：`DEFAULT_STAGE_CONFIG` / `load_stage_config` / `validate_stage_config`；
#   ② 阶段真值两符号：`current_stage` / `describe_stage` —— 四条路径（行在内 / 行值非法 / 无行 /
#     读库异常）全部 **fail-closed 到 `default_stage`**（校验层只放行 observation / learning）；
#   ③ `load_stage_config` 三态：**行存在 / 行缺失 / JSON 损坏**（外加 0003 未跑的 sqlite3.Error）；
#   ④ `validate_stage_config` 拒绝非法值且**不清洗**（回写入参 / 删非法键 / 补默认值都不许）；
#   ⑥ 本组即约束 6 说的「⑭ 组」。
# 本组**不**断言 3.3 / 3.4 符号（`require_capability` / `evaluate` / 三个钩子 …）的缺席 —— 与 ⑬ 组
# 同一口径：写一条「现在必须不存在」的用例会把后续子步的落地顺序锁死。


def _raw_execute(sql, params=()):
    """绕过 `database.get_connection()` 直连库文件执行一条 SQL（造前置态 / 模拟「人手 SQL 写坏」）。

    刻意不走 `database.get_connection()`：本组有「读数只发 SELECT」的语句级断言（`sql_log`），
    造前置态的写语句若走同一条口子，就分不清「测试自己写的」与「被测代码写的」。
    """
    conn = sqlite3.connect(database.DB_PATH)
    try:
        conn.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


def _raw_scalar(sql, params=()):
    """绕过 `database.get_connection()` 直连库文件读一个标量（断言「库没被写坏」用）。"""
    conn = sqlite3.connect(database.DB_PATH)
    try:
        return conn.execute(sql, params).fetchone()[0]
    finally:
        conn.close()


def _clear_stage_config_rows():
    """删掉 `agent_stage_config` 全部行（含迁移种子的全局行）→ 造「行缺失」态。"""
    _raw_execute("DELETE FROM agent_stage_config")


def _put_raw_config_row(teacher_name, raw_config_json):
    """直接写一行 `config_json`（**原文照写**，用于造「JSON 损坏 / 非对象」态）。"""
    _raw_execute(
        "INSERT INTO agent_stage_config (teacher_name, config_json, updated_at) VALUES (?, ?, '') "
        "ON CONFLICT(teacher_name) DO UPDATE SET config_json = excluded.config_json",
        (teacher_name, raw_config_json),
    )


def _put_raw_state_row(teacher_name, stage, pending_task_id=0, stage_since="", stage_source="default",
                       pending_stage=""):
    """直接写一行状态（各列**原文照写**，用于造「白名单外值 / 坏整数 / 已有行」态）。"""
    _raw_execute(
        "INSERT INTO agent_stage_state "
        "(teacher_name, stage, stage_since, stage_source, pending_stage, pending_task_id, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, '') "
        "ON CONFLICT(teacher_name) DO UPDATE SET stage = excluded.stage, "
        "stage_since = excluded.stage_since, stage_source = excluded.stage_source, "
        "pending_stage = excluded.pending_stage, pending_task_id = excluded.pending_task_id",
        (teacher_name, stage, stage_since, stage_source, pending_stage, pending_task_id),
    )


# ---- 配置链 ①：内置默认配置（§3.5 键表 = 唯一硬编码点）----

def test_default_stage_config_matches_design_key_table():
    """§3.5 的 16 键键表**逐字**钉住（含每个默认值），并交叉核对键名确实出现在设计文档里。

    本常量是全 Epic 的**唯一硬编码点**（§3.4：最终配置 = 内置默认 ← 全局行 ← 老师行 ← env）：
    它漂移了，① ② 的阈值、冷却、TTL 就全线跟着漂 —— 所以钉字面值，不做「大致相等」。
    """
    import agent_stage_service

    expected = {
        "schema_version": 1,
        "default_stage": "learning",
        "window_days": 90,
        "max_samples": 50,
        "min_samples": 5,
        "min_template_match": 0.75,
        "min_modification_consistency": 0.80,
        "max_violations": 0,
        "max_permission_denials": 0,
        "recommend_cooldown_hours": 24,
        "demote_consistency_floor": 0.50,
        "demote_streak": 3,
        "truncate_chars": 2000,
        "template_match_weights": {"section_hit": 0.6, "section_order": 0.4},
        "metrics_ttl_hours": 24,
        "matrix_enforced": True,
    }
    assert agent_stage_service.DEFAULT_STAGE_CONFIG == expected
    assert len(expected) == 16, "§3.5 键表共 16 键（键表增删必须同步设计文档）"

    # 键名交叉核对：设计文档 §3.5 键表里必须有过这个名字（防「凭空多键 / 悄悄少键」）
    doc = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(database.__file__))),
                       "docs", "epic2-agent-stage-design-v1.md")
    with open(doc, encoding="utf-8") as fh:
        text = fh.read()
    for key in expected:
        assert "`%s`" % key in text, "§3.5 键表里没有 `%s`（常量与设计分叉）" % key


def test_load_stage_config_returns_fresh_objects(db):
    """每次调用返回**新建对象**（含嵌套的 `template_match_weights`）：改它不得污染常量 / 上次结果。"""
    import agent_stage_service

    first = agent_stage_service.load_stage_config(TEACHER)
    first["min_samples"] = 999
    first["template_match_weights"]["section_hit"] = 0.0

    assert agent_stage_service.DEFAULT_STAGE_CONFIG["min_samples"] == 5
    assert agent_stage_service.DEFAULT_STAGE_CONFIG["template_match_weights"]["section_hit"] == 0.6
    assert agent_stage_service.load_stage_config(TEACHER)["min_samples"] == 5


# ---- 配置链 ②：四层合并链（§3.4 第 1 条）----

def test_load_stage_config_row_absent_uses_builtin_defaults_silently(db, capsys):
    """**三态之一：行缺失** → 全内置默认，且**不告警**（新老师还没有专属行 = 正常态）。"""
    import agent_stage_service

    _clear_stage_config_rows()

    assert agent_stage_service.load_stage_config(TEACHER) == agent_stage_service.DEFAULT_STAGE_CONFIG
    assert "[warn]" not in capsys.readouterr().out, "行缺失属正常态，不该打告警"


def test_load_stage_config_global_row_overrides_builtin(db):
    """全局行（`teacher_name=''`）逐键覆盖内置默认，其余键仍是内置值。"""
    import agent_stage_service

    _put_raw_config_row("", json.dumps({"min_template_match": 0.6, "window_days": 30}))

    cfg = agent_stage_service.load_stage_config(TEACHER)
    assert cfg["min_template_match"] == 0.6
    assert cfg["window_days"] == 30
    assert cfg["min_samples"] == 5, "未被覆盖的键必须回落内置默认"
    assert cfg["matrix_enforced"] is True


def test_load_stage_config_teacher_row_overrides_global_row(db):
    """老师专属行**赢过**全局行（§3.4 的覆盖顺序），且只覆盖它自己声明的键。"""
    import agent_stage_service

    _put_raw_config_row("", json.dumps({"min_samples": 7, "max_samples": 20, "demote_streak": 5}))
    _put_raw_config_row(TEACHER, json.dumps({"min_samples": 9}))

    cfg = agent_stage_service.load_stage_config(TEACHER)
    assert cfg["min_samples"] == 9, "老师专属行优先"
    assert cfg["max_samples"] == 20, "老师行没声明的键仍由全局行覆盖"
    assert cfg["demote_streak"] == 5

    other = agent_stage_service.load_stage_config(OTHER_TEACHER)
    assert other["min_samples"] == 7, "别的老师不受这位老师的专属行影响"


def test_load_stage_config_keeps_unknown_keys(db):
    """未知键**原样保留**（前向兼容，§3.4 第 1 条）：本层的合并器不得当过滤器用。"""
    import agent_stage_service

    _clear_stage_config_rows()
    _put_raw_config_row("", json.dumps({"future_scoring": {"mode": "strict"}, "extra_flag": True}))

    cfg = agent_stage_service.load_stage_config(TEACHER)
    assert cfg["future_scoring"] == {"mode": "strict"}
    assert cfg["extra_flag"] is True
    assert cfg["min_samples"] == 5


# ---- 配置链 ③：三态之「JSON 损坏」（该层按无覆盖处理 + 告警；不抛）----

def test_load_stage_config_corrupt_global_row_is_ignored_with_warning(db, capsys):
    """全局行 `config_json` 不是合法 JSON → 该行按「无覆盖」处理 + 告警，**不抛异常**。"""
    import agent_stage_service

    _clear_stage_config_rows()
    _put_raw_config_row("", "{not json at all")

    assert agent_stage_service.load_stage_config(TEACHER) == agent_stage_service.DEFAULT_STAGE_CONFIG
    out = capsys.readouterr().out
    assert "損壞" in out and "全局" in out, "损坏行必须留下可定位的告警：%r" % out


def test_load_stage_config_corrupt_teacher_row_keeps_global_row(db, capsys):
    """老师行损坏时**只丢坏的那一层**：全局行的覆盖照旧生效（不是整份回落内置默认）。"""
    import agent_stage_service

    _clear_stage_config_rows()
    _put_raw_config_row("", json.dumps({"window_days": 30}))
    _put_raw_config_row(TEACHER, "{\"window_days\": 30,")

    cfg = agent_stage_service.load_stage_config(TEACHER)
    assert cfg["window_days"] == 30, "全局行仍应生效"
    assert cfg["min_samples"] == 5
    assert "老師專屬" in capsys.readouterr().out


@pytest.mark.parametrize("raw", ["[1, 2, 3]", "\"just a string\"", "null", "42"])
def test_load_stage_config_non_object_json_is_treated_as_corrupt(db, capsys, raw):
    """合法 JSON 但**不是对象**（数组 / 字符串 / null / 数字）→ 与损坏同款处理（该层无覆盖 + 告警）。"""
    import agent_stage_service

    _clear_stage_config_rows()
    _put_raw_config_row("", raw)

    assert agent_stage_service.load_stage_config(TEACHER) == agent_stage_service.DEFAULT_STAGE_CONFIG
    assert "不是 JSON 對象" in capsys.readouterr().out


# ---- 配置链 ④：非法值 → 整份回落内置默认（§3.4 第 5 条「读取时回落」）----

def test_load_stage_config_invalid_value_falls_back_wholesale(db, capsys):
    """行里的值越界（`min_samples > max_samples`）→ **整份**回落内置默认 + 告警。

    刻意不「只丢那一个键」：§3.4 第 5 条写的是「读取时非法 → 回落内置默认」；半信半疑地混用
    「一半脏值 + 一半默认」，会让老师看到的阈值来源无法解释。
    """
    import agent_stage_service

    _clear_stage_config_rows()
    _put_raw_config_row("", json.dumps({"min_samples": 9, "max_samples": 5, "window_days": 30}))

    cfg = agent_stage_service.load_stage_config(TEACHER)
    assert cfg == agent_stage_service.DEFAULT_STAGE_CONFIG
    assert cfg["window_days"] == 90, "同一行里合法的键也不得生效（整份回落）"
    out = capsys.readouterr().out
    assert "非法" in out and "min_samples" in out


def test_load_stage_config_missing_store_degrades_to_builtin(db, monkeypatch, tmp_path, capsys):
    """**库层异常**（0003 未跑：`agent_stage_config` 表不在）→ 内置默认 + 告警、**绝不抛**（§1.5 第 3 条）。"""
    import agent_stage_service

    path = _copy_tested_db(monkeypatch, tmp_path, "no_config_table.db")
    _drop_table(path, "agent_stage_config")

    assert agent_stage_service.load_stage_config(TEACHER) == agent_stage_service.DEFAULT_STAGE_CONFIG
    assert "失敗" in capsys.readouterr().out


# ---- 配置链 ⑤：环境变量白名单（§3.4 第 2 条）----

def test_load_stage_config_applies_env_whitelist_over_every_row(db, monkeypatch):
    """env 是**最高一层**（内置 ← 全局 ← 老师 ← env），按各键类型转换；总闸不入配置。"""
    import agent_stage_service

    _put_raw_config_row("", json.dumps({"max_samples": 20, "window_days": 30}))
    _put_raw_config_row(TEACHER, json.dumps({"max_samples": 10}))

    monkeypatch.setenv("AGENT_STAGE_MAX_SAMPLES", "123")
    monkeypatch.setenv("AGENT_STAGE_MATRIX_ENFORCED", "off")
    monkeypatch.setenv("AGENT_STAGE_MIN_TEMPLATE_MATCH", "0.5")
    monkeypatch.setenv("AGENT_STAGE_DEFAULT_STAGE", "  Observation  ")
    monkeypatch.setenv("AGENT_STAGE_ENABLED", "on")

    cfg = agent_stage_service.load_stage_config(TEACHER)
    assert cfg["max_samples"] == 123, "env 赢过老师专属行与全局行"
    assert cfg["matrix_enforced"] is False, "布尔键按 on/off 语义解析"
    assert cfg["min_template_match"] == 0.5
    assert cfg["default_stage"] == "observation", "阶段名统一小写，并去掉前后空白"
    assert cfg["window_days"] == 30, "未被 env 覆盖的键仍走行"
    assert "enabled" not in cfg, "AGENT_STAGE_ENABLED 是总闸、不是配置键（不得混进配置）"


def test_load_stage_config_ignores_non_whitelisted_env_with_warning(db, monkeypatch, capsys):
    """白名单外的 `AGENT_STAGE_*` 一律忽略 + 告警（防 typo 静默生效）。

    `template_match_weights` 这种复合键**不在** env 白名单里：env 的字符串无法无损表达它，
    只能走配置行（否则「半边覆盖」会让权重来源无法解释）。
    """
    import agent_stage_service

    monkeypatch.setenv("AGENT_STAGE_TEMPLATE_MATCH_WEIGHTS", "{\"section_hit\": 1.0}")
    monkeypatch.setenv("AGENT_STAGE_WINDOWDAYS", "30")

    cfg = agent_stage_service.load_stage_config(TEACHER)
    assert cfg["template_match_weights"] == {"section_hit": 0.6, "section_order": 0.4}
    assert cfg["window_days"] == 90, "拼错的键不得生效（否则 typo 静默生效）"
    out = capsys.readouterr().out
    assert "未知的環境變量 AGENT_STAGE_TEMPLATE_MATCH_WEIGHTS" in out
    assert "未知的環境變量 AGENT_STAGE_WINDOWDAYS" in out


def test_load_stage_config_bad_env_value_is_ignored_not_fatal(db, monkeypatch, capsys):
    """env 值无法解析（给整数键写 `abc`）→ 只忽略该键 + 告警，其余链路照常（**不炸链路**）。"""
    import agent_stage_service

    _put_raw_config_row("", json.dumps({"window_days": 30}))
    monkeypatch.setenv("AGENT_STAGE_MAX_SAMPLES", "abc")
    monkeypatch.setenv("AGENT_STAGE_MATRIX_ENFORCED", "maybe")

    cfg = agent_stage_service.load_stage_config(TEACHER)
    assert cfg["max_samples"] == 50, "坏值 → 回落下一级（内置）"
    assert cfg["matrix_enforced"] is True
    assert cfg["window_days"] == 30, "同一次调用里其它层照旧生效"
    out = capsys.readouterr().out
    assert "無法解析" in out and "AGENT_STAGE_MAX_SAMPLES" in out


def test_load_stage_config_out_of_range_env_falls_back_wholesale(db, monkeypatch, capsys):
    """env 值**能解析但非法**（`0` / `apprentice`）→ 与行里的脏值同款：整份回落内置默认 + 告警。

    这条是 fail-closed 的 env 侧证明：`AGENT_STAGE_DEFAULT_STAGE=apprentice` 绝不能生效 ——
    否则运维一个错字就能把全体未初始化老师的兜底阶段抬到見習期以上。
    """
    import agent_stage_service

    monkeypatch.setenv("AGENT_STAGE_MAX_SAMPLES", "0")
    assert agent_stage_service.load_stage_config(TEACHER) == agent_stage_service.DEFAULT_STAGE_CONFIG

    monkeypatch.delenv("AGENT_STAGE_MAX_SAMPLES")
    monkeypatch.setenv("AGENT_STAGE_DEFAULT_STAGE", "apprentice")
    cfg = agent_stage_service.load_stage_config(TEACHER)
    assert cfg == agent_stage_service.DEFAULT_STAGE_CONFIG
    assert cfg["default_stage"] == "learning"
    assert "default_stage" in capsys.readouterr().out


def test_load_stage_config_re_reads_every_call_and_only_selects(db, sql_log, monkeypatch):
    """§3.4 第 3 条「每次调用现读、不缓存」+ 本段纪律「读数只发 SELECT」。"""
    import agent_stage_service

    _put_raw_config_row("", json.dumps({"window_days": 30}))

    marker = len(_all_calls(sql_log))
    assert agent_stage_service.load_stage_config(TEACHER)["window_days"] == 30

    monkeypatch.setenv("AGENT_STAGE_WINDOW_DAYS", "45")     # 不缓存 → 立刻生效，无需重启
    assert agent_stage_service.load_stage_config(TEACHER)["window_days"] == 45

    statements = [sql for sql, _ in _all_calls(sql_log)[marker:]]
    assert statements, "必须真的读了库（否则「现读」无从谈起）"
    assert all(sql.lstrip().upper().startswith("SELECT") for sql in statements), statements


# ---- 配置校验层 ⑥：合法边界（§3.4 第 5 条 / 只拦不清）----

def test_validate_stage_config_accepts_builtin_partial_and_unknown():
    """内置默认配置 / 部分键 / 未知键都算合法：**缺失 = 回落上一级**、**未知 = 前向兼容**。"""
    import agent_stage_service

    assert agent_stage_service.validate_stage_config(agent_stage_service.DEFAULT_STAGE_CONFIG) == (True, [])
    assert agent_stage_service.validate_stage_config({}) == (True, [])
    assert agent_stage_service.validate_stage_config({"min_samples": 3}) == (True, [])
    assert agent_stage_service.validate_stage_config({"future_key": "x", "min_samples": 3}) == (True, [])


@pytest.mark.parametrize("cfg", [
    {"schema_version": 1},
    {"window_days": 1}, {"window_days": 3650},
    {"max_samples": 1}, {"max_samples": 500},
    {"min_samples": 1, "max_samples": 1},                      # 边界相等合法
    {"truncate_chars": 200}, {"truncate_chars": 4000},
    {"demote_streak": 1}, {"demote_streak": 10},
    {"max_violations": 0}, {"max_violations": 50},
    {"max_permission_denials": 0}, {"max_permission_denials": 100},
    {"recommend_cooldown_hours": 0}, {"metrics_ttl_hours": 0},  # 设计未给上界 → 只拦负数
    {"min_template_match": 0.0}, {"min_template_match": 1.0},  # 比率闭区间两端
    {"min_modification_consistency": 0}, {"min_modification_consistency": 1},
    {"demote_consistency_floor": 0.5},
    {"default_stage": "observation"}, {"default_stage": "learning"},
    {"matrix_enforced": True}, {"matrix_enforced": False},
    {"template_match_weights": {"section_hit": 0, "section_order": 1}},
])
def test_validate_stage_config_accepts_boundary_values(cfg):
    """闭区间端点 / 布尔两态 / 权重取到端点，都必须放行（边界不能靠「大概」判）。"""
    import agent_stage_service

    ok, errors = agent_stage_service.validate_stage_config(cfg)
    assert ok is True and errors == [], "应放行却报了错：%r → %r" % (cfg, errors)


@pytest.mark.parametrize("cfg, path", [
    # 契约版本
    ({"schema_version": 2}, "schema_version"),
    ({"schema_version": "1"}, "schema_version"),
    ({"schema_version": True}, "schema_version"),
    # 整数键：越界
    ({"window_days": 0}, "window_days"), ({"window_days": 3651}, "window_days"),
    ({"max_samples": 0}, "max_samples"), ({"max_samples": 501}, "max_samples"),
    ({"min_samples": 0}, "min_samples"), ({"min_samples": 501}, "min_samples"),
    ({"truncate_chars": 199}, "truncate_chars"), ({"truncate_chars": 4001}, "truncate_chars"),
    ({"demote_streak": 0}, "demote_streak"), ({"demote_streak": 11}, "demote_streak"),
    ({"max_violations": -1}, "max_violations"), ({"max_violations": 51}, "max_violations"),
    ({"max_permission_denials": -1}, "max_permission_denials"),
    ({"max_permission_denials": 101}, "max_permission_denials"),
    ({"recommend_cooldown_hours": -1}, "recommend_cooldown_hours"),
    ({"metrics_ttl_hours": -1}, "metrics_ttl_hours"),
    # 整数键：类型（bool 必须被拒 —— `True` 是 int 子类，静默当 1 用就是静默清洗）
    ({"window_days": "90"}, "window_days"),
    ({"max_samples": True}, "max_samples"),
    ({"demote_streak": 1.5}, "demote_streak"),
    # 跨键关系
    ({"min_samples": 9, "max_samples": 5}, "min_samples"),
    # 比率键
    ({"min_template_match": 1.0001}, "min_template_match"),
    ({"min_template_match": -0.01}, "min_template_match"),
    ({"min_modification_consistency": "0.9"}, "min_modification_consistency"),
    ({"demote_consistency_floor": 2}, "demote_consistency_floor"),
    # 布尔键 / 权重
    ({"matrix_enforced": "true"}, "matrix_enforced"),
    ({"matrix_enforced": 1}, "matrix_enforced"),
    ({"template_match_weights": "x"}, "template_match_weights"),
    ({"template_match_weights": {}}, "template_match_weights"),
    ({"template_match_weights": {"section_hit": 0, "section_order": 0}}, "template_match_weights"),
    ({"template_match_weights": {"section_hit": -0.1}}, "template_match_weights.section_hit"),
    ({"template_match_weights": {"section_hit": True, "section_order": 1}},
     "template_match_weights.section_hit"),
])
def test_validate_stage_config_rejects_out_of_range_by_path(cfg, path):
    """越界 / 类型错的每一项都必须在 `errors[].path` 上**指名道姓**（400 的 errors 直接给老师看）。"""
    import agent_stage_service

    ok, errors = agent_stage_service.validate_stage_config(cfg)
    assert ok is False
    assert path in [item["path"] for item in errors], "%r 应报在 %s 上：%r" % (cfg, path, errors)


@pytest.mark.parametrize("stage", ["apprentice", "assistant", "authorized", "observation_", "*"])
def test_validate_stage_config_refuses_privileged_default_stage(stage):
    """**fail-closed 的关键一条**：`default_stage` 只能是 observation / learning。

    若放行 `apprentice` 及以上，「读不到状态行」就等于「自动提权」—— 而 `describe_stage` 的兜底
    路径正是「读不到时返回 `default_stage`」（§1.5 结尾）。这条用例是那道闸的守门人。
    """
    import agent_stage_service

    ok, errors = agent_stage_service.validate_stage_config({"default_stage": stage})
    assert ok is False
    assert "default_stage" in [item["path"] for item in errors]


def test_validate_stage_config_reports_all_errors_and_never_cleans():
    """多处非法 → **一次全报**（不短路）；且**不清洗**：入参一个字节都不许被改。"""
    import agent_stage_service

    cfg = {"min_samples": 0, "matrix_enforced": "true", "default_stage": "apprentice",
           "unknown_future": {"keep": "me"}}
    snapshot = json.loads(json.dumps(cfg))

    ok, errors = agent_stage_service.validate_stage_config(cfg)
    assert ok is False
    assert sorted(item["path"] for item in errors) == ["default_stage", "matrix_enforced", "min_samples"]
    assert cfg == snapshot, "校验层回写了入参（静默清洗）"
    assert set(errors[0]) == {"path", "msg"}, "错误条目形状必须与统一错误体一致（errors: [{path,msg}]）"
    assert all(isinstance(item["msg"], str) and item["msg"] for item in errors), "msg 必须是人话"


@pytest.mark.parametrize("cfg", [None, [], "x", 3, True])
def test_validate_stage_config_rejects_non_dict(cfg):
    """根不是 JSON 对象 → 一条错误、path 为空串（对应「请求体本身就不是配置对象」）。"""
    import agent_stage_service

    ok, errors = agent_stage_service.validate_stage_config(cfg)
    assert ok is False
    assert len(errors) == 1 and errors[0]["path"] == ""


# ---- 阶段真值读取 ⑦：四条路径（§1.5）----

def test_describe_stage_row_present_is_truth(db):
    """路径①：状态行存在且 stage 合法 → **原样采用**（含 stage_since / stage_source / pending_*）。"""
    import agent_stage_service

    _put_raw_state_row(TEACHER, "apprentice", stage_since="2026-09-01T10:00:00",
                       stage_source="teacher_confirm", pending_stage="assistant", pending_task_id=7)

    view = agent_stage_service.describe_stage(TEACHER)
    assert view == {
        "teacher_name": TEACHER,
        "stage": "apprentice",
        "stage_label": "見習期",
        "stage_since": "2026-09-01T10:00:00",
        "stage_source": "teacher_confirm",
        "pending_stage": "assistant",
        "pending_task_id": 7,
        "degraded": False,
    }
    assert view["stage_label"] == agent_stage_service.STAGE_LABELS["apprentice"], "徽章文案走唯一真相源"


def test_describe_stage_without_row_uses_default_stage_without_writing(db):
    """路径③：无行 → 取**配置链**的 `default_stage`、`degraded=False`、**不写库**。

    「新老师还没有状态行」是正常态：既不许报错，也不许为此写一行假状态（那会把「未初始化」变成
    「已初始化成默认值」，将来想区分就再也分不清了）。
    """
    import agent_stage_service

    before = _raw_scalar("SELECT COUNT(*) FROM agent_stage_state")
    _put_raw_config_row("", json.dumps({"default_stage": "observation"}))

    view = agent_stage_service.describe_stage(TEACHER)
    assert view["stage"] == "observation", "兜底值必须来自配置链（不是硬编码 learning）"
    assert view["stage_source"] == "default"
    assert view["stage_since"] == "" and view["pending_stage"] == "" and view["pending_task_id"] == 0
    assert view["degraded"] is False, "无行是正常态，不是降级"
    assert _raw_scalar("SELECT COUNT(*) FROM agent_stage_state") == before, "读数把状态行写出来了"

    assert agent_stage_service.current_stage(TEACHER) == "observation"


def test_current_stage_is_scalar_matching_describe(db):
    """`current_stage` 恒为 `STAGES` 内的字符串，且与 `describe_stage` 同源（只有一份读库实现）。"""
    import agent_stage_service

    assert isinstance(agent_stage_service.current_stage(TEACHER), str)
    assert agent_stage_service.current_stage(TEACHER) in agent_stage_service.STAGES

    _put_raw_state_row(TEACHER, "authorized")
    assert agent_stage_service.current_stage(TEACHER) == "authorized"
    assert agent_stage_service.current_stage(TEACHER) == agent_stage_service.describe_stage(TEACHER)["stage"]


# ---- 阶段真值读取 ⑧：读数纪律（零写入 / 只发 SELECT / 不读 flag）----

def test_stage_read_path_only_selects_and_writes_nothing(db, sql_log):
    """读数全链路 **只发 SELECT**，且**不改数据、不写审计**。

    走的是「非法 stage 行」这条降级路径：读完之后脏行必须**原样**留在库里；`agent_stage_log` 也
    增量为零（§1.5 第 1 条的 evaluation 事件写入属 3.4 的 `evaluate()`；§3.8 要求 GET 无副作用）。
    """
    import agent_stage_service

    _put_raw_config_row("", json.dumps({"window_days": 30}))
    _put_raw_state_row(TEACHER, "master")
    state_before = _raw_scalar("SELECT COUNT(*) FROM agent_stage_state")
    log_before = _raw_scalar("SELECT COUNT(*) FROM agent_stage_log")

    marker = len(_all_calls(sql_log))
    agent_stage_service.load_stage_config(TEACHER)
    agent_stage_service.describe_stage(TEACHER)
    agent_stage_service.current_stage(TEACHER)

    statements = [sql for sql, _ in _all_calls(sql_log)[marker:]]
    assert statements, "必须真的读了库"
    assert all(sql.lstrip().upper().startswith("SELECT") for sql in statements), statements
    assert _raw_scalar("SELECT COUNT(*) FROM agent_stage_state") == state_before
    assert _raw_scalar("SELECT COUNT(*) FROM agent_stage_log") == log_before, "读数写了审计日志"


@pytest.mark.parametrize("flag", [None, "on", "off"])
def test_stage_read_path_ignores_flag(db, monkeypatch, flag):
    """读数**不读 flag**：flag 三态下结果逐字节一致（门卫属 3.3 的 `require_capability` / step 4 接口层）。"""
    import agent_stage_service

    if flag is None:
        monkeypatch.delenv("AGENT_STAGE_ENABLED", raising=False)
    else:
        monkeypatch.setenv("AGENT_STAGE_ENABLED", flag)

    _put_raw_state_row(TEACHER, "apprentice", stage_source="teacher_confirm")

    assert agent_stage_service.describe_stage(TEACHER) == {
        "teacher_name": TEACHER,
        "stage": "apprentice",
        "stage_label": "見習期",
        "stage_since": "",
        "stage_source": "teacher_confirm",
        "pending_stage": "",
        "pending_task_id": 0,
        "degraded": False,
    }
    assert agent_stage_service.current_stage(TEACHER) == "apprentice"
    assert agent_stage_service.load_stage_config(TEACHER) == agent_stage_service.DEFAULT_STAGE_CONFIG


def test_describe_stage_illegal_row_value_degrades_to_default_stage(db, capsys):
    """路径②：行在但 `stage` 白名单外（人手 SQL 写坏 / 高版本数据）→ 回落 `default_stage` + 降级标记。

    同时钉住两件事：① `stage_since` **一并不采用**（返回的阶段已不是那行的阶段，带上它的时间会误导
    前端）；② **不改写那行脏数据**（读数零写入 —— 脏数据怎么处理属 3.4 的评估流程 + 审计）。
    """
    import agent_stage_service

    _put_raw_config_row("", json.dumps({"default_stage": "observation"}))
    _put_raw_state_row(TEACHER, "master", stage_since="2026-09-01T10:00:00",
                       stage_source="teacher_confirm")

    view = agent_stage_service.describe_stage(TEACHER)
    assert view["stage"] == "observation"
    assert view["stage_source"] == "default"
    assert view["stage_since"] == "", "非法行的 stage_since 不得被继承"
    assert view["degraded"] is True
    assert "master" in capsys.readouterr().out, "非法值必须留下告警（含原值，便于定位）"

    assert _raw_scalar("SELECT stage FROM agent_stage_state WHERE teacher_name = ?", (TEACHER,)) == "master", \
        "读数改写了脏数据（零写入纪律）"


def test_describe_stage_default_stage_never_escalates(db, capsys):
    """**fail-closed 端到端**：全局行 / 老师行里塞高阶段兜底值 → 校验拒绝 → 整份回落内置 learning。

    「读不到状态行」是兜底路径，若 `default_stage` 能取到 `apprentice` 及以上，它就成了「自动提权」。
    """
    import agent_stage_service

    _put_raw_config_row("", json.dumps({"default_stage": "apprentice"}))
    assert agent_stage_service.load_stage_config(TEACHER)["default_stage"] == "learning"
    assert agent_stage_service.describe_stage(TEACHER)["stage"] == "learning"

    _put_raw_config_row(TEACHER, json.dumps({"default_stage": "authorized"}))
    assert agent_stage_service.describe_stage(TEACHER)["stage"] == "learning"
    assert "default_stage" in capsys.readouterr().out


def test_describe_stage_store_missing_degrades_and_never_raises(db, monkeypatch, tmp_path, capsys):
    """路径④：0003 未跑（状态表不在）→ `default_stage` + `degraded=True` + 告警、**绝不抛**（§1.5 第 3 条）。"""
    import agent_stage_service

    path = _copy_tested_db(monkeypatch, tmp_path, "no_state_table.db")
    _drop_table(path, "agent_stage_state")

    view = agent_stage_service.describe_stage(TEACHER)      # 不抛异常 = 本用例的核心断言
    assert view["stage"] == "learning"
    assert view["stage_source"] == "default"
    assert view["degraded"] is True
    assert view["stage_label"] == agent_stage_service.STAGE_LABELS["learning"]
    assert "失敗" in capsys.readouterr().out


def test_describe_stage_tolerates_corrupt_pending_task_id(db):
    """库列无 CHECK（§1.2）：`pending_task_id` 被人手 SQL 写成字符串时，读数降级成 0 而不是炸 500。"""
    import agent_stage_service

    _put_raw_state_row(TEACHER, "learning", pending_task_id="oops")

    view = agent_stage_service.describe_stage(TEACHER)      # 不抛异常 = 核心断言
    assert view["stage"] == "learning" and view["pending_task_id"] == 0


# ============ ⑮ 【施工步骤 3.3】唯一能力闸门：require_capability ============
#
# CTO 2026-09-28 放行 step 3.3 的六条约束，本组逐条落地（本组即约束 6 说的「⑮ 组」）：
#   ① 矩阵是**显式数据结构**：25 格**逐格**行为断言 + 数据表 ↔ 设计文档 §2.3 表格逐格交叉核对
#      + 源码级守护「闸门体内没有能力字面量分支」；
#   ② **白名单、默认拒绝**：未知 / 拼写错 / 非字符串 / 三不铁律的能力键一律拒（阶段给到最高也一样）；
#   ③ **拒绝同点写审计**：`permission_denied` 事件（当前阶段 / 能力键 / 时间）+ 越权告警；拒绝路径
#      **只**多这一条审计写入（业务表零改动 = §6.2-15 的服务层等价物）；
#   ④ **三不铁律独立于开关**：`matrix_enforced=False` 下矩阵解锁，但枚举外键仍全拒；flag off 同理；
#   ⑤ **返回 bool、拒绝不抛**：三张新表全被删也不抛；审计写失败只告警、判定结果不变；
#   ⑥ 五阶段 × 关键 capability 的**组合矩阵逐格验证**（25 格 + 五条「五键组合」）。
# 本组**不改** ⑭ 组一行：只复用它的造数 / 断言助手（`_put_raw_state_row` / `_put_raw_config_row` /
# `_raw_scalar` / `_copy_tested_db` / `_drop_table` / `_all_calls`），造数一律绕过 `get_connection`
# 直连库文件（⑭ 组的既有口径：避免与被测代码的语句级断言混在一起）。
# 与 ⑬ ⑭ 组同一纪律：**不**断言 3.4 符号（`evaluate` / 三个钩子 …）的缺席。


@pytest.fixture
def gate(monkeypatch):
    """⑮ 组公共前置：打开总闸 `AGENT_STAGE_ENABLED=on`（矩阵只在 flag on 时才会被问到）。"""
    monkeypatch.setenv("AGENT_STAGE_ENABLED", "on")


# §2.3 表格的**逐格字面量转录**（刻意不从 `CAPABILITY_MATRIX` 取值：数据表漂移时必须红）
_GATE_STAGES = ("observation", "learning", "apprentice", "assistant", "authorized")
_GATE_CAPS = ("record_observation", "generate_draft", "predict_pattern",
              "suggest_prescription", "generate_predraft")
_GATE_GRID = {
    "observation": (True, False, False, False, False),
    "learning": (True, True, False, False, False),
    "apprentice": (True, True, True, False, False),
    "assistant": (True, True, True, True, False),
    "authorized": (True, True, True, True, True),
}

# §2.1 三不铁律（AI 永不诊断 / 永不开方 / 永不签字）的**能力键形态**：它们是「不存在的能力」，
# 故任何阶段的矩阵里都没有它们的格子 —— 含 §4.5-① 禁止 import 清单里的符号名。
_BANNED_CAPABILITIES = ("diagnose", "create_prescription", "sign_draft", "update_draft_content",
                        "batch_deduct_herbs", "open_prescription")


def _gate_cells():
    """五阶段 × 五能力 = 25 格（stage, capability, expected）三元组。"""
    return [(stage, cap, expected)
            for stage in _GATE_STAGES
            for cap, expected in zip(_GATE_CAPS, _GATE_GRID[stage])]


# ---- 闸门 ①：矩阵是数据（数据表自检 + 设计文档交叉核对）----

def test_capability_matrix_is_design_table_transcribed():
    """交付自检：`CAPABILITY_MATRIX` 就是 §2.3 表格的逐格转录（含五键顺序 = `CAPABILITIES`）。"""
    import agent_stage_service

    assert agent_stage_service.CAPABILITIES == _GATE_CAPS
    assert agent_stage_service.STAGES == _GATE_STAGES
    assert agent_stage_service.CAPABILITY_MATRIX == {
        stage: dict(zip(_GATE_CAPS, _GATE_GRID[stage])) for stage in _GATE_STAGES
    }
    assert all(isinstance(cell, bool)
               for row in agent_stage_service.CAPABILITY_MATRIX.values() for cell in row.values()), \
        "矩阵格子必须是真 bool（`1` / `0` 会让「查表」与「真值判断」分叉）"


def test_capability_matrix_matches_design_document_table():
    """矩阵 ↔ 设计文档 §2.3 表格**逐格**交叉核对（防服务层手抄漂移：表格改了，用例立刻红）。"""
    import agent_stage_service

    doc = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(database.__file__))),
                       "docs", "epic2-agent-stage-design-v1.md")
    with open(doc, encoding="utf-8") as fh:
        lines = fh.read().splitlines()

    parsed = {}
    for line in lines:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 7 or not cells[0].startswith("`"):
            continue            # §2.3 表：能力 + 五阶段 + 说明 = 7 列
        name = cells[0].strip("`").split("`")[0]
        if name not in _GATE_CAPS:
            continue
        row = []
        for cell in cells[1:6]:
            assert ("✅" in cell) != ("❌" in cell), "§2.3 表格格子无法判读：%r" % cell
            row.append("✅" in cell)
        parsed[name] = tuple(row)

    assert set(parsed) == set(_GATE_CAPS), "§2.3 表格行与能力枚举分叉：%s" % sorted(parsed)
    expected = {cap: tuple(_GATE_GRID[stage][index] for stage in _GATE_STAGES)
                for index, cap in enumerate(_GATE_CAPS)}
    assert parsed == expected, "服务层矩阵与设计文档 §2.3 表格不一致"


# ---- 闸门 ②：25 格逐格判定 + 五阶段「五键组合」（§2.3 / §6.2 9–13 的服务层等价物）----

@pytest.mark.parametrize("stage,capability,expected", _gate_cells(),
                         ids=["%s-%s" % (stage, cap) for stage, cap, _ in _gate_cells()])
def test_require_capability_matches_design_matrix_cell(db, gate, stage, capability, expected):
    """**逐格**（约束 6）：该阶段 × 该能力的闸门结果必须 = §2.3 表格那一格。"""
    import agent_stage_service

    _put_raw_state_row(TEACHER, stage)

    assert agent_stage_service.require_capability(TEACHER, capability) is expected


@pytest.mark.parametrize("stage", _GATE_STAGES)
def test_require_capability_stage_capability_combination(db, gate, stage):
    """五条「五键能力组合」：每个阶段的能力组合与 §2.3 表格该行**完全一致**（顺序也钉住）。"""
    import agent_stage_service

    _put_raw_state_row(TEACHER, stage)

    combo = tuple(agent_stage_service.require_capability(TEACHER, cap) for cap in _GATE_CAPS)

    assert combo == _GATE_GRID[stage]


# ---- 闸门 ③：白名单、默认拒绝（§2.1 三不铁律的代码级形态 = 「不存在的能力」）----

@pytest.mark.parametrize("capability", ("", "diagnose", "create_prescription", "sign_draft",
                                        "update_draft_content", "batch_deduct_herbs",
                                        "open_prescription", "Generate_Draft",
                                        "record_observations", "predict_pattern "))
def test_require_capability_denies_unknown_capability(db, gate, capability):
    """约束 2：枚举外的键（三不铁律 / 拼写错 / 大小写错 / 多一个空格 / 空串）一律拒 ——
    即便阶段已经给到最高（`authorized`）：白名单外没有格子，任何阶段都不放行。"""
    import agent_stage_service

    _put_raw_state_row(TEACHER, "authorized")

    assert agent_stage_service.require_capability(TEACHER, capability) is False

    rows = db.get_agent_stage_logs(TEACHER)
    assert len(rows) == 1 and rows[0]["event_type"] == "permission_denied", \
        "未知能力被拒也必须留痕（含三不铁律的越权尝试）"


@pytest.mark.parametrize("capability", (None, 123, 3.14, True, ["predict_pattern"],
                                        {"predict_pattern": True}, ("predict_pattern",)))
def test_require_capability_denies_non_string_capability(db, gate, capability):
    """非字符串入参（接口层传错类型 / JSON 里塞了别的类型）走同一条白名单拒绝路径：不抛、不崩。"""
    import agent_stage_service

    _put_raw_state_row(TEACHER, "authorized")

    assert agent_stage_service.require_capability(TEACHER, capability) is False
    assert len(db.get_agent_stage_logs(TEACHER)) == 1
    assert db.get_agent_stage_logs(TEACHER)[0]["capability"] == repr(capability), \
        "非字符串入参也要在审计里留下可读的值（`repr`）"


@pytest.mark.parametrize("stage", _GATE_STAGES)
def test_require_capability_matrix_disabled_still_denies_banned_capabilities(db, gate, monkeypatch, stage):
    """约束 4（本步最关键的一条）：`matrix_enforced=False` 放宽矩阵，但三不铁律**仍全拒** ——
    放宽开关只能放宽 §2.3 表里**已有的格子**，造不出不存在的格子；五个阶段都不例外。"""
    import agent_stage_service

    monkeypatch.setenv("AGENT_STAGE_MATRIX_ENFORCED", "off")
    _put_raw_state_row(TEACHER, stage)

    assert agent_stage_service.load_stage_config(TEACHER)["matrix_enforced"] is False

    for capability in _BANNED_CAPABILITIES:
        assert agent_stage_service.require_capability(TEACHER, capability) is False, capability
    for capability in ("", None, 123, "DIAGNOSE"):
        assert agent_stage_service.require_capability(TEACHER, capability) is False, capability


# ---- 闸门 ④：`matrix_enforced=False` 的放宽范围（§2.5 逐项枚举）+ 开关来自配置链 ----

def test_require_capability_matrix_disabled_relaxes_only_l2(db, gate, monkeypatch):
    """§2.5 的作用域：只放宽**逐项枚举的三个新能力**（L2 阶段门控）；`generate_draft` 在
    `observation` 期**仍是 False** —— 那一格是 §5.3 的本地骨架路径（观察期智能体不参与），
    不是权限闸门，放宽矩阵不该把本地确定性链路也一并放开。"""
    import agent_stage_service

    monkeypatch.setenv("AGENT_STAGE_MATRIX_ENFORCED", "off")
    assert agent_stage_service.load_stage_config(TEACHER)["matrix_enforced"] is False

    _put_raw_state_row(TEACHER, "observation")

    for capability in ("predict_pattern", "suggest_prescription", "generate_predraft"):
        assert agent_stage_service.require_capability(TEACHER, capability) is True, capability
    assert agent_stage_service.require_capability(TEACHER, "generate_draft") is False
    assert agent_stage_service.require_capability(TEACHER, "record_observation") is True


def test_require_capability_matrix_enabled_default_keeps_matrix(db, gate, monkeypatch):
    """默认（未设 `AGENT_STAGE_MATRIX_ENFORCED`）= 矩阵继续强制：learning 期三个新能力照旧全拒。"""
    import agent_stage_service

    monkeypatch.delenv("AGENT_STAGE_MATRIX_ENFORCED", raising=False)
    _put_raw_state_row(TEACHER, "learning")

    assert agent_stage_service.load_stage_config(TEACHER)["matrix_enforced"] is True
    assert agent_stage_service.require_capability(TEACHER, "predict_pattern") is False


def test_require_capability_reads_matrix_enforced_from_config_chain(db, gate):
    """放宽开关取自**四层配置链**（不只 env）：老师专属行只放宽自己那一份（别人不受影响），
    配置读坏 → 整份回落内置 `True` → 继续强制（绝不因「读不到配置」而放大权限）。"""
    import agent_stage_service

    _put_raw_config_row(TEACHER, json.dumps({"matrix_enforced": False}))
    _put_raw_state_row(TEACHER, "learning")
    _put_raw_state_row(OTHER_TEACHER, "learning")

    assert agent_stage_service.require_capability(TEACHER, "suggest_prescription") is True
    assert agent_stage_service.require_capability(OTHER_TEACHER, "suggest_prescription") is False

    _put_raw_config_row(OTHER_TEACHER, "{ 这不是 JSON")
    assert agent_stage_service.require_capability(OTHER_TEACHER, "suggest_prescription") is False, \
        "配置读坏必须回落内置默认（matrix_enforced=True）而不能放宽"


# ---- 闸门 ⑤：拒绝留痕（约束 3：同点写审计 + 告警）与「业务表零改动」 ----

def test_require_capability_denial_writes_permission_denied_event(db, gate, capsys):
    """约束 3：拒绝**同点**写一条 `permission_denied` 审计（§1.3 契约名）—— stage / capability /
    时间三要素齐全，并配一条越权告警（§2.4）。字段口径照 §1.3：`to_stage=''`、`task_id=0`、`metrics_json={}`。"""
    import agent_stage_service

    _put_raw_state_row(TEACHER, "learning")

    assert agent_stage_service.require_capability(TEACHER, "predict_pattern") is False

    assert "越權被拒" in capsys.readouterr().out, "拒绝必须配一条可解释告警"

    rows = db.get_agent_stage_logs(TEACHER)
    assert [row["event_type"] for row in rows] == ["permission_denied"]
    row = rows[0]
    assert row["teacher_name"] == TEACHER
    assert row["capability"] == "predict_pattern", "审计必须记下**被拒的能力键**"
    assert row["from_stage"] == "learning", "审计必须记下**当时的阶段**"
    assert row["to_stage"] == "" and row["task_id"] == 0 and row["metrics_json"] == "{}"
    assert row["created_at"], "审计必须带时间戳（约束 3 的时间要素）"
    assert "見習期" in row["detail"] and "學習期" in row["detail"], \
        "审计文案要说清「差多少」（可解释拒绝，§2.4）"


def test_require_capability_denial_touches_only_the_audit_table(db, gate, sql_log):
    """§6.2-15 的服务层等价物：拒绝路径**只多一条 `INSERT INTO agent_stage_log`** ——
    业务表（drafts / patient_records / prescriptions）与状态表 / 配置表**零改动**，其余全是 SELECT。"""
    import agent_stage_service

    _put_raw_state_row(TEACHER, "learning")
    counted = ("drafts", "patient_records", "prescriptions", "agent_stage_state",
               "agent_stage_config", "agent_stage_log")
    before = {table: _raw_scalar("SELECT COUNT(*) FROM %s" % table) for table in counted}

    marker = len(_all_calls(sql_log))
    assert agent_stage_service.require_capability(TEACHER, "generate_predraft") is False

    writes = [sql for sql, _ in _all_calls(sql_log)[marker:]
              if not sql.lstrip().upper().startswith("SELECT")]
    assert len(writes) == 1 and writes[0].startswith("INSERT INTO agent_stage_log"), writes

    for table in counted[:-1]:
        assert _raw_scalar("SELECT COUNT(*) FROM %s" % table) == before[table], table
    assert _raw_scalar("SELECT COUNT(*) FROM agent_stage_log") == before["agent_stage_log"] + 1


def test_require_capability_relaxed_allow_is_audited_as_permission_relaxed(db, gate, monkeypatch, capsys):
    """§2.5 ③「放行也留痕」：放宽下的放行写**反向事件** `permission_relaxed`（不许静默放宽）；
    矩阵本来就放行的格子不写（那里没有「放宽」这回事）。"""
    import agent_stage_service

    monkeypatch.setenv("AGENT_STAGE_MATRIX_ENFORCED", "off")
    _put_raw_state_row(TEACHER, "learning")

    assert agent_stage_service.require_capability(TEACHER, "suggest_prescription") is True
    assert "放寬" in capsys.readouterr().out

    rows = db.get_agent_stage_logs(TEACHER)
    assert [row["event_type"] for row in rows] == ["permission_relaxed"]
    assert rows[0]["capability"] == "suggest_prescription"
    assert rows[0]["from_stage"] == "learning" and rows[0]["created_at"]

    assert agent_stage_service.require_capability(TEACHER, "record_observation") is True
    assert len(db.get_agent_stage_logs(TEACHER)) == 1, "矩阵本就放行的格子不该写「放宽」事件"


# ---- 闸门 ⑥：总闸 off 的既有行为（§2.3 例外 + §5.1 红线①）----

def test_require_capability_flag_off_allows_legacy_generate_draft_only(db, monkeypatch, sql_log):
    """§2.3 的 flag off 例外 + §5.1 红线①：off 时**只有** `generate_draft` 恒放行（既有行为 1:1），
    其余（基础能力 / 三个新能力 / 三不 / 未知键 / 非字符串）全拒，且**零 DB 访问、零审计** ——
    off 的语义是「功能没开」，不许碰任何新表。"""
    import agent_stage_service

    monkeypatch.delenv("AGENT_STAGE_ENABLED", raising=False)
    assert agent_stage_service.agent_stage_enabled() is False

    marker = len(_all_calls(sql_log))
    assert agent_stage_service.require_capability(TEACHER, "generate_draft") is True
    for capability in ("record_observation", "predict_pattern", "suggest_prescription",
                       "generate_predraft") + _BANNED_CAPABILITIES + ("", None, 123):
        assert agent_stage_service.require_capability(TEACHER, capability) is False, capability

    assert _all_calls(sql_log)[marker:] == [], "flag off 不得触库（连 SELECT 都不发）"
    assert _raw_scalar("SELECT COUNT(*) FROM agent_stage_log") == 0
    _put_raw_state_row(TEACHER, "authorized")
    assert agent_stage_service.require_capability(TEACHER, "generate_draft") is True, \
        "既有行为与阶段无关（off 时本路径不读状态表）"


def test_require_capability_gate_really_follows_the_flag(db, monkeypatch):
    """闸门真的看总闸（不是摆设）：同一个 `authorized` 阶段，flag on → 放行，flag off → 拒绝。"""
    import agent_stage_service

    _put_raw_state_row(TEACHER, "authorized")

    monkeypatch.setenv("AGENT_STAGE_ENABLED", "on")
    assert agent_stage_service.require_capability(TEACHER, "predict_pattern") is True

    monkeypatch.delenv("AGENT_STAGE_ENABLED", raising=False)
    assert agent_stage_service.require_capability(TEACHER, "predict_pattern") is False


@pytest.mark.parametrize("flag,expected", [("on", True), ("1", True), ("true", True), ("TRUE", True),
                                           ("yes", True), (" yes ", True),
                                           ("off", False), ("0", False), ("no", False),
                                           ("maybe", False), ("", False)])
def test_require_capability_flag_values_match_agent_stage_enabled(db, monkeypatch, flag, expected):
    """总闸取值口径与 `agent_stage_enabled()`（⑨ 组钉过的真值集）**逐个**一致 ——
    闸门不许自造第二套 flag 判断；同一个 `authorized` 阶段下四个新能力随 flag 起落。"""
    import agent_stage_service

    _put_raw_state_row(TEACHER, "authorized")
    monkeypatch.setenv("AGENT_STAGE_ENABLED", flag)

    assert agent_stage_service.agent_stage_enabled() is expected
    for capability in ("predict_pattern", "suggest_prescription", "generate_predraft"):
        assert agent_stage_service.require_capability(TEACHER, capability) is expected, capability


# ---- 闸门 ⑦：fail-closed（库坏了不抛、脏行 / 无行不悄悄提权）----

def test_require_capability_store_missing_never_raises_and_fails_closed(db, gate, monkeypatch,
                                                                       tmp_path, capsys):
    """约束 5 + §1.5 + §2.4：三张新表全被删（0003 未跑 / 库坏了）→ **不抛异常**，判定 fail-closed
    到配置链的 `default_stage`；审计写不进去**只告警、不改判定**（「拒绝先于日志」）。"""
    import agent_stage_service

    path = _copy_tested_db(monkeypatch, tmp_path, "gate_without_tables.db")
    for table in ("agent_stage_state", "agent_stage_config", "agent_stage_log"):
        _drop_table(path, table)

    assert agent_stage_service.require_capability(TEACHER, "predict_pattern") is False, \
        "读不到状态必须 fail-closed 到兜底阶段，而不是放行"

    out = capsys.readouterr().out
    assert "失敗" in out, "阶段真值读取降级必须留告警"
    assert "審計" in out, "审计写入失败必须留告警（不许静默吞掉、更不许抛出去）"

    assert agent_stage_service.require_capability(TEACHER, "record_observation") is True, \
        "兜底阶段（内置 default_stage = learning）下基础能力仍可用：fail-closed 不是阻断既有链路"


def test_require_capability_judges_on_fallback_stage_when_row_absent_or_dirty(db, gate, capsys):
    """fail-closed 端到端：**无行**（③，正常态）与**脏行**（②，人手 SQL 写坏）都按配置链的
    `default_stage` 判能力，且脏行不会悄悄提权；审计里记的也必须是**判定所用的兜底阶段**。"""
    import agent_stage_service

    _put_raw_config_row("", json.dumps({"default_stage": "observation"}))

    assert agent_stage_service.require_capability(OTHER_TEACHER, "record_observation") is True
    assert agent_stage_service.require_capability(OTHER_TEACHER, "predict_pattern") is False

    _put_raw_state_row(TEACHER, "master")           # 白名单外阶段（人手 SQL 写坏）
    assert agent_stage_service.require_capability(TEACHER, "predict_pattern") is False
    assert "不在五階段枚舉內" in capsys.readouterr().out, "脏行必须留痕（不静默兜底）"

    rows = db.get_agent_stage_logs(TEACHER)
    assert len(rows) == 1
    assert rows[0]["event_type"] == "permission_denied"
    assert rows[0]["from_stage"] == "observation"


# ---- 闸门 ⑧：约束 1 的源码级守护（矩阵 = 数据，判定 = 查表）----

def test_require_capability_body_has_no_capability_branches():
    """能力名只许出现在**数据表 / 常量**里：闸门函数体内不得出现 `== "能力名"` 这类散落分支
    （否则「矩阵是显式数据结构」就退化成 if-else 链）；flag off 例外也只许来自那一个常量。"""
    import inspect

    import agent_stage_service

    source = inspect.getsource(agent_stage_service.require_capability)
    offenders = [cap for cap in agent_stage_service.CAPABILITIES
                 if '== "%s"' % cap in source or '!= "%s"' % cap in source]
    assert offenders == [], "能力名散落在闸门体内：%s" % offenders
    assert "CAPABILITY_MATRIX" in source, "闸门必须查显式矩阵表（约束 1）"

    assert agent_stage_service.LEGACY_ALLOWED_WHEN_DISABLED == {"generate_draft"}, \
        "§2.3 的 flag off 例外只许来自这一个常量（「该特例只写一处，不得散落」）"
    assert agent_stage_service._MATRIX_RELAXED_CAPABILITIES == (
        "predict_pattern", "suggest_prescription", "generate_predraft"), \
        "§2.5 的放宽范围必须逐项枚举（且不含 generate_draft：那是 §5.3 的本地骨架路径）"


# ============ ⑯ 【施工步骤 3.4-a】指标层：① 模板匹配度 + ② 病历修改一致率 ============
#
# CTO 2026-09-29 放行 step 3.4-a 的边界，本组逐条落地（本组即「⑯ 组」）：
#   ① 「3.4 含 ①②」→ §6.3 里属指标层的用例（第 20–26 条）在本组落地；**第 27 条**
#      （③ `inquiry_preference_consistency` 恒为 `null` 的占位键）测的是 `evaluate` 的返回体
#      → 随 3.4-b 落地，本组不含（也不断言其缺席）；
#   ② **空集语义**（CTO 硬约束 2）：`value is None`（**不是 0**）+ 对应 blocker，并钉住
#      「`None` 与阈值比较抛 `TypeError`」这一不变量 → 3.4-b 的判定只能显式 `is not None`；
#   ③ **指标只读**：语句级断言（只发 SELECT / PRAGMA）+ 五张表零写入；flag off 下照常算出结果
#      （闸门在 `evaluate`，不在纯计算里）；
#   ④ **不硬编码**：权重（`template_match_weights`）与截断（`truncate_chars`）改配置即改结果；
#   ⑤ 库层只读原语 `get_draft_samples`（批复 C-1）：9 键形状 / 两类来源 / 每类各自带 LIMIT /
#      窗口只作用于病历 / `visit_at` 为空的老行照收 / 缺列降级（迁移 0002 / 0003 / 0004 未跑都不抛）。
# 本组**不改** ⑭ ⑮ 组一行：只复用它们的造数 / 断言助手（`_raw_execute` / `_raw_scalar` /
# `_copy_tested_db` / `sql_log` / `_all_calls`）。造数一律走裸 sqlite3（⑭ 组既有口径）。
# 与 ⑬ ⑭ ⑮ 组同一纪律：**不**断言 3.4-b 符号（`evaluate` / 三个钩子 / `get_agent_stage_log_stats`）的缺席。

# ⑯ 组的 5 段模板（§9.2 默认骨架的前 5 段：2 段 `ai` + 3 段 `teacher`）——
# 与 `template_service._DEFAULT_RECORD_SECTIONS` 的前 5 项逐字一致，改默认骨架时必须同步这里。
_METRIC_SECTIONS = (
    ("chief_complaint", "主訴（學生原話）", "ai"),
    ("past_records", "既往病歷參考", "ai"),
    ("tongue", "舌象", "teacher"),
    ("pulse", "脈象", "teacher"),
    ("pattern", "辨證", "teacher"),
)

# 「完美样本」：5 段全中、段序全对、`teacher` 段全部留空（含 `【】` 包裹与 `- ` 列表符两种写法）
_PERFECT_DRAFT = (
    "【主訴（學生原話）】\n頭痛三日，無發熱\n"
    "【既往病歷參考】\n無\n"
    "- 舌象：（留待老師）\n"
    "- 脈象：（留待老師）\n"
    "- 辨證：（留待老師）"
)

# 「段序打乱」样本：命中率满分（5/5）但顺序一致率下降（严格 LCS = 2/5）→ 用于证明权重来自配置
_OUT_OF_ORDER_DRAFT = (
    "辨證：（留待老師）\n"
    "舌象：（留待老師）\n"
    "脈象：（留待老師）\n"
    "主訴（學生原話）：頭痛三日\n"
    "既往病歷參考：無"
)


@pytest.fixture
def metric_env(monkeypatch):
    """⑯ 组公共前置：打开 Epic 1 病歷模板通道（① 的基准来自生效 `record` 模板）。

    刻意**不**开总闸 `AGENT_STAGE_ENABLED`：两个指标函数不看 flag（纯计算、零写入），
    闸门判定在 `evaluate`（3.4-b）—— ⑯ 组用 flag off 下照常算出结果来钉住这条。
    """
    monkeypatch.setenv("TEMPLATE_API_ENABLED", "on")


def _today():
    """今天的 ISO 时间串（写 `visit_at` 用；与 `database.sign_draft()` 的写法一致）。"""
    return datetime.now().isoformat()


def _publish_record_template(sections=None, teacher=TEACHER, version=1, status="active"):
    """直接写一行模板（裸 SQL，绕开模板接口）→ 返回模板 id。

    ① 读的是**库里的生效行**（`template_service.get_active_record_template()`），
    故这里只需把 `schema_json` 造成 §9.2 的形状（`sections[].title / order / writable_by`）。
    """
    schema = {
        "version": 1,
        "sections": [
            {"key": key, "title": title, "hint": "", "order": index + 1,
             "required": False, "writable_by": writable_by}
            for index, (key, title, writable_by) in enumerate(sections or _METRIC_SECTIONS)
        ],
        "tone": {"style": "", "forbidden": []},
        "meta": {},
    }
    _raw_execute(
        "INSERT INTO templates (type, lineage_id, teacher_id, name, schema_json, version, "
        "parent_template_id, status, created_at, updated_at) "
        "VALUES ('record', '', ?, '病歷', ?, ?, NULL, ?, '', '')",
        (teacher, json.dumps(schema, ensure_ascii=False), version, status),
    )
    return _raw_scalar("SELECT MAX(id) FROM templates")


def _seed_draft(text, template_id, teacher=TEACHER, snapshot=None):
    """直接写一行**未签字草案**（§4.2 改 1 的落库形状）→ 返回 draft id。

    `snapshot=None` → 快照列写同一份 `text`（flag on 的真实形态）；传 `""` → 无快照的老草案。
    """
    _raw_execute(
        "INSERT INTO drafts (transcript_id, patient_name, teacher_name, content, signed, "
        "template_id, template_version, ai_original_content) VALUES (0, '张三', ?, ?, 0, ?, 1, ?)",
        (teacher, text, template_id, text if snapshot is None else snapshot),
    )
    return _raw_scalar("SELECT MAX(id) FROM drafts")


def _seed_record(ai_text, final_text, template_id, visit_at=None, teacher=TEACHER, with_snapshot=True):
    """直接写一行**已签字病历** → 返回 record id。

    `with_snapshot=True` → `ai_original_text` 落 AI 侧文本（② 的 `strict` 样本）；
    `False` → 快照列为空、只有 `ai_draft`（存量旧数据，② 的 `approx` 样本）。
    """
    _raw_execute(
        "INSERT INTO patient_records (patient_name, teacher_name, ai_draft, final_plan, doctor, "
        "visit_at, ai_original_text, template_id, template_version) "
        "VALUES ('张三', ?, ?, ?, ?, ?, ?, ?, 1)",
        (teacher, ai_text, final_text, teacher, _today() if visit_at is None else visit_at,
         ai_text if with_snapshot else "", template_id),
    )
    return _raw_scalar("SELECT MAX(id) FROM patient_records")


def _drop_column(path, table, column):
    """删一列（模拟「对应迁移未跑」的老库）：SQLite 3.35+ 支持 `DROP COLUMN`（本机实测 3.49.1）。"""
    conn = sqlite3.connect(path)
    conn.execute("ALTER TABLE %s DROP COLUMN %s" % (table, column))
    conn.commit()
    conn.close()


def _table_counts():
    """⑯ 组「零写入」断言用的五张表行数快照（三张新表 + 两张业务表）。"""
    return {
        table: _raw_scalar("SELECT COUNT(*) FROM %s" % table)
        for table in ("agent_stage_state", "agent_stage_config", "agent_stage_log",
                      "drafts", "patient_records")
    }


# ---- ① 模板匹配度（§3.2；§6.3 第 20–23 条）----

def test_template_match_perfect(db, metric_env):
    """§6.3-20：草案完全按模板段名与段序 → `value ≈ 1.0`（两个子项也都满分）。

    样本刻意混用两种标题写法（`【主訴（學生原話）】` 与 `- 舌象：（留待老師）`），
    钉住「行首列表符 / `【】` 包裹 / `（留待老師）` 尾巴」三种允许差异（口径 B）。
    """
    import agent_stage_service

    template_id = _publish_record_template()
    _seed_draft(_PERFECT_DRAFT, template_id)

    metric = agent_stage_service.compute_template_match(TEACHER, {})

    assert metric["samples"] == 1
    assert metric["value"] == pytest.approx(1.0)
    assert metric["hit_rate"] == pytest.approx(1.0)
    assert metric["order_rate"] == pytest.approx(1.0)
    assert metric["violations"] == 0
    assert metric["blockers"] == []
    assert (metric["skipped_no_template"], metric["skipped_stale_template"],
            metric["skipped_empty"]) == (0, 0, 0)


def test_template_match_missing_sections(db, metric_env):
    """§6.3-21：5 段模板里只出现 3 段 → 命中率与段序一致率都是 3/5，落值按权重可复算。"""
    import agent_stage_service

    template_id = _publish_record_template()
    _seed_draft("主訴（學生原話）：頭痛三日\n舌象：（留待老師）\n辨證：（留待老師）", template_id)

    metric = agent_stage_service.compute_template_match(TEACHER, {})

    assert metric["samples"] == 1
    assert metric["hit_rate"] == pytest.approx(3 / 5)
    assert metric["order_rate"] == pytest.approx(3 / 5)
    # 权重来自内置默认（`section_hit=0.6` / `section_order=0.4`）→ 0.6 * 0.6 + 0.4 * 0.6
    assert metric["value"] == pytest.approx(0.6 * 0.6 + 0.4 * 0.6)
    assert metric["violations"] == 0


def test_template_match_teacher_section_filled_is_violation(db, metric_env):
    """§6.3-22（铁律）：AI 填了 `writable_by='teacher'` 的段 → 该样本 `match = 0.0`、`violations + 1`；
    同一样本的命中率 / 段序仍是满分 —— 证明 0 分来自违规规则，而不是「漏填段」。"""
    import agent_stage_service

    template_id = _publish_record_template()
    violated = _PERFECT_DRAFT.replace("- 舌象：（留待老師）", "- 舌象：舌紅苔薄白")
    _seed_draft(violated, template_id)

    metric = agent_stage_service.compute_template_match(TEACHER, {})

    assert metric["value"] == 0.0
    assert metric["violations"] == 1
    assert metric["hit_rate"] == pytest.approx(1.0)
    assert metric["order_rate"] == pytest.approx(1.0)


def test_template_match_skips_stale_and_no_template(db, metric_env):
    """§6.3-23：`template_id=0`（无模板生成的样本）与旧版 `template_id`（换过版本）分别计入
    `skipped_no_template` / `skipped_stale_template`，**不进均值**（均值仍等于满分样本的 1.0）。"""
    import agent_stage_service

    template_id = _publish_record_template()
    _seed_draft(_PERFECT_DRAFT, template_id)
    _seed_draft("當時沒有生效模板的舊輸出", 0)
    _seed_draft("舊版本模板的輸出", template_id + 7)

    metric = agent_stage_service.compute_template_match(TEACHER, {})

    assert metric["samples"] == 1
    assert metric["value"] == pytest.approx(1.0)
    assert metric["skipped_no_template"] == 1
    assert metric["skipped_stale_template"] == 1


def test_template_match_counts_empty_text_samples_explicitly(db, metric_env):
    """§3.2「排除样本必须显式计数，不静默丢」：命中模板但 AI 侧文本为空的样本 → `skipped_empty`，
    不进均值（`value` 仍只看有效样本）；若一份有效样本都没有 → `value is None` + blocker。"""
    import agent_stage_service

    template_id = _publish_record_template()
    _seed_draft("", template_id)
    perfect_id = _seed_draft(_PERFECT_DRAFT, template_id)

    metric = agent_stage_service.compute_template_match(TEACHER, {})

    assert metric["skipped_empty"] == 1 and metric["samples"] == 1
    assert metric["value"] == pytest.approx(1.0)

    _raw_execute("DELETE FROM drafts WHERE id = ?", (perfect_id,))
    only_empty = agent_stage_service.compute_template_match(TEACHER, {})

    assert only_empty["value"] is None
    assert only_empty["samples"] == 0
    assert only_empty["skipped_empty"] == 1
    assert only_empty["blockers"] == ["template_match_no_samples"]


def test_template_match_no_active_template_is_null_not_zero(db, metric_env):
    """口径 A：老师没有生效 `record` 模板（含 `TEMPLATE_API_ENABLED` off）→
    `value is None` + `blockers=["no_active_record_template"]`（**不是 0 分**：空值 ≠ 差评）。"""
    import agent_stage_service

    no_template = agent_stage_service.compute_template_match(TEACHER, {})
    assert no_template["value"] is None and no_template["samples"] == 0
    assert no_template["blockers"] == ["no_active_record_template"]

    _publish_record_template()
    no_sample = agent_stage_service.compute_template_match(TEACHER, {})
    assert no_sample["value"] is None
    assert no_sample["blockers"] == ["template_match_no_samples"]


def test_template_match_weights_come_from_config(db, metric_env):
    """不硬编码（§3.4 / §6.4-29 的指标侧）：权重改配置即改结果。

    样本 = `_OUT_OF_ORDER_DRAFT`（命中率 5/5、严格 LCS = 2/5）：
      · 内置默认 0.6 / 0.4 → 0.6 * 1.0 + 0.4 * 0.4 = 0.76；
      · 只给 `section_hit=1.0` → 就是命中率 1.0（缺省子键按 0 计，不做部分合并，裁决 B）；
      · 0.5 / 0.5 → 0.5 * 1.0 + 0.5 * 0.4 = 0.8。
    """
    import agent_stage_service

    template_id = _publish_record_template()
    _seed_draft(_OUT_OF_ORDER_DRAFT, template_id)

    default_weights = agent_stage_service.compute_template_match(TEACHER, {})
    hit_only = agent_stage_service.compute_template_match(
        TEACHER, {"template_match_weights": {"section_hit": 1.0}})
    balanced = agent_stage_service.compute_template_match(
        TEACHER, {"template_match_weights": {"section_hit": 0.5, "section_order": 0.5}})

    assert default_weights["hit_rate"] == pytest.approx(1.0)
    assert default_weights["order_rate"] == pytest.approx(2 / 5)
    assert default_weights["value"] == pytest.approx(0.6 + 0.4 * 0.4)
    assert hit_only["value"] == pytest.approx(1.0)
    assert balanced["value"] == pytest.approx(0.5 + 0.5 * 0.4)


def test_template_match_order_rate_uses_strict_lcs(db, metric_env):
    """回归：段序一致率用**严格 LCS**（§3.2 的公式），不是 `difflib` 的块匹配启发式。

    实测同一对段序 `[A,B,C,D,E]` vs `[A,C,E,D,B]`：块匹配只得 2、严格 LCS = 3 ——
    改用块匹配会把 `order_rate` 系统性低估（更难达标）。本条把口径钉死（服务层 `_lcs_length()`）。"""
    import difflib

    import agent_stage_service

    sections = tuple((chr(ord("a") + index), chr(ord("A") + index), "ai") for index in range(5))
    template_id = _publish_record_template(sections=sections)
    _seed_draft("\n".join("%s：（留待老師）" % title for title in ("A", "C", "E", "D", "B")),
                template_id)

    metric = agent_stage_service.compute_template_match(TEACHER, {})

    block_matching = sum(block.size for block in difflib.SequenceMatcher(
        None, list("ABCDE"), list("ACEDB"), autojunk=False).get_matching_blocks())
    assert block_matching == 2, "difflib 块匹配的实测值（口径说明的论据，变了必须复核）"
    assert agent_stage_service._lcs_length(list("ABCDE"), list("ACEDB")) == 3
    assert metric["hit_rate"] == pytest.approx(1.0)
    assert metric["order_rate"] == pytest.approx(3 / 5)
    assert metric["value"] == pytest.approx(0.6 + 0.4 * 0.6)


# ---- ② 病历修改一致率（§3.3；§6.3 第 24–26 条）----

def test_modification_consistency_strict_pair(db, metric_env):
    """§6.3-24：新数据（`ai_original_text` 有值 = `strict` 样本）→ ② 与手算
    `SequenceMatcher` 逐位一致。

    样本刻意不含 CRLF / 连续空白 / 首尾空白 → `norm()` 是恒等映射，测试因此不必复刻归一化实现
    （否则「同一条实现比对自身」就失去验证意义）。
    """
    import difflib

    import agent_stage_service

    ai_text = "主訴：頭痛三日，無發熱。舌象：（留待老師）脈象：（留待老師）辨證：（留待老師）"
    final_text = "主訴：頭痛三日。舌象：舌淡紅。脈象：脈細。辨證：風寒表證。"
    _seed_record(ai_text, final_text, template_id=0)

    metric = agent_stage_service.compute_modification_consistency(TEACHER, {})

    expected = difflib.SequenceMatcher(None, ai_text, final_text, autojunk=False).ratio()
    assert metric["samples"] == 1 and metric["approx_samples"] == 0
    assert metric["value"] == pytest.approx(expected)
    assert metric["min"] == pytest.approx(expected)
    assert metric["blockers"] == []


def test_modification_consistency_approx_pair(db, metric_env):
    """§6.3-25：旧数据（`ai_original_text = ''`、只有 `ai_draft`）→ 计入均值且 `approx_samples = 1`
    （前端据此显示「含 N 份近似樣本（舊數據）」）。"""
    import difflib

    import agent_stage_service

    ai_draft = "舊格式草案：頭痛"
    final_plan = "頭痛，風寒表證，桂枝湯加減"
    _seed_record(ai_draft, final_plan, template_id=0, with_snapshot=False)

    metric = agent_stage_service.compute_modification_consistency(TEACHER, {})

    expected = difflib.SequenceMatcher(None, ai_draft, final_plan, autojunk=False).ratio()
    assert metric["samples"] == 1
    assert metric["approx_samples"] == 1
    assert metric["value"] == pytest.approx(expected)
    assert metric["min"] == pytest.approx(expected)


def test_modification_consistency_ignores_drafts_and_empty_pairs(db, metric_env):
    """② 只看已签字病历（§3.3）：未签字草案**不进样本**（老师还没定稿）；任一侧文本为空 →
    `skipped_empty`（不静默丢，也不进均值）。"""
    import agent_stage_service

    _seed_draft(_PERFECT_DRAFT, 0)                                  # 草案 → ② 不算
    _seed_record("", "只有老師的最終方案", template_id=0)              # AI 侧空 → 排除
    _seed_record("只有 AI 的草案", "", template_id=0)                  # 老师侧空 → 排除
    _seed_record("主訴：頭痛", "主訴：頭痛，無發熱", template_id=0)      # 唯一有效配对

    metric = agent_stage_service.compute_modification_consistency(TEACHER, {})

    assert metric["samples"] == 1
    assert metric["skipped_empty"] == 2
    assert metric["approx_samples"] == 0


def test_modification_consistency_reads_truncate_chars_from_config(db, metric_env):
    """不硬编码（§3.3）：`truncate_chars` 缩到差异之前 → 两份文本判满分（也是「耗时有界」的机制）。"""
    import agent_stage_service

    _seed_record("甲甲乙丙丁", "甲甲戊己庚", template_id=0)

    truncated = agent_stage_service.compute_modification_consistency(TEACHER, {"truncate_chars": 2})
    full = agent_stage_service.compute_modification_consistency(TEACHER, {"truncate_chars": 2000})

    assert truncated["value"] == pytest.approx(1.0)     # 两侧都只剩「甲甲」
    assert full["value"] < 1.0


def test_metrics_null_when_no_samples(db, metric_env):
    """§6.3-26 + CTO 硬约束 2（空集语义）：无样本 → `value is None`（**不是 0**）+ 对应 blocker；
    且 `None` 与阈值比较抛 `TypeError` —— 3.4-b 的判定只能显式 `is not None`，
    空值没有「静默通过」的路径。"""
    import agent_stage_service

    _publish_record_template()      # ① 有基准，但一份样本都没有

    template_match = agent_stage_service.compute_template_match(TEACHER, {})
    consistency = agent_stage_service.compute_modification_consistency(TEACHER, {})

    for metric, blocker in ((template_match, "template_match_no_samples"),
                            (consistency, "modification_consistency_no_samples")):
        assert metric["value"] is None
        assert metric["value"] != 0, "空集（无样本）与 0 分是两件事"
        assert metric["samples"] == 0
        assert metric["blockers"] == [blocker]
        with pytest.raises(TypeError):
            metric["value"] >= 0.75


# ---- 指标层的只读性与文本层口径（CTO 约束 3 / 口径 B）----

def test_metric_functions_are_read_only(db, sql_log, metric_env, monkeypatch):
    """指标层**零写入**（CTO 约束 3 / §5.1 红线① 的服务层等价物）：

    · 全部语句只有 SELECT / PRAGMA（没有 INSERT / UPDATE / DELETE / CREATE）；
    · 两条样本 SELECT 都必须带 `LIMIT`（批复 C 的硬约束）；
    · 五张表（三张新表 + `drafts` / `patient_records`）行数与草案内容一字不变；
    · flag off 下照常算出结果（指标是纯计算，闸门在 `evaluate`），但依旧一行不写。
    """
    import agent_stage_service

    template_id = _publish_record_template()
    _seed_draft(_PERFECT_DRAFT, template_id)
    _seed_record("主訴：頭痛", "主訴：頭痛，無發熱", template_id)
    before = _table_counts()
    draft_content = _raw_scalar("SELECT content FROM drafts ORDER BY id DESC LIMIT 1")

    monkeypatch.delenv("AGENT_STAGE_ENABLED", raising=False)    # flag off：指标仍可算，只是不落盘
    metric = agent_stage_service.compute_template_match(TEACHER, {})
    consistency = agent_stage_service.compute_modification_consistency(TEACHER, {})

    assert metric["value"] is not None and consistency["value"] is not None, \
        "指标不读 flag：闸门与判定在 evaluate（3.4-b）"

    statements = [sql for sql, _ in _all_calls(sql_log)]
    assert statements, "至少要发出读样本的 SELECT"
    assert [sql for sql in statements if not sql.startswith(("SELECT", "PRAGMA"))] == [], \
        "指标层只许发读语句"
    sample_statements = [sql for sql in statements
                         if "FROM drafts" in sql or "FROM patient_records" in sql]
    assert len(sample_statements) == 4, sample_statements        # 两个指标 × 两类来源各一条
    assert all("LIMIT" in sql for sql in sample_statements), "样本读取必须带 LIMIT（批复 C）"

    assert _table_counts() == before, "指标层不得写任何表"
    assert _raw_scalar("SELECT content FROM drafts ORDER BY id DESC LIMIT 1") == draft_content


def test_metric_text_normalization_contract():
    """口径 B 的文本层契约（纯函数、无需 DB）：② 的折叠 / 截断、① 的行结构与标题尾巴白名单、
    违规判定的「提示语不算内容」。这些规则是**指标可解释性的地基**，故逐条钉住。"""
    import agent_stage_service as service

    assert service._normalize_metric_text("  頭痛\r\n\r\n三日  ", None) == "頭痛 三日"
    assert service._normalize_metric_text("甲甲乙丙", 2) == "甲甲"
    assert service._normalize_metric_text(None) == ""
    assert service._normalize_metric_text(123) == ""

    assert service._normalize_section_text("【主訴】：　頭痛\r\n\r\n- 舌象（留待老師）　") == \
        "【主訴】: 頭痛\n舌象（留待老師）"
    assert service._split_heading("【主訴】: 頭痛") == ("主訴", "頭痛")
    assert service._split_heading("舌象: （留待老師）") == ("舌象", "（留待老師）")

    assert service._heading_matches("舌象（留待老師）", "舌象") is True
    assert service._heading_matches("舌象。", "舌象") is True
    assert service._heading_matches("舌象", "舌象") is True
    assert service._heading_matches("舌紅苔薄白", "舌象") is False
    assert service._heading_matches("舌象", "舌象（留待老師）") is False, "不做缩写 / 模糊匹配"
    assert service._strip_heading_tail("主訴（學生原話）") == "主訴（學生原話）", "真标题不被误剥"

    assert service._teacher_section_is_filled("（留待老師）") is False
    assert service._teacher_section_is_filled("　← 留待老師（智能體永不填）") is False
    assert service._teacher_section_is_filled("") is False
    assert service._teacher_section_is_filled("舌紅苔薄白") is True

    assert service._lcs_length(["A", "B", "C"], ["A", "C"]) == 2
    assert service._lcs_length([], ["A"]) == 0


# ---- 库层只读原语 `database.get_draft_samples`（批复 C-1）----

def test_get_draft_samples_returns_both_sources_with_contract_keys(db):
    """返回契约：9 键 + 两类来源 + 顺序（已签字病历 → 未签字草案，各自倒序）；
    草案按 `id DESC`（唯一的「新近」信号），病历带时间锚。"""
    template_id = _publish_record_template()
    _seed_draft("草案一", template_id)
    _seed_draft("草案二", 0)
    _seed_record("AI 原稿", "老師終稿", template_id)

    samples = database.get_draft_samples(TEACHER, 90, 5)

    assert [row["source"] for row in samples] == ["record", "draft", "draft"]
    expected_keys = {"source", "id", "patient_name", "ai_text", "final_text",
                     "template_id", "template_version", "has_snapshot", "at"}
    assert set(samples[0]) == expected_keys
    assert set(samples[1]) == expected_keys
    assert (samples[0]["ai_text"], samples[0]["final_text"]) == ("AI 原稿", "老師終稿")
    assert samples[0]["has_snapshot"] is True and samples[0]["at"] != ""
    assert samples[0]["template_id"] == template_id
    assert (samples[1]["ai_text"], samples[1]["template_id"]) == ("草案二", 0)
    assert samples[1]["at"] == "" and samples[1]["has_snapshot"] is True
    assert samples[2]["ai_text"] == "草案一"


def test_get_draft_samples_falls_back_to_content_without_snapshot(db):
    """快照列为空（flag off 期间落库的老草案）→ `ai_text` 回落 `content`、`has_snapshot = False`
    （② 据此把它算成 `approx`）；病历侧同款回落 `ai_draft`。"""
    _seed_draft("老草案（無快照）", 0, snapshot="")
    _seed_record("舊 AI 文本", "舊終稿", 0, with_snapshot=False)

    samples = database.get_draft_samples(TEACHER, 90, 5)

    record, draft = samples[0], samples[1]
    assert (record["ai_text"], record["has_snapshot"]) == ("舊 AI 文本", False)
    assert (draft["ai_text"], draft["has_snapshot"]) == ("老草案（無快照）", False)


def test_get_draft_samples_limit_applies_per_source(db):
    """`limit` 对**每个来源**各生效（最多 2 × limit 行，两指标因此互不挤占）；
    坏 `limit`（`<= 0` / 非数字）→ 回落默认 50。"""
    for index in range(3):
        _seed_draft("草案 %d" % index, 0)
    for index in range(3):
        _seed_record("AI %d" % index, "老師 %d" % index, 0, visit_at="")

    samples = database.get_draft_samples(TEACHER, 90, 2)

    assert len([row for row in samples if row["source"] == "draft"]) == 2
    assert len([row for row in samples if row["source"] == "record"]) == 2
    assert len(database.get_draft_samples(TEACHER, 90, 0)) == 6
    assert len(database.get_draft_samples(TEACHER, 90, "不是數字")) == 6


def test_get_draft_samples_window_applies_to_records_only(db):
    """窗口只作用于**有时间锚**的病历：今天之内 → 收；`2000-01-01`（远超任何窗口）→ 排除；
    `visit_at = ''`（迁移前的老签字）→ **照收**（§3.3 的 `approx` 样本就在这类行里）；
    草案无时间列 → 不受窗口影响（口径 2 / 3）。"""
    _seed_draft("草案（id 序即新近信号）", 0)
    _seed_record("最近的", "最近的", 0)
    _seed_record("很久以前的", "很久以前的", 0, visit_at="2000-01-01T00:00:00")
    _seed_record("老數據（無時間）", "老數據（無時間）", 0, visit_at="")

    texts = [row["ai_text"] for row in database.get_draft_samples(TEACHER, 1, 10)]

    assert "最近的" in texts and "老數據（無時間）" in texts
    assert "很久以前的" not in texts
    assert "草案（id 序即新近信号）" in texts


def test_get_draft_samples_survives_missing_migration_columns(monkeypatch, tmp_path, db):
    """迁移 0002 / 0003 / 0004 的列都还没跑的老库 → 照常返回（缺列读作 `0` / `''`、AI 侧回落
    `content` / `ai_draft`），**不抛异常**（§4.5-①「指标可降级，存储没坏」）。"""
    path = _copy_tested_db(monkeypatch, tmp_path, "samples_without_new_columns.db")
    for table, column in (("drafts", "template_id"), ("drafts", "template_version"),
                          ("drafts", "ai_original_content"),
                          ("patient_records", "template_id"),
                          ("patient_records", "template_version"),
                          ("patient_records", "ai_original_text")):
        _drop_column(path, table, column)

    _raw_execute("INSERT INTO drafts (transcript_id, patient_name, teacher_name, content, signed) "
                 "VALUES (0, '张三', ?, '老庫草案', 0)", (TEACHER,))
    _raw_execute("INSERT INTO patient_records (patient_name, teacher_name, ai_draft, final_plan, "
                 "doctor, visit_at) VALUES ('张三', ?, '老庫 AI', '老庫終稿', ?, '')",
                 (TEACHER, TEACHER))

    samples = database.get_draft_samples(TEACHER, 90, 10)      # 不抛异常 = 本条的核心断言

    record, draft = samples[0], samples[1]
    assert (record["template_id"], record["template_version"]) == (0, 0)
    assert (record["ai_text"], record["final_text"], record["has_snapshot"]) == \
        ("老庫 AI", "老庫終稿", False)
    assert (draft["template_id"], draft["template_version"]) == (0, 0)
    assert (draft["ai_text"], draft["has_snapshot"]) == ("老庫草案", False)


def test_get_draft_samples_is_read_only_and_limited(db, sql_log):
    """批复 C 的两条硬约束：**只读**（无写语句）+ **必带 LIMIT**（每条样本 SELECT 都有）。"""
    _seed_draft("草案", 0)
    _seed_record("AI 文本", "老師文本", 0)

    samples = database.get_draft_samples(TEACHER, 90, 3)

    assert len(samples) == 2
    statements = [sql for sql, _ in _all_calls(sql_log)]
    assert statements and all(sql.startswith(("SELECT", "PRAGMA")) for sql in statements), statements
    sample_statements = [sql for sql in statements
                         if "FROM drafts" in sql or "FROM patient_records" in sql]
    assert len(sample_statements) == 2
    assert all("LIMIT" in sql for sql in sample_statements)


def test_get_draft_samples_bad_input_is_safe(db):
    """坏入参不炸：空老师名 → `[]`（连 SQL 都不发）；坏窗口 → 不过滤；坏 limit → 兜底默认。"""
    _seed_draft("草案", 0)

    assert database.get_draft_samples("", 90, 10) == []
    assert len(database.get_draft_samples(TEACHER, "不是數字", 1)) == 1
    assert len(database.get_draft_samples(TEACHER, None, None)) == 1


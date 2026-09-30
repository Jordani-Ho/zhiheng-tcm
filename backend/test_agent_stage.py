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
       的反向硬断言已按 CTO 批复② 于 step 2.4 删除（§4.5-① 允许服务层 import database）
       + §2.2 **单一收口点**守护（§6.3 第 16 条）：全仓扫描 `current_stage(` 的调用点，
       只许落在 §2.2 白名单（服务层 + step 4 的接口层）内 —— 白名单外的任何文件出现调用 = 绕过
       矩阵（`require_capability()` 仍是唯一放行点）；
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

    ⑰ 【施工步骤 3.4-b】**判定层**：`evaluate()`（§3.6 `can_recommend` + §3.8 失败方向）+
       `stage_config_source()`（§3.4 第 4 条）+ 库层只读统计 `database.get_agent_stage_log_stats`
       （批复 C-2：越权计数 + 推荐冷却）。CTO 八条约束逐条钉住：
       ① 三块各有契约用例；② `evaluate()` 首行 flag 闸门（off → 零 SQL、零写入）；
       ③ **绝不向上写 `stage`**（AST 数 `stage=` 关键字实参并**逐处归位**：`_ensure_state_row()` 的
        零 delta 一处、3.4-c 老师确认钩子的唯一向上写一处、该钩子返回体回显一处（不落库）——
        3.4-c 落地后由 3 处断言接续钉住；4a 落地降级入口后 +2 处（`_demote()` 的唯一向下写 + 其返回体回显）→ 现为
        **5 处**（零 delta upsert + 向上 upsert + 向上回显 + 向下 upsert + 向下回显；方向由 ⑲ 组
         按「值必须严格减少 rank」行为级补齐）；另配「有行老师 `stage` /
        `stage_since` / `stage_source` 评估前后逐字节不变」与「无行老师生效阶段 + 权限面不变」
        两条行为级断言）；
       ④ 十条判定逐条进 `blockers`（`value=None` / `pending_stage` / 冷却期三条各有专项）；
       ⑤ `pending_stage` 与 `pending_task_id` **成对**写（先 state 后建单 + 建单抛异常不留半对）；
       ⑥ `stage_config_source()` 与 `load_stage_config` **同源**（同一层走读 + 调用点唯一守护）；
       ⑦ `agent_action_log` 只在推荐建单时写（无推荐的评估一行都不写）；⑧ 阈值改了判定就变。
       本组**不改** ⑬–⑯ 组一行，只复用它们的造数 / 断言助手。

    ⑱ 【施工步骤 3.4-c】**三个既有链路钩子** + 「唯一向上写路径」：`on_draft_signed`（薄封装，
       只转一次评估）/ `apply_upgrade_confirmation`（老师 ✅ 确认 → **全系统唯一 rank 增加点**）/
       `decline_upgrade`（老师 ❌ 忽略 → 清待确认对 + 冷却起点）。CTO 约束逐条钉住：
       ① 唯一向上写路径（**源码级**：全文件 `stage=` 写入点枚举 + 逐处归位到「所属函数 + 所属调用」，
       真正落库的状态行写入点恰好 3 处（零 delta + 唯一向上 + 4a 的唯一向下）、其中
       **rank 增加点计数 = 1**、**rank 减少点计数 = 1**，且向上那处的值表达式恒为钩子入参
       `to_stage`、向下那处的值恒为「现场校验后的落点变量」（方向由 ⑲ 组行为级钉住）；
       `**` 展开形状出现即红；**行为级**：越级 / 向下 / 非法目标一律拒绝且阶段一个字不动）；
       ② 拒绝用既有 `upgrade_declined` 事件（**不新造第 11 类**、**不用**语义不符的 `permission_denied`），
       跳级 detail 固定含「越級請求被拒：to_stage=X, current=Y」；
       ③ 幂等（已在目标阶段 → `stage` / `stage_since` / `stage_source` 逐字节不变、不写第二条
       `stage_upgraded`）；④ `on_draft_signed` 是薄封装（**不判 flag**：总闸只许一份，源码级断言体内
       无 flag 标识符且只有一次评估调用）；⑤ 三钩子互不调用（源码级无环）；⑥ `agent_action_log`
       只写升阶 / 被拒两类（`confirm_upgrade` / `decline_upgrade`）；⑦ 端到端：签字 → 评估 → 推荐
       （阶段不动）+ ❌ → 紧接着的评估被 3.4-b 口径 F 的冷却拦住 + flag off 三钩子零 SQL 零写入。
       本组**不改** ⑬–⑯ 组一行；⑰ 组那条「恰好 1 处」的临时钉按它自己的预告升级为「3 处 + 逐处
       归位」，⑪ 组两条 flag on 用例按「钩子已真实存在」调整口径（前 5 条语句仍逐字节等于 flag off
       基线，评估链语句一律排在其后）。


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
    """白名单 ↔ 0003 建表列 逐列一致（列名漂移立刻红）。

    【Epic 4 step 4.1 同步点】迁移 `0005_add_lineage` 按 CTO 裁决 ③-C / 设计 §2.3 给
    `agent_stage_log` 补了一列 `lineage_id`（**只作审计标注**：阶段本身仍恒「老师维度」，
    `agent_stage_state` 结构一字未动）。故本用例的日志表期望集合显式多出这一列 ——
    除它以外仍逐列严格相等，列名漂移依旧立刻红；`AGENT_STAGE_LOG_INSERT_FIELDS` 常量本身
    （= `insert_agent_stage_log` 的写入字段）**一字不改**，带 lineage 写入属 step 4.2 的写路径改造。
    """
    conn = database.get_connection()
    state_columns = {row["name"] for row in conn.execute("PRAGMA table_info('agent_stage_state')")}
    log_columns = {row["name"] for row in conn.execute("PRAGMA table_info('agent_stage_log')")}
    conn.close()

    assert set(database.AGENT_STAGE_STATE_UPSERT_FIELDS) | {"teacher_name"} == state_columns
    assert set(database.AGENT_STAGE_LOG_INSERT_FIELDS) | {
        "id",
        "teacher_name",
        "event_type",
        "lineage_id",  # 【Epic 4 裁决③-C】0005 新增的审计标注列（唯一白名单外例外）
    } == log_columns


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


def test_find_pending_upgrade_task_ignores_resolved_tasks(db, monkeypatch):
    """本用例的断言口径是**既有决策留痕行为不变**（§5.5-②）→ 显式关总闸：

    flag on 时 `resolve_agent_task` 的升级钩子会按结果**再补一行** `confirm_upgrade` /
    `decline_upgrade` 行动日志（钩子转发段本身**不判 flag**，CTO 批复①），`[0]` 就不再是 `approve`。
    """
    monkeypatch.delenv("AGENT_STAGE_ENABLED", raising=False)
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


# ---- §2.2 单一收口点：`current_stage(` 只许在 §2.2 白名单（服务层 / step 4 接口层）内被调用 ----

# 扫描范围排除项（只认**生产模块**：测试文件里出现这个符号恰恰是为了断言它不存在）
_SCAN_SKIP_DIRS = {"__pycache__", "node_modules", "site-packages", "venv", "env"}

# §2.2 / §6.3 第 16 条的**调用点白名单**（原句：「扫描 `agent_stage_service` / `agent_stage_api`
# 之外的文件不得直接出现 `current_stage` 的调用」）—— 白名单外 = 绕过唯一能力闸门。
_MATRIX_CHOKE_POINT_FILES = {"agent_stage_service.py", "agent_stage_api.py"}


def _production_python_files():
    """全仓 `*.py` 里的**生产模块**路径（按目录名 / 文件名排除测试文件与三方、缓存、工具目录）。

    仓库根 = `backend/` 的父目录（由 `database.__file__` 反推，不硬编码盘符）；带 `.` 前缀的目录
    （`.git` / `.venv` / `.pytest_cache` …）一律跳过。
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(database.__file__)))
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames
                       if not name.startswith(".") and name not in _SCAN_SKIP_DIRS]
        for filename in filenames:
            if filename.endswith(".py") and not filename.startswith("test_") \
                    and filename != "conftest.py":
                found.append(os.path.join(dirpath, filename))
    return sorted(found)


def _current_stage_uses(source):
    """AST 口径：抽出本文件里 `current_stage` 的**真实**定义点与调用点行号。

    必须用 AST 才能把「注释 / docstring / 告警文案里提到 `current_stage(`」与「代码里真的读了一次
    阶段真值」分开（本文件头部与 §2.2 的说明文字里就大量「提到」它）。裸调用
    `current_stage(...)` 与 `模块.current_stage(...)` 都算调用。
    """
    import ast

    tree = ast.parse(source)
    defined, called = [], []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and node.name == "current_stage":
            defined.append(node.lineno)
        if isinstance(node, ast.Call):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            if name == "current_stage":
                called.append(node.lineno)
    return sorted(defined), sorted(called)


def test_matrix_single_choke_point():
    """【§2.2 / §6.3 第 16 条】能力闸门**单一收口点**的源码级守护：`current_stage(` 只许出现在
    §2.2 白名单里 —— 服务层 `agent_stage_service.py`（今天唯一的调用点）+ step 4 落地后的接口层
    `agent_stage_api.py`。

    为什么：`require_capability()` 是唯一读 `agent_stage_state` 做放行判定的函数（§2.2），而它拿阶段
    真值的唯一入口就是 `current_stage()`。别的文件（尤其接口层）自己调一次 `current_stage()` 再自行
    判定，等于在矩阵之外长出**第二个闸门** —— 越权面从「一处可审」散成「各处各自为政」，而「同一个
    判断只许有一份实现」是本项目红线（Epic 4 裁决①同句）。

    扫描**全仓生产 `*.py`**（跳过测试文件与三方 / 缓存目录），断言三条（白名单口径见 §2.2 / §6.3 第 16 条）：
      ① **调用点白名单**：`current_stage(...)` 的调用点只许落在 §2.2 白名单内（服务层
         `agent_stage_service.py` + step 4 落地后的接口层 `agent_stage_api.py`）；白名单外的任何文件
         （`main.py` / 前端链路 / 未来新模块）出现调用 = 在矩阵之外长出**第二个闸门**；
       ② **闸门在场**：白名单里必须真有服务层的调用点（`require_capability()` 的唯一真值来源）；
       ③ **定义点唯一**：`current_stage` 也只许有一份实现（别处再来一份 = fail-closed 口径要漂移；
          step 4 的接口层只许**调用**、不许自建门）。
    口径：AST 精确判定**定义 / 调用节点**（注释 / docstring 里「提到」不算）；测试文件不在扫描范围。
    """
    callers, definers = {}, {}
    scanned = _production_python_files()
    assert scanned, "扫描范围不得为空（守护自身不许静默失效）"

    for path in scanned:
        with open(path, encoding="utf-8") as fh:
            source = fh.read()
        if "current_stage" not in source:            # 先按字面粗筛，再逐文件 AST 精判
            continue
        defined, called = _current_stage_uses(source)
        if defined:
            definers[os.path.basename(path)] = defined
        if called:
            callers[os.path.basename(path)] = called

    assert set(callers) <= _MATRIX_CHOKE_POINT_FILES, \
        "`current_stage(` 只许在 §2.2 白名单（服务层 / step 4 接口层）内被调用（实测 %r）—— 白名单" \
        "外出现调用 = 在「唯一能力闸门」之外长出第二个阶段真值读取点" % callers
    assert "agent_stage_service.py" in callers, \
        "闸门自身必须在场：`require_capability()` 的唯一真值来源就是服务层的 `current_stage()`" \
        "（实测 %r）" % callers
    assert sorted(definers) == ["agent_stage_service.py"], \
        "`current_stage` 只许有一份实现（实测 %r）—— 第二份 = fail-closed 口径可能漂移（接口层只许" \
        "调用、不许自建门）" % definers

    # 更强的一条只在「step 4 尚未落地」时成立（`agent_stage_api.py` 不存在 ⇒ 调用点不可能来自接口层）。
    # 挂在**文件存在性**上 → 接口层合法落地的那天自动让位给上面的白名单，不会变成假红。
    api_module = os.path.join(os.path.dirname(os.path.abspath(database.__file__)),
                              "agent_stage_api.py")
    if not os.path.exists(api_module):
        assert sorted(callers) == ["agent_stage_service.py"], \
            "step 4 尚未落地（agent_stage_api.py 不存在）：`current_stage(` 的唯一调用点必须是 " \
            "agent_stage_service.py（实测 %r）" % callers


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
    """双闸门的第二道：flag 已 on 但列未就位（老库）→ 仍走原 6 列 SQL，序列与 flag off 基线一致。

    【3.4-c 注】钩子真实存在之后，flag on 的签字会在 commit 之后追加一次评估（§4.2 改 2b：新病历 =
    新样本）。老库里那次评估会逐级降级（库表未就位、绝不改阶段），但**语句照样入账**；故本条按
    「签字那一段逐字节等于 flag off 基线 + 评估链的语句一律排在它之后」来钉，见下面两行断言。
    """
    monkeypatch.setenv("AGENT_STAGE_ENABLED", "on")
    draft_id = _sign_fixture_draft(legacy_full_db)
    sql_log.clear()

    assert legacy_full_db.sign_draft(draft_id, "最终方案", "完整病历") == "张三"

    sql, _params = _patient_record_insert_call(sql_log)
    assert "ai_original_text" not in sql, "列未就位 → 必须走原 6 列 SQL"

    calls = _normalized_calls(sql_log)
    assert calls[1] == ("PRAGMA table_info('patient_records')", ()), "flag on 时必须真的探到列（第二道闸门）"
    # 【3.4-c 起】钩子真实存在 → 签字之后接一次评估。本条只钉**签字那一段**：前 5 条与 flag off
    # 基线逐字节相同，且评估链的语句一律排在它们**之后**（钩子在 commit 之后才被调用）。
    non_pragma = [c for c in calls if not c[0].startswith("PRAGMA")]
    assert non_pragma[:5] == _sign_draft_baseline(draft_id), \
        "签字那一段的语句序列必须与 flag off 基线逐字节一致（评估语句只许跟在后面）"


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
    import agent_stage_service

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
    # 【3.4-c 起】flag on 的 `sign_draft()` 会在 commit 后真实触发一次评估（§4.2 改 2b），而评估链
    # 自己也会过闸门、探阶段表的列 → 本条只量**两个快照写入点**，故把钩子换成零副作用的哨兵
    # （与 ⑫ 组 `_install_fake_hooks` 同款纪律）。
    seen = []
    monkeypatch.setattr(agent_stage_service, "on_draft_signed", seen.append, raising=False)

    draft_id = _sign_fixture_draft(db)                        # insert_draft：闸门 1 次 + 草案列探测 1 次
    db.sign_draft(draft_id, "最终方案")                        # sign_draft：闸门 1 次 + 历史表列探测 1 次

    assert calls.count("gate") == 2, "两个写入点各过一次**同一个**闸门（不得存在第二份 flag 判断）"
    assert calls.count("probe:drafts") == 1 and calls.count("probe:patient_records") == 1, \
        "两个快照列探测共用唯一实现 _table_has_columns"
    assert seen == [TEACHER], "签字钩子恰好被调用一次，且实参是草案上的老师（评估链已被哨兵隔离）"


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


# ============ ⑰ 【施工步骤 3.4-b】判定层：evaluate / stage_config_source / 审计统计 ============
#
# CTO 2026-09-29 放行 step 3.4-b 的八条约束，本组逐条落地（本组即「⑰ 组」）：
#   ① 施工顺序（库层统计 → 配置来源 → evaluate）→ 三块各有契约用例；
#   ② `evaluate()` 首行 flag 闸门：flag off → **零 SQL、零写入**（语句级 + 五张表零增量）；
#   ③ **绝不向上写 `stage`**：AST 数 `stage=` 关键字实参 = 1（只在 `_ensure_state_row()`、
#      值恒为 `view["stage"]` 的零 delta 形态）+ 两条行为级断言（有行老师逐字节不变 /
#      无行老师生效阶段与权限面不变）；
#   ④ `can_recommend` 十条全真才推荐、逐条进 `blockers`（`value=None` / `pending_stage` /
#      冷却期三条有专项；越权 / 违规 / 最高阶段 / 放宽态各一条）；
#   ⑤ `pending_stage` / `pending_task_id` **成对写**：先 state 后建单（语句顺序）+ 建单抛异常
#      → 不留半对（monkeypatch 钉住）；
#   ⑥ `stage_config_source()` 口径：行存在性 / env 白名单 + 采纳 / 与 `load_stage_config` 同源；
#   ⑦ `agent_action_log` 写点克制：推荐建单写一行、无推荐的评估**一行都不写**；
#   ⑧ 阈值改了判定就变（`min_template_match` 0.99 → 0.7）。
#
# 本组**不改** ⑬–⑯ 组一行：只复用它们的造数 / 断言助手（`_raw_execute` / `_raw_scalar` /
# `_put_raw_state_row` / `_drop_table` / `sql_log` / `_all_calls` / `_table_counts` /
# `_publish_record_template` / `_seed_draft` / `_seed_record` / `_PERFECT_DRAFT` /
# `_OUT_OF_ORDER_DRAFT`）。造数一律走裸 sqlite3 或库层真实写函数（⑭ 组既有口径）。

# `evaluate()` 返回体的**逐键**契约（18 键快照 + `changed`；短路体同形状）
_EVALUATE_SNAPSHOT_KEYS = (
    "teacher_name", "skipped", "reason",
    "stage", "stage_label", "stage_since", "stage_source", "pending_stage", "pending_task_id",
    "degraded", "metrics", "metrics_reason", "thresholds", "config_source", "next_stage",
    "blockers", "evaluated_at", "metrics_ttl_hours",
)

# 「AI 填了 `teacher` 段」的违规样本（§3.2：该样本 `match = 0`、`violations + 1`）
_VIOLATING_DRAFT = _PERFECT_DRAFT.replace("（留待老師）", "舌紅苔薄白")

# 内置默认阈值（用例改配置时会显式覆盖；断言优先读返回体的 `thresholds` 回显）
_MIN_TEMPLATE_MATCH = 0.75
_MIN_MODIFICATION = 0.80


@pytest.fixture
def stage_gate(monkeypatch):
    """⑰ 组公共前置：打开总闸（`evaluate()` 的第一道门）+ Epic 1 病歷模板通道（① 的基准）。"""
    monkeypatch.setenv("AGENT_STAGE_ENABLED", "on")
    monkeypatch.setenv("TEMPLATE_API_ENABLED", "on")


def _seed_ready_for_recommendation(teacher=TEACHER):
    """造「十条全真」的前置：满分草案 + 满分病历 + `min_samples = 1` 的老师配置行。

    样本只有 1 份（默认 `min_samples = 5` 要 5 份草案 + 5 份病历），本组只关心判定链路，
    故把门槛调到 1；样本量不足的情形另有专门用例（`samples_below_minimum`）。
    返回 `(template_id, draft_id, record_id)`。
    """
    database.upsert_agent_stage_config(teacher, {"min_samples": 1})
    template_id = _publish_record_template(teacher=teacher)
    draft_id = _seed_draft(_PERFECT_DRAFT, template_id, teacher=teacher)
    record_id = _seed_record(_PERFECT_DRAFT, _PERFECT_DRAFT, template_id, teacher=teacher)
    return template_id, draft_id, record_id


# ---- 闸门 ①：flag 闸门（约束 2）与返回体形状 ----

def test_evaluate_flag_off_is_zero_sql_and_zero_writes(db, sql_log, monkeypatch, capsys):
    """CTO 约束 2：`evaluate()` **首行**就是总闸 —— flag off → 立即返回（零 SQL、零写入）。

    §5.1 红线① 的语义：开关关了，评估链不许成为「新表还在长」的缺口。
    """
    import agent_stage_service

    monkeypatch.delenv("AGENT_STAGE_ENABLED", raising=False)
    before = _table_counts()
    marker = len(_all_calls(sql_log))

    result = agent_stage_service.evaluate(TEACHER)

    assert _all_calls(sql_log)[marker:] == [], "flag off 必须零查詢（连一次 SELECT 都不许）"
    assert _table_counts() == before, "flag off 必须零写入"
    assert result["skipped"] is True
    assert result["reason"] == "agent_stage_disabled"
    assert result["blockers"] == ["agent_stage_disabled"]
    assert result["changed"] == {"stage_changed": False, "recommended": False, "demoted": False,
                                 "reason": "agent_stage_disabled"}
    assert set(result) == set(_EVALUATE_SNAPSHOT_KEYS) | {"changed"}
    assert result["config_source"] == {"global": False, "teacher_override": False,
                                       "env_override": []}
    assert result["thresholds"] == {} and result["evaluated_at"] == ""
    assert result["metrics_reason"] == {"inquiry_preference_consistency": "deferred_to_epic3"}
    assert result["metrics"]["template_match"]["blockers"] == ["agent_stage_disabled"]
    assert "未啟用" in capsys.readouterr().out


def test_evaluate_without_teacher_name_is_rejected_with_zero_sql(db, sql_log, monkeypatch):
    """空 `teacher_name` = 无效调用（接口层本来就 400 `teacher_required`）：直接跳过，
    **绝不**给状态表写一行 `teacher_name=''` 的垃圾行。"""
    import agent_stage_service

    monkeypatch.setenv("AGENT_STAGE_ENABLED", "on")
    before = _table_counts()
    marker = len(_all_calls(sql_log))

    result = agent_stage_service.evaluate("")

    assert _all_calls(sql_log)[marker:] == []
    assert _table_counts() == before
    assert database.get_agent_stage_state("") is None
    assert result["skipped"] is True and result["reason"] == "teacher_required"


def test_evaluate_short_circuit_shape_matches_normal_path(db, monkeypatch):
    """短路体与正常体**逐键同形**（前端 / 接口层不必为 flag off 或失败分支写第二套渲染）。"""
    import agent_stage_service

    monkeypatch.delenv("AGENT_STAGE_ENABLED", raising=False)
    short = agent_stage_service.evaluate(TEACHER)

    monkeypatch.setenv("AGENT_STAGE_ENABLED", "on")
    _put_raw_state_row(TEACHER, "learning")
    full = agent_stage_service.evaluate(TEACHER)

    assert set(short) == set(full) == set(_EVALUATE_SNAPSHOT_KEYS) | {"changed"}
    for key in ("metrics", "metrics_reason", "changed"):
        assert set(short[key]) == set(full[key]), key
    assert set(short["metrics"]["template_match"]) == set(full["metrics"]["template_match"])
    assert set(short["metrics"]["modification_consistency"]) == \
        set(full["metrics"]["modification_consistency"])


def test_evaluate_third_metric_is_null_placeholder(db, stage_gate):
    """§6.3-27：③ `inquiry_preference_consistency` 恒为 `null` + `reason = deferred_to_epic3`；
    ①② 的阈值一并回显（`thresholds`），前端据此逐条解释「差多少」。"""
    import agent_stage_service

    _put_raw_state_row(TEACHER, "learning")
    _publish_record_template()

    result = agent_stage_service.evaluate(TEACHER)

    assert result["metrics"]["inquiry_preference_consistency"] is None
    assert result["metrics_reason"] == {"inquiry_preference_consistency": "deferred_to_epic3"}
    assert set(result["metrics"]) == {"template_match", "modification_consistency",
                                      "inquiry_preference_consistency"}
    assert result["thresholds"]["min_template_match"] == _MIN_TEMPLATE_MATCH
    assert result["thresholds"]["min_modification_consistency"] == _MIN_MODIFICATION
    assert result["thresholds"]["min_samples"] == 5
    assert result["metrics"]["template_match"]["value"] is None
    assert result["metrics"]["template_match"]["blockers"] == ["template_match_no_samples"]


# ---- 约束 3：绝不向上写 stage（AST 守护 + 两条行为级断言）----

def test_evaluate_stage_write_point_is_pinned_to_the_zero_delta_helper():
    """CTO 约束 3 的**精确形态**（3.4-c 落地后按预告升级，4a 再按同一预告 +2）：服务层的
    `stage=` 关键字实参**恰好 5 处**，逐处归位 —— ① `_ensure_state_row()`：值表达式恒为
    `view["stage"]`（评估前 `describe_stage()` 已报告的同一个阶段 → **零 delta**）；② 3.4-c 老师
    确认钩子的状态行写入（**全系统唯一 rank 增加点**，见 ⑱ 组）；③ 同一钩子把结果装进**返回体**时对
    `_transition_result()` 的 `stage=` 回显（**不落库**）；④ 4a `_demote()` 的状态行写入（**全系统
    唯一 rank 减少点**，值恒为现场校验后的落点变量 `target`，见 ⑲ 组）；⑤ 同一降级函数把结果装进
    **返回体**时对 `_transition_result()` 的 `stage=` 回显（**不落库**）。
    5 处构成 = 零 delta upsert + 向上 upsert + 向上回显 + 向下 upsert + 向下回显
    （**3 处落库 + 2 处回显**）；CTO 裁决：`apply_upgrade_confirmation` 与 `_demote` 是对称操作，
    写法必须一致（各自的 upsert 与回显传的必须是**同一个变量**，见 ⑱ 组逐处归位）。
    `pending_stage=` / `from_stage=` / `to_stage=` 是别的形参名，AST 精确匹配不计入。
    """
    import ast
    import inspect

    import agent_stage_service

    tree = ast.parse(inspect.getsource(agent_stage_service))
    keywords = [node for node in ast.walk(tree)
                if isinstance(node, ast.keyword) and node.arg == "stage"]
    assert len(keywords) == 5, \
        "4a 落地后 stage= 关键字实参必须恰好 5 处（零 delta + 向上 upsert + 向上回显 + " \
        "向下 upsert + 向下回显），实测行号 %r" % [n.lineno for n in keywords]
    keywords.sort(key=lambda node: node.lineno)

    lines, start = inspect.getsourcelines(agent_stage_service._ensure_state_row)
    zero_delta = [kw for kw in keywords if kw.lineno in range(start, start + len(lines))]
    assert len(zero_delta) == 1, \
        "唯一的一处零 delta 写入只许在 _ensure_state_row() 里（别处出现就是「向上写」）"

    assert ast.dump(zero_delta[0].value) == ast.dump(ast.parse('view["stage"]', mode="eval").body), \
        "写入值必须是「评估前读到的阶段」本身（零 delta），不得是别的表达式"

    # 只读族逐个钉住「体内没有一行 stage= 实参」：读函数绝不许写阶段真值（口径 A 的 AST 形态；
    # 4a 新增的四个符号一并纳入，降级写点只许在 `_demote()` 里）
    for name in ("evaluate", "_evaluate", "_recommend_upgrade", "stage_config_source",
                 "stage_view", "_stage_view", "_stage_view_short_circuit",
                 "effective_capabilities", "_capability_view", "save_stage_config",
                 "_save_stage_config", "_config_save_short_circuit"):
        body = ast.parse(inspect.getsource(getattr(agent_stage_service, name)))
        assert [node.lineno for node in ast.walk(body)
                if isinstance(node, ast.keyword) and node.arg == "stage"] == [], name


def test_evaluate_never_self_upgrades_after_recommendation(db, stage_gate):
    """§6.1-4 + 约束 3：达标后 `stage` **不变**，只新增 `pending_stage` 与一条 pending 请示；
    有行老师的 `stage_since` / `stage_source` 逐字节不变（`_ensure_state_row` 一个字段都不碰）。"""
    import agent_stage_service

    _put_raw_state_row(TEACHER, "learning")
    _seed_ready_for_recommendation()

    result = agent_stage_service.evaluate(TEACHER)

    row = database.get_agent_stage_state(TEACHER)
    assert row["stage"] == "learning", "评估绝不自我升阶（§3.6 / §6.1-4）"
    assert row["stage_since"] == "" and row["stage_source"] == "default"
    assert result["changed"]["stage_changed"] is False
    assert result["changed"]["recommended"] is True
    assert row["pending_stage"] == "apprentice"
    assert row["pending_task_id"] == result["pending_task_id"] != 0
    assert result["next_stage"] == "apprentice"
    assert result["blockers"] == []


def test_evaluate_keeps_effective_stage_for_teacher_without_state_row(db, stage_gate):
    """§1.5 ③（无状态行 = 未初始化）+ 约束 3 的 fail-safe 形态：评估只在**无行时**补一次
    兜底阶段 → 生效阶段与权限面在评估前后完全一致（不会被状态表的 DDL 默认 `observation`
    静默降一级、把既有 `generate_draft` 收回）。"""
    import agent_stage_service

    before = agent_stage_service.current_stage(TEACHER)
    assert before == "learning", "无行老师的兜底阶段来自配置链的 default_stage"
    assert database.get_agent_stage_state(TEACHER) is None
    assert agent_stage_service.require_capability(TEACHER, "generate_draft") is True

    result = agent_stage_service.evaluate(TEACHER)

    row = database.get_agent_stage_state(TEACHER)
    assert row["stage"] == before, "评估不得改掉未初始化老师的生效阶段（零 delta）"
    assert row["stage_source"] == "default" and row["stage_since"] == ""
    assert agent_stage_service.current_stage(TEACHER) == before
    assert agent_stage_service.require_capability(TEACHER, "generate_draft") is True
    assert result["stage"] == before and result["degraded"] is False


# ---- 约束 4：十条判定逐条进 blockers（空值 / pending / 冷却 各有专项）----

def test_evaluate_null_metrics_block_recommendation(db, stage_gate):
    """CTO 约束 4 专项（①/② 空值）：`value is None`（**不是 0 分**）阻断推荐 ——
    原因用「没有证据」表达（`*_no_samples`），并叠加 `samples_below_minimum`。"""
    import agent_stage_service

    _put_raw_state_row(TEACHER, "learning")
    _publish_record_template()          # ① 有基准、一份样本都没有
    database.upsert_agent_stage_config(TEACHER, {"min_samples": 1})

    result = agent_stage_service.evaluate(TEACHER)

    assert result["blockers"] == ["template_match_no_samples",
                                  "modification_consistency_no_samples",
                                  "samples_below_minimum"]
    assert result["metrics"]["template_match"]["value"] is None
    assert result["metrics"]["modification_consistency"]["value"] is None
    assert result["changed"]["recommended"] is False
    assert result["changed"]["reason"] == "blocked"
    row = database.get_agent_stage_state(TEACHER)
    assert (row["pending_stage"], row["pending_task_id"]) == ("", 0)
    assert database.find_pending_upgrade_task(TEACHER) is None
    assert _raw_scalar("SELECT COUNT(*) FROM agent_tasks") == 0


def test_evaluate_without_active_template_reports_basis_not_score(db, stage_gate):
    """口径 A：此刻没有生效 `record` 模板 → ① 无基准 → `no_active_record_template`
    （**不是 0 分**：0 分会变成「智能体不守模板」的错误指控）。"""
    import agent_stage_service

    _put_raw_state_row(TEACHER, "learning")

    result = agent_stage_service.evaluate(TEACHER)

    assert result["blockers"] == ["no_active_record_template",
                                  "modification_consistency_no_samples",
                                  "samples_below_minimum"]
    assert result["metrics"]["template_match"]["value"] is None


def test_evaluate_pending_recommendation_blocks_and_is_not_duplicated(db, stage_gate):
    """CTO 约束 4 专项（`pending_stage`）：已有未确认的推荐 → 阻断（不重复建单），
    回显的 `pending_*` 仍是**状态行里的那一对**（前端继续显示「⏳ 待你确认」）。"""
    import agent_stage_service

    _put_raw_state_row(TEACHER, "learning", pending_stage="apprentice", pending_task_id=42)
    _seed_ready_for_recommendation()

    result = agent_stage_service.evaluate(TEACHER)

    assert result["blockers"] == ["upgrade_pending"]
    assert result["pending_stage"] == "apprentice" and result["pending_task_id"] == 42
    row = database.get_agent_stage_state(TEACHER)
    assert (row["pending_stage"], row["pending_task_id"]) == ("apprentice", 42)
    assert result["metrics"]["template_match"]["value"] == pytest.approx(1.0), "指标本身是达标的"
    assert _raw_scalar("SELECT COUNT(*) FROM agent_tasks") == 0


def test_evaluate_cooldown_blocks_and_config_clears_it(db, stage_gate):
    """CTO 约束 4 专项（冷却期）：上次「被拒」未满 `recommend_cooldown_hours` → 阻断；
    把冷却调到 0 → 立刻不阻断（冷却时长是配置，不是硬编码）。"""
    import agent_stage_service

    _put_raw_state_row(TEACHER, "learning")
    _seed_ready_for_recommendation()
    database.insert_agent_stage_log(TEACHER, "upgrade_declined", from_stage="learning",
                                    detail="老師拒絕了升級推薦")

    blocked = agent_stage_service.evaluate(TEACHER)

    assert blocked["blockers"] == ["cooldown_active"]
    assert blocked["metrics"]["template_match"]["value"] == pytest.approx(1.0)

    database.upsert_agent_stage_config(TEACHER, {"min_samples": 1, "recommend_cooldown_hours": 0})
    allowed = agent_stage_service.evaluate(TEACHER)

    assert allowed["blockers"] == []
    assert allowed["changed"]["recommended"] is True


def test_evaluate_permission_denial_in_window_blocks_upgrade(db, stage_gate):
    """§6.2-19：窗口内 1 次越权 + 指标全达标 → 不推荐（`blockers` 含 §2.4 的契约名
    `permission_denied_in_window`）；`max_permission_denials` 调到 1 → 放行。"""
    import agent_stage_service

    _put_raw_state_row(TEACHER, "learning")
    _seed_ready_for_recommendation()
    database.insert_agent_stage_log(TEACHER, "permission_denied", from_stage="learning",
                                    capability="predict_pattern", detail="智能體越權被拒")

    blocked = agent_stage_service.evaluate(TEACHER)

    assert "permission_denied_in_window" in blocked["blockers"]
    assert blocked["changed"]["recommended"] is False

    database.upsert_agent_stage_config(TEACHER, {"min_samples": 1, "max_permission_denials": 1})
    allowed = agent_stage_service.evaluate(TEACHER)

    assert "permission_denied_in_window" not in allowed["blockers"]
    assert allowed["changed"]["recommended"] is True


def test_evaluate_violations_block_and_are_counted(db, stage_gate):
    """§3.2 铁律违规（AI 填了 `writable_by='teacher'` 的段）→ ① 该样本 `match = 0`、
    `violations + 1`；`max_violations = 0` 时阻断推荐（§3.7 `rule_reset` 的同一信号）。"""
    import agent_stage_service

    _put_raw_state_row(TEACHER, "learning")
    database.upsert_agent_stage_config(TEACHER, {"min_samples": 1})
    template_id = _publish_record_template()
    _seed_draft(_VIOLATING_DRAFT, template_id)

    result = agent_stage_service.evaluate(TEACHER)

    assert result["metrics"]["template_match"]["violations"] == 1
    assert result["metrics"]["template_match"]["value"] == pytest.approx(0.0)
    assert "violations_exceeded" in result["blockers"]
    assert "template_match_below_threshold" in result["blockers"]
    assert result["changed"]["recommended"] is False
    assert _raw_scalar("SELECT COUNT(*) FROM agent_tasks") == 0


def test_evaluate_samples_below_minimum_blocks(db, stage_gate):
    """口径 E `samples >= min_samples`：指标可以达标（1 份满分），但样本数不够 → 阻断。"""
    import agent_stage_service

    _put_raw_state_row(TEACHER, "learning")
    template_id = _publish_record_template()
    _seed_draft(_PERFECT_DRAFT, template_id)
    _seed_record(_PERFECT_DRAFT, _PERFECT_DRAFT, template_id)

    result = agent_stage_service.evaluate(TEACHER)      # min_samples 用内置默认 5

    assert result["metrics"]["template_match"]["value"] == pytest.approx(1.0)
    assert result["metrics"]["modification_consistency"]["value"] == pytest.approx(1.0)
    assert result["metrics"]["template_match"]["samples"] == 2
    assert result["metrics"]["modification_consistency"]["samples"] == 1
    assert result["blockers"] == ["samples_below_minimum"]
    assert result["changed"]["recommended"] is False


def test_evaluate_authorized_teacher_gets_null_next_stage(db, stage_gate):
    """§3.6：已是最高阶段 → `next_stage = None` + `already_authorized`
    （不做「还能升到哪」的假设，也不建单）。"""
    import agent_stage_service

    _put_raw_state_row(TEACHER, "authorized")
    _seed_ready_for_recommendation()

    result = agent_stage_service.evaluate(TEACHER)

    assert result["stage"] == "authorized"
    assert result["next_stage"] is None
    assert result["blockers"] == ["already_authorized"]
    assert result["changed"]["recommended"] is False
    assert _raw_scalar("SELECT COUNT(*) FROM agent_tasks") == 0


def test_evaluate_matrix_relaxed_never_recommends_upgrade(db, stage_gate):
    """§2.5：`matrix_enforced=false` 是临时运维闸（放宽方向）→ 该状态下不推荐升级。"""
    import agent_stage_service

    _put_raw_state_row(TEACHER, "learning")
    seed = _seed_ready_for_recommendation()
    database.upsert_agent_stage_config(TEACHER, {"min_samples": 1, "matrix_enforced": False})
    assert seed, "样本已就绪（指标达标）—— 阻断只可能来自 matrix_relaxed"

    result = agent_stage_service.evaluate(TEACHER)

    assert result["blockers"] == ["matrix_relaxed"]
    assert result["changed"]["recommended"] is False
    assert _raw_scalar("SELECT COUNT(*) FROM agent_tasks") == 0


def test_evaluate_second_call_is_deduped_by_pending_and_cooldown(db, stage_gate):
    """§6.1-7：连续两次 `evaluate()` → 请示只有 1 条（第二次被 `pending_stage` + 冷却挡住）。"""
    import agent_stage_service

    _put_raw_state_row(TEACHER, "learning")
    _seed_ready_for_recommendation()

    first = agent_stage_service.evaluate(TEACHER)
    second = agent_stage_service.evaluate(TEACHER)

    assert first["changed"]["recommended"] is True
    assert second["changed"]["recommended"] is False
    assert "upgrade_pending" in second["blockers"]
    assert "cooldown_active" in second["blockers"], "刚推荐过 → 冷却期也必须挡住"
    assert _raw_scalar("SELECT COUNT(*) FROM agent_tasks WHERE status = 'pending'") == 1
    assert database.get_agent_stage_state(TEACHER)["pending_task_id"] == first["pending_task_id"]


# ---- 约束 5 / 7：推荐建单（先 state 后建单、成对、留痕克制）----

def test_evaluate_recommendation_writes_state_before_task_and_keeps_pair(db, stage_gate, sql_log):
    """约束 5：**先**写 state（`pending_stage` 一对的一半）→ **后**建请示 → 再把真 `task_id`
    写回（语句顺序 + 成对断言）；§3.6 step 3 的请示字段与 `action_data` 形状逐项钉住。"""
    import agent_stage_service

    _put_raw_state_row(TEACHER, "learning")
    _seed_ready_for_recommendation()
    marker = len(_all_calls(sql_log))

    result = agent_stage_service.evaluate(TEACHER)

    calls = _all_calls(sql_log)[marker:]
    pending_writes = [index for index, (sql, _params) in enumerate(calls)
                      if sql.startswith("INSERT INTO agent_stage_state") and "pending_stage" in sql]
    task_writes = [index for index, (sql, _params) in enumerate(calls)
                   if sql.startswith("INSERT INTO agent_tasks")]
    assert pending_writes and len(task_writes) == 1, calls
    assert pending_writes[0] < task_writes[0], "约束 5：先写 state（pending_stage）再建单"

    row = database.get_agent_stage_state(TEACHER)
    assert (row["pending_stage"], row["pending_task_id"]) == \
        ("apprentice", result["pending_task_id"])

    task = database.find_pending_upgrade_task(TEACHER)
    assert task["id"] == result["pending_task_id"]
    assert (task["task_type"], task["category"], task["status"]) == ("request", "agent", "pending")
    assert task["title"] == "智能體可升入「見習期」"
    assert "模板匹配度 100%（達標 75%）" in task["content"]
    assert "病歷修改一致率 100%（達標 80%）" in task["content"]
    assert "樣本 1 份" in task["content"] and "你可隨時降級" in task["content"]

    action = task["action"]
    assert action["action"] == "upgrade_agent_stage"
    assert (action["from"], action["to"]) == ("learning", "apprentice")
    assert action["config_source"] == result["config_source"]
    assert set(action["metrics"]) == {"template_match", "modification_consistency",
                                      "inquiry_preference_consistency"}
    assert action["metrics"]["inquiry_preference_consistency"] is None


def test_evaluate_recommendation_logs_stage_event_and_action_log(db, stage_gate):
    """§3.6 step 3 的两条痕：`upgrade_recommended`（带 `task_id` 与指标快照）+
    `agent_action_log`（工作台「行动日志」区块直接显示的人话）；`evaluation` 每次评估都写。"""
    import agent_stage_service

    _put_raw_state_row(TEACHER, "learning")
    _seed_ready_for_recommendation()

    result = agent_stage_service.evaluate(TEACHER)

    events = database.get_agent_stage_logs(TEACHER)
    assert [event["event_type"] for event in events] == ["evaluation", "upgrade_recommended"]
    evaluation, recommended = events
    assert evaluation["task_id"] == result["pending_task_id"]
    assert evaluation["from_stage"] == "learning" and evaluation["to_stage"] == ""
    assert evaluation["capability"] == ""
    assert "已推薦升入「見習期」" in evaluation["detail"]
    assert json.loads(evaluation["metrics_json"])["template_match"]["value"] == pytest.approx(1.0)

    assert recommended["task_id"] == result["pending_task_id"]
    assert recommended["from_stage"] == "learning"
    assert "智能體推薦升級至「見習期」" in recommended["detail"]

    actions = database.get_agent_action_log(TEACHER)
    assert [item["action"] for item in actions] == ["recommend_upgrade"]
    assert actions[0]["task_id"] == result["pending_task_id"]
    assert "智能體推薦升級至「見習期」" in actions[0]["detail"]


def test_evaluate_without_recommendation_writes_no_action_log(db, stage_gate, sql_log):
    """约束 7：`agent_action_log` 只在「推荐建单」写 —— 无推荐的评估**一行都不写**；
    写入面恰好是「指标快照 + `evaluation` 审计」两条。"""
    import agent_stage_service

    _put_raw_state_row(TEACHER, "learning")
    _publish_record_template()          # ① 有基准、无样本 → 不推荐
    marker = len(_all_calls(sql_log))

    result = agent_stage_service.evaluate(TEACHER)

    written = [sql for sql, _params in _all_calls(sql_log)[marker:]
               if not sql.lstrip().upper().startswith(("SELECT", "PRAGMA"))]
    assert len(written) == 2, written
    assert sum(1 for sql in written if sql.startswith("INSERT INTO agent_stage_state")) == 1
    assert sum(1 for sql in written if sql.startswith("INSERT INTO agent_stage_log")) == 1
    assert not any("agent_action_log" in sql or "agent_tasks" in sql for sql in written)
    assert database.get_agent_action_log(TEACHER) == []
    assert database.find_pending_upgrade_task(TEACHER) is None

    row = database.get_agent_stage_state(TEACHER)
    assert row["last_evaluated_at"] == result["evaluated_at"] != ""
    snapshot = json.loads(row["last_metrics_json"])
    assert "changed" not in snapshot, "口径 D：落库的快照不含 changed（它属于返回体）"
    assert snapshot["reason"] == "blocked"
    assert snapshot["metrics"]["template_match"]["value"] is None


def test_evaluate_snapshot_matches_returned_body(db, stage_gate):
    """口径 D：`last_metrics_json` = 返回体去掉 `changed`（逐键一致），`last_evaluated_at` =
    返回体的 `evaluated_at` → 前端 `GET` 直读快照与刚评估完的返回体**不会两套口径**。"""
    import agent_stage_service

    _put_raw_state_row(TEACHER, "learning")
    _seed_ready_for_recommendation()

    result = agent_stage_service.evaluate(TEACHER)

    row = database.get_agent_stage_state(TEACHER)
    snapshot = json.loads(row["last_metrics_json"])
    assert set(snapshot) == set(_EVALUATE_SNAPSHOT_KEYS)
    assert snapshot == {key: value for key, value in result.items() if key != "changed"}
    assert row["last_evaluated_at"] == result["evaluated_at"]
    assert result["changed"]["recommended"] is True
    assert snapshot["pending_stage"] == "apprentice", "落库快照含推荐后的最终状态（只落一次）"


def test_evaluate_task_insert_failure_leaves_no_half_pair(db, stage_gate, monkeypatch, capsys):
    """约束 5（失败分支）：建单抛异常 → 立刻清空 `pending_stage` / `pending_task_id` ——
    **不留半对**（「有 pending_stage 却查不到请示」会让老师端的 ✅ 永远点不出结果）。"""
    import agent_stage_service

    _put_raw_state_row(TEACHER, "learning")
    _seed_ready_for_recommendation()

    def boom(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(database, "insert_agent_stage_upgrade_task", boom)

    result = agent_stage_service.evaluate(TEACHER)

    row = database.get_agent_stage_state(TEACHER)
    assert (row["pending_stage"], row["pending_task_id"]) == ("", 0), "不许留半对"
    assert row["stage"] == "learning" and row["stage_source"] == "default"
    assert result["changed"] == {"stage_changed": False, "recommended": False, "demoted": False,
                                 "reason": "recommend_task_write_failed"}
    assert result["blockers"] == ["recommend_task_write_failed"]
    assert (result["pending_stage"], result["pending_task_id"]) == ("", 0)
    assert _raw_scalar("SELECT COUNT(*) FROM agent_tasks") == 0
    assert "不留半對" in capsys.readouterr().out

    # 评估本身没失败（指标照落、evaluation 照写），只是「没推荐成」
    snapshot = json.loads(row["last_metrics_json"])
    assert snapshot["blockers"] == ["recommend_task_write_failed"]
    assert [event["event_type"] for event in database.get_agent_stage_logs(TEACHER)] == ["evaluation"]
    assert database.get_agent_action_log(TEACHER) == []


# ---- 约束 8 / §6.4-29：阈值改了判定就变（无硬编码）----

def test_threshold_change_alters_decision(db, stage_gate):
    """§6.4-29：同一个老师、同一批样本 —— `min_template_match = 0.99` 不推荐，调到 `0.7`
    就推荐（判定完全跟着生效配置走；`thresholds` 回显当前值）。"""
    import agent_stage_service

    _put_raw_state_row(TEACHER, "learning")
    template_id = _publish_record_template()
    _seed_draft(_OUT_OF_ORDER_DRAFT, template_id)                       # ① = 0.6*1.0 + 0.4*0.4 = 0.76
    _seed_record(_OUT_OF_ORDER_DRAFT, _OUT_OF_ORDER_DRAFT, template_id)  # ② = 1.0

    database.upsert_agent_stage_config(TEACHER, {"min_samples": 1, "min_template_match": 0.99})
    strict = agent_stage_service.evaluate(TEACHER)

    assert strict["metrics"]["template_match"]["value"] == pytest.approx(0.76)
    assert strict["thresholds"]["min_template_match"] == 0.99
    assert strict["blockers"] == ["template_match_below_threshold"]
    assert strict["changed"]["recommended"] is False

    database.upsert_agent_stage_config(TEACHER, {"min_samples": 1, "min_template_match": 0.7})
    lenient = agent_stage_service.evaluate(TEACHER)

    assert lenient["thresholds"]["min_template_match"] == 0.7
    assert lenient["blockers"] == []
    assert lenient["changed"]["recommended"] is True


# ---- §3.8 失败方向：读不到 / 写不进去都不抛、都不改阶段 ----

def test_evaluate_store_missing_degrades_without_raising(db, stage_gate, monkeypatch, tmp_path,
                                                         capsys):
    """§3.8：状态表不可写（0003 未跑 / 库被锁）→ 不抛、不改任何阶段、留一行 `evaluation` 审计
    （`detail` 以「評估失敗」开头，运维据此定位）。

    在**副本库**上做（⑬ 组口径）：库层函数不吞 `sqlite3.Error` 时会漏掉 `conn.close()`，
    在真 test.db 上砸坏表会连累下一个用例的 `db` fixture（Windows 文件锁）。
    """
    import agent_stage_service

    _put_raw_state_row(TEACHER, "learning")
    target = _copy_tested_db(monkeypatch, tmp_path, "evaluate_store_missing.db")
    _drop_table(target, "agent_stage_state")

    result = agent_stage_service.evaluate(TEACHER)

    assert result["skipped"] is False
    assert result["reason"] == "evaluate_failed"
    assert result["blockers"] == ["evaluate_failed"]
    assert result["changed"]["stage_changed"] is False
    assert "評估流程異常" in capsys.readouterr().out
    events = database.get_agent_stage_logs(TEACHER)
    assert [event["event_type"] for event in events] == ["evaluation"]
    assert events[0]["detail"].startswith("評估失敗")


def test_evaluate_audit_table_missing_is_best_effort(db, stage_gate, monkeypatch, tmp_path, capsys):
    """审计表不可写 → 判定与指标快照照旧（§3.8：审计是旁路，不许把「评估成功」变成「评估失败」）。

    同样在**副本库**上做：读审计表抛异常时库层的连接会漏在打开的句柄里（库层既有行为）。
    """
    import agent_stage_service

    _put_raw_state_row(TEACHER, "learning")
    _publish_record_template()
    target = _copy_tested_db(monkeypatch, tmp_path, "evaluate_audit_missing.db")
    _drop_table(target, "agent_stage_log")

    result = agent_stage_service.evaluate(TEACHER)

    assert result["skipped"] is False and result["reason"] == "blocked"
    assert "寫入階段審計失敗" in capsys.readouterr().out
    snapshot = json.loads(database.get_agent_stage_state(TEACHER)["last_metrics_json"])
    assert snapshot["reason"] == "blocked"


# ---- 约束 6：stage_config_source（§3.4 第 4 条）----

def test_stage_config_source_answers_rows_and_env(db, monkeypatch):
    """约束 6：`global` / `teacher_override` = 该行是否存在；`env_override` = 能解析 +
    在白名单内 + **本次真被采纳**的键（白名单外 / 解析失败 / 总闸一律不入列）。"""
    import agent_stage_service

    _clear_stage_config_rows()
    assert agent_stage_service.stage_config_source(TEACHER) == {
        "global": False, "teacher_override": False, "env_override": []}

    database.upsert_agent_stage_config("", {"min_samples": 3})
    source = agent_stage_service.stage_config_source(TEACHER)
    assert source == {"global": True, "teacher_override": False, "env_override": []}
    assert agent_stage_service.load_stage_config(TEACHER)["min_samples"] == 3

    database.upsert_agent_stage_config(TEACHER, {"min_samples": 4})
    monkeypatch.setenv("AGENT_STAGE_MIN_TEMPLATE_MATCH", "0.9")
    monkeypatch.setenv("AGENT_STAGE_WINDOWDAYS", "7")             # typo：不在白名单
    monkeypatch.setenv("AGENT_STAGE_MAX_SAMPLES", "不是數字")      # 能看见、解析不了
    monkeypatch.setenv("AGENT_STAGE_ENABLED", "on")               # 总闸：静默跳过

    source = agent_stage_service.stage_config_source(TEACHER)
    assert source["global"] is True and source["teacher_override"] is True
    assert source["env_override"] == ["min_template_match"], "只列真正生效的 env 键"

    cfg = agent_stage_service.load_stage_config(TEACHER)
    assert cfg["min_template_match"] == 0.9, "同源：环境覆盖确实生效了"
    assert cfg["min_samples"] == 4, "老师专属行赢过全局行"
    assert cfg["window_days"] == 90, "白名单外的 typo 不得生效"


def test_stage_config_source_drops_env_when_config_falls_back(db, monkeypatch):
    """口径：合并结果非法 → 整份回落内置默认（§3.4 第 5 条）→ 那一刻 env 一个键都没被采纳
    → `env_override` 如实清空（「列出来却没生效」比不列更误导）。"""
    import agent_stage_service

    monkeypatch.setenv("AGENT_STAGE_WINDOW_DAYS", "99999")        # 越界 → 整份回落

    source = agent_stage_service.stage_config_source(TEACHER)

    assert source["env_override"] == []
    assert agent_stage_service.load_stage_config(TEACHER)["window_days"] == 90


def test_stage_config_source_shares_the_only_layer_walk():
    """约束 6「层判定与 load_stage_config 同源」的源码级守护：读取链只经
    `_resolve_stage_config()`（层判定不可能分叉），两个公开入口都经它。"""
    import inspect

    import agent_stage_service

    source = inspect.getsource(agent_stage_service)
    assert source.count("database.get_agent_stage_config_row(") == 1, \
        "配置行的读取点只许有一处（否则层判定会分叉）"
    assert source.count("def _resolve_stage_config(") == 1
    assert "_resolve_stage_config(" in inspect.getsource(agent_stage_service.load_stage_config)
    assert "_resolve_stage_config(" in inspect.getsource(agent_stage_service.stage_config_source)


# ---- 批复 C-2：库层只读统计 database.get_agent_stage_log_stats ----

def test_get_agent_stage_log_stats_counts_and_latest_moment(db):
    """契约（6 键）：`counts` 含请求过的全部事件名（没有的记 0）、`last_at` = 最新一条的时刻
    （§3.6 冷却判定用）、`since` = 时间下界、`total` = 计数和、`limit` = 行上限。"""
    database.insert_agent_stage_log(TEACHER, "permission_denied", created_at="2026-01-01T00:00:00")
    database.insert_agent_stage_log(TEACHER, "upgrade_recommended", created_at="2026-01-02T00:00:00")
    database.insert_agent_stage_log(TEACHER, "permission_denied", created_at="2026-01-03T00:00:00")
    database.insert_agent_stage_log(OTHER_TEACHER, "permission_denied",
                                    created_at="2026-01-04T00:00:00")

    stats = database.get_agent_stage_log_stats(
        TEACHER, ("permission_denied", "upgrade_declined"), "")

    assert stats == {
        "since": "",
        "counts": {"permission_denied": 2, "upgrade_declined": 0},
        "total": 2,
        "last_at": "2026-01-03T00:00:00",
        "truncated": False,
        "limit": 200,
    }

    windowed = database.get_agent_stage_log_stats(TEACHER, ("permission_denied",),
                                                 "2026-01-02T00:00:00")
    assert windowed["counts"] == {"permission_denied": 1}
    assert windowed["last_at"] == "2026-01-03T00:00:00"
    assert windowed["since"] == "2026-01-02T00:00:00"


def test_get_agent_stage_log_stats_is_read_only_and_limited(db, sql_log):
    """批复 C：**只读**（一条 SELECT、无任何写语句）+ **必带 LIMIT**（上限是内部常量 200）。"""
    database.insert_agent_stage_log(TEACHER, "evaluation", created_at="2026-01-01T00:00:00")
    marker = len(_all_calls(sql_log))

    stats = database.get_agent_stage_log_stats(TEACHER, ("evaluation",), "")

    calls = _all_calls(sql_log)[marker:]
    assert len(calls) == 1, calls
    sql, params = calls[0]
    assert sql.lstrip().upper().startswith("SELECT") and "LIMIT ?" in sql
    assert params[0] == TEACHER and params[-1] == 200
    assert stats["limit"] == 200 and stats["counts"] == {"evaluation": 1}


def test_get_agent_stage_log_stats_bad_input_is_safe(db):
    """坏入参不炸、不发无用 SQL：空老师名 → 空统计；`event_types=None` → 空 counts；
    单个字符串按「一个事件名」处理；`since` 非字符串 → 不过滤。"""
    database.insert_agent_stage_log(TEACHER, "evaluation", created_at="2026-01-01T00:00:00")

    assert database.get_agent_stage_log_stats("", ("evaluation",), "") == {
        "since": "", "counts": {"evaluation": 0}, "total": 0, "last_at": "",
        "truncated": False, "limit": 200}
    assert database.get_agent_stage_log_stats(TEACHER, None, None)["counts"] == {}
    single = database.get_agent_stage_log_stats(TEACHER, "evaluation", None)
    assert single["counts"] == {"evaluation": 1} and single["since"] == ""


# ============ ⑱ 【§4.2 改 2b / 改 3 / 施工步骤 3.4-c】三个既有链路钩子 + 唯一向上写路径 ============
#
# 本组**零接线**：库层两条链路的转发段（2.3 的 `sign_draft()`、2.4 的 `resolve_agent_task()`）已接好，
# 本组用「直接调用」+「真实转发」两条视角验证服务层三个钩子；造数 / 断言助手全部复用 ⑯⑰ 组。
#
# 钩子清单（源码级守护与「互不调用」断言共用同一份清单，避免两处漂移）：
_HOOK_NAMES = ("on_draft_signed", "apply_upgrade_confirmation", "decline_upgrade")

# 状态转移钩子返回体的**逐键**契约（13 键，形状即契约；flag off 的短路体同形）
_TRANSITION_KEYS = (
    "teacher_name", "skipped", "applied", "degraded", "reason",
    "stage", "stage_label", "previous_stage", "stage_since", "stage_source",
    "pending_stage", "pending_task_id", "task_id",
)

# 库层「状态行唯一写口」的函数名（源码级写入点归位用；库层改名 → 本组守护即红）
_STATE_ROW_WRITER = "upsert_agent_stage_state"


def _stage_write_sites():
    """【⑱ 核心守护的骨架】枚举服务层全文件的 `stage=` 关键字实参并**逐处归位**。

    返回 `(sites, state_row_sites, star_expansions)`：
      · `sites`：`[(所属函数名, 所属调用名, 行号, 值表达式 AST)]`，按行号升序 —— 即「谁写的、写给谁」；
      · `state_row_sites`：`sites` 里**真落库**的那些（所属调用 = `upsert_agent_stage_state`）；
      · `star_expansions`：状态行写入点里用了 `**` 展开的所属函数名 —— **必须为空**：`stage` 一旦
        被藏进 `**fields` 里，上面的枚举口径就不再完整，守护会**静默失效**。

    口径：只认 `ast.keyword(arg="stage")`，故 `pending_stage=` / `from_stage=` / `to_stage=` 天然不计入；
    归属映射取**最内层**函数（`ast.walk` 先父后子，后写覆盖 → 内层胜出）。
    """
    import ast
    import inspect

    import agent_stage_service

    tree = ast.parse(inspect.getsource(agent_stage_service))

    owners = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for inner in ast.walk(node):
                owners[id(inner)] = node.name

    callers = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            for keyword in node.keywords:
                callers[id(keyword)] = name

    sites, state_row_sites, star = [], [], []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            if name == _STATE_ROW_WRITER and any(kw.arg is None for kw in node.keywords):
                star.append(owners.get(id(node), ""))
        if isinstance(node, ast.keyword) and node.arg == "stage":
            site = (owners.get(id(node), ""), callers.get(id(node), ""), node.lineno, node.value)
            sites.append(site)
            if site[1] == _STATE_ROW_WRITER:
                state_row_sites.append(site)
    sites.sort(key=lambda site: site[2])
    return sites, state_row_sites, star


# ---- 交付面：钩子存在 + 签名（库层按位置传参）+ flag off 零 SQL 零写入 ----

def test_stage_hooks_exist_with_the_contract_signatures():
    """【3.4-c 交付面】三个钩子必须是**模块级可调用**，且签名与 CTO 指定的调用形状逐参一致。

    库层转发段（2.3 / 2.4 已接线）按**位置**传参：改参数名/加必填位 = 静默断链，故逐个钉死。
    """
    import inspect

    import agent_stage_service

    expected = {
        "on_draft_signed": ("teacher_name",),
        "apply_upgrade_confirmation": ("teacher_name", "to_stage", "task_id"),
        "decline_upgrade": ("teacher_name", "task_id"),
    }
    for name in _HOOK_NAMES:
        hook = getattr(agent_stage_service, name, None)
        assert callable(hook), "%s 必须存在（库层转发段已在调它）" % name
        parameters = list(inspect.signature(hook).parameters.values())
        assert tuple(p.name for p in parameters) == expected[name], name
        assert all(p.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
                   and p.default is inspect.Parameter.empty for p in parameters), name


def test_all_three_stage_hooks_flag_off_are_zero_sql_and_zero_writes(db, sql_log, monkeypatch, capsys):
    """【3.4-c 约束 2 / 4 + §5.1 红线①】flag off：三个钩子各自**零 SQL、零写入**、返回短路体。

    「零写入」含**状态行都不许建**（`_ensure_state_row` 那条路径也进不去）—— 开关关了，新表
    不许再长一行（这是 3.4-b 已定的红线①，本步把三个新入口一并钉在同一坐标上）。
    """
    import agent_stage_service

    monkeypatch.delenv("AGENT_STAGE_ENABLED", raising=False)
    before = _table_counts()
    marker = len(_all_calls(sql_log))

    draft_result = agent_stage_service.on_draft_signed(TEACHER)
    apply_result = agent_stage_service.apply_upgrade_confirmation(TEACHER, "apprentice", 7)
    decline_result = agent_stage_service.decline_upgrade(TEACHER, 7)

    assert _all_calls(sql_log)[marker:] == [], "flag off 下三个钩子连一次 SELECT 都不许发"
    assert _table_counts() == before, "flag off 必须零写入"
    assert database.get_agent_stage_state(TEACHER) is None, "连状态行都不许建"

    assert draft_result["skipped"] is True and draft_result["reason"] == "agent_stage_disabled"
    assert set(draft_result) == set(_EVALUATE_SNAPSHOT_KEYS) | {"changed"}, \
        "签字钩子是评估的薄封装 → 返回体就是评估契约（18 键 + changed）"

    for result in (apply_result, decline_result):
        assert set(result) == set(_TRANSITION_KEYS)
        assert (result["skipped"], result["applied"], result["degraded"]) == (True, False, False)
        assert result["reason"] == "agent_stage_disabled"
        assert (result["stage"], result["stage_since"], result["stage_source"]) == ("", "", "")
        assert result["task_id"] == 7
    assert "未啟用" in capsys.readouterr().out, "短路必须留一条繁体告警（可观测）"


def test_hooks_present_with_flag_off_keep_both_forwarders_zero_stage_sql(db, task_sql_log, monkeypatch):
    """【3.4-c 约束 2 + 要求 3 的「钩子真实存在」形态】flag off：两条既有链路跑完，
    **一条碰阶段三表的语句都没有**，任务状态与返回值照旧。

    ⑪ / ⑫ 组用「改动前实测基线」逐字节钉住整条语句序列；本条补的是**阶段表视角** —— 钩子从
    「不存在」变成「存在」，转发段照样发零条阶段 SQL（闸门在服务层首行，不在转发段）。
    """
    monkeypatch.delenv("AGENT_STAGE_ENABLED", raising=False)
    draft_id = _sign_fixture_draft(db)
    task_id = _seed_agent_task(_TASK_UPGRADE, _TITLE_UPGRADE)
    before = _table_counts()
    task_sql_log.clear()

    assert db.sign_draft(draft_id, "最终方案") == "张三"
    assert db.resolve_agent_task(task_id, "approved") == {"message": "已处理", "status": "approved"}

    touched = [sql for sql, _params in _all_calls(task_sql_log) if "agent_stage" in sql]
    assert touched == [], "flag off 下不得有任何一条语句碰阶段三表（实测 %r）" % touched
    assert _table_counts()["agent_stage_state"] == before["agent_stage_state"], \
        "flag off 下阶段状态表一行都不许长（迁移给存量老师的那 1 行是基线）"
    assert _table_counts()["agent_stage_log"] == before["agent_stage_log"] == 0, "审计表零写入"
    assert database.get_agent_stage_state(TEACHER) is None
    assert database.find_pending_upgrade_task(TEACHER) is None


# ---- 约束 1：唯一向上写路径（源码级：写入点枚举 + 逐处归位 + rank 增加点计数 = 1）----

def test_only_upward_stage_write_path_is_teacher_confirmation():
    """【3.4-c 约束 1 · 源码级守护】全文件 `stage=` 写入点枚举 + 逐处归位 + **rank 增加点计数 = 1**。

    枚举口径（两条形状都枚举，漏一种守护就有缝）：
      ① `<调用>(..., stage=…)` 关键字实参 —— 逐处归位到「所属函数 + 所属调用」；
      ② 状态行写入函数的 `**` 展开形状 —— **出现即红**（`stage` 可能被藏在展开里，枚举就不再完整）。
    `pending_stage=` / `from_stage=` / `to_stage=` 是别的形参名，AST 精确匹配天然不计入。

    4a 落地后的定态（**五处 `stage=` 实参 / 三处状态行写入 / 一处 rank 增加 / 一处 rank 减少**；
    构成 = 零 delta upsert + 向上 upsert + 向上回显 + 向下 upsert + 向下回显 = 3 处落库 + 2 处回显）：
      · `_ensure_state_row()` 的零 delta 写入（值恒为 `view["stage"]` → 不改变 rank）；
      · `apply_upgrade_confirmation()` 的状态行写入（**唯一 rank +1**，值恒为钩子入参 `to_stage`）；
      · 同一钩子把结果装配进返回体时对 `_transition_result()` 的 `stage=` 回显（**不落库**）；
      · `_demote()` 的状态行写入（**唯一 rank −1**，值 = 现场校验后的落点变量 `target`）。
      · 同一降级函数把结果装配进返回体时对 `_transition_result()` 的 `stage=` 回显（**不落库**）
        —— CTO 裁决：`apply_upgrade_confirmation()` 与 `_demote()` 是对称操作，写法必须一致。
    为什么钉「写入点」而不是直接钉「向上 / 向下」：rank 变化是**运行时**属性，源码级只能钉「值从哪来」
    + 「属于哪个函数」；向上那处的值恒为 `to_stage`、向下那处的值恒为 `target` 且只在「严格低于当前」
    的校验**之后**才可达 —— 两句分别由 `test_apply_upgrade_confirmation_rejects_cross_level_targets`
    与 ⑲ 组的 `test_demote_never_raises_stage_rank`（行为级）补全。
    """
    import ast
    import inspect

    import agent_stage_service

    sites, state_row_sites, star = _stage_write_sites()

    assert sites, "枚举必须能抓到写入点（守护自身不许静默失效）"
    assert star == [], "状态行写入点不得用 ** 展开（实测 %r）：stage 藏进展开里枚举就漏了" % star
    assert [(s[0], s[1]) for s in sites] == [
        ("_ensure_state_row", _STATE_ROW_WRITER),
        ("apply_upgrade_confirmation", _STATE_ROW_WRITER),
        ("apply_upgrade_confirmation", "_transition_result"),
        ("_demote", _STATE_ROW_WRITER),
        ("_demote", "_transition_result"),
    ], "stage= 写入点清单变了（实测 %r）—— 多一处就说明「唯一向上 / 向下写路径」被绕开" % [
        (s[0], s[1], s[2]) for s in sites]

    assert len(state_row_sites) == 3 and len(sites) == 5
    # 方向按**所属函数**归属（rank 增减是运行时属性）：向上点恰好 1 个（老师确认）、向下点恰好 1 个
    by_owner = {}
    for site in state_row_sites:
        by_owner.setdefault(site[0], []).append(site)
    assert sorted(by_owner) == ["_demote", "_ensure_state_row", "apply_upgrade_confirmation"], \
        "落库写入点的所属函数清单变了（实测 %r）" % sorted(by_owner)
    increasing = by_owner["apply_upgrade_confirmation"]
    decreasing = by_owner["_demote"]
    assert len(increasing) == 1 and len(decreasing) == 1, \
        "向上 / 向下各**恰好 1 个**落库点（实测 向上 %d 个 / 向下 %d 个）" % (
            len(increasing), len(decreasing))

    # 返回体回显恰好 2 处（向上 / 向下各一），且**回显的值必须与同一函数的落库写入点是同一个变量**
    # —— CTO 裁决「`apply_upgrade_confirmation` 与 `_demote` 是对称操作，写法必须一致」的源码级形态
    echoes = {site[0]: site for site in sites if site[1] != _STATE_ROW_WRITER}
    assert sorted(echoes) == ["_demote", "apply_upgrade_confirmation"], \
        "返回体回显必须恰好 2 处（向上 / 向下各一），实测 %r" % sorted(echoes)
    for owner, echo in echoes.items():
        assert ast.dump(echo[3]) == ast.dump(by_owner[owner][0][3]), \
            "%s：回显的值必须与同函数的落库写入点同一个变量（禁止另起一份表达式）" % owner

    zero_delta = by_owner["_ensure_state_row"][0]
    assert ast.dump(zero_delta[3]) == ast.dump(ast.parse('view["stage"]', mode="eval").body), \
        "零 delta 写入的值必须是「评估前读到的阶段」本身"
    assert ast.dump(increasing[0][3]) == ast.dump(ast.parse("to_stage", mode="eval").body), \
        "唯一向上写路径的值必须是钩子入参 to_stage（不是字面量、也不是别处的行值）"
    assert ast.dump(decreasing[0][3]) == ast.dump(ast.parse("target", mode="eval").body), \
        "唯一向下写路径的值必须是降级函数体内的落点变量 target（手动 = 入参 to_stage、规则 = 规则落点）"

    # `target` 的赋值来源只有 §1.6 / §3.7 的三条（多一条 = 「向下写」不再收敛）；方向的**现成校验**
    # （必须严格低于当前阶段）属行为级，见 ⑲ 组。源码级只钉形态，不改这三行的语义。
    assigned = [line.strip() for line in inspect.getsource(agent_stage_service._demote).splitlines()
                if line.strip().startswith("target = ")]
    assert assigned == ["target = to_stage", "target = _CONSERVATIVE_STAGE",
                        "target = STAGES[max(current_rank - 1, 0)]"], \
        "落点变量的赋值来源只有三条（手动 / 规则重置 / 规则降级），实测 %r" % assigned

    # 逐处按行号归位：行号必须落在「所属函数」的源码区间内，且所属调用名必须非空
    for owner, called, lineno, _value in sites:
        lines, start = inspect.getsourcelines(getattr(agent_stage_service, owner))
        assert lineno in range(start, start + len(lines)), (owner, lineno)
        assert called, (owner, lineno)


def test_three_stage_hooks_never_call_each_other():
    """【3.4-c 约束 5】三个钩子**互不调用、无环**：任一钩子体内不得出现另一个钩子的**调用**。

    为什么重要：钩子互调会让一次老师点击产生两条链路（签字顺带评估、确认又顺带评估…），
    「谁负责升阶」「写了几次」立刻含糊。故源码级钉住。
    """
    import ast
    import inspect

    import agent_stage_service

    for name in _HOOK_NAMES:
        body = ast.parse(inspect.getsource(getattr(agent_stage_service, name)))
        called = {
            (node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", ""))
            for node in ast.walk(body) if isinstance(node, ast.Call)
        }
        assert name not in called, "%s 不得自我调用" % name
        assert called.isdisjoint(set(_HOOK_NAMES)), \
            "%s 体内调了另一个钩子 %r —— 钩子互调 = 一次点击两条链路" % (
                name, sorted(called & set(_HOOK_NAMES)))


def test_stage_hook_gate_placement_is_single_and_first_line():
    """【3.4-c 约束 4】闸门位置：`on_draft_signed` **不判 flag**（总闸只许一份，在评估入口首行）；
    另两个钩子**首行就是闸门**，且闸门不通过时**立即 `return`**（这是「零 SQL」的源码级形态）。"""
    import ast
    import inspect

    import agent_stage_service

    def _body(name):
        tree = ast.parse(inspect.getsource(getattr(agent_stage_service, name)))
        function = tree.body[0]
        statements = [s for s in function.body
                      if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant)
                              and isinstance(s.value.value, str))]
        return function, statements

    # ① 薄封装：体内**没有** flag 标识符，且只有一次评估调用
    function, statements = _body("on_draft_signed")
    assert "agent_stage_enabled" not in ast.dump(function), \
        "薄封装不得自判 flag（flag 判定只许一份：评估入口的第一条语句）"
    called = [node.func.id for node in ast.walk(function)
              if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)]
    assert called.count("evaluate") == 1, "薄封装只转调一次评估（实测 %r）" % called
    assert set(called) <= {"evaluate", "_config_warn"}, "薄封装不得调别的东西（实测 %r）" % called
    assert len(statements) == 1 and isinstance(statements[0], ast.Try), \
        "薄封装体 = 一个 try（转调 + 第二道保险），不得长出别的语句"

    # ② 另两个钩子：**第一条 `if` 就是总闸**且不通过时立即 return；它前面只许有「无害赋值」
    #    （`name = teacher_name or ""` 这类：体内没有任何函数调用 → 不可能发 SQL）
    for name in ("apply_upgrade_confirmation", "decline_upgrade"):
        _function, statements = _body(name)
        first_if = next(s for s in statements if isinstance(s, ast.If))
        assert "agent_stage_enabled" in ast.dump(first_if.test), \
            "%s 的第一条 if 必须是总闸（它不经过评估入口，须自判 flag）" % name
        assert any(isinstance(s, ast.Return) for s in first_if.body), \
            "%s 闸门不通过必须立即返回（零 SQL）" % name
        for leading in statements[:statements.index(first_if)]:
            assert isinstance(leading, ast.Assign) and not any(
                isinstance(node, ast.Call) for node in ast.walk(leading)), \
                "%s 闸门前只许有无害赋值（出现调用就可能先发 SQL）" % name


# ---- 约束 1 行为级 + 约束 2：升阶生效；越级 / 向下 / 非法目标一律拒绝且阶段不动 ----

def test_apply_upgrade_confirmation_upgrades_exactly_one_level_with_audit(db, stage_gate):
    """老师点 ✅：**单级**升阶（`learning` → `apprentice`）→ 状态行写全（阶段真值 + 进入时刻 +
    来源 `teacher_confirm` + 清待确认对），并留两行留痕（`stage_upgraded` 事件 + `confirm_upgrade` 行动）。"""
    import agent_stage_service

    _put_raw_state_row(TEACHER, "learning", pending_stage="apprentice", pending_task_id=12)
    before = database.get_agent_stage_state(TEACHER)

    result = agent_stage_service.apply_upgrade_confirmation(TEACHER, "apprentice", 12)

    assert set(result) == set(_TRANSITION_KEYS)
    assert (result["skipped"], result["applied"], result["degraded"]) == (False, True, False)
    assert result["reason"] == "stage_upgraded"
    assert result["stage"] == "apprentice" and result["previous_stage"] == "learning"
    assert result["stage_label"] == agent_stage_service.STAGE_LABELS["apprentice"]
    assert result["stage_source"] == "teacher_confirm" and result["task_id"] == 12
    assert (result["pending_stage"], result["pending_task_id"]) == ("", 0)

    row = database.get_agent_stage_state(TEACHER)
    assert (row["stage"], row["stage_source"]) == ("apprentice", "teacher_confirm")
    assert row["stage_since"] == result["stage_since"] != before["stage_since"], \
        "升阶必须刷新进入时刻（新阶段的 `stage_since` 基准）"
    assert (row["pending_stage"], row["pending_task_id"]) == ("", 0), "升阶后不得残留「⏳ 待確認」"

    logs = database.get_agent_stage_logs(TEACHER)
    assert [log["event_type"] for log in logs] == ["stage_upgraded"], "变更类事件只此一行"
    assert (logs[0]["from_stage"], logs[0]["to_stage"]) == ("learning", "apprentice"), \
        "§1.3：变更类事件 from_stage / to_stage 都必填"
    assert logs[0]["task_id"] == 12 and "見習期" in logs[0]["detail"]

    actions = database.get_agent_action_log(TEACHER)
    assert [action["action"] for action in actions] == ["confirm_upgrade"]
    assert actions[0]["task_id"] == 12


@pytest.mark.parametrize("to_stage, expected_detail", [
    ("assistant", "越級請求被拒：to_stage=assistant, current=learning"),   # 跳级（rank +2）
    ("observation", "降級請求被拒"),                                      # 向下（误走升级钩子）
    (None, "目標階段非法"),                                               # 缺 to
    ("", "目標階段非法"),                                                 # 空串
    ("vip", "目標階段非法"),                                              # 五阶段白名单外
])
def test_apply_upgrade_confirmation_rejects_cross_level_targets(db, stage_gate, to_stage, expected_detail):
    """【3.4-c 约束 2】目标 ≠ 「当前 + 1」→ **拒绝且阶段一个字不动**（含阶段起始时刻与来源）。

    跳级 / 向下 / 非法目标**都不新造第 11 类事件**、也**不用** `permission_denied`（那条的语义是
    「智能体越权被拦」，§2.4），统一用既有 `upgrade_declined`；跳级 detail 是 CTO 指定的字面形态。
    顺手清掉待确认对：`to_stage ≠ 下一阶段` 的请示**永远无法**被满足，留着会挡住后续推荐、老师端
    还永远显示「⏳ 待你確認」。
    """
    import agent_stage_service

    _put_raw_state_row(TEACHER, "learning", stage_since="S1", stage_source="default",
                       pending_stage="apprentice", pending_task_id=12)

    result = agent_stage_service.apply_upgrade_confirmation(TEACHER, to_stage, 12)

    assert set(result) == set(_TRANSITION_KEYS)
    assert (result["applied"], result["skipped"]) == (False, False)
    assert result["reason"] == "stage_transition_invalid"
    assert result["previous_stage"] == "learning" and result["stage"] == "learning"

    row = database.get_agent_stage_state(TEACHER)
    assert (row["stage"], row["stage_since"], row["stage_source"]) == ("learning", "S1", "default")
    assert (row["pending_stage"], row["pending_task_id"]) == ("", 0)
    assert database.find_pending_upgrade_task(TEACHER) is None

    logs = database.get_agent_stage_logs(TEACHER)
    assert [log["event_type"] for log in logs] == ["upgrade_declined"], \
        "不新造第 11 类事件、不用 permission_denied"
    assert expected_detail in logs[0]["detail"]
    assert (logs[0]["from_stage"], logs[0]["to_stage"]) == ("learning", ""), \
        "§1.3：被拒不是阶段变更 → to_stage 留空（目标写在 detail 里）"
    assert logs[0]["task_id"] == 12
    assert [action["action"] for action in database.get_agent_action_log(TEACHER)] == ["decline_upgrade"]


def test_apply_upgrade_confirmation_is_idempotent_when_already_at_target(db, stage_gate):
    """【3.4-c 约束 3】已在目标阶段（老师重复点 ✅）→ 幂等 no-op：`stage` / `stage_since` /
    `stage_source` **逐字节不变**、不写第二条 `stage_upgraded`（否则阶段审计无法区分「真升了两次」与
    「老师点了两次」）；只清残留待确认对 + 一行写明「無需變更」的行动日志（§1.1）。"""
    import agent_stage_service

    _put_raw_state_row(TEACHER, "apprentice", stage_since="S9", stage_source="teacher_confirm",
                       pending_stage="assistant", pending_task_id=99)
    before = database.get_agent_stage_state(TEACHER)

    result = agent_stage_service.apply_upgrade_confirmation(TEACHER, "apprentice", 99)

    assert set(result) == set(_TRANSITION_KEYS)
    assert (result["applied"], result["reason"]) == (False, "already_at_stage")
    assert (result["previous_stage"], result["stage"]) == ("apprentice", "apprentice")

    row = database.get_agent_stage_state(TEACHER)
    assert (row["stage"], row["stage_since"], row["stage_source"]) == \
        (before["stage"], before["stage_since"], before["stage_source"]) == \
        ("apprentice", "S9", "teacher_confirm")
    assert (row["pending_stage"], row["pending_task_id"]) == ("", 0), "残留的旧待确认对必须清掉"
    assert database.get_agent_stage_logs(TEACHER) == [], "不得写第二条变更类事件"

    actions = database.get_agent_action_log(TEACHER)
    assert [action["action"] for action in actions] == ["confirm_upgrade"]
    assert "無需變更" in actions[0]["detail"] and actions[0]["task_id"] == 99


# ---- 失败方向（§1.5 / §3.8）+ ❌ 忽略推荐（含 3.4-b 口径 F 的冷却端到端）----

def test_apply_upgrade_confirmation_fail_closed_when_stage_read_degraded(db, stage_gate,
                                                                        monkeypatch, capsys):
    """读不到阶段真值（库坏 / 表未就位）→ **绝不升阶**（fail-closed）：`degraded=True` +
    `stage_read_degraded`，且**零写入**（连审计都不写：读不到真值就根本无从记起「谁被升到哪」）。

    与 §1.5 的关键区分：「读不到」≠「当前是兜底阶段」—— 后者可以零 delta 落一行，前者一个字节都不许动。
    """
    import sqlite3 as _sqlite3

    import agent_stage_service

    _put_raw_state_row(TEACHER, "learning")
    before = _table_counts()

    def boom(teacher_name):
        raise _sqlite3.OperationalError("no such table: agent_stage_state")

    monkeypatch.setattr(database, "get_agent_stage_state", boom)

    result = agent_stage_service.apply_upgrade_confirmation(TEACHER, "apprentice", 12)

    assert set(result) == set(_TRANSITION_KEYS)
    assert (result["degraded"], result["skipped"], result["applied"]) == (True, False, False)
    assert result["reason"] == "stage_read_degraded"
    assert result["stage"] == "learning", "回显配置链的兜底阶段（如实回显，不编造、不改动）"
    assert _table_counts() == before, "读不到真值 → 零写入（不改阶段、不写审计）"
    assert "讀不到階段真值" in capsys.readouterr().out, "降级必须留繁体告警"


def test_decline_upgrade_clears_pending_and_feeds_the_34b_cooldown(db, stage_gate):
    """❌ 端到端（**真实转发段** + 3.4-b 口径 F 的冷却链路）：真实推荐 → 老师点 ❌ → 待确认对摘掉 +
    阶段不动 + 紧接着的 `evaluate()` 被 `cooldown_active` 拦住。

    冷却**不新增字段**（§1.2 的状态行没有冷却列）：冷却 = 审计里最新一条 `upgrade_recommended` /
    `upgrade_declined` 的时刻 + `recommend_cooldown_hours`（3.4-b 的 `_cooldown_blocks()` 唯一读法）
    —— 本钩子写下的这一行 `upgrade_declined` 就是冷却起点。
    注：`agent_tasks` 那一行由库层 `resolve_agent_task()` 先落定（2.4 已接线的决策），本钩子只管
    阶段状态与审计（约束 6 的写点克制）。
    """
    import agent_stage_service

    _put_raw_state_row(TEACHER, "learning")
    _seed_ready_for_recommendation()

    recommended = agent_stage_service.evaluate(TEACHER)
    assert recommended["changed"]["recommended"] is True
    task_id = recommended["pending_task_id"]
    assert task_id and database.get_agent_stage_state(TEACHER)["pending_stage"] == "apprentice"

    # 老师点 ❌：库层先落定决策（`status='rejected'` + 行动日志，已 commit）→ best-effort 转发本钩子
    assert db.resolve_agent_task(task_id, "rejected") == {"message": "已处理", "status": "rejected"}

    row = database.get_agent_stage_state(TEACHER)
    assert row["stage"] == "learning", "拒绝绝不改阶段（也不降级）"
    assert (row["pending_stage"], row["pending_task_id"]) == ("", 0), "老师已明确忽略 → 摘掉「⏳ 待確認」"
    assert database.find_pending_upgrade_task(TEACHER) is None, "请示已落定（那行任务归 2.4 管）"

    # 下面两行留痕**只可能**来自服务层钩子 → 它们出现即证明转发链路真的跑通了
    logs = database.get_agent_stage_logs(TEACHER)
    # 倒序读（`created_at DESC`，同刻按 id DESC）：写入顺序是 推荐 → 评估快照 → ❌，倒序读正好反过来
    assert [log["event_type"] for log in logs[:3]] == \
        ["upgrade_declined", "evaluation", "upgrade_recommended"]
    assert logs[0]["task_id"] == task_id and "冷卻" in logs[0]["detail"]
    assert [action["action"] for action in database.get_agent_action_log(TEACHER)] == \
        ["decline_upgrade", "reject", "recommend_upgrade"]

    after = agent_stage_service.evaluate(TEACHER)

    assert after["changed"]["recommended"] is False
    assert after["blockers"] == ["cooldown_active"], \
        "刚被拒 → 24h 冷却期内不再推荐（口径 F：被拒的那一行就是冷却起点）"
    assert (after["pending_stage"], after["pending_task_id"]) == ("", 0)
    assert database.get_agent_stage_state(TEACHER)["stage"] == "learning", "评估链也绝不升阶"


def test_decline_upgrade_is_repeatable_and_never_touches_stage(db, stage_gate):
    """❌ 幂等：重复点（同一条已处理的请示再点一次）→ 阶段三元组**逐字节不变**、审计只增一行
    （每次点击如实留一行），绝不产生 `stage_upgraded`。"""
    import agent_stage_service

    _put_raw_state_row(TEACHER, "learning", stage_since="S7", stage_source="default",
                       pending_stage="apprentice", pending_task_id=12)

    first = agent_stage_service.decline_upgrade(TEACHER, 12)
    second = agent_stage_service.decline_upgrade(TEACHER, 12)

    assert first["reason"] == second["reason"] == "upgrade_declined"
    assert (first["applied"], first["skipped"]) == (second["applied"], second["skipped"]) == (False, False)

    row = database.get_agent_stage_state(TEACHER)
    assert (row["stage"], row["stage_since"], row["stage_source"]) == ("learning", "S7", "default")
    assert (row["pending_stage"], row["pending_task_id"]) == ("", 0)
    assert [log["event_type"] for log in database.get_agent_stage_logs(TEACHER)] == \
        ["upgrade_declined", "upgrade_declined"], "审计只增、每次点击一行"
    assert [action["action"] for action in database.get_agent_action_log(TEACHER)] == \
        ["decline_upgrade", "decline_upgrade"]


# ---- 端到端（真实转发段）+ 永不抛 / 形状恒同形 + 行为级「只有确认路径动 stage」----

def test_on_draft_signed_end_to_end_recommends_without_upgrading(db, stage_gate):
    """§4.2 改 2b 端到端：真实 `sign_draft()` → 库层转发段 → `on_draft_signed` → 一次评估。

    新病历 = 新样本（这正是「签字后再评估」的理由）→ 满分样本下**推荐**升级（待确认对 + 请示 + 事件）；
    但阶段**一个字节都不动** —— 升阶只能由老师点 ✅ 走 `apply_upgrade_confirmation`（约束 1）。
    """
    import agent_stage_service

    _put_raw_state_row(TEACHER, "learning", stage_since="S1", stage_source="default")
    template_id, _draft_id, _record_id = _seed_ready_for_recommendation()
    draft_id = _seed_draft(_PERFECT_DRAFT, template_id)      # 待签字草案（第 2 个触发点）

    assert db.sign_draft(draft_id, _PERFECT_DRAFT) == "张三"

    row = database.get_agent_stage_state(TEACHER)
    assert (row["stage"], row["stage_since"], row["stage_source"]) == ("learning", "S1", "default"), \
        "评估绝不升阶（钩子只转调评估）"
    assert row["pending_stage"] == "apprentice" and row["pending_task_id"] > 0, "推荐写成待确认对"
    assert row["last_evaluated_at"], "评估把「评估时刻」写进状态行（同一位老师，参数透传）"
    assert database.find_pending_upgrade_task(TEACHER) is not None, "推荐建了请示单"

    # 倒序读：写入顺序是 推荐（建单留痕）→ 评估快照留痕，故倒序读 = 快照在前
    assert [log["event_type"] for log in database.get_agent_stage_logs(TEACHER)] == \
        ["evaluation", "upgrade_recommended"], "推荐 + 评估各留一行（倒序读）"
    assert [action["action"] for action in database.get_agent_action_log(TEACHER)] == ["recommend_upgrade"]


def test_stage_hooks_never_raise_and_keep_uniform_shape(db, stage_gate, monkeypatch):
    """无效调用 / 缺 `to` / 库坏 都**不抛**，且返回体恒同形（前端不必写第二套渲染）。

    尤其「库坏了」：老师这次点击照样进审计（限制方向的留痕不能丢），但读降级**如实**报出去
    （`degraded=True`）—— 调用方不得把它当「已落库的结果」。
    """
    import sqlite3 as _sqlite3

    import agent_stage_service

    _put_raw_state_row(TEACHER, "learning", stage_since="S1", pending_stage="apprentice",
                       pending_task_id=7)

    empty_apply = agent_stage_service.apply_upgrade_confirmation("", "apprentice", 7)
    empty_decline = agent_stage_service.decline_upgrade("", 7)
    assert empty_apply["reason"] == empty_decline["reason"] == "teacher_required"
    assert set(empty_apply) == set(empty_decline) == set(_TRANSITION_KEYS)

    illegal = agent_stage_service.apply_upgrade_confirmation(TEACHER, None, None)
    assert illegal["reason"] == "stage_transition_invalid" and illegal["task_id"] == 0

    def boom(teacher_name):
        raise _sqlite3.OperationalError("庫壞了")

    monkeypatch.setattr(database, "get_agent_stage_state", boom)
    broken = agent_stage_service.decline_upgrade(TEACHER, 7)

    assert set(broken) == set(_TRANSITION_KEYS)
    assert broken["reason"] == "upgrade_declined" and broken["degraded"] is True
    assert broken["stage"] == "learning", "回显兜底阶段（读不到真值就如实报 degraded=True）"
    assert (broken["pending_stage"], broken["pending_task_id"]) == ("", 0)


def test_only_confirmation_path_changes_the_stage_triple(db, stage_gate):
    """行为级配对（与源码级守护同口径）：`evaluate`（含签字钩子转调）与 `decline_upgrade` 跑完，
    `stage` / `stage_since` / `stage_source` **逐字节不变**；同一行的老师点 ✅ 才变。"""
    import agent_stage_service

    _put_raw_state_row(TEACHER, "learning", stage_since="S1", stage_source="default",
                       pending_stage="apprentice", pending_task_id=12)
    _seed_ready_for_recommendation()

    agent_stage_service.on_draft_signed(TEACHER)          # 有待确认对 → 本轮只挡不写（`upgrade_pending`）
    agent_stage_service.decline_upgrade(TEACHER, 12)

    row = database.get_agent_stage_state(TEACHER)
    assert (row["stage"], row["stage_since"], row["stage_source"]) == ("learning", "S1", "default")
    assert (row["pending_stage"], row["pending_task_id"]) == ("", 0)

    agent_stage_service.apply_upgrade_confirmation(TEACHER, "apprentice", 12)

    row = database.get_agent_stage_state(TEACHER)
    assert (row["stage"], row["stage_source"]) == ("apprentice", "teacher_confirm")
    assert row["stage_since"] != "S1", "确认路径是**唯一**动这三列的地方"


# ===========================================================================
# ⑳ 【施工步骤 4b-2】接口层：#1–#5 五个 endpoint（§4.6 表格逐行 + §4.5-② 的顺序纪律）
#
# 本组的边界（⑲ 组留给 4a 服务层三件套 `stage_view` / `demote` / `save_stage_config` 的专门用例，
# 故接口层这组编号顺延到 ⑳）：
#   ① 五条路由的**顺序纪律**：`_guard()`（flag → 404 / 存储未就绪 → 503）**先于** `_check_identity()`
#      （缺栏位 400 / 名字与 ID 不一致 403）—— 文件头第 23–26 行那条「顺序不可颠倒」的行为级守护；
#   ② 逐条对齐 §4.6 的「出参（要点）」列：#1 直出 15 键、#2 直出 18 键 + `changed`、#3 三键、
#      #4 三键（`{effective, source, warnings}`）、#5 四键（`{stage, previous_stage, stage_since, stage_source}`）；
#   ③ 只读接口**零写入**（#1 / #3 各连发十次：五张表行数不变、审计表零增量）；
#   ④ 写接口的**失败语义**：#4 校验未过 → 400 + `errors[].path` + **旧值不变**（只拦不清、整体不写入）；
#      #5 同阶 / 向上 → 409、非法值 → 400，两种都「阶段一字不动、审计一行不写」；
#   ⑤ #6 `suggest` / #7 `predraft` **本步不注册**：路由表里没有它们，请求落 FastAPI 默认 404
#      （`agent_stage_api.py` 那句「假实现比 404 更糟」的行为级守护；4c 落地时本组要改成
#      403 `stage_forbidden` / 404 `stage_draft_not_found` 那一族）；
#   ⑥ 源码级：接口层不 import `database` / `sqlite3`、不碰 §2.1 六个禁忌符号（接口层文件头的承诺）。
# 本组**不改** ⑬–⑱ 组一行：造数 / 断言助手全部复用现有实现（`_raw_scalar` / `_put_raw_state_row` /
# `_table_counts` / `database.get_agent_stage_state` / `database.get_agent_stage_logs` /
# `database.get_agent_action_log` / `_EVALUATE_SNAPSHOT_KEYS` / `_GATE_CAPS` / `_GATE_GRID`）。
# 接口层用例一律走 `conftest.client`（真实 HTTP，含 4b-1 在 `main.py` 注册的 `AgentStageError` 处理器）。
# ===========================================================================

# 五条已注册路由的 (方法, 路径)——「flag off 全部 404」与「路由表恰好这些」共用同一份清单，避免两处漂移
_STAGE_ROUTE_TABLE = (
    ("get", "/api/agent/stage"),
    ("post", "/api/agent/stage/evaluate"),
    ("get", "/api/agent/stage/config"),
    ("put", "/api/agent/stage/config"),
    ("post", "/api/agent/stage/demote"),
)

# 本步**已注册**的 (方法, 路径) 集合（#1–#5）；#6 `suggest` / #7 `predraft` 不在其中（见组头 ⑤）
_STAGE_REGISTERED_ROUTES = {
    ("GET", "/api/agent/stage"),
    ("POST", "/api/agent/stage/evaluate"),
    ("GET", "/api/agent/stage/config"),
    ("PUT", "/api/agent/stage/config"),
    ("POST", "/api/agent/stage/demote"),
}

# §4.6-①「出参（要点）」列的**逐键转写**（服务层契约是 15 键；`stage_view()` 的 docstring 同列，
# 刻意不从返回值反推键集：键集漂移时必须红）
_STAGE_VIEW_KEYS = (
    "teacher_name", "stage", "stage_label", "stage_since", "stage_source", "pending_stage",
    "pending_task_id", "capabilities", "metrics", "thresholds", "next_stage", "blockers",
    "config_source", "stale", "degraded",
)

# §2.3 表格 learning 那一行的逐格字面量（复用 ⑮ 组的 `_GATE_CAPS` / `_GATE_GRID` 表，不另抄一份）
_LEARNING_CAPABILITIES = {cap: cell for cap, cell in zip(_GATE_CAPS, _GATE_GRID["learning"])}

# §3.1 三个指标键（`metrics` 一节的键集；③ `inquiry_preference_consistency` 是占位键）
_METRIC_KEYS = ("template_match", "modification_consistency", "inquiry_preference_consistency")


def _auth(teacher=TEACHER):
    """双栏位鉴权（§4.6 全表入参都是 `teacher_name` + `teacher_id` 成对，且必须是同一个人）。"""
    return {"teacher_name": teacher, "teacher_id": teacher}


def _api_source():
    """接口层源码（源码级守护用；路径由 `database.__file__` 反推，不硬编码盘符）。"""
    path = os.path.join(os.path.dirname(os.path.abspath(database.__file__)), "agent_stage_api.py")
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _api_detail(response):
    """统一错误体的四键 `{error, msg, errors, warnings}`（§0.3 惯例：真 HTTP 状态码 + 统一错误体）。"""
    return response.json()["detail"]


def _stage_log_events(teacher=TEACHER):
    """该老师的审计事件类型（⑮ 组的读法；`id` 倒序，单条断言时只看内容）。"""
    return [row["event_type"] for row in database.get_agent_stage_logs(teacher)]


def _stage_actions(teacher=TEACHER):
    """该老师的行动日志 `action` 列（工作台「📜 行動日誌」的数据源）。"""
    return [row["action"] for row in database.get_agent_action_log(teacher)]


# ---- ② 顺序纪律：flag → 存储 → 鉴权 ----

def test_api_flag_off_all_five_routes_404_agent_stage_disabled(client, monkeypatch):
    """§5.1 红线① / §7.1-⑫：flag off → 五条路由**全部** 404 `agent_stage_disabled`（统一错误体），
    且**先于**鉴权 —— 缺栏位 / 名字与 ID 不一致的请求同样是 404，不是 400 / 403。

    为什么顺序不能反（`agent_stage_api.py` 文件头第 23–26 行）：倒过来的话，flag off 时「缺参数」
    会漏出 400 —— 前端就分不清「功能没开（整卡不渲染）」与「老师填错了」。"""
    monkeypatch.setenv("AGENT_STAGE_ENABLED", "off")

    for method, path in _STAGE_ROUTE_TABLE:
        for payload in ({"teacher_name": "", "teacher_id": ""}, _auth()):
            call = getattr(client, method)
            res = call(path, json=payload) if method in ("post", "put") else call(path, params=payload)
            assert res.status_code == 404, "%s %s 应 404（实测 %d）" % (method, path, res.status_code)
            detail = _api_detail(res)
            assert detail["error"] == "agent_stage_disabled"
            assert set(detail) == {"error", "msg", "errors", "warnings"}, "统一错误体四键"


def test_api_store_not_ready_is_503_and_precedes_identity(client, monkeypatch):
    """flag on 但 0003 三表未就绪 → 503 `agent_stage_store_unavailable`（**不是** 404 / 400），
    且同样先於鉴权（先回答「服务能不能用」，再谈「你是谁」；§7.1-⑫ 要求 404 与 503 不得合并）。

    这里 monkeypatch 服务层探针（⑬ 组已在四种真实库形态上钉住探针本身；本组要钉的是**接线**：
    接口层确实问了它、并把 False 如实翻成 503 —— 若某天 `_guard()` 忘了问，本用例立刻红）。"""
    import agent_stage_service

    monkeypatch.setattr(agent_stage_service, "agent_stage_store_ready", lambda: False)

    for params in (_auth(), {"teacher_name": TEACHER, "teacher_id": ""}):
        res = client.get("/api/agent/stage", params=params)
        assert res.status_code == 503
        assert _api_detail(res)["error"] == "agent_stage_store_unavailable"


def test_api_identity_requires_both_fields_and_matching_names(client):
    """§4.6 全表入参：`teacher_name` + `teacher_id` 缺一 → 400 `teacher_required`；两者不等 → 403
    `teacher_mismatch`（每个 endpoint 的第二句，**在 `_guard()` 之后**）。

    400 覆盖「忘了传名字」这一形态：空名会命中**全局行**（服务层 `save_stage_config` 的注释），
    故接口层必须在触到业务之前拦住请求 —— 顺带钉住「空名的 PUT 不会写到全局行」。"""
    no_id = client.get("/api/agent/stage", params={"teacher_name": TEACHER, "teacher_id": ""})
    assert no_id.status_code == 400 and _api_detail(no_id)["error"] == "teacher_required"

    mismatch = client.get("/api/agent/stage",
                          params={"teacher_name": TEACHER, "teacher_id": OTHER_TEACHER})
    assert mismatch.status_code == 403 and _api_detail(mismatch)["error"] == "teacher_mismatch"

    empty_put = client.put("/api/agent/stage/config",
                           json={"teacher_name": "", "teacher_id": "",
                                 "config": {"schema_version": 1}})
    assert empty_put.status_code == 400 and _api_detail(empty_put)["error"] == "teacher_required"
    assert _raw_scalar("SELECT COUNT(*) FROM agent_stage_config WHERE teacher_name = ?", ("",)) == 1, \
        "空名请求必须被拦在业务之前：全局行仍是迁移种下的那一行（没被改写成新配置）"


# ---- ① #1 阶段视图（§4.6-①）----

def test_api_stage_view_shape_and_capabilities_for_default_stage(client):
    """§4.6-① / §2.3 / §3.1：`GET /api/agent/stage` 直出 `stage_view()` 的 15 键；未初始化老师
    （无状态行）落在配置链的 `default_stage`（`learning`）→ `capabilities` 逐格 = §2.3 的 learning 行；
    三个新能力里 `predict_pattern` / `suggest_prescription` / `generate_predraft` 一律 False。"""
    import agent_stage_service

    res = client.get("/api/agent/stage", params=_auth())
    assert res.status_code == 200
    view = res.json()

    assert set(view) == set(_STAGE_VIEW_KEYS), "接口层直出：键集必须与 §4.6-① 逐键一致"
    assert view["teacher_name"] == TEACHER
    assert view["stage"] == "learning" and view["stage_source"] == "default"
    assert view["stage_label"] == agent_stage_service.STAGE_LABELS["learning"]
    assert view["stage_since"] == "", "无状态行（未初始化）→ 兜底体不带起始时刻"
    assert view["degraded"] is False
    assert view["stale"] is True, "没快照 → stale（提示再点一次评估，不阻断任何东西）"
    assert view["blockers"] == ["evaluation_not_run"], "没评估过 → 唯一一条「尚未评估」"
    assert view["next_stage"] == "apprentice"

    assert set(view["capabilities"]) == set(_GATE_CAPS), "能力面五键（§2.3 的列）"
    assert view["capabilities"] == _LEARNING_CAPABILITIES
    assert set(view["metrics"]) == set(_METRIC_KEYS)
    assert view["metrics"]["inquiry_preference_consistency"] is None, "③ 占位键恒为 null（§3.1）"
    assert len(view["thresholds"]) == 13, "§4.6-① 的 thresholds 是 `_THRESHOLD_KEYS` 十三键（快照回显）"
    assert view["thresholds"]["min_template_match"] == \
        agent_stage_service.DEFAULT_STAGE_CONFIG["min_template_match"]
    assert "schema_version" not in view["thresholds"], "版本号不是判定阈值（不进快照）"


def test_api_stage_view_is_read_only_across_ten_calls(client):
    """§3.8 / 口径 A：#1 是**只读**接口 —— 连点十次，五张表行数不变、`agent_stage_log` 零增量
    （权限面只做投影、不调闸门，故不会为「拒绝」长出 `permission_denied`）。"""
    before = _table_counts()

    for _ in range(10):
        assert client.get("/api/agent/stage", params=_auth()).status_code == 200

    assert _table_counts() == before, "只读接口不得写任何一张表（含审计表）"
    assert _stage_log_events() == []


# ---- ③ #3 读配置（§4.6-③）----

def test_api_get_config_three_keys_same_source_as_service(client):
    """§4.6-③ / §3.4 第 4 条：`GET /api/agent/stage/config` 的三键 —— `effective` 与 `source`
    **同源**（与直接调服务层逐键相等）、`source` 如实回答「全局行在、老师行还没写」、
    `defaults` 是 §3.5 十六键内置默认的**副本**（不是服务层那个共享字典本身）。"""
    import agent_stage_service

    res = client.get("/api/agent/stage/config", params=_auth())
    assert res.status_code == 200
    body = res.json()

    assert set(body) == {"effective", "source", "defaults"}
    assert body["effective"] == agent_stage_service.load_stage_config(TEACHER)
    assert body["source"] == agent_stage_service.stage_config_source(TEACHER)
    assert body["source"] == {"global": True, "teacher_override": False, "env_override": []}, \
        "迁移种了全局行 → global=True；老师还没写过自己那一行 → teacher_override=False"
    assert body["effective"]["default_stage"] == "learning"
    assert body["defaults"] == agent_stage_service.DEFAULT_STAGE_CONFIG
    assert len(body["defaults"]) == 16, "§3.5 的 16 键键表（唯一硬编码点在服务层常量）"
    assert body["defaults"] is not agent_stage_service.DEFAULT_STAGE_CONFIG, "必须是副本（深拷贝）"


def test_api_get_config_is_read_only_across_ten_calls(client):
    """口径 A 同款：#3 十次调用零写入 —— 「老师还没写过自己那一行」这件事不能被一个 GET 悄悄改变。"""
    before = _table_counts()

    for _ in range(10):
        assert client.get("/api/agent/stage/config", params=_auth()).status_code == 200

    assert _table_counts() == before, "只读接口不得写任何一张表（含配置表 / 审计表）"
    assert _raw_scalar("SELECT COUNT(*) FROM agent_stage_config WHERE teacher_name = ?",
                       (TEACHER,)) == 0, "GET 不得替老师建行"
    assert _stage_log_events() == []


# ---- ④ #4 写配置（§4.6-④）----

def test_api_put_config_success_returns_effective_source_warnings(client):
    """§4.6-④：写成功 → 200 + 三键 `{effective, source, warnings}`；`effective` 是**写完再读**的四层
    合并值（老师行盖过内置默认）、`source` 如实回答「这两层现在都在」、`warnings` 为空（写进去的两个
    键都在 §3.5 键表内、也没被 env 覆盖）；同时钉住落库 + `config_changed` 审计一行。"""
    payload = {"schema_version": 1, "min_template_match": 0.9, "max_samples": 20}

    res = client.put("/api/agent/stage/config", json=dict(_auth(), config=payload))
    assert res.status_code == 200
    body = res.json()

    assert set(body) == {"effective", "source", "warnings"}, "§4.6-④ 出参三键（服务层其余键不下发）"
    assert body["warnings"] == []
    assert body["effective"]["min_template_match"] == 0.9
    assert body["effective"]["max_samples"] == 20
    assert body["effective"]["default_stage"] == "learning", "没提交的键回落到上一级（不是部分合并）"
    assert body["source"] == {"global": True, "teacher_override": True, "env_override": []}

    assert _raw_scalar("SELECT COUNT(*) FROM agent_stage_config WHERE teacher_name = ?",
                       (TEACHER,)) == 1, "写入目标是老师自己的行（不是全局行）"
    assert _stage_log_events() == ["config_changed"], "配置变更留审计一行"


def test_api_put_config_invalid_is_400_with_errors_and_zero_write(client):
    """§3.4 第 5 条 / §4.6-④：校验未过 → 400 `stage_config_invalid` + `errors[{path,msg}]`，
    且**整体不写入**（「只拦不清」）→ 该老师的生效配置仍是写入前那一份（旧值不变）、审计一行不写。

    顺带钉住「请求体缺 `config` 键」（`config=None`）走的是同一条 400，而不是 500 / FastAPI 的 422：
    服务层 `validate_stage_config()` 对「根不是对象」只回一条错误（`path=''`）。"""
    import agent_stage_service

    bad = client.put("/api/agent/stage/config",
                     json=dict(_auth(), config={"schema_version": 1, "min_template_match": 1.5}))
    assert bad.status_code == 400
    detail = _api_detail(bad)
    assert detail["error"] == "stage_config_invalid"
    assert [err["path"] for err in detail["errors"]] == ["min_template_match"]
    assert detail["msg"]

    missing = client.put("/api/agent/stage/config", json=_auth())
    assert missing.status_code == 400
    assert _api_detail(missing)["error"] == "stage_config_invalid"
    assert _api_detail(missing)["errors"][0]["path"] == "", "缺 config 键 = 根不是对象（同一条 400）"

    after = client.get("/api/agent/stage/config", params=_auth()).json()
    assert after["effective"]["min_template_match"] == \
        agent_stage_service.DEFAULT_STAGE_CONFIG["min_template_match"], "旧值不变（没写进去）"
    assert after["source"]["teacher_override"] is False, "老师行根本没建过"
    assert _stage_log_events() == []


# ---- ⑤ #5 手动降级（§4.6-⑤）----

def test_api_demote_lower_stage_returns_four_keys_and_manual_source(client):
    """§4.6-⑤：#5 手动降级成功 → 200 + **恰好四键** `{stage, previous_stage, stage_since,
    stage_source}`（工作台要显示「見習期 → 觀察期」与「自何时起」）；`stage_source` 恒为
    `manual_demote`、`stage_since` 刷新为本次时刻；落库 + 两类留痕（`stage_demoted` 事件 +
    `manual_demote` 行动日志）。"""
    _put_raw_state_row(TEACHER, "assistant", stage_since="S1", stage_source="default")

    res = client.post("/api/agent/stage/demote",
                      json=dict(_auth(), to_stage="observation", reason="測試降級"))
    assert res.status_code == 200
    body = res.json()

    assert set(body) == {"stage", "previous_stage", "stage_since", "stage_source"}
    assert body["stage"] == "observation" and body["previous_stage"] == "assistant"
    assert body["stage_source"] == "manual_demote"
    assert body["stage_since"] and body["stage_since"] != "S1", "进入时刻刷新为本次时刻"

    row = database.get_agent_stage_state(TEACHER)
    assert (row["stage"], row["stage_source"]) == ("observation", "manual_demote")

    logs = database.get_agent_stage_logs(TEACHER)
    assert [log["event_type"] for log in logs] == ["stage_demoted"]
    assert (logs[0]["from_stage"], logs[0]["to_stage"]) == ("assistant", "observation")
    assert "測試降級" in (logs[0]["detail"] or ""), "老师填的说明原样进审计人话"
    assert _stage_actions() == ["manual_demote"]


def test_api_demote_same_or_higher_stage_is_409_and_changes_nothing(client):
    """§4.6-⑤ / §6.1-8：同阶 / 高于当前的「降级」请求 → 409 `stage_transition_invalid`
    （不可能被满足的请求，**不许假成功**）；阶段三列与待确认对逐字节不动、审计零新增。"""
    _put_raw_state_row(TEACHER, "apprentice", stage_since="S1", stage_source="default",
                       pending_stage="assistant", pending_task_id=7)

    same = client.post("/api/agent/stage/demote", json=dict(_auth(), to_stage="apprentice"))
    higher = client.post("/api/agent/stage/demote", json=dict(_auth(), to_stage="authorized"))

    for res in (same, higher):
        assert res.status_code == 409, "「降级」指向不低于当前的位置 = 无法满足的请求"
        assert _api_detail(res)["error"] == "stage_transition_invalid"

    row = database.get_agent_stage_state(TEACHER)
    assert (row["stage"], row["stage_since"], row["stage_source"]) == ("apprentice", "S1", "default")
    assert (row["pending_stage"], row["pending_task_id"]) == ("assistant", 7), "被拒的降级不动任何一列"
    assert _stage_log_events() == [] and _stage_actions() == []


def test_api_demote_illegal_target_is_400_and_changes_nothing(client):
    """§4.6-⑤：`to_stage` 不在五阶段内 → 400 `stage_invalid_value`（空串 / 缺键也走这条 ——
    模型层的 `to_stage: str = ""` 就是为了让「缺键」落在这个可读的码上，而不是 FastAPI 的 422）。"""
    _put_raw_state_row(TEACHER, "assistant", stage_since="S1")

    for to_stage in ("vip", ""):
        res = client.post("/api/agent/stage/demote", json=dict(_auth(), to_stage=to_stage))
        assert res.status_code == 400, "to_stage=%r 应 400（实测 %d）" % (to_stage, res.status_code)
        assert _api_detail(res)["error"] == "stage_invalid_value"

    assert _raw_scalar("SELECT stage FROM agent_stage_state WHERE teacher_name = ?",
                       (TEACHER,)) == "assistant"
    assert _stage_log_events() == []


# ---- ② #2 跑一次评估（§4.6-②）----

def test_api_evaluate_returns_snapshot_with_changed_and_stays_at_stage(client):
    """§4.6-② / §3.6 / 约束 3：`POST /evaluate` 直出 18 键快照 + `changed`；没有有效样本 →
    `blockers` 逐条写明、`reason='blocked'`、`recommended=False`、`stage_changed=False`（**绝不向上写
    stage**）；两次调用各留一行 `evaluation` 审计、`last_evaluated_at` 落库。"""
    before = client.get("/api/agent/stage", params=_auth()).json()

    first = client.post("/api/agent/stage/evaluate", json=_auth())
    assert first.status_code == 200
    body = first.json()

    assert set(body) == set(_EVALUATE_SNAPSHOT_KEYS) | {"changed"}, "接口层直出：18 键 + changed"
    assert body["skipped"] is False and body["reason"] == "blocked"
    assert body["stage"] == "learning" and body["stage_label"] == before["stage_label"]
    assert body["blockers"], "没样本 / 没模板 → 逐条写明为什么没推荐（不翻 4xx）"
    assert body["changed"] == {"stage_changed": False, "recommended": False, "demoted": False,
                               "reason": "blocked"}
    assert body["evaluated_at"]

    row = database.get_agent_stage_state(TEACHER)
    assert row["stage"] == "learning", "评估不向上写阶段"
    assert row["last_evaluated_at"] == body["evaluated_at"], "快照落库，供 #1 的 stale 判定"

    second = client.post("/api/agent/stage/evaluate", json=_auth())
    assert second.status_code == 200
    assert second.json()["changed"]["stage_changed"] is False

    assert _stage_log_events() == ["evaluation", "evaluation"], "每次评估（含无推荐）各留一行"
    assert _stage_actions() == [], "没有推荐就没有行动日志（写点克制）"


# ---- ⑥ 路由面与源码级守护 ----

def test_api_router_registers_only_the_five_step_4b2_routes(client):
    """本步的路由面**恰好**是 #1–#5：路由表里没有 #6 `suggest` / #7 `predraft`（服务侧能力入口属 4c）。

    「名字在、行为不在」的假实现比 404 更糟（接口层文件头第 39–41 行的说明）→ 既查路由表，也真发一次请求钉住
    它落的是 FastAPI 默认 404（`{"detail": "Not Found"}`，**不是**统一错误体）；4c 落地后本用例要改成
    403 `stage_forbidden` / 404 `stage_draft_not_found` 那一族。"""
    import agent_stage_api

    registered = {(method, route.path)
                  for route in agent_stage_api.router.routes
                  for method in (getattr(route, "methods", None) or ())
                  if method in ("GET", "POST", "PUT", "DELETE")}    # GET 会被自动补 HEAD，故只看显式四种
    assert registered == _STAGE_REGISTERED_ROUTES

    for path, payload in (("/api/agent/stage/suggest", dict(_auth(), draft_id=1, kind="pattern")),
                          ("/api/agent/stage/predraft", dict(_auth(), draft_id=1))):
        res = client.post(path, json=payload)
        assert res.status_code == 404, "%s 本步不得注册（实测 %d）" % (path, res.status_code)
        assert res.json() == {"detail": "Not Found"}, "未注册的路由由 FastAPI 默认 404 兜底"


def test_api_module_never_imports_database_or_forbidden_symbols():
    """源码级（接口层文件头第 18–22 行的承诺）：接口层不 import `database` / `sqlite3`、不碰 §2.1 六个
    禁忌符号 —— 业务侧全在服务层，路由面因此天然「AI 永不落库 / 永不开方 / 永不签字」（§4.6 末段）。

    与 ⑩ 组同口径（复用同一套 AST 提取器）：只看**真的 import 了什么**与 `database.<属性>` 访问，
    文档 / 注释里「提到」这些名字不算违规（接口层文件头就列着这份清单）。"""
    imported, attributes = _service_imports_and_database_attrs(_api_source())

    assert "agent_stage_service" in imported, "守护自身不得静默失效：接口层必须经服务层处理业务"
    assert "database" not in imported, "接口层不得 import database（分层：业务侧全在 agent_stage_service）"
    assert "sqlite3" not in imported, "接口层不得 import sqlite3（存储就绪探针由服务层转发）"
    assert attributes == set(), "接口层不得访问 database.<任何东西>"
    for symbol in _FORBIDDEN_SERVICE_IMPORTS:
        assert symbol not in imported, "接口层不得 import 禁忌符号 %s" % symbol

"""add agent stage tables + AI snapshot columns (Epic 2 五阶段)

Epic 2「老師智能體五階段」第一步：**数据底座**（3 张新表 + 2 个快照列 + 种子），零业务逻辑。

- 对齐：docs/epic2-agent-stage-design-v1.md §1.2（状态行字段）/ §1.3（审计日志字段）/
        §1.4（**DDL 唯一真相源 = 本迁移**，含 downgrade 安全闸与「不删列」纪律）/
        §3.5（配置表契约）/ §7.1-①（两个快照列）②（种子 = learning）⑪（新表走迁移）。
- 新建 3 表（全部 TEXT / INTEGER，**零外键、零 CHECK**，与存量 24+ 张表同构）：
    agent_stage_state   一位老师一行；无行 = 未初始化（按 default_stage 兜底，**不报错**，§1.5）
    agent_stage_log     治理审计（只增不改不删，§1.3；与 Epic 3 的学习事件流分工见 §1.3 注）
    agent_stage_config  配置行（teacher_name='' = 全局默认行，其余 = 老师专属覆盖行，§3.5）
- 补 2 列（**零回填**，老行由 DEFAULT '' 兜底 = 未记录；downgrade 时**不删**）：
    drafts.ai_original_content         生成时的 AI 原始输出（不可变快照，② 指标基准）
    patient_records.ai_original_text   签字时把上述快照一并落进历史表（草案行签字后会被删除）
- 种子（幂等）：① `teachers` 里尚无状态行的老师 → `stage='learning'`
  （§7.1-②：存量老师已有「生成病历草案」能力，不可降级；想改成观察期只改本文件 SEED_STAGE +
  配置 `default_stage`，零代码改动）；② `agent_stage_config` 写一行 `teacher_name=''` /
  `config_json='{}'`（显式承载「全局行存在但用内置默认」，§1.4）。
- 可重跑：建表 / 建索引一律 `IF [NOT] EXISTS`；补列先 `PRAGMA table_info` 探测（沿用迁移 0002）；
  种子用 `NOT EXISTS` / `INSERT OR IGNORE` 自证幂等。
- downgrade：**带安全闸** —— `agent_stage_log` 有审计事件（非种子）时中止并提示先导出留档
  （沿用迁移 0001 §6.4 的安全闸口径）；通过后删 3 张新表，**两个快照列保留**
  （列里是历史快照，删掉就永久丢失 ② 的口径，沿用迁移 0002 的纪律）。
- 离线预审产物：docs/migrations/0003_add_agent_stage.sql
  （由 `alembic upgrade 0002_add_draft_template_refs:head --sql` 导出 **本 revision 的增量**，
  与 0001 产物的「CLI --sql 离线预审」习惯一致；离线模式下无法探测表 / 列是否已存在，输出里已注明）。

Revision ID: 0003_add_agent_stage
Revises: 0002_add_draft_template_refs
Create Date: 2026-09-28
"""
from datetime import datetime

import sqlalchemy as sa
from alembic import context, op

revision = "0003_add_agent_stage"
down_revision = "0002_add_draft_template_refs"
branch_labels = None
depends_on = None

# ---------------------------------------------------------------------------
# 种子常量（§1.4 / §7.1-②）
# ---------------------------------------------------------------------------
GLOBAL_CONFIG_ROW = ""                  # agent_stage_config.teacher_name = '' → 全局默认行
SEED_STAGE = "learning"                 # 存量老师的初始阶段：不降级（今天已有生成草案能力）
SEED_STAGE_SOURCE = "default"           # 与 §1.2 的 stage_source 白名单一致
SEED_CONFIG_JSON = "{}"                 # 空对象 = 全部键走内置兜底默认值（§3.5）

# ---------------------------------------------------------------------------
# 3 张新表（§1.2 / §1.3 / §3.5）
# ---------------------------------------------------------------------------
STATE_DDL = """
CREATE TABLE IF NOT EXISTS agent_stage_state (
    teacher_name TEXT PRIMARY KEY,
    lineage_id TEXT NOT NULL DEFAULT '',
    stage TEXT NOT NULL DEFAULT 'observation',
    stage_since TEXT NOT NULL DEFAULT '',
    stage_source TEXT NOT NULL DEFAULT 'default',
    pending_stage TEXT NOT NULL DEFAULT '',
    pending_task_id INTEGER DEFAULT 0,
    last_evaluated_at TEXT NOT NULL DEFAULT '',
    last_metrics_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL DEFAULT ''
)
"""

LOG_DDL = """
CREATE TABLE IF NOT EXISTS agent_stage_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    teacher_name TEXT,
    event_type TEXT,
    from_stage TEXT,
    to_stage TEXT,
    capability TEXT,
    task_id INTEGER,
    metrics_json TEXT,
    detail TEXT,
    created_at TEXT
)
"""

CONFIG_DDL = """
CREATE TABLE IF NOT EXISTS agent_stage_config (
    teacher_name TEXT PRIMARY KEY,
    config_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL DEFAULT ''
)
"""

TABLE_DDL = (STATE_DDL, LOG_DDL, CONFIG_DDL)

INDEX_DDL = (
    # §1.4：agent_stage_state 索引 (lineage_id, stage)
    # 用途：按师门 + 阶段筛「同一阶段的老师」（Epic 2 恒 lineage_id=''，Epic 4 起成为隔离键）
    "CREATE INDEX IF NOT EXISTS idx_agent_stage_state_scope "
    "ON agent_stage_state (lineage_id, stage)",
    # §1.4：agent_stage_log 索引 (teacher_name, created_at DESC)
    # 用途：某老师最近事件倒序（与 get_agent_action_log 的排序口径一致，created_at 同秒面用 id 兜底）
    "CREATE INDEX IF NOT EXISTS idx_agent_stage_log_teacher_time "
    "ON agent_stage_log (teacher_name, created_at DESC)",
)

DROP_INDEX_DDL = (
    "DROP INDEX IF EXISTS idx_agent_stage_log_teacher_time",
    "DROP INDEX IF EXISTS idx_agent_stage_state_scope",
)

# 先删日志（§1.4 downgrade 顺序），再删状态 / 配置；索引随表一起消失，上面仍显式先 drop 一遍（沿用 0001 口径）
DROP_TABLE_DDL = (
    "DROP TABLE IF EXISTS agent_stage_log",
    "DROP TABLE IF EXISTS agent_stage_state",
    "DROP TABLE IF EXISTS agent_stage_config",
)

# ---------------------------------------------------------------------------
# 2 个快照列（§1.4 / §7.1-①）：零回填，downgrade 不删
# ---------------------------------------------------------------------------
ADD_COLUMNS = (
    (
        "drafts",
        "ai_original_content",
        "ALTER TABLE drafts ADD COLUMN ai_original_content TEXT DEFAULT ''",
    ),
    (
        "patient_records",
        "ai_original_text",
        "ALTER TABLE patient_records ADD COLUMN ai_original_text TEXT DEFAULT ''",
    ),
)

# ---------------------------------------------------------------------------
# 种子 SQL（幂等）
# ---------------------------------------------------------------------------
SEED_STATE_SQL = """
INSERT INTO agent_stage_state
    (teacher_name, stage, stage_since, stage_source, updated_at)
SELECT t.name, :stage, :stamp, :source, :stamp
FROM teachers AS t
WHERE NOT EXISTS (
    SELECT 1 FROM agent_stage_state AS s WHERE s.teacher_name = t.name
)
"""

SEED_CONFIG_SQL = """
INSERT OR IGNORE INTO agent_stage_config (teacher_name, config_json, updated_at)
VALUES (:teacher_name, :config_json, :stamp)
"""

STATE_COUNT_SQL = "SELECT COUNT(*) FROM agent_stage_state"
GLOBAL_CONFIG_COUNT_SQL = (
    "SELECT COUNT(*) FROM agent_stage_config WHERE teacher_name = ''"
)
LOG_EVENT_COUNT_SQL = "SELECT COUNT(*) FROM agent_stage_log"



# ---------------------------------------------------------------------------
# 探测 / 执行辅助（与迁移 0001 / 0002 同款实现）
# ---------------------------------------------------------------------------
def _exec(sql, **params):
    """统一发出 SQL（与迁移 0001 同款实现）。

    带参时走 `sa.text().bindparams()`：离线模式（literal_binds=True）会把参数内联，
    保证 `alembic upgrade ... --sql` 打印出的就是真正会执行的语句，可直接人工预审。
    """
    if params:
        op.execute(sa.text(sql).bindparams(**params))
    else:
        op.execute(sql)


def _table_exists(conn, name):
    row = conn.exec_driver_sql(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
    ).fetchone()
    return row is not None


def _columns(conn, table):
    return {
        row[1]
        for row in conn.exec_driver_sql("PRAGMA table_info('%s')" % table).fetchall()
    }


def _stamp():
    """时间列一律 TEXT ISO 字符串（全库惯例，database.py / 迁移 0001 同源）。"""
    return datetime.now().isoformat()


def upgrade():
    if context.is_offline_mode():
        _upgrade_offline()
    else:
        _upgrade_online()


def _upgrade_offline():
    # 离线模式只输出 SQL，不做任何数据库探测（上线前人工预审）
    print(
        "-- [0003] offline：无法探测表 / 索引 / 列是否已存在（在线模式靠 sqlite_master + "
        "PRAGMA table_info 幂等）；若目标库已有这些对象，请人工跳过对应语句"
    )
    for ddl in TABLE_DDL:
        _exec(ddl)
    for ddl in INDEX_DDL:
        _exec(ddl)
    print(
        "-- [0003] offline：下面两条 ADD COLUMN 依赖目标库已有 drafts / patient_records 表"
        "（由 init_db() 创建）；表不存在时请人工跳过"
    )
    for _table, _column, ddl in ADD_COLUMNS:
        _exec(ddl)
    print(
        "-- [0003] offline：下面两条种子依赖目标库已有 teachers 表；"
        "agent_stage_config 的全局行（teacher_name=''）必须存在"
    )
    _exec(SEED_STATE_SQL, stage=SEED_STAGE, stamp=_stamp(), source=SEED_STAGE_SOURCE)
    _exec(
        SEED_CONFIG_SQL,
        teacher_name=GLOBAL_CONFIG_ROW,
        config_json=SEED_CONFIG_JSON,
        stamp=_stamp(),
    )


def _upgrade_online():
    conn = op.get_bind()
    stamp = _stamp()

    # 1. 建 3 张新表 + 2 个索引（IF NOT EXISTS，脏库已手建过时兜底不报错）
    for ddl in TABLE_DDL:
        _exec(ddl)
    for ddl in INDEX_DDL:
        _exec(ddl)
    print("[0003] agent_stage_state / agent_stage_log / agent_stage_config 与索引就绪")

    # 2. 补 2 个快照列（表不存在 / 列已存在 → 跳过并提示，沿用 0002 口径）
    added = []
    for table, column, ddl in ADD_COLUMNS:
        if not _table_exists(conn, table):
            print("[0003] %s 表不存在（全新库尚未 init_db），无列可补：跳过 %s" % (table, column))
            continue
        if column in _columns(conn, table):
            print("[0003] %s.%s 已存在，跳过" % (table, column))
            continue
        _exec(ddl)
        added.append("%s.%s" % (table, column))
    print(
        "[0003] AI 原始快照列就绪（本次新增 %s）；老行由 DEFAULT '' 兜底 = 未记录"
        % (", ".join(added) if added else "无（已是目标状态）")
    )

    # 3. 种子 ①：存量老师 → learning（已有状态行则跳过）
    if not _table_exists(conn, "teachers"):
        print(
            "[0003] teachers 不存在（全新库尚未 init_db）：无存量老师可种子；新老师按 default_stage 兜底"
        )
    else:
        before = conn.exec_driver_sql(STATE_COUNT_SQL).scalar()
        _exec(SEED_STATE_SQL, stage=SEED_STAGE, stamp=stamp, source=SEED_STAGE_SOURCE)
        after = conn.exec_driver_sql(STATE_COUNT_SQL).scalar()
        print(
            "[0003] 阶段状态种子：存量老师 %d 位 → stage='%s'（本次插入 %d 行；§7.1-② 存量不降级）"
            % (after, SEED_STAGE, after - before)
        )

    # 4. 种子 ②：全局配置行（幂等：INSERT OR IGNORE）
    _exec(
        SEED_CONFIG_SQL,
        teacher_name=GLOBAL_CONFIG_ROW,
        config_json=SEED_CONFIG_JSON,
        stamp=stamp,
    )

    # 5. 收尾校验（与 0001 第 4 步同款纪律）：全局配置行必须恰好 1 行，否则整体回滚，不留半张表
    global_rows = conn.exec_driver_sql(GLOBAL_CONFIG_COUNT_SQL).scalar()
    if global_rows != 1:
        raise RuntimeError(
            "agent_stage_config 全局行（teacher_name=''）应恰好 1 行，实测 %d 行（本 revision 已整体回滚）"
            % global_rows
        )
    print("[0003] 种子就绪：agent_stage_config 全局行 1 行（config_json='{}' = 全部走内置默认）")


def downgrade():
    if context.is_offline_mode():
        _downgrade_offline()
    else:
        _downgrade_online()


def _downgrade_offline():
    print(
        "-- [0003] offline：安全闸（agent_stage_log 有审计事件时中止降级）无法离线判定，"
        "请人工确认 agent_stage_log 为空（或已导出留档）再执行以下语句；"
        "drafts.ai_original_content / patient_records.ai_original_text 两列**不删**（§1.4）"
    )
    for ddl in DROP_INDEX_DDL:
        _exec(ddl)
    for ddl in DROP_TABLE_DDL:
        _exec(ddl)


def _downgrade_online():
    conn = op.get_bind()

    if not _table_exists(conn, "agent_stage_log"):
        print("[0003] agent_stage_log 不存在，downgrade 已是目标状态（可重跑）")
    else:
        events = conn.exec_driver_sql(LOG_EVENT_COUNT_SQL).scalar()
        if events:
            # 【安全闸】§1.4：升级推荐 / 越权拒绝 / 配置变更 / 降级原因都在日志里，
            # 直接 DROP 会永久丢失治理留痕 —— 先导出再人工清空，或优先用 flag 回退。
            raise RuntimeError(
                "downgrade 已中止：agent_stage_log 中有 %d 行审计事件（阶段流转 / 越权 / 配置变更 / 评估）。"
                "请先导出留档（`SELECT * FROM agent_stage_log;`，或直接备份整个库文件），"
                "确认归档后人工清空该表再重跑 downgrade；"
                "若只是要停用功能，优先用 flag 回退（AGENT_STAGE_ENABLED=off：新接口 404、阶段评估停止、"
                "既有链路不变），**不必**删表。" % events
            )

    # 索引 → 表（顺序与 §1.4 一致）；两个快照列**保留**
    for ddl in DROP_INDEX_DDL:
        _exec(ddl)
    for ddl in DROP_TABLE_DDL:
        _exec(ddl)
    print(
        "[0003] downgrade 完成：agent_stage_log / agent_stage_state / agent_stage_config 与 2 个索引已删除；"
        "drafts.ai_original_content / patient_records.ai_original_text 两列按 §1.4 保留（历史快照，不删）"
    )

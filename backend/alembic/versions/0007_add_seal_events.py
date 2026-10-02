"""add seal_events table + 1 index (B 板块「数据主权」step B5-a · 数据封存数据底座)

B 板块「数据主权」子项 5（数据封存）第一步：**数据底座**（1 张新表 + 1 个索引），零业务逻辑
（查询 API / 手动触发属后续步；链上填充属阶段四）。

对齐：docs/phase2-data-sovereignty-design.md §3.5（数据封存）
  §3.5.1（阶段二只做「封存事件记录 + 查询 + 手动触发」，不自动判定 / 不拦截 / 不实际上链）
  §3.5.2（**不读** `agent_stage_log`：其 10 类事件中无一为除名；除名事件未定义）
  §3.5.4（`seal_events` DDL —— **DDL 唯一真相源 = 本迁移**；`database.py::init_db()` 不重复一份）
  §3.5.5（B 板块**不定义除名事件**：`action` 取值只含 `seal` / `readmit`，**不含** `remove`）
  §3.5.6（API 契约：`/api/seal/events` GET + `/api/seal/trigger` POST；flag `SEAL_ENABLED` 默认 off）
  §3.5.7（阶段四预留：`chain_ready` / `chain_hash` 本步只建列、**不填值**，填充归阶段四）

纪律（与 0001 / 0003 / 0005 / 0006 同款）：
  · 只新增 1 张表 + 1 个索引；**不 ALTER 任何既有表、不重建任何表、不动任何既有列一个字节**；
  · 可重跑：建表 / 建索引一律 `IF NOT EXISTS`，收尾按名字探测结构完整性（不符即抛错回滚）；
  · downgrade 只 DROP 新表与新索引（**TD-003 口径**：只回收结构，不删任何业务列）——本 revision
    本来就没有既有列可删，故全文与离线产物中**零删列语句**；
  · downgrade 带安全闸：表内有封存事件行时中止并提示先导出留档（沿用 0003 / 0005 / 0006 口径）。
    理由：封存 / 重新接纳事件是**数据主权行为的见证记录**，一删即无法回溯「何时、由谁、为何」封存。

离线预审产物：docs/migrations/0007_add_seal_events.sql
  · 生成命令（backend/ 下）：`alembic upgrade 0006_add_agent_learning_events:head --sql`；
  · 离线模式**不做在线判定**（表 / 索引存在性、downgrade 安全闸都无法离线判定），
    也不读库（本 revision 无种子 / 无回填 / 无需枚举存量数据），产物与在线语句逐字一致。

Revision ID: 0007_add_seal_events
Revises: 0006_add_agent_learning_events
Create Date: 2026-10-02
"""
from alembic import context, op

revision = "0007_add_seal_events"
down_revision = "0006_add_agent_learning_events"
branch_labels = None
depends_on = None

# ---------------------------------------------------------------------------
# §3.5.4 表名 + DDL（唯一真相源）
# ---------------------------------------------------------------------------
SEAL_EVENTS_TABLE = "seal_events"

TABLE_DDL = """
CREATE TABLE IF NOT EXISTS seal_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_type TEXT NOT NULL,
    subject_name TEXT NOT NULL,
    action       TEXT NOT NULL,
    reason       TEXT,
    operator     TEXT,
    created_at   TEXT NOT NULL,
    chain_ready  BOOLEAN DEFAULT FALSE,
    chain_hash   TEXT
)
"""

# §3.5.4 列全集（顺序 = DDL 顺序；测试逐字比对，防「悄悄加列」）
ALL_COLUMNS = (
    "id",
    "subject_type",
    "subject_name",
    "action",
    "reason",
    "operator",
    "created_at",
    "chain_ready",
    "chain_hash",
)

# ---------------------------------------------------------------------------
# §3.5.4 索引：按主体的封存 / 重新接纳历史倒序读路径
# ---------------------------------------------------------------------------
INDEX_DDL = (
    # 读路径：列出某主体（`subject_type` + `subject_name`）的封存 / 重新接纳历史，最近事件在前。
    # 照 0006 `idx_agent_learning_events_teacher_time` 同款：显式命名 → 可单独 drop、可被 sqlite_master 探测。
    "CREATE INDEX IF NOT EXISTS idx_seal_events_subject "
    "ON seal_events (subject_type, subject_name, id DESC)",
)
INDEX_NAMES = ("idx_seal_events_subject",)
DROP_INDEX_DDL = ("DROP INDEX IF EXISTS idx_seal_events_subject",)
DROP_TABLE_DDL = ("DROP TABLE IF EXISTS seal_events",)

# downgrade 安全闸 / 收尾校验共用的计数口径
COUNT_SQL = "SELECT COUNT(*) FROM seal_events"


# ---------------------------------------------------------------------------
# 探测 / 执行辅助（与迁移 0001 / 0003 / 0005 / 0006 同款实现）
# ---------------------------------------------------------------------------
def _exec(sql):
    """统一发出 SQL（无参 —— 本 revision 无种子 / 无回填）。"""
    op.execute(sql)


def _table_exists(conn, name):
    row = conn.exec_driver_sql(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
    ).fetchone()
    return row is not None


def _object_exists(conn, name):
    """按名字探测表**或**索引（收尾结构校验用；不吃 sqlite_autoindex_*，因为索引都显式命名）。"""
    row = conn.exec_driver_sql(
        "SELECT name FROM sqlite_master WHERE name = ?", (name,)
    ).fetchone()
    return row is not None


def _scalar(conn, sql):
    return conn.exec_driver_sql(sql).scalar()


# ---------------------------------------------------------------------------
# upgrade
# ---------------------------------------------------------------------------
def upgrade():
    if context.is_offline_mode():
        _upgrade_offline()
    else:
        _upgrade_online()


def _upgrade_offline():
    print(
        "-- [0007] offline：无法判定表 / 索引是否已存在（在线模式靠 sqlite_master 幂等）；"
        "若目标库已有同名对象，请人工跳过对应语句；本 revision 无种子 / 无回填 / 不读库"
    )
    _exec(TABLE_DDL)
    print("-- [0007] 已输出：CREATE TABLE seal_events")
    for ddl in INDEX_DDL:
        _exec(ddl)
    print("-- [0007] 已输出：%s" % " / ".join(INDEX_NAMES))
    print(
        "-- [0007] offline：收尾结构校验与 downgrade 安全闸只在在线执行时判定，离线产物不含"
    )


def _upgrade_online():
    conn = op.get_bind()

    # ① 建表（§3.5.4；DDL 唯一真相源 = 本迁移）
    _exec(TABLE_DDL)
    print("[0007] seal_events 表就绪（DDL = 设计 §3.5.4）")

    # ② 建索引（§3.5.4：按主体封存历史倒序读路径）
    for ddl in INDEX_DDL:
        _exec(ddl)
    print("[0007] 索引就绪：%s" % " / ".join(INDEX_NAMES))

    # ③ 收尾结构校验（与 0001 / 0003 / 0005 / 0006 同款纪律）：表与 1 个索引必须都在，
    #    否则抛错 —— env.py 一个事务跑完全链，抛错 = 整 revision 回滚（不留半张表）。
    missing = [name for name in (SEAL_EVENTS_TABLE,) + INDEX_NAMES if not _object_exists(conn, name)]
    if missing:
        raise RuntimeError(
            "seal_events 结构不完整，缺：%s（本 revision 已整体回滚）" % ", ".join(missing)
        )

    columns = [
        row[1] for row in conn.exec_driver_sql("PRAGMA table_info('seal_events')").fetchall()
    ]
    if tuple(columns) != ALL_COLUMNS:
        raise RuntimeError(
            "seal_events 列集合与设计 §3.5.4 不符：实测 %s（本 revision 已整体回滚）"
            % ", ".join(columns)
        )

    rows = _scalar(conn, COUNT_SQL)
    print(
        "[0007] 就绪：%s 表（%d 列）+ %d 个索引；当前 %d 行"
        "（查询 API / 手动触发属后续步；链上填充属阶段四）"
        % (SEAL_EVENTS_TABLE, len(ALL_COLUMNS), len(INDEX_NAMES), rows)
    )


# ---------------------------------------------------------------------------
# downgrade（TD-003 口径：只回收结构，不删任何业务列）
# ---------------------------------------------------------------------------
def downgrade():
    if context.is_offline_mode():
        _downgrade_offline()
    else:
        _downgrade_online()


def _downgrade_offline():
    print(
        "-- [0007] offline downgrade：安全闸（表内有封存事件行时中止降级）无法离线判定，"
        "请人工确认 seal_events 为空（或已导出留档）后再执行；"
        "本 revision 只 drop 新表与新索引，**不改任何既有表 / 列 / 数据**"
    )
    for ddl in DROP_INDEX_DDL:
        _exec(ddl)
    print("-- [0007] 已输出：DROP INDEX %s" % " / ".join(INDEX_NAMES))
    for ddl in DROP_TABLE_DDL:
        _exec(ddl)
    print("-- [0007] 已输出：DROP TABLE seal_events")


def _downgrade_online():
    conn = op.get_bind()

    if not _table_exists(conn, SEAL_EVENTS_TABLE):
        print("[0007] seal_events 表不存在，downgrade 已是目标状态（可重跑）")
    else:
        events = _scalar(conn, COUNT_SQL)
        if events:
            # 【安全闸】封存 / 重新接纳事件是数据主权行为的见证记录（何时 / 由谁 / 为何），
            # 一删即无法回溯（无法从业务数据反推）。故有事件行即中止。
            raise RuntimeError(
                "downgrade 已中止：seal_events 中有 %d 行封存事件（不可重建）。"
                "请先导出留档（`SELECT * FROM seal_events ORDER BY id;`，"
                "或直接备份整个库文件），确认归档后人工清空该表再重跑 downgrade；"
                "若只是要停用功能，优先用 flag 回退（SEAL_ENABLED=off：新接口 404、"
                "封存事件停写），**不必**删表。" % events
            )

    # 索引 → 表；既有表 / 列 / 数据一字未动
    for ddl in DROP_INDEX_DDL:
        _exec(ddl)
    for ddl in DROP_TABLE_DDL:
        _exec(ddl)
    print(
        "[0007] downgrade 完成：seal_events 表与 1 个索引已删除；"
        "既有表 / 列 / 数据一字未动（TD-003 口径：只回收结构，不删业务列）"
    )

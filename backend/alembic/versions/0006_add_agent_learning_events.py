"""add agent_learning_events table + 2 indexes (Epic 3 学习闭环 step 3.1)

Epic 3「学习闭环」第一步：**数据底座**（1 张新表 + 2 个索引 + 哈希链口径常量冻结），零业务逻辑
（哈希链纯函数属 step 3.2、事件接线属 step 3.3、③ 指标转正属 step 3.4、接口 + 前端属 step 3.5）。

对齐：docs/epic3-learning-design-v1.md
  §2.1（`agent_learning_events` DDL —— **DDL 唯一真相源 = 本迁移**；`database.py::init_db()` 不重复一份）
  §2.2（表字段全集 +「投影列 / 链元列」两分法：每个投影列都有一个**同名 payload 顶层键**，
        `payload_json` 为权威源、列 = 可检索投影）
  §2.3（canonical 口径逐字：`sort_keys=True` / `separators=(",", ":")` / `ensure_ascii=False`；
        顶层 9 键 = 参与哈希的键集合）
  §2.4（A3 链节指纹公式 + `GENESIS_HASH`）
  §2.5（A2 `seq` 语义：**按老师单链**单调递增 + `UNIQUE(teacher_name, seq)`）
  §3（A6 与 `agent_stage_log` 的边界：**不纳入同链**，边界复述见 epic2 设计 §1.3 注）
  §4（与 `docs/epic4-lineage-design-v1.md:620` 的复用承诺 + **口径冻结声明**）
  §5（A4 flag `LEARNING_ENABLED`；A5 定位键口径：`patient_name_hash` / `draft_id` / `template_id` /
        `lineage_id`（仅审计标注）—— **明文姓名不入链**）
  §6（A7 API 契约：新文件 `learning_api.py`，统计接口独立端点）
  §7（回退方案：flag off → 只回收结构）
  §8（§5.6 交叉风险备忘：Epic 3 零产品语义降级 + 事件写**不借道** `permission_denied`）

CTO 2026-09-30「Epic 3 调研验收 + A1–A8 裁决」逐条落点：
  A1 ③ 转正 / A8 差异记录两类：**本步不实现**（落设计 §5 / §9 条文，3.4 / 3.3 施工）
  A2 `seq` 按老师单链 + `UNIQUE(teacher_name, seq)` → 本文件 `uq_agent_learning_events_teacher_seq`
  A3 `prev_hash` = 链节指纹 → 本文件 `GENESIS_HASH` + §2.4 公式常量（3.2 实现）
  A4 flag `LEARNING_ENABLED`（照 on/1/true/yes、现读、默认 off）→ 本文件 `FLAG_*` 常量（3.5 实现）
  A5 定位键（`patient_name_hash = sha256(patient_name)[:16]` + `draft_id` / `template_id` 明文 +
     `lineage_id` 仅审计标注）→ 本文件 `PATIENT_NAME_HASH_LEN` + 列 / payload 键
  A6 `agent_stage_log` **不**纳入同链 → 本迁移**零补列语句**（`test_0006_source_keeps_epic3_redlines` 钉住）
  A7 API：新文件 `learning_api.py` + 统计独立端点 → 设计 §6

纪律（与 0001 / 0003 / 0005 同款）：
  · 只新增 1 张表 + 2 个索引；**不 ALTER 任何既有表、不重建任何表、不动 `agent_stage_log` 一个字节**；
  · 可重跑：建表 / 建索引一律 `IF NOT EXISTS`，收尾按名字探测结构完整性（不符即抛错回滚）；
  · downgrade 只 DROP 新表与新索引（**TD-003 新口径**：只回收结构，不删任何业务列）——本 revision
    本来就没有既有列可删，故全文与离线产物中**零删列语句**（由用例与产物守护用例双双钉住）；
  · downgrade 带安全闸：表内有学习事件行（= 哈希链节）时中止并提示先导出留档（沿用 0003 / 0005 口径）。
    理由：链节是**不可重建**的见证基准（`seq` / `prev_hash` / `payload_hash` 一删即永久失去可验证性）。

离线预审产物：docs/migrations/0006_add_agent_learning_events.sql
  · 生成命令（backend/ 下）：`alembic upgrade 0005_add_lineage:head --sql`；
  · 离线模式**不做在线判定**（表 / 索引存在性、downgrade 安全闸都无法离线判定），
    也不读库（本 revision 无种子 / 无回填 / 无需枚举存量数据），产物与在线语句逐字一致。

Revision ID: 0006_add_agent_learning_events
Revises: 0005_add_lineage
Create Date: 2026-09-30
"""
from alembic import context, op

revision = "0006_add_agent_learning_events"
down_revision = "0005_add_lineage"
branch_labels = None
depends_on = None

# ---------------------------------------------------------------------------
# §2.1 表名 + DDL（唯一真相源）
# ---------------------------------------------------------------------------
EVENTS_TABLE = "agent_learning_events"

TABLE_DDL = """
CREATE TABLE IF NOT EXISTS agent_learning_events (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    teacher_name      TEXT NOT NULL,
    seq               INTEGER NOT NULL,
    event_type        TEXT NOT NULL,
    lineage_id        TEXT NOT NULL DEFAULT '',
    patient_name_hash TEXT NOT NULL DEFAULT '',
    draft_id          INTEGER DEFAULT 0,
    template_id       INTEGER DEFAULT 0,
    payload_json      TEXT NOT NULL DEFAULT '{}',
    payload_hash      TEXT NOT NULL DEFAULT '',
    prev_hash         TEXT NOT NULL DEFAULT '',
    created_at        TEXT NOT NULL DEFAULT ''
)
"""

# §2.2 列全集（顺序 = DDL 顺序；测试逐字比对，防「悄悄加列」）
ALL_COLUMNS = (
    "id",
    "teacher_name",
    "seq",
    "event_type",
    "lineage_id",
    "patient_name_hash",
    "draft_id",
    "template_id",
    "payload_json",
    "payload_hash",
    "prev_hash",
    "created_at",
)


# §2.2「投影列」：每个都对应一个**同名 payload 顶层键**（§2.3）—— 权威源恒为 payload_json，
# 列为可检索 / 可审计的投影；两者一致性由 step 3.3 的同事务写 + 用例钉住。
PROJECTION_COLUMNS = (
    "teacher_name",
    "seq",
    "event_type",
    "lineage_id",
    "patient_name_hash",
    "draft_id",
    "template_id",
    "created_at",
)

# §2.2「链元列」：不属于 payload，由 step 3.2 的哈希链纯函数产出（不参与 canonical payload）
CHAIN_META_COLUMNS = ("id", "payload_json", "payload_hash", "prev_hash")

# ---------------------------------------------------------------------------
# §2.5 索引（A2：UNIQUE(teacher_name, seq) 是「按老师单链」的硬约束）
# ---------------------------------------------------------------------------
INDEX_DDL = (
    # 【A2】按老师单链：seq 单调且不重复。**唯一索引**而不是表内 UNIQUE 约束 —— 与 0001 的
    # `uq_templates_active_one` 同款：显式命名 → 可单独 drop、可被 sqlite_master 探测（表内
    # 约束会生成不可命名的 sqlite_autoindex_*，无法在 downgrade 里单独回收）。
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_learning_events_teacher_seq "
    "ON agent_learning_events (teacher_name, seq)",
    # 读路径：某老师最近事件倒序 + 时间窗（证据模式快照）；照 0003 `idx_agent_stage_log_teacher_time` 同款。
    # （(teacher_name, seq) 已能服务 seq 序读；本条专供 created_at 时间窗筛选。）
    "CREATE INDEX IF NOT EXISTS idx_agent_learning_events_teacher_time "
    "ON agent_learning_events (teacher_name, created_at DESC)",
)
INDEX_NAMES = (
    "uq_agent_learning_events_teacher_seq",
    "idx_agent_learning_events_teacher_time",
)
# drop 顺序：普通索引在前、唯一索引在后（与 0003 DROP_INDEX_DDL 同款「先弱后强」）
DROP_INDEX_DDL = (
    "DROP INDEX IF EXISTS idx_agent_learning_events_teacher_time",
    "DROP INDEX IF EXISTS uq_agent_learning_events_teacher_seq",
)
DROP_TABLE_DDL = ("DROP TABLE IF EXISTS agent_learning_events",)

# downgrade 安全闸 / 收尾校验共用的计数口径
EVENT_COUNT_SQL = "SELECT COUNT(*) FROM agent_learning_events"

# ---------------------------------------------------------------------------
# §2.4 / §5 哈希链口径常量（**冻结见证**）
# ---------------------------------------------------------------------------
# 本段的常量是「口径冻结」的机器可读见证：step 3.2 的实现**必须**在其用例里与本处逐字对齐
# （照 0005 ↔ `lineage_service` 对 `slugify` 的双向对齐纪律，见设计 §9）。
GENESIS_HASH = "0" * 64        # 创世哈希：64 个 ASCII '0'（= 空链的「上一条链节指纹」）
PAYLOAD_HASH_ALGO = "sha256"   # 摘要算法（唯一允许值）
PATIENT_NAME_HASH_LEN = 16     # 【A5】patient_name_hash = sha256(patient_name)[:16]

# §2.3 canonical 口径（逐字冻结；step 3.2 的 canonical_json() 必须逐参对齐）
CANONICAL_SORT_KEYS = True
CANONICAL_SEPARATORS = (",", ":")
CANONICAL_ENSURE_ASCII = False
# §2.3 参与哈希的键集合 = payload 的**顶层 9 键**（`detail` 内部键参与哈希但随事件类型演进）
PAYLOAD_TOP_LEVEL_KEYS = (
    "seq",
    "event_type",
    "teacher_name",
    "created_at",
    "lineage_id",
    "patient_name_hash",
    "draft_id",
    "template_id",
    "detail",
)

# §2.2 / development-plan-v1.md §3.3-D3 事件流：5 类事件（顺序 = 登记顺序，非先后约束）
EVENT_TYPES = (
    "template_configured",
    "draft_generated",
    "draft_modified",
    "learning_event_emitted",
    "agent_updated",
)

# ---------------------------------------------------------------------------
# §5 A4 总闸 flag（照 template / agent_stage / lineage 三套惯例：on/1/true/yes、现读、默认 off）
# ---------------------------------------------------------------------------
FLAG_NAME = "LEARNING_ENABLED"
FLAG_VALUES = ("on", "1", "true", "yes")
FLAG_DEFAULT = "off"


# ---------------------------------------------------------------------------
# 探测 / 执行辅助（与迁移 0001 / 0003 / 0005 同款实现）
# ---------------------------------------------------------------------------
def _exec(sql):
    """统一发出 SQL（无参 —— 本 revision 无种子 / 无回填，故不需要 0005 的 `bindparams` 分支）。"""
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
        "-- [0006] offline：无法判定表 / 索引是否已存在（在线模式靠 sqlite_master 幂等）；"
        "若目标库已有同名对象，请人工跳过对应语句；本 revision 无种子 / 无回填 / 不读库"
    )
    _exec(TABLE_DDL)
    print("-- [0006] 已输出：CREATE TABLE agent_learning_events")
    for ddl in INDEX_DDL:
        _exec(ddl)
    print("-- [0006] 已输出：%s" % " / ".join(INDEX_NAMES))
    print(
        "-- [0006] offline：收尾结构校验与 downgrade 安全闸只在在线执行时判定，离线产物不含"
    )


def _upgrade_online():
    conn = op.get_bind()

    # ① 建表（§2.1；DDL 唯一真相源 = 本迁移）
    _exec(TABLE_DDL)
    print("[0006] agent_learning_events 表就绪（DDL = 设计 §2.1）")

    # ② 建 2 个索引（§2.5：唯一索引 = A2 的按老师单链约束；时间索引 = 事件倒序 / 时间窗读路径）
    for ddl in INDEX_DDL:
        _exec(ddl)
    print("[0006] 索引就绪：%s" % " / ".join(INDEX_NAMES))

    # ③ 收尾结构校验（与 0001 / 0003 / 0005 同款纪律）：表与 2 个索引必须都在，
    #    否则抛错 —— env.py 一个事务跑完全链，抛错 = 整 revision 回滚（不留半张表）。
    missing = [name for name in (EVENTS_TABLE,) + INDEX_NAMES if not _object_exists(conn, name)]
    if missing:
        raise RuntimeError(
            "agent_learning_events 结构不完整，缺：%s（本 revision 已整体回滚）" % ", ".join(missing)
        )

    columns = [
        row[1] for row in conn.exec_driver_sql("PRAGMA table_info('agent_learning_events')").fetchall()
    ]
    if tuple(columns) != ALL_COLUMNS:
        raise RuntimeError(
            "agent_learning_events 列集合与设计 §2.2 不符：实测 %s（本 revision 已整体回滚）"
            % ", ".join(columns)
        )

    rows = _scalar(conn, EVENT_COUNT_SQL)
    print(
        "[0006] 就绪：%s 表（%d 列）+ %d 个索引；当前 %d 行"
        "（哈希链纯函数属 step 3.2、事件接线属 step 3.3；本步零业务逻辑）"
        % (EVENTS_TABLE, len(ALL_COLUMNS), len(INDEX_NAMES), rows)
    )


# ---------------------------------------------------------------------------
# downgrade（TD-003 新口径：只回收结构，不删任何业务列）
# ---------------------------------------------------------------------------
def downgrade():
    if context.is_offline_mode():
        _downgrade_offline()
    else:
        _downgrade_online()


def _downgrade_offline():
    print(
        "-- [0006] offline downgrade：安全闸（表内有学习事件行时中止降级）无法离线判定，"
        "请人工确认 agent_learning_events 为空（或已导出留档）后再执行；"
        "本 revision 只 drop 新表与新索引，**不改任何既有表 / 列 / 数据**"
    )
    for ddl in DROP_INDEX_DDL:
        _exec(ddl)
    print("-- [0006] 已输出：DROP INDEX %s" % " / ".join(INDEX_NAMES))
    for ddl in DROP_TABLE_DDL:
        _exec(ddl)
    print("-- [0006] 已输出：DROP TABLE agent_learning_events")


def _downgrade_online():
    conn = op.get_bind()

    if not _table_exists(conn, EVENTS_TABLE):
        print("[0006] agent_learning_events 表不存在，downgrade 已是目标状态（可重跑）")
    else:
        events = _scalar(conn, EVENT_COUNT_SQL)
        if events:
            # 【安全闸】链节是**不可重建**的见证基准：`seq` / `prev_hash` / `payload_hash` 一旦随表
            # 删除，哈希链的「自证未篡改」能力即永久丧失（无法从业务数据反推）。故有事件行即中止。
            raise RuntimeError(
                "downgrade 已中止：agent_learning_events 中有 %d 行学习事件（哈希链节，不可重建）。"
                "请先导出留档（`SELECT * FROM agent_learning_events ORDER BY teacher_name, seq;`，"
                "或直接备份整个库文件），确认归档后人工清空该表再重跑 downgrade；"
                "若只是要停用功能，优先用 flag 回退（LEARNING_ENABLED=off：新接口 404、事件停写、"
                "既有链路不变），**不必**删表。" % events
            )

    # 索引 → 表（先普通索引、后唯一索引）；既有表 / 列 / 数据一字未动
    for ddl in DROP_INDEX_DDL:
        _exec(ddl)
    for ddl in DROP_TABLE_DDL:
        _exec(ddl)
    print(
        "[0006] downgrade 完成：agent_learning_events 表与 2 个索引已删除；"
        "既有表 / 列 / 数据一字未动（TD-003 新口径：只回收结构，不删业务列）"
    )

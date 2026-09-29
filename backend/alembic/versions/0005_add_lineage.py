"""add lineage table + 12 lineage_id columns + default lineage seeds + backfill (Epic 4 step 4.1)

Epic 4「多师管理（师门归属与隔离）」第一步：**数据底座**（1 张新表 + 2 个索引 + 12 张必须表补列 +
默认师门种子 + 存量回填 + 计数校验），零业务逻辑（读 / 写路径过滤属 step 4.2）。

对齐：docs/epic4-lineage-design-v1.md
  §2.1（`lineage` DDL —— **DDL 唯一真相源 = 本迁移**，`init_db()` 不重复写一份）
  §2.2（`patient_teachers` 升级为事实上的 `student_lineage`：本步只补列 + 回填，改入口属 4.2）
  §2.3（必须 12 张表补 `lineage_id`；明确不加：`patients` / `patient_profiles` / `teachers` /
        `agent_stage_state` / `agent_stage_config` / `teacher_settings` / `herb_inventory` / `invites` /
        `accounts` / `points_*` / `transactions` / **`plan_templates`**）
  §2.4（`''` = 未归属的唯一哨兵；**禁止**把未归属 COALESCE 兜底成默认师门，见 §2.4 纪律 3）
  §2.5（建 `idx_lineage_owner` 与 `idx_patient_teachers_lineage`；其余业务表的 lineage 索引默认不建）
  §6.1（upgrade 七步，全部幂等）/ §6.2（真机回填基线 1/10/5/4/1 + 孤儿行留 `''`）
  §6.3（downgrade 统一口径：**只回收结构，不删业务列**；带安全闸）
  §6.4（离线产物 docs/migrations/0005_add_lineage.sql，与本文件内联语句逐字一致）
裁决 ②（空串语义）/ ③（阶段是老师维度：**不动** `agent_stage_state` 结构）/ ④（downgrade 不删列）/ ⑤（TEXT 主键）
CTO 2026-09-29「step 4.1 放行」五条约束：
  1. 七步按 §6.1 执行，每步可回滚；
  2. 回填计数校验：真机预期 1/10/5/4/1（teachers/patient_teachers/templates/patient_records/drafts），
     实填 ≠ 预期 → 抛错、**整 revision 回滚**（见 _upgrade_online 第 ⑥ 步）；
     实测注（step 4.1）：本机 SQLAlchemy / pysqlite 默认隔离级别下 **DDL 不在事务内**
     （`CREATE TABLE lineage` / `ADD COLUMN lineage_id` 不受回滚保护，已实测留证），故「整 revision 回滚」
     的实际语义 = **`alembic_version` 停在 0004 + 业务数据零变更**；DDL 残留（空 `lineage` 表、空
     `lineage_id` 列）由本迁移自身的幂等探测在下一次 `upgrade` 时吸收（不重复建表 / 不重复补列），
     即「修好触发条件后重跑即收敛」——已用测试 `test_0005_backfill_count_mismatch_aborts_revision` 固定。
     若要连 DDL 一起回滚，需改 `alembic/env.py` 的事务接入方式（超出 step 4.1 范围，已上报 CTO）；
  3. downgrade 只 drop `lineage` 表 / 索引，**不 drop 任何业务列**；
  4. 先红后绿（`test_migrations.py` 的 0005 组用例先红、迁移后绿）；
  5. 离线 SQL 产物与在线执行语句逐字一致（同一批内联常量，见 _upgrade_offline）。

upgrade 七步（§6.1；②③ 次序按 SQLite 现实做了**一处**调整，见注）：
  ① `CREATE TABLE IF NOT EXISTS lineage` + `idx_lineage_owner`；
  ② 12 张必须表 `ADD COLUMN lineage_id TEXT NOT NULL DEFAULT ''`（`PRAGMA table_info` 探测 + 可重跑，
     表不存在则跳过 —— 全新库尚未 `init_db()` / 0003 尚未建 `agent_stage_log` 时是正常态）；
  ③ `CREATE INDEX IF NOT EXISTS idx_patient_teachers_lineage`（§2.5 建议索引）；
  ④ 种子默认师门：`id='lin-'+slugify(name)`、`name=name+'師門'`、`owner_teacher_name=name`、
     `status='active'`；slug 由 **Python 侧**算（SQLite 无 slugify / sha1），逐老师 `INSERT ... WHERE NOT EXISTS`；
  ⑤ 存量回填：逐表 `UPDATE ... WHERE lineage_id = '' AND EXISTS(映射)`（§6.2 形状，纯 SQL、幂等）；
  ⑥ 收尾计数校验：① 每表「应填 == 实填」（不符即抛错回滚）；② 命中真机基线签名时再断言 1/10/5/4/1；
     ③ 每位老师都必须有默认师门；
  ⑦ 纪律：不 ALTER `agent_stage_state`、不重建任何表、不改 `templates` 既有 3 个索引、不碰 `plan_templates` 数据。
  注：§6.1 把索引列在补列之前，但 SQLite 不允许在**尚不存在的列**上建索引 —— 故实际执行次序为
      「补列 → 建该索引」，**结果与 §6.1 完全一致**（索引就位），只调整了语句先后。

downgrade（§6.3 / 裁决 ④）：
  - 安全闸（沿用 0003 口径）：`lineage` 行数 > 老师数（= 已有老师自建 / 多师门数据），或
    `patient_teachers` 存在 `lineage_id` 非空且 `status='inactive'` 的退出记录 → 抛异常中止，提示先导出 /
    改用 flag 回退；
  - 通过后：`DROP INDEX idx_patient_teachers_lineage` → `DROP INDEX idx_lineage_owner` → `DROP TABLE lineage`；
    **12 张表的 `lineage_id` 列与其值全部保留**（与 0004 的「删列」例外口径不同，TD-003 已记）。

离线预审产物：docs/migrations/0005_add_lineage.sql
  - 生成命令（backend/ 下）：`alembic upgrade 0004_add_patient_record_template_refs:head --sql`；
  - 离线模式**不做在线判定**（表 / 列存在性、回填计数、downgrade 安全闸都无法离线判定），
    但会以 `mode=ro` **只读**打开目标库、仅用于枚举存量老师，以便把种子语句连同真实 `lin-*` id
    一并导出（满足「离线产物与在线语句逐字一致」；只读不写库文件、不建 journal）；
    库不存在 / 读不到时退化为「占位 + 人工核对」形式，并在输出里注明。

Revision ID: 0005_add_lineage
Revises: 0004_add_patient_record_template_refs
Create Date: 2026-09-29
"""
from datetime import datetime
import hashlib
import os
import sqlite3

import sqlalchemy as sa
from alembic import context, op

revision = "0005_add_lineage"
down_revision = "0004_add_patient_record_template_refs"
branch_labels = None
depends_on = None

# backend/ 目录（本文件在 backend/alembic/versions/ 下）
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ---------------------------------------------------------------------------
# §2.1 `lineage` 表（逐字照录设计；TEXT 主键，与 templates.lineage_id 同构）
# ---------------------------------------------------------------------------
LINEAGE_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS lineage (
    id                  TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    owner_teacher_name  TEXT NOT NULL,
    description         TEXT DEFAULT '',
    status              TEXT NOT NULL DEFAULT 'active',
    created_at          TEXT NOT NULL DEFAULT '',
    updated_at          TEXT NOT NULL DEFAULT ''
)
"""

SEED_STATUS = "active"        # §2.1 status 白名单（active / archived）；种子恒 active
LINEAGE_NAME_SUFFIX = "師門"  # §6.1-③：默认师门中文名 = <老师名> + '師門'（UI 文案一律繁体古字）
LINEAGE_ID_PREFIX = "lin-"    # §0.1 / §2.1：id = 'lin-' + slugify(teacher_name)

LINEAGE_INDEX_DDL = (
    # §2.5：老师端「某老师的师门 / 活跃师门清单」是 P0 读路径
    "CREATE INDEX IF NOT EXISTS idx_lineage_owner ON lineage (owner_teacher_name, status)",
)
LINEAGE_INDEX_DROP_DDL = ("DROP INDEX IF EXISTS idx_lineage_owner",)

PATIENT_TEACHERS_INDEX_DDL = (
    # §2.5 建议索引：老师端「本师门学生名单」（既有 PK (patient_name, teacher_name) 帮不上 lineage_id 前缀）
    "CREATE INDEX IF NOT EXISTS idx_patient_teachers_lineage "
    "ON patient_teachers (lineage_id, teacher_name, status)",
)
PATIENT_TEACHERS_INDEX_DROP_DDL = ("DROP INDEX IF EXISTS idx_patient_teachers_lineage",)

# ---------------------------------------------------------------------------
# §2.3「必须」12 张表（`templates` 自带 lineage_id，只回填；`agent_stage_state` 明确不加）
# ---------------------------------------------------------------------------
ADD_COLUMNS = (
    ("drafts", "lineage_id"),
    ("patient_records", "lineage_id"),
    ("complaints", "lineage_id"),
    ("appointments", "lineage_id"),
    ("prescriptions", "lineage_id"),
    ("homework", "lineage_id"),
    ("transcriptions", "lineage_id"),
    ("record_tags", "lineage_id"),
    ("agent_tasks", "lineage_id"),
    ("agent_action_log", "lineage_id"),
    ("agent_stage_log", "lineage_id"),   # 裁决 ③-C：审计区分用（阶段本身恒老师维度）
    ("patient_teachers", "lineage_id"),  # §2.2：= student_lineage 的实现
)
ADD_COLUMN_TPL = "ALTER TABLE %s ADD COLUMN lineage_id TEXT NOT NULL DEFAULT ''"

# 回填来源（表, 老师的列名）；§6.2：`templates` 用 teacher_id，其余用 teacher_name
# ⚠️ `plan_templates` **不在**此（A1 裁决 2026-09-29：Epic 1 兼容镜像，不师门化 → 不补列 / 不回填 / 不过滤）
BACKFILL_SOURCES = (
    ("patient_teachers", "teacher_name"),
    ("templates", "teacher_id"),
    ("patient_records", "teacher_name"),
    ("drafts", "teacher_name"),
    ("complaints", "teacher_name"),
    ("appointments", "teacher_name"),
    ("prescriptions", "teacher_name"),
    ("homework", "teacher_name"),
    ("transcriptions", "teacher_name"),
    ("record_tags", "teacher_name"),
    ("agent_tasks", "teacher_name"),
    ("agent_action_log", "teacher_name"),
    ("agent_stage_log", "teacher_name"),
)

# 种子（幂等：同 id / 同 owner 已存在则不动）—— §6.1-③
SEED_LINEAGE_SQL = """
INSERT INTO lineage (id, name, owner_teacher_name, description, status, created_at, updated_at)
SELECT :lin_id, :lin_name, :owner, '', :status, :stamp, :stamp
WHERE NOT EXISTS (
    SELECT 1 FROM lineage WHERE id = :lin_id OR owner_teacher_name = :owner
)
"""

# ---------------------------------------------------------------------------
# 真机回填基线（§6.2 只读实测 2026-09-29；CTO 放行约束 2）
#   签名 = 5 张核心表的整表行数（同时命中才认为是「真机同形库」，避免在别处误报中止）；
#   命中后断言：lineage 行数 == 1，且 patient_teachers / templates / patient_records / drafts 的回填
#   「应填」必须分别等于 10 / 5 / 4 / 1，不符则抛错、整 revision 回滚。
# ---------------------------------------------------------------------------
REAL_DB_SIGNATURE = (
    ("teachers", 1),
    ("patient_teachers", 10),
    ("templates", 5),
    ("patient_records", 4),
    ("drafts", 1),
)
REAL_DB_EXPECTED_FILL = (
    ("patient_teachers", 10),
    ("templates", 5),
    ("patient_records", 4),
    ("drafts", 1),
)


# ---------------------------------------------------------------------------
# 探测 / 执行 / id 契约（与迁移 0001 / 0002 / 0003 / 0004 同款实现）
# ---------------------------------------------------------------------------
def _exec(sql, **params):
    """统一发出 SQL（与迁移 0003 同款）。

    带参时走 `sa.text().bindparams()`：离线模式（literal_binds=True）会把参数**内联**，
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
    return {row[1] for row in conn.exec_driver_sql("PRAGMA table_info('%s')" % table).fetchall()}


def _scalar(conn, sql):
    return conn.exec_driver_sql(sql).scalar()


def _stamp():
    """时间列一律 TEXT ISO 字符串（全库惯例，database.py / 迁移 0001 同源）。"""
    return datetime.now().isoformat()


def slugify(name):
    """老师名 → 小写 ASCII 安全串（§0.1）。

    小写化 → 非 `[a-z0-9]` 一律转 `-` → 折叠连续 `-` → 去首尾 `-`；结果为空（纯中文名等）
    时回落 `u<sha1(名)[:8]>` —— 稳定、可复现、跨机一致（**禁止**把 id 写成代码常量）。
    """
    raw = "" if name is None else str(name)
    slug = "".join(
        ch if ("a" <= ch <= "z" or "0" <= ch <= "9") else "-" for ch in raw.strip().lower()
    )
    while "--" in slug:
        slug = slug.replace("--", "-")
    slug = slug.strip("-")
    if not slug:
        slug = "u" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]
    return slug


def lineage_id_for(teacher_name):
    """§0.1 / §2.1：`id = 'lin-' + slugify(teacher_name)`（本迁移与后续服务层唯一口径）。"""
    return LINEAGE_ID_PREFIX + slugify(teacher_name)


def lineage_name_for(teacher_name):
    """§6.1-③：默认师门中文名 = `<老师名>師門`。"""
    return "%s%s" % (teacher_name, LINEAGE_NAME_SUFFIX)


def backfill_sql(table, owner_column):
    """§6.2「回填 SQL 形状」（逐字）：只碰 `lineage_id = ''` 且有映射的行；禁止 COALESCE 兜底。"""
    return (
        "UPDATE %s\n"
        "   SET lineage_id = (SELECT id FROM lineage WHERE owner_teacher_name = %s.%s)\n"
        " WHERE lineage_id = ''\n"
        "   AND EXISTS (SELECT 1 FROM lineage WHERE owner_teacher_name = %s.%s)"
        % (table, table, owner_column, table, owner_column)
    )


def _pending_sql(table, owner_column):
    """「应回填行数」= 未归属且有映射的行数（回填前先算，回填后与实填数比对）。"""
    return (
        "SELECT COUNT(*) FROM %s WHERE lineage_id = '' AND EXISTS ("
        "SELECT 1 FROM lineage WHERE owner_teacher_name = %s.%s)" % (table, table, owner_column)
    )


def _assigned_sql(table):
    """已归属行数（`lineage_id <> ''`）—— 「实回填行数」= 回填后 − 回填前。"""
    return "SELECT COUNT(*) FROM %s WHERE lineage_id <> ''" % table


def _orphan_sql(table, owner_column):
    """孤儿行 = 未归属且**无映射**（预期 0）；按 §6.2 留 `''` + 出清单，不中止。"""
    return (
        "SELECT COUNT(*) FROM %s WHERE lineage_id = '' AND NOT EXISTS ("
        "SELECT 1 FROM lineage WHERE owner_teacher_name = %s.%s)" % (table, table, owner_column)
    )


def _target_db_path():
    """按 env.py 的优先级解析目标 SQLite 文件（离线只读探测老师清单用）；非 sqlite → None。"""
    url = (context.config.attributes.get("sqlalchemy_url") or "").strip()
    if not url:
        url = (context.config.get_main_option("sqlalchemy.url") or "").strip()
    if url:
        return url[len("sqlite:///"):] if url.startswith("sqlite:///") else None
    db_file = os.environ.get("ZHIENG_DB", "zhiheng.db")
    return db_file if os.path.isabs(db_file) else os.path.join(BACKEND_DIR, db_file)


def _probe_teacher_names():
    """离线模式**只读**（`mode=ro`：不写库文件、不建 journal）枚举存量老师，只为把种子语句
    连同真实 `lin-*` id 一并导出（CTO 放行约束 5：离线产物与在线语句逐字一致）。

    返回 (names, note)：names=None 表示探测失败（库不存在 / 非 sqlite / 无 teachers 表），
    此时离线输出退化为「占位 + 人工核对」形式；names=[] 表示库可读但确实没有存量老师。
    """
    path = _target_db_path()
    if not path:
        return None, "目标库不是 sqlite 文件（离线无法枚举老师）"
    if not os.path.exists(path):
        return None, "目标库文件不存在：%s" % path
    try:
        conn = sqlite3.connect("file:%s?mode=ro" % path.replace("\\", "/"), uri=True)
    except sqlite3.Error as exc:
        return None, "只读打开失败：%s" % exc
    try:
        rows = conn.execute("SELECT name FROM teachers ORDER BY name").fetchall()
    except sqlite3.Error as exc:
        return None, "读取 teachers 失败（表不存在？）：%s" % exc
    finally:
        conn.close()
    return [row[0] for row in rows], None


# ---------------------------------------------------------------------------
# upgrade
# ---------------------------------------------------------------------------
def upgrade():
    if context.is_offline_mode():
        _upgrade_offline()
    else:
        _upgrade_online()


def _upgrade_offline():
    # 离线只输出 SQL；唯一例外是「只读」枚举老师清单（种子 id 需 Python 侧 slugify，SQLite 无 sha1）
    names, note = _probe_teacher_names()
    print(
        "-- [0005] offline：无法判定表 / 列是否已存在（在线模式靠 sqlite_master + PRAGMA table_info 幂等）、"
        "不做回填计数校验与 downgrade 安全闸（二者只在在线执行时判定）；"
        "若目标库已有同名列，请人工跳过对应 ADD COLUMN 语句"
    )

    # ① lineage 表 + idx_lineage_owner
    _exec(LINEAGE_TABLE_DDL)
    print("-- [0005] 已输出：CREATE TABLE lineage")
    for ddl in LINEAGE_INDEX_DDL:
        _exec(ddl)
    print("-- [0005] 已输出：idx_lineage_owner")

    # ② 12 张必须表补 lineage_id（离线无法探测，故全部输出）
    for table, _column in ADD_COLUMNS:
        _exec(ADD_COLUMN_TPL % table)
        print("-- [0005] 已输出：ALTER TABLE %s ADD COLUMN lineage_id" % table)

    # ③ idx_patient_teachers_lineage（§2.5；必须在补列之后 —— SQLite 不允许索引引用不存在的列）
    for ddl in PATIENT_TEACHERS_INDEX_DDL:
        _exec(ddl)
    print("-- [0005] 已输出：idx_patient_teachers_lineage")

    # ④ 种子默认师门（逐个老师、字面量内联；探测失败时退化为人工核对提示）
    if names is None:
        print(
            "-- [0005] offline：无法枚举存量老师（%s）→ 种子语句未导出；"
            "请在在线执行前人工核对：每位老师必须有一行 `id='lin-'+slugify(name)` / "
            "`name=name+'師門'` / `owner_teacher_name=name` / `status='active'` 的 lineage 行" % note
        )
    elif not names:
        print("-- [0005] offline：目标库 teachers 表无存量老师 → 无默认师门可种子（新老师由 4.2 服务层创建）")
    else:
        stamp = _stamp()
        for name in names:
            _exec(
                SEED_LINEAGE_SQL,
                lin_id=lineage_id_for(name),
                lin_name=lineage_name_for(name),
                owner=name,
                status=SEED_STATUS,
                stamp=stamp,
            )
            print(
                "-- [0005] 已输出：种子默认师门 %s（owner=%s，name=%s）"
                % (lineage_id_for(name), name, lineage_name_for(name))
            )

    # ⑤ 存量回填（纯 SQL，与在线逐字一致；孤儿行按 §6.2 留 ''）
    for table, owner_column in BACKFILL_SOURCES:
        _exec(backfill_sql(table, owner_column))
        print("-- [0005] 已输出：回填 %s（按 %s）" % (table, owner_column))
    print(
        "-- [0005] offline：收尾计数校验（应填==实填、真机基线 1/10/5/4/1、每位老师有师门）"
        "与 downgrade 安全闸只在在线执行时判定，离线产物不含"
    )


def _upgrade_online():
    conn = op.get_bind()
    stamp = _stamp()

    # ① lineage 表 + idx_lineage_owner（§2.1；DDL 唯一真相源 = 本迁移）
    _exec(LINEAGE_TABLE_DDL)
    for ddl in LINEAGE_INDEX_DDL:
        _exec(ddl)
    print("[0005] lineage 表与 idx_lineage_owner 就绪（DDL = 设计 §2.1）")

    # ② 12 张必须表补 lineage_id（探测式、可重跑；表不存在 = 正常态，跳过）
    added, kept, missing = [], [], []
    for table, column in ADD_COLUMNS:
        if not _table_exists(conn, table):
            missing.append(table)
            continue
        if column in _columns(conn, table):
            kept.append(table)
            continue
        _exec(ADD_COLUMN_TPL % table)
        added.append(table)
    print(
        "[0005] lineage_id 补列：新增 %s；已存在跳过 %s；表不存在跳过 %s"
        "（全新库尚未 init_db() / 0003 未建 agent_stage_log 时后两类属正常态）"
        % (", ".join(added) or "无", ", ".join(kept) or "无", ", ".join(missing) or "无")
    )

    # ③ idx_patient_teachers_lineage（§2.5）—— 必须在补列之后：SQLite 不允许索引引用尚不存在的列
    if _table_exists(conn, "patient_teachers") and "lineage_id" in _columns(conn, "patient_teachers"):
        for ddl in PATIENT_TEACHERS_INDEX_DDL:
            _exec(ddl)
        print("[0005] idx_patient_teachers_lineage 就绪（§2.5 建议索引）")
    else:
        print("[0005] patient_teachers 表或 lineage_id 列不存在 → 跳过 idx_patient_teachers_lineage")

    # ④ 种子默认师门（§6.1-③：id = 'lin-' + slugify(name)，逐老师 INSERT ... WHERE NOT EXISTS，幂等）
    if not _table_exists(conn, "teachers"):
        print("[0005] teachers 表不存在（全新库尚未 init_db()）→ 无默认师门可种子")
        teacher_rows = 0
        seeded = 0
    else:
        teacher_names = [
            row[0]
            for row in conn.exec_driver_sql("SELECT name FROM teachers ORDER BY name").fetchall()
        ]
        teacher_rows, seeded = len(teacher_names), 0
        for name in teacher_names:
            before = _scalar(conn, "SELECT COUNT(*) FROM lineage")
            _exec(
                SEED_LINEAGE_SQL,
                lin_id=lineage_id_for(name),
                lin_name=lineage_name_for(name),
                owner=name,
                status=SEED_STATUS,
                stamp=stamp,
            )
            if _scalar(conn, "SELECT COUNT(*) FROM lineage") > before:
                seeded += 1
        print(
            "[0005] 默认师门种子：存量老师 %d 位 → 本次新增 %d 行（已有同 id / 同 owner 则跳过）"
            % (teacher_rows, seeded)
        )

    # ⑤ 存量回填（§6.2 形状；只有「未归属且有映射」的行会被写，纯 SQL、幂等）
    pending = {}
    assigned_after = {}
    for table, owner_column in BACKFILL_SOURCES:
        if not _table_exists(conn, table):
            print("[0005] 回填跳过：%s 表不存在" % table)
            continue
        if "lineage_id" not in _columns(conn, table):
            print("[0005] 回填跳过：%s 尚无 lineage_id 列" % table)
            continue
        expect = _scalar(conn, _pending_sql(table, owner_column))
        before = _scalar(conn, _assigned_sql(table))
        _exec(backfill_sql(table, owner_column))
        after = _scalar(conn, _assigned_sql(table))
        filled = after - before
        orphans = _scalar(conn, _orphan_sql(table, owner_column))
        pending[table] = expect
        assigned_after[table] = after
        print(
            "[0005] 回填 %s（按 %s）：应填 %d / 实填 %d；已归属 %d 行；未归属（孤儿，预期 0）%d 行"
            % (table, owner_column, expect, filled, after, orphans)
        )
        if filled != expect:
            # ⑥-a「应填 == 实填」（§6.1-⑥）：不符即抛错 —— env.py 一个事务跑完全链，抛错 = 整 revision 回滚
            raise RuntimeError(
                "回填计数校验失败：%s 应回填 %d 行、实回填 %d 行（应填≠实填 → 整 revision 回滚）"
                % (table, expect, filled)
            )

    # ⑥ 收尾计数校验
    if _table_exists(conn, "teachers"):
        uncovered = _scalar(
            conn,
            "SELECT COUNT(*) FROM teachers AS t WHERE NOT EXISTS ("
            "SELECT 1 FROM lineage AS l WHERE l.owner_teacher_name = t.name)",
        )
        if uncovered:
            raise RuntimeError(
                "默认师门种子校验失败：%d 位老师没有对应 lineage 行（每位老师必须有默认师门 → 整 revision 回滚）"
                % uncovered
            )

    # ⑥-b 真机基线（CTO 放行约束 2）：签名命中才断言 1/10/5/4/1，避免在别处误报
    signature_ok = True
    signature_actual = {}
    for table, expected in REAL_DB_SIGNATURE:
        if not _table_exists(conn, table):
            signature_ok = False
            signature_actual[table] = None
            continue
        signature_actual[table] = _scalar(conn, "SELECT COUNT(*) FROM %s" % table)
        if signature_actual[table] != expected:
            signature_ok = False
    if signature_ok:
        mismatch = []
        lineage_rows = _scalar(conn, "SELECT COUNT(*) FROM lineage")
        if lineage_rows != 1:
            mismatch.append("lineage 应 1 行、实测 %d 行" % lineage_rows)
        for table, expected in REAL_DB_EXPECTED_FILL:
            actual = assigned_after.get(table)
            if actual != expected:
                mismatch.append(
                    "%s 已归属行数应 %d 行、实测 %s"
                    % (table, expected, actual if actual is not None else "未回填（表 / 列缺失）")
                )
        if mismatch:
            raise RuntimeError(
                "回填计数校验失败（真机基线 §6.2 = 1/10/5/4/1，实填≠预期 → 整 revision 回滚）："
                + "；".join(mismatch)
            )
        print(
            "[0005] 真机基线校验通过：lineage 1 行；回填 patient_teachers 10 / templates 5 / "
            "patient_records 4 / drafts 1"
        )
    else:
        print(
            "[0005] 真机基线签名不匹配（实测 %s；签名 %s）→ 只做「应填==实填」校验；"
            "若这仍是真机库，请人工核对设计 §6.2" % (signature_actual, dict(REAL_DB_SIGNATURE))
        )

    print(
        "[0005] 就绪：lineage 表 + 2 个索引 + 12 张必须表 lineage_id + 默认师门种子 + 存量回填；"
        "读 / 写路径过滤属 step 4.2（当前 flag off，零行为变化）"
    )


# ---------------------------------------------------------------------------
# downgrade（§6.3 / 裁决 ④：只回收结构，不删业务列）
# ---------------------------------------------------------------------------
def downgrade():
    if context.is_offline_mode():
        _downgrade_offline()
    else:
        _downgrade_online()


def _downgrade_offline():
    print(
        "-- [0005] offline downgrade：安全闸（lineage 行数 > 老师数 / 有已退出师门记录）无法离线判定，"
        "请人工确认后再执行；12 张表的 lineage_id 列与其值**一律不删**（裁决 ④：只回收结构）"
    )
    for ddl in PATIENT_TEACHERS_INDEX_DROP_DDL:
        _exec(ddl)
    print("-- [0005] 已输出：DROP INDEX idx_patient_teachers_lineage")
    for ddl in LINEAGE_INDEX_DROP_DDL:
        _exec(ddl)
    print("-- [0005] 已输出：DROP INDEX idx_lineage_owner")
    _exec("DROP TABLE IF EXISTS lineage")
    print("-- [0005] 已输出：DROP TABLE lineage")


def _downgrade_online():
    conn = op.get_bind()

    if not _table_exists(conn, "lineage"):
        print("[0005] lineage 表不存在，downgrade 已是目标状态（可重跑）")
    else:
        # 【安全闸 1】§6.3：师门数 > 老师数 = 已有老师自建 / 多师门数据，直接 DROP 会吃掉师门归属事实
        lineage_rows = _scalar(conn, "SELECT COUNT(*) FROM lineage")
        teacher_rows = (
            _scalar(conn, "SELECT COUNT(*) FROM teachers") if _table_exists(conn, "teachers") else 0
        )
        if lineage_rows > teacher_rows:
            raise RuntimeError(
                "downgrade 已中止：lineage 有 %d 行、teachers 只有 %d 位老师 → 存在老师自建 / 多师门数据。"
                "请先导出留档（`SELECT * FROM lineage;` 或直接备份整个库文件 / 相关列表接口），"
                "确认归档后再重跑；若只是要停用功能，优先用 flag 回退（LINEAGE_ENABLED=off：新接口 404、"
                "过滤停止、既有链路不变），**不必**删表。" % (lineage_rows, teacher_rows)
            )
        # 【安全闸 2】§6.3：已退出师门的归属行（lineage_id 非空 + status='inactive'）是「退出不删数据」的留痕
        if _table_exists(conn, "patient_teachers"):
            columns = _columns(conn, "patient_teachers")
            if "lineage_id" in columns and "status" in columns:
                exits = _scalar(
                    conn,
                    "SELECT COUNT(*) FROM patient_teachers "
                    "WHERE lineage_id <> '' AND status = 'inactive'",
                )
                if exits:
                    raise RuntimeError(
                        "downgrade 已中止：patient_teachers 有 %d 行「已退出师门」记录"
                        "（status='inactive' 且 lineage_id 非空）。请先导出留档再重跑；"
                        "若只是要停用功能，优先用 flag 回退（LINEAGE_ENABLED=off），**不必**删表。" % exits
                    )

    # 索引 → 表（顺序与 §6.3 一致）；12 张表的 lineage_id 列与其值 **一律保留**
    for ddl in PATIENT_TEACHERS_INDEX_DROP_DDL:
        _exec(ddl)
    for ddl in LINEAGE_INDEX_DROP_DDL:
        _exec(ddl)
    _exec("DROP TABLE IF EXISTS lineage")
    print(
        "[0005] downgrade 完成：lineage 表与 idx_lineage_owner / idx_patient_teachers_lineage 已删除；"
        "12 张表的 lineage_id 列与值按裁决 ④ 保留（历史归属事实，不删）"
    )






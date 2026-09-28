"""create templates table + backfill legacy plan_templates

Epic 1「四类模板完整版」第一阶段：Template 模型 + 存量单向回填。

- 对齐：docs/epic1-template-design-v1.md §1（模型）/ §5.2 第 3 条（回填）/ §6.3-§6.4（升降级步骤）
- 涉及存量表：**无**。本 revision 只新建 `templates` + 3 个索引，对 `plan_templates` **只读**（零写入）
  → downgrade 天然无损存量数据。
- 回退方案：`alembic downgrade base`；带安全闸（老师已新建过模板则中止，见 §6.4 第 1 条）。
- 可重跑：CREATE / DROP 一律 IF [NOT] EXISTS，回填用 NOT EXISTS 自证幂等。
- 离线预审：`alembic upgrade head --sql` 输出的 SQL 与联网执行的是**同一批语句**（只有
  「SQLite 版本断言」与「回填计数校验」两处探测在离线模式下跳过，并在输出里注明）。

Revision ID: 0001_create_templates
Revises:
Create Date: 2026-09-28
"""
from datetime import datetime

import sqlalchemy as sa
from alembic import context, op

revision = "0001_create_templates"
down_revision = None
branch_labels = None
depends_on = None

# 【批复 4】存量回填的统一命名与幂等标记（schema_json.meta.legacy_source）
LEGACY_NAME = "施治模板（存量迁移）"
LEGACY_SOURCE = "plan_templates"

# 部分唯一索引依赖 SQLite >= 3.8（实测 3.49.1）。低于该版本直接报错中止，不静默降级成普通索引。
MIN_SQLITE_VERSION = (3, 8, 0)

TEMPLATES_DDL = """
CREATE TABLE IF NOT EXISTS templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL DEFAULT '',
    lineage_id TEXT NOT NULL DEFAULT '',
    teacher_id TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL DEFAULT '',
    schema_json TEXT NOT NULL DEFAULT '{}',
    version INTEGER NOT NULL DEFAULT 1,
    parent_template_id INTEGER,
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT ''
)
"""

INDEX_DDL = (
    # 主力读路径：老师端「按类型列模板 + 更新时间倒序」
    "CREATE INDEX IF NOT EXISTS idx_templates_scope "
    "ON templates (lineage_id, teacher_id, type, status, updated_at DESC)",
    # 版本链查询（沿 parent_template_id 上溯 / 取链内最新版）
    "CREATE INDEX IF NOT EXISTS idx_templates_lineage "
    "ON templates (parent_template_id, version DESC)",
    # 硬约束：同一老师 + 同一师门 + 同一类型最多一条 active
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_templates_active_one "
    "ON templates (lineage_id, teacher_id, type) WHERE status = 'active'",
)

DROP_INDEX_DDL = (
    "DROP INDEX IF EXISTS idx_templates_lineage",
    "DROP INDEX IF EXISTS idx_templates_scope",
    "DROP INDEX IF EXISTS uq_templates_active_one",
)

# 判断某行 schema_json 是否为存量回填行。CASE WHEN 保证「先 json_valid 再 json_extract」的求值顺序，
# 脏数据（非法 JSON）不会让整条语句报错。
_IS_LEGACY = (
    "(CASE WHEN json_valid({alias}.schema_json) "
    "THEN json_extract({alias}.schema_json, '$.meta.legacy_source') END) = 'plan_templates'"
)

# 存量回填主体（幂等：同 scope 已有 legacy 行或已有 active 行则跳过该行）
BACKFILL_SQL = """
INSERT INTO templates
    (type, lineage_id, teacher_id, name, schema_json, version, parent_template_id, status, created_at, updated_at)
SELECT
    'treatment', '', pt.teacher_name, :legacy_name,
    json_object(
        'format', 'text',
        'content', COALESCE(pt.content, ''),
        'placeholders', json_array(),
        'meta', json_object('legacy_source', 'plan_templates')
    ),
    1, NULL, 'active',
    COALESCE(NULLIF(pt.updated_at, ''), :stamp),
    COALESCE(NULLIF(pt.updated_at, ''), :stamp)
FROM plan_templates AS pt
WHERE TRIM(COALESCE(pt.content, '')) <> ''
  AND NOT EXISTS (
      SELECT 1 FROM templates AS t
      WHERE t.type = 'treatment' AND t.teacher_id = pt.teacher_name
        AND {is_legacy_t}
  )
  AND NOT EXISTS (
      SELECT 1 FROM templates AS a
      WHERE a.type = 'treatment' AND a.teacher_id = pt.teacher_name AND a.status = 'active'
  )
""".format(is_legacy_t=_IS_LEGACY.format(alias="t"))

# 回填计数校验用的两条查询（与上面 INSERT 的 WHERE 条件逐条对应，改一处必须改两处）
MARKED_COUNT_SQL = (
    "SELECT COUNT(*) FROM templates "
    "WHERE type = 'treatment' AND status = 'active' AND " + _IS_LEGACY.format(alias="templates")
)

# downgrade 用的计数：不区分 status（存量回填行可能已被后续发布顶替成 archived）
LEGACY_ROWS_COUNT_SQL = (
    "SELECT COUNT(*) FROM templates WHERE type = 'treatment' AND " + _IS_LEGACY.format(alias="templates")
)

ELIGIBLE_SQL = """
SELECT COUNT(*)
FROM plan_templates AS pt
WHERE TRIM(COALESCE(pt.content, '')) <> ''
  AND NOT EXISTS (
      SELECT 1 FROM templates AS t
      WHERE t.type = 'treatment' AND t.teacher_id = pt.teacher_name
        AND {is_legacy_t}
  )
  AND NOT EXISTS (
      SELECT 1 FROM templates AS a
      WHERE a.type = 'treatment' AND a.teacher_id = pt.teacher_name AND a.status = 'active'
  )
""".format(is_legacy_t=_IS_LEGACY.format(alias="t"))


def _exec(sql, **params):
    """统一发出 SQL。

    带参时走 `sa.text().bindparams()`：离线模式（literal_binds=True）会把参数内联，
    保证 `alembic upgrade head --sql` 打印出的就是真正会执行的语句，可直接人工预审。
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


def _sqlite_version_tuple(conn):
    raw = conn.exec_driver_sql("SELECT sqlite_version()").scalar()
    parts = []
    for piece in str(raw).split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3]), raw


def upgrade():
    if context.is_offline_mode():
        _upgrade_offline()
    else:
        _upgrade_online()


def _upgrade_offline():
    # 离线模式只输出 SQL，不做任何数据库探测（§6.5 步骤 ②：上线前人工预审）
    print("-- [0001] offline：SQLite 版本断言与回填计数校验在离线模式下跳过，请人工核对")
    _exec(TEMPLATES_DDL)
    for ddl in INDEX_DDL:
        _exec(ddl)
    _exec(BACKFILL_SQL, legacy_name=LEGACY_NAME, stamp=datetime.now().isoformat())


def _upgrade_online():
    conn = op.get_bind()

    version_tuple, version_raw = _sqlite_version_tuple(conn)
    if version_tuple < MIN_SQLITE_VERSION:
        raise RuntimeError(
            "SQLite 版本过低（%s）：uq_templates_active_one 需要部分唯一索引（>= 3.8）。"
            "本迁移拒绝静默降级成普通索引。" % version_raw
        )
    print("[0001] SQLite %s，开始建 templates 表与索引" % version_raw)

    # 1. 建表（脏库已手建过时靠 IF NOT EXISTS 兜底，不报错）
    if _table_exists(conn, "templates"):
        print("[0001] templates 已存在（脏库），跳过建表")
    _exec(TEMPLATES_DDL)

    # 2. 建索引（先普通后唯一）
    for ddl in INDEX_DDL:
        _exec(ddl)

    # 3. 存量回填：plan_templates(content 非空) → templates(type=treatment, status=active, version=1)
    if not _table_exists(conn, "plan_templates"):
        print("[0001] plan_templates 不存在（全新库），无存量可回填")
        return

    expected = conn.exec_driver_sql(ELIGIBLE_SQL).scalar()
    before = conn.exec_driver_sql(MARKED_COUNT_SQL).scalar()
    _exec(BACKFILL_SQL, legacy_name=LEGACY_NAME, stamp=datetime.now().isoformat())
    after = conn.exec_driver_sql(MARKED_COUNT_SQL).scalar()
    print("[0001] 存量回填：可回填 %d 行，实际插入 %d 行" % (expected, after - before))

    # 4. 收尾校验（§6.3 第 6 条）：数量不符直接抛错 → 整个 upgrade 事务回滚，不留半张表
    if after - before != expected:
        raise RuntimeError(
            "回填数量不一致：应插入 %d 条，实际 %d 条（本 revision 已整体回滚）" % (expected, after - before)
        )


def downgrade():
    if context.is_offline_mode():
        _downgrade_offline()
    else:
        _downgrade_online()


def _downgrade_offline():
    print(
        "-- [0001] offline：安全闸（老师已新建模板时中止降级）无法离线判定，"
        "请人工确认 templates 中除存量回填外无其它数据，再执行以下语句"
    )
    for ddl in DROP_INDEX_DDL:
        _exec(ddl)
    _exec("DROP TABLE IF EXISTS templates")


def _downgrade_online():
    conn = op.get_bind()

    if not _table_exists(conn, "templates"):
        print("[0001] templates 不存在，downgrade 已是目标状态（可重跑）")
        return

    total = conn.exec_driver_sql("SELECT COUNT(*) FROM templates").scalar()
    legacy = conn.exec_driver_sql(LEGACY_ROWS_COUNT_SQL).scalar()
    if total > legacy:
        # 【安全闸】§6.4 第 1 条：不让降级悄悄吃掉老师配好的模板
        raise RuntimeError(
            "downgrade 已中止：templates 中有 %d 行非存量回填数据（老师已新建/发布过模板）。"
            "请先用 GET /api/templates 导出 JSON 备份，或改用 feature flag（TEMPLATE_API_ENABLED=off）回退，"
            "不要直接 drop 表。" % (total - legacy)
        )

    # 普通索引 → 唯一索引 → 表（与 §6.4 的顺序一致）
    for ddl in DROP_INDEX_DDL:
        _exec(ddl)
    _exec("DROP TABLE IF EXISTS templates")
    print("[0001] downgrade 完成：templates 与 3 个索引已删除；plan_templates 原表原数据未动（回填从未写它）")
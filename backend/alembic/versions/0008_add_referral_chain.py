"""C 板块 0008：新增 referral_chain 表与索引。

对齐文档
--------
- 设计文档：docs/phase3-governance-design.md §3.1 数据模型
- 施工骨架：docs/phase3-construction-outline.md §1.2 引荐链
- 白皮书 2.0：§1.6 + §4.2.1 + §4.4.1

纪律
----
- 只新增表 + 索引，不 ALTER 既有表
- 建表 / 建索引一律 IF NOT EXISTS（可重跑）
- downgrade 只 DROP 新表与新索引（TD-003 口径）
- downgrade 安全闸：表内有业务行时中止
- 收尾按 sqlite_master 探测结构完整性

Revision ID: 0008_add_referral_chain
Revises: 0007_add_seal_events
Create Date: 2026-10-02
"""

from alembic import context, op


# ---------- 版本标识 ----------
revision = "0008_add_referral_chain"
down_revision = "0007_add_seal_events"
branch_labels = None
depends_on = None


# ---------- 常量段 ----------
TABLE_NAME = "referral_chain"

TABLE_DDL = """
CREATE TABLE IF NOT EXISTS referral_chain (
    referral_id        TEXT PRIMARY KEY,
    referrer_id        TEXT NOT NULL,
    referrer_type      TEXT NOT NULL,
    referee_id         TEXT NOT NULL,
    referee_type       TEXT NOT NULL,
    lineage_id         TEXT,
    referral_reason    TEXT,
    created_at         TIMESTAMP NOT NULL,
    revoked_at         TIMESTAMP,
    revoke_reason      TEXT,
    chain_ready        BOOLEAN DEFAULT FALSE,
    chain_hash         TEXT
)
"""

ALL_COLUMNS = [
    "referral_id",
    "referrer_id",
    "referrer_type",
    "referee_id",
    "referee_type",
    "lineage_id",
    "referral_reason",
    "created_at",
    "revoked_at",
    "revoke_reason",
    "chain_ready",
    "chain_hash",
]

INDEX_DDL = [
    "CREATE INDEX IF NOT EXISTS idx_referral_chain_referrer "
    "ON referral_chain (referrer_id)",
    "CREATE INDEX IF NOT EXISTS idx_referral_chain_referee "
    "ON referral_chain (referee_id)",
    "CREATE INDEX IF NOT EXISTS idx_referral_chain_lineage "
    "ON referral_chain (lineage_id)",
]

INDEX_NAMES = [
    "idx_referral_chain_referrer",
    "idx_referral_chain_referee",
    "idx_referral_chain_lineage",
]

DROP_INDEX_DDL = [
    "DROP INDEX IF EXISTS idx_referral_chain_referrer",
    "DROP INDEX IF EXISTS idx_referral_chain_referee",
    "DROP INDEX IF EXISTS idx_referral_chain_lineage",
]

DROP_TABLE_DDL = "DROP TABLE IF EXISTS referral_chain"


# ---------- 辅助函数 ----------
def _exec(sql):
    """通过 Alembic op 执行单条 SQL。offline / online 统一走 op.execute。"""
    op.execute(sql)


def _table_exists(table_name):
    """探测表是否已存在（sqlite_master）。"""
    bind = op.get_bind()
    row = bind.exec_driver_sql(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _object_exists(obj_type, obj_name):
    """探测任意 sqlite_master 对象是否已存在。"""
    bind = op.get_bind()
    row = bind.exec_driver_sql(
        "SELECT 1 FROM sqlite_master WHERE type = ? AND name = ?",
        (obj_type, obj_name),
    ).fetchone()
    return row is not None


def _scalar(sql, params=()):
    """执行 SQL 并返回第一行第一列。"""
    bind = op.get_bind()
    row = bind.exec_driver_sql(sql, params).fetchone()
    return row[0] if row else None


# ---------- upgrade ----------
def upgrade():
    if context.is_offline_mode():
        _upgrade_offline()
    else:
        _upgrade_online()


def _upgrade_offline():
    _exec(TABLE_DDL)
    for ddl in INDEX_DDL:
        _exec(ddl)


def _upgrade_online():
    if not _table_exists(TABLE_NAME):
        _exec(TABLE_DDL)

    for ddl in INDEX_DDL:
        _exec(ddl)

    # 结构完整性探测
    if not _table_exists(TABLE_NAME):
        raise RuntimeError(f"[0008] 表 {TABLE_NAME} 创建失败")

    for idx_name in INDEX_NAMES:
        if not _object_exists("index", idx_name):
            raise RuntimeError(f"[0008] 索引 {idx_name} 创建失败")


# ---------- downgrade ----------
def downgrade():
    if context.is_offline_mode():
        _downgrade_offline()
    else:
        _downgrade_online()


def _downgrade_offline():
    for ddl in DROP_INDEX_DDL:
        _exec(ddl)
    _exec(DROP_TABLE_DDL)


def _downgrade_online():
    if not _table_exists(TABLE_NAME):
        return

    # 安全闸：表内有业务行时中止
    row_count = _scalar(f"SELECT COUNT(*) FROM {TABLE_NAME}") or 0
    if row_count > 0:
        raise RuntimeError(
            f"[0008] downgrade 中止：{TABLE_NAME} 有 {row_count} 行业务数据。"
            f"如需强制降级，请先手动清空表。"
        )

    for ddl in DROP_INDEX_DDL:
        _exec(ddl)

    if _table_exists(TABLE_NAME):
        _exec(DROP_TABLE_DDL)
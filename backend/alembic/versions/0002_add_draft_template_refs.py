"""add drafts.template_id / template_version (Epic 1 生成接入)

Epic 1「四类模板完整版」第二阶段：病歷草案記「依哪個模板的哪個版本生成」。

- 對齊：docs/epic1-template-design-v1.md §12.1（schema 變更）/ §12.2（生成接入）/
        §14.1 待確認清單第 5 條（`drafts` 補列走遷移，DDL 單一真相源）。
- 變更範圍：**只** `ALTER TABLE drafts ADD COLUMN` 兩列（`INTEGER DEFAULT 0`，`0` = 未記錄：
  老數據 / 無模板生成）。不改 `plan_templates`、不改 `patient_records`、不碰任何存量行內容。
- 可重跑：`PRAGMA table_info('drafts')` 探測後再補列；`drafts` 不存在（全新庫尚未 init_db）→ 跳過並提示。
- downgrade：**默認不刪列**（§12.1：刪列會丟引用信息）；只把版本號退回 0001，兩列原樣保留。
- 離線預審：`alembic upgrade head --sql`；離線模式下無法探測列是否已存在，此點在輸出裏註明。

Revision ID: 0002_add_draft_template_refs
Revises: 0001_create_templates
Create Date: 2026-09-28
"""
from alembic import context, op

revision = "0002_add_draft_template_refs"
down_revision = "0001_create_templates"
branch_labels = None
depends_on = None

# 兩列與遷移 0001 的 templates 慣例一致：整數 + DEFAULT 0（不加 NOT NULL，存量全庫無此約束）
ADD_COLUMNS = (
    ("template_id", "ALTER TABLE drafts ADD COLUMN template_id INTEGER DEFAULT 0"),
    ("template_version", "ALTER TABLE drafts ADD COLUMN template_version INTEGER DEFAULT 0"),
)


def _exec(sql):
    op.execute(sql)


def _table_exists(conn, name):
    row = conn.exec_driver_sql(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
    ).fetchone()
    return row is not None


def _columns(conn, table):
    return {row[1] for row in conn.exec_driver_sql("PRAGMA table_info('%s')" % table).fetchall()}


def upgrade():
    if context.is_offline_mode():
        _upgrade_offline()
    else:
        _upgrade_online()


def _upgrade_offline():
    print(
        "-- [0002] offline：無法探測列是否已存在（在線模式靠 PRAGMA table_info 冪等）——"
        "若 drafts 已有這兩列，請人工跳過對應語句"
    )
    for column, ddl in ADD_COLUMNS:
        _exec(ddl)
        print("-- [0002] 已輸出：drafts.%s" % column)


def _upgrade_online():
    conn = op.get_bind()

    if not _table_exists(conn, "drafts"):
        print("[0002] drafts 表不存在（全新庫尚未 init_db），無列可補：本 revision 已完成")
        return

    existing = _columns(conn, "drafts")
    added = []
    for column, ddl in ADD_COLUMNS:
        if column in existing:
            print("[0002] drafts.%s 已存在，跳過" % column)
            continue
        _exec(ddl)
        added.append(column)
    print(
        "[0002] drafts 模板引用列就緒（本次新增 %s）；老行由 DEFAULT 0 兜底 = 未記錄"
        % (", ".join(added) if added else "無（已是目標狀態）")
    )


def downgrade():
    # §12.1：SQLite 3.49 支持 DROP COLUMN，但默認不刪列——兩列是「歷史草案的溯源信息」，
    # 刪掉就再也無法還原「這份草案依哪個模板哪個版本生成」。回退只退版本號，列與數據保留。
    print(
        "[0002] downgrade：按設計 §12.1 保留 drafts.template_id / template_version（不刪列），"
        "只回退 alembic 版本號到 0001_create_templates"
    )

"""add patient_records.template_id / template_version（Epic 2 步骤 3.0 · CTO 批复 A1）

Epic 2「老師智能體五階段」：① 一致率指标的 **已签字样本** 必须能按模板归因
（「這份已簽字病歷當初依哪個模板 / 哪個版本生成」）。设计 §3.2 假设 `patient_records`
带模板引用列，实探该表只有 8 列、**无 `template_id`** —— 故按 CTO 2026-09-28 批复 A1
新建本迁移补列，**不做**「按模板 updated_at 近似归因」。

- 变更范围：**只** `ALTER TABLE patient_records ADD COLUMN` 两列（`INTEGER DEFAULT 0`，
  `0` = 未記錄：老數據 / 無模板生成 / 非模板生成鏈路）。不改其他表、不碰存量行內容、
  不建索引（样本筛选是「template_id 等值 + visit_at 区间」，单表行数小，无需索引）。
- 可重跑：`PRAGMA table_info('patient_records')` 探測後再補列；表不存在（全新庫尚未
  init_db）→ 跳過並提示。
- downgrade：**刪列**（A1 批復「downgrade 可删列」）。兩列由 step 3.5 起寫入，回退即放棄
  「已簽字樣本按模板歸因」這一 Epic 2 自有能力，不影響 Epic 1 / 存量鏈路。同樣探測後
  逐列 DROP COLUMN，可重跑。
- 離線預審：`alembic upgrade 0003_add_agent_stage:head --sql`；離線模式無法探測列是否
  已存在，此點在輸出裏註明。

Revision ID: 0004_add_patient_record_template_refs
Revises: 0003_add_agent_stage
Create Date: 2026-09-28
"""
from alembic import context, op

revision = "0004_add_patient_record_template_refs"
down_revision = "0003_add_agent_stage"
branch_labels = None
depends_on = None

TABLE = "patient_records"

# 與 0002 的 drafts 模板引用列慣例一致：整數 + DEFAULT 0（不加 NOT NULL，存量庫無此約束）
ADD_COLUMNS = (
    ("template_id", "ALTER TABLE patient_records ADD COLUMN template_id INTEGER DEFAULT 0"),
    (
        "template_version",
        "ALTER TABLE patient_records ADD COLUMN template_version INTEGER DEFAULT 0",
    ),
)

# 刪列順序與加列相反（後加的先刪），純為可讀性；兩列互不依賴
DROP_COLUMNS = (
    ("template_version", "ALTER TABLE patient_records DROP COLUMN template_version"),
    ("template_id", "ALTER TABLE patient_records DROP COLUMN template_id"),
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
        "-- [0004] offline：無法探測列是否已存在（在線模式靠 PRAGMA table_info 冪等）——"
        "若 patient_records 已有這兩列，請人工跳過對應語句"
    )
    for column, ddl in ADD_COLUMNS:
        _exec(ddl)
        print("-- [0004] 已輸出：patient_records.%s" % column)


def _upgrade_online():
    conn = op.get_bind()

    if not _table_exists(conn, TABLE):
        print("[0004] patient_records 表不存在（全新庫尚未 init_db），無列可補：本 revision 已完成")
        return

    existing = _columns(conn, TABLE)
    added = []
    for column, ddl in ADD_COLUMNS:
        if column in existing:
            print("[0004] patient_records.%s 已存在，跳過" % column)
            continue
        _exec(ddl)
        added.append(column)
    print(
        "[0004] patient_records 模板引用列就緒（本次新增 %s）；老行由 DEFAULT 0 兜底 = 未記錄"
        % (", ".join(added) if added else "無（已是目標狀態）")
    )


def downgrade():
    if context.is_offline_mode():
        _downgrade_offline()
    else:
        _downgrade_online()


def _downgrade_offline():
    print(
        "-- [0004] offline downgrade：刪 patient_records.template_id / template_version；"
        "離線模式無法探測列是否存在，若已刪過請人工跳過"
    )
    for column, ddl in DROP_COLUMNS:
        _exec(ddl)
        print("-- [0004] 已輸出：DROP patient_records.%s" % column)


def _downgrade_online():
    # A1 批復：本 revision 的 downgrade 刪列（0002 的 drafts 引用列「默認不刪」，兩者口徑不同，
    # 因為 patient_records 這兩列是 Epic 2 一致率指標自用的歸因位，非存量業務數據的溯源信息）。
    conn = op.get_bind()

    if not _table_exists(conn, TABLE):
        print("[0004] patient_records 表不存在，無列可刪：本 revision 已完成")
        return

    existing = _columns(conn, TABLE)
    dropped = []
    for column, ddl in DROP_COLUMNS:
        if column not in existing:
            print("[0004] patient_records.%s 不存在，跳過" % column)
            continue
        try:
            _exec(ddl)
        except Exception as exc:  # noqa: BLE001 —— 失敗必須可見，不能靜默當成回退成功
            raise RuntimeError(
                "[0004] patient_records.%s 刪列失敗（SQLite 需 3.35+ 才支持 DROP COLUMN）："
                "%s: %s —— 請手工執行 `%s` 後重跑 downgrade"
                % (column, type(exc).__name__, exc, ddl)
            )
        dropped.append(column)
    print(
        "[0004] patient_records 模板引用列已回退（本次刪除 %s）"
        % (", ".join(dropped) if dropped else "無（已是目標狀態）")
    )

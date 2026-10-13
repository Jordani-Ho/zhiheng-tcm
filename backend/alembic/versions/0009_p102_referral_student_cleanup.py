"""C 板块 0009：P-102 / C1 引荐链清理 —— 删除「学生引荐亲友」的历史数据。

对齐文档
--------
- 施工大纲：docs/phase3-construction-outline.md §P-102（8 删 + 1 迁移）
- 白皮书 v2.1：§4.1.1（L990）「引荐**不是**『审核资格』，是『我愿意为他背书』」
  → 原「学生引荐亲友 · 年度额度 3 位」是**给背书动作装配额闸**，与宪法冲突
- 设计：docs/phase3-governance-design.md §3.3（学生引荐亲友）**已废**

本迁移做什么
------------
**纯数据清理，不改表结构、不加字段。** 学生引荐（`referrer_type='STUDENT'`）
与其产出（`referee_type IN ('STUDENT','DEPENDENT')`）的历史行一并删除。

代码侧的白名单已同时收窄为仅 `TEACHER`：
  · `database.REFERRAL_REFERRER_TYPES = ("TEACHER",)`
  · `database.REFERRAL_REFEREE_TYPES = ("TEACHER",)`
  · 已删 `REFERRAL_ANNUAL_QUOTA` / `count_referrals_by_referrer_in_year`
  · 已删 `referral_service.create_student_referral` / `get_annual_referral_count`
  · 已删 `POST /api/referral/student`

纪律
----
- **可重跑**：DELETE 是幂等的；无匹配行时不报错
- **安全闸（默认不删）**：若表内确有学生引荐行，**默认中止迁移**并要求显式放行 ——
  避免"静默毁数据"。放行方式：设 `P102_PURGE_LEGACY_STUDENT_REFERRALS=on` 后重跑。
- **downgrade 不做数据恢复**：被删的是**宪法冲突的越权数据**，无恢复语义；
  且原始值未留副本（如需留档应在放行前自行导出）。
  故 downgrade 只清 `alembic_version` 标记（no-op 的显式声明）。

Revision ID: 0009_p102_referral_student_cleanup
Revises: 0008_add_referral_chain
Create Date: 2026-10-12
"""

import os

from alembic import context, op


# ---------- 版本标识 ----------
revision = "0009_p102_referral_student_cleanup"
down_revision = "0008_add_referral_chain"
branch_labels = None
depends_on = None


# ---------- 常量段 ----------
TABLE_NAME = "referral_chain"

# 放行开关：只有显式设成这些值之一才允许删数据
_PURGE_ENV = "P102_PURGE_LEGACY_STUDENT_REFERRALS"
_PURGE_ENABLED_VALUES = ("on", "1", "true", "yes")

# 「学生引荐」的历史行判据：引荐人是学生，**或被引荐人是学生/被监护人**
# （后者只可能由学生引荐路径产出 —— 老师引荐老师的 referee_type 只会是 TEACHER）
COUNT_LEGACY_SQL = (
    "SELECT COUNT(*) FROM " + TABLE_NAME
    + " WHERE referrer_type = 'STUDENT' OR referee_type IN ('STUDENT', 'DEPENDENT')"
)

DELETE_LEGACY_SQL = (
    "DELETE FROM " + TABLE_NAME
    + " WHERE referrer_type = 'STUDENT' OR referee_type IN ('STUDENT', 'DEPENDENT')"
)


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


def _scalar(sql):
    """执行 SQL 并返回第一行第一列。"""
    bind = op.get_bind()
    row = bind.exec_driver_sql(sql).fetchone()
    return row[0] if row else None


def _purge_allowed():
    return os.environ.get(_PURGE_ENV, "").strip().lower() in _PURGE_ENABLED_VALUES


# ---------- upgrade ----------
def upgrade():
    if context.is_offline_mode():
        _upgrade_offline()
    else:
        _upgrade_online()


def _upgrade_offline():
    """offline（--sql 模式）：表可能不存在于执行环境，直接发 DELETE。

    注：offline 模式无法探测表/行数，也不该做交互式中止 —— 由使用方保证环境。
    """
    _exec(DELETE_LEGACY_SQL)


def _upgrade_online():
    # 表不存在（早于 0008 的库）：无需清理，幂等返回
    if not _table_exists(TABLE_NAME):
        return

    legacy = _scalar(COUNT_LEGACY_SQL) or 0

    if legacy == 0:
        # 最常见的路径：本就无学生引荐数据（实测真库当前 = 0 行）
        return

    if not _purge_allowed():
        raise RuntimeError(
            "%s 中有 %d 行「学生引荐」历史数据（P-102 决定删除）。\n"
            "为避免静默毁数据，本迁移**默认中止**。\n"
            "确认要删除后，请显式放行再重跑：\n"
            "    set %s=on        （Windows cmd）\n"
            "    $env:%s='on'     （PowerShell）\n"
            "    export %s=on     （bash）\n"
            "如需留档，请在放行前先导出这些行。"
            % (TABLE_NAME, legacy, _PURGE_ENV, _PURGE_ENV, _PURGE_ENV)
        )

    _exec(DELETE_LEGACY_SQL)

    # 收尾探测：确认已清空（不静默放过）
    remain = _scalar(COUNT_LEGACY_SQL) or 0
    if remain != 0:
        raise RuntimeError(
            "P-102 清理未完成：%s 中仍有 %d 行学生引荐数据" % (TABLE_NAME, remain)
        )


# ---------- downgrade ----------
def downgrade():
    """**不做数据恢复**（显式声明，非遗漏）。

    被删的是与白皮书 §4.1.1 冲突的越权数据（学生引荐亲友 + 年度额度），
    删除是**单向**决策；且原始行未留副本，无法也不应自动恢复。
    如需回滚，须先从备份恢复数据，再改回白皮书与代码 —— 属人工流程。

    故本函数为空：Alembic 会把版本号退回 0008，数据保持已清理状态。
    """
    return

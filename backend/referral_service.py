"""C 板块「引荐链」的服务层：业务规则 + 库层薄封装（零 SQL、零 sqlite3）。

对齐：docs/phase3-governance-design.md §3（引荐链）
  §3.1  数据模型（12 列，0008 迁移落盘）
  §3.2  老师引荐老师：referral_reason 必填，不得自引荐
  §3.3  学生引荐亲友：额度 3 位/年，可自理 / 不能自理两分支
  §3.4  引荐人信誉降级：不连坐，只降级
  §3.5  上链预留：chain_ready / chain_hash（本步不写）

CTO 2026-10-02 施工裁决（本文件的依据）：
  · 本步 = 服务层骨架：create_teacher_referral / create_student_referral /
    revoke_referral / 5 个查询转发；不写 API（下一条指令）、不写测试（再下一条）。
  · 分层（同 learning_service）：SQL 全在 database.py；本文件零 SQL 字面量、
    零 import sqlite3；database 层 7 原语只做薄转发。
  · 信誉降级（§3.4）：本步不落 `downgrade_referrer_reputation`。理由：
    信誉模型不在 C 板块交付范围内；B 板块除名流程尚未实现；现在落会成为无调用方的占位。
    登记为 C 板块 v0.6 待办。§3.4 的降级动作由 B 板块在除名流程里调
    `list_referrals_by_referee(referee_id)` 查引荐人后自行执行。
"""
from datetime import datetime


# ---------------------------------------------------------------------------
# 库层薄封装（同 learning_service._db）
# ---------------------------------------------------------------------------
def _db():
    """延迟取 database 模块：SQL / 连接 / row_factory 全在 database.py 单点持有。

    本模块只允许碰 database 的 7 个 referral 原语（C 板块 0008 落盘）：
      insert_referral_chain / get_referral / get_referrals_by_referrer /
      get_referrals_by_referee / get_referrals_by_lineage /
      count_referrals_by_referrer_in_year / revoke_referral。
    """
    import database
    return database


# ---------------------------------------------------------------------------
# 老师引荐老师（§3.2）
# ---------------------------------------------------------------------------
def create_teacher_referral(referrer_id, referee_id, referral_reason,
                            lineage_id=None, created_at=None):
    """老师引荐老师 → 新 referral_id。

    业务规则（database 层已校验，本函数不重复）：
      · referral_reason 必填；
      · referrer_id != referee_id（不得自引荐）；
      · referrer_type 固定 TEACHER，referee_type 固定 TEACHER。

    database 层负责：入参校验 + ID 生成 + 落盘。
    """
    return _db().insert_referral_chain(
        referrer_id=referrer_id,
        referrer_type="TEACHER",
        referee_id=referee_id,
        referee_type="TEACHER",
        lineage_id=lineage_id,
        referral_reason=referral_reason,
        created_at=created_at,
    )


# ---------------------------------------------------------------------------
# 学生引荐亲友（§3.3）
# ---------------------------------------------------------------------------
def create_student_referral(referrer_id, referee_id, referee_type="STUDENT",
                            lineage_id=None, created_at=None, year=None):
    """学生引荐亲友 → 新 referral_id。

    业务规则（本函数负责）：
      · referee_type ∈ {STUDENT, DEPENDENT}（学生不能引荐老师）；
      · 额度：同一年内，同一 referrer_id 最多 3 条；
      · 可自理者 → referee_type="STUDENT"；
        不能自理者/未成年人 → referee_type="DEPENDENT"。

    year：年份参数（默认当年）；用于测试注入。
    """
    if referee_type not in ("STUDENT", "DEPENDENT"):
        raise ValueError(
            "create_student_referral 的 referee_type 必须是 STUDENT 或 DEPENDENT，实得：%r"
            % (referee_type,)
        )
    if not referrer_id:
        raise ValueError("create_student_referral 必须给 referrer_id")
    if not referee_id:
        raise ValueError("create_student_referral 必须给 referee_id")

    db = _db()
    quota = db.REFERRAL_ANNUAL_QUOTA
    target_year = int(year) if year is not None else datetime.now().year
    used = db.count_referrals_by_referrer_in_year(referrer_id, target_year)
    if used >= quota:
        raise ValueError(
            "create_student_referral：引荐人 %r 在 %d 年的引荐额度已满（%d/%d）"
            % (referrer_id, target_year, used, quota)
        )

    return db.insert_referral_chain(
        referrer_id=referrer_id,
        referrer_type="STUDENT",
        referee_id=referee_id,
        referee_type=referee_type,
        lineage_id=lineage_id,
        referral_reason=None,
        created_at=created_at,
    )


# ---------------------------------------------------------------------------
# 撤回背书（§3.4 引荐人主动撤回 = 无影响）
# ---------------------------------------------------------------------------
def revoke_referral(referral_id, revoke_reason=None):
    """撤回一条引荐（软撤回：写 revoked_at + revoke_reason，不删行）。

    database 层负责：存在性校验 + 重复撤回校验 + 落盘。
    """
    return _db().revoke_referral(referral_id, revoke_reason)


# ---------------------------------------------------------------------------
# 查询转发（5 个）
# ---------------------------------------------------------------------------
def get_referral(referral_id):
    """单条查询。不存在 → None。"""
    return _db().get_referral(referral_id)


def list_referrals_by_referrer(referrer_id, limit=None):
    """查某引荐人引荐过谁 → [dict]，按 created_at 倒序。"""
    return _db().get_referrals_by_referrer(referrer_id, limit)


def list_referrals_by_referee(referee_id, limit=None):
    """查某被引荐人被谁引荐 → [dict]，按 created_at 倒序。

    用途（§3.4）：B 板块除名流程查「谁引荐的」，据此自行处理信誉降级。
    """
    return _db().get_referrals_by_referee(referee_id, limit)


def list_referrals_by_lineage(lineage_id, limit=None):
    """查某师门内的引荐链 → [dict]，按 created_at 倒序。"""
    return _db().get_referrals_by_lineage(lineage_id, limit)


def get_annual_referral_count(referrer_id, year=None):
    """某引荐人在某年的引荐总数（默认当年）。用于额度查看。"""
    target_year = int(year) if year is not None else datetime.now().year
    return _db().count_referrals_by_referrer_in_year(referrer_id, target_year)
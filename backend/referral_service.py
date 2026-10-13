"""C 板块「引荐链」的服务层：业务规则 + 库层薄封装（零 SQL、零 sqlite3）。

对齐：docs/phase3-governance-design.md §3（引荐链）
  §3.1  数据模型（12 列，0008 迁移落盘）
  §3.2  老师引荐老师：referral_reason 必填，不得自引荐
  §3.3  学生引荐亲友：**已整体删除**（P-102 / C1 清理，见下方删除说明）
  §3.4  引荐人信誉降级：不连坐，只降级
  §3.5  上链预留：chain_ready / chain_hash（本步不写）
  【现仅存】§3.2 老师引荐老师 —— 引荐人只可能是老师、被引荐人也只可能是老师。

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

    本模块只允许碰 database 的 referral 原语（C 板块 0008 落盘；**P-102 后为 6 个**）：
      insert_referral_chain / get_referral / get_referrals_by_referrer /
      get_referrals_by_referee / get_referrals_by_lineage / revoke_referral。
      （原有第 7 个 `count_referrals_by_referrer_in_year` 随「年度额度」一起删除了——
        额度与宪法 §4.1.1「引荐不是审核资格」冲突，见本文件 §学生引荐亲友 的删除说明。）
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
# 【P-102 / C1 清理 / D-089】学生引荐亲友（§3.3）**已整体删除**
# ---------------------------------------------------------------------------
# 删除理由（三重）：
#   ① **宪法冲突**：白皮书 v2.1 §4.1.1（L990）逐字「引荐**不是**『审核资格』，是
#      『我愿意为他背书』」——而本条带「年度额度 3 位」的配额闸，**额度就是一种审核**。
#   ② **白皮书未定义额度**：§4.3.1 L1053 只说「单向、一次性」，是逐次语义，不是年度配额。
#   ③ **越权面**：`POST /api/referral/student` 可被学生调用凭空建引荐记录。
# 一并删除：`create_student_referral` / `REFERRAL_ANNUAL_QUOTA` /
#           `count_referrals_by_referrer_in_year` / `get_annual_referral_count`
#           （后两者只服务额度校验，实测**全仓零调用方**）。
# 迁移 `0009` 负责清理白名单与历史数据。**本区段不得重新引入。**


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


# 【P-102 / D-089】`get_annual_referral_count`（原 L146-149）**已删**：
# 它只封装 `database.count_referrals_by_referrer_in_year`（额度计数），
# 而额度校验随学生引荐一起删除 → 该函数成为死代码。
# 核实依据：全仓检索该符号，**除定义处外零引用**（无调用方、无测试）。
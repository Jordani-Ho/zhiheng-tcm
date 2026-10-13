"""C 板塊「引薦鏈」API：老師引薦 / 查詢 / 撤回（前綴 `/api/referral`）。

對齊：docs/phase3-governance-design.md §9.1
  · POST /api/referral/teacher            老師引薦老師
  · GET  /api/referral/chain/{agent_id}   雙向引薦鏈查詢
  · GET  /api/referral/{referral_id}      單條查詢
  · POST /api/referral/{referral_id}/revoke  撤回背書

【P-102 / D-089】原「POST /api/referral/student 學生引薦親友」**已刪除**（越權面 + 憲法衝突）。

落地分工（照 seal_api 同款）：
  · 本文件只做四件事 —— 門衛 → 入參校驗 → 調用 referral_service → 統一錯誤體；
    零 SQL、零 DDL、零業務判定（業務規則在 referral_service）；
  · feature flag `REFERRAL_ENABLED`（**默認 off**）：off → 全部端點 404 `referral_disabled`，
    既有鏈路一字不改；flag **每次請求現讀**；
  · 錯誤體：`{"detail": {"error": code, "msg": ...}}`（與 seal_api 同款）；
  · 本文件用 `HTTPException` 直出、**無**自定義異常類。

啟用方式（本機 / 生產，PowerShell）：
    $env:REFERRAL_ENABLED = "on"    # 不設或 off = 全部 404
"""
from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/referral", tags=["referral"])

# 錯誤碼 → HTTP 狀態碼
_REFERRAL_ERROR_STATUS = {
    "referral_disabled": 404,
    "referrer_required": 400,
    "referee_required": 400,
    "reason_required": 400,
    "self_referral": 400,
    "referee_type_invalid": 400,
    "quota_exceeded": 400,
    "referral_invalid": 400,
    "referral_not_found": 404,
    "already_revoked": 400,
}

_ENABLED_VALUES = ("on", "1", "true", "yes")

# 【P-102 / D-089】原 `_REFEREE_TYPES = ("STUDENT", "DEPENDENT")` 已删
# —— 它只服务已删除的学生引荐端点，删除后成为死代码。


def _fail(status_code, code, msg):
    """統一錯誤體：`{"detail": {"error", "msg"}}`（照 seal_api._fail）。"""
    raise HTTPException(status_code=status_code, detail={"error": code, "msg": msg})


def _fail_code(code, msg):
    """按 `_REFERRAL_ERROR_STATUS` 取真實 HTTP 狀態碼（表外的碼兜底 400）。"""
    _fail(_REFERRAL_ERROR_STATUS.get(code, 400), code, msg)


def _guard():
    """每個接口的第一道門：flag off → 404 `referral_disabled`。"""
    enabled = os.environ.get("REFERRAL_ENABLED", "off").strip().lower() in _ENABLED_VALUES
    if not enabled:
        _fail_code("referral_disabled", "referral api disabled")


# ---------------------------------------------------------------------------
# 請求體（**本文件自帶**：字段全給默認值 —— 缺字段走「校驗失敗」而非 422，
# 保證 flag 關閉態的 404 不被 FastAPI 的 422 蓋掉）
# ---------------------------------------------------------------------------
class TeacherReferralInput(BaseModel):
    """`POST /teacher`：老師引薦老師（referral_reason 必填）。"""
    referrer_id: str = ""
    referee_id: str = ""
    referral_reason: str = ""
    lineage_id: str = ""


# 【P-102 / D-089】原 `StudentReferralInput` 已删 —— 它只服务已删除的学生引荐端点。


class RevokeInput(BaseModel):
    """`POST /{referral_id}/revoke`：撤回背書（revoke_reason 可省）。"""
    revoke_reason: str = ""


# ---------------------------------------------------------------------------
# 端點（顺序：具体路径在泛化路径之前）
# ---------------------------------------------------------------------------
@router.post("/teacher")
def create_teacher_referral(data: TeacherReferralInput):
    """老師引薦老師 → 返回新 referral_id。"""
    import referral_service
    _guard()
    if not data.referrer_id:
        _fail_code("referrer_required", "referrer_id required")
    if not data.referee_id:
        _fail_code("referee_required", "referee_id required")
    if data.referrer_id == data.referee_id:
        _fail_code("self_referral", "referrer_id and referee_id must differ")
    if not data.referral_reason:
        _fail_code("reason_required", "referral_reason required for teacher referral")
    referral_id = referral_service.create_teacher_referral(
        referrer_id=data.referrer_id,
        referee_id=data.referee_id,
        referral_reason=data.referral_reason,
        lineage_id=data.lineage_id or None,
    )
    return {"referral_id": referral_id}


# 【P-102 / C1 清理 / D-089】`POST /api/referral/student`（學生引薦親友）**已整體刪除**。
# 理由：
#   ① 白皮書 v2.1 §4.1.1（L990）逐字「引薦**不是**『審核資格』，是『我願意為他背書』」
#      —— 該端點帶「年度額度 3 位」配額閘，**額度即審核**，與憲法衝突；
#   ② §4.3.1 L1053 只說「單向、一次性」，是逐次語義，**不是年度配額**；
#   ③ 越權面：學生可調用它憑空建立引薦記錄。
# 一併刪除：`StudentReferralInput` 模型 與 `_REFEREE_TYPES` 常量。
# 遷移 `0009` 負責清理歷史數據。**本端點不得重新引入。**
# 遷移 `0009` 負責清理歷史數據。**本端點不得重新引入。**


@router.get("/chain/{agent_id}")
def get_referral_chain(agent_id: str, direction: str = "both"):
    """雙向引薦鏈查詢。

    direction ∈ {as_referrer, as_referee, both}（默認 both）。
    """
    import referral_service
    _guard()
    if not agent_id:
        _fail_code("referrer_required", "agent_id required")
    result = {}
    if direction in ("as_referrer", "both"):
        result["as_referrer"] = referral_service.list_referrals_by_referrer(agent_id)
    if direction in ("as_referee", "both"):
        result["as_referee"] = referral_service.list_referrals_by_referee(agent_id)
    return result


@router.get("/{referral_id}")
def get_referral(referral_id: str):
    """單條查詢。不存在 → 404 `referral_not_found`。"""
    import referral_service
    _guard()
    row = referral_service.get_referral(referral_id)
    if row is None:
        _fail_code("referral_not_found", "referral_id not found")
    return row


@router.post("/{referral_id}/revoke")
def revoke_referral(referral_id: str, data: RevokeInput):
    """撤回一條引薦（軟撤回）。"""
    import referral_service
    _guard()
    try:
        referral_service.revoke_referral(referral_id, data.revoke_reason or None)
    except ValueError as exc:
        msg = str(exc)
        if "不存在" in msg:
            _fail_code("referral_not_found", msg)
        if "已撤回" in msg:
            _fail_code("already_revoked", msg)
        _fail_code("referral_invalid", msg)
    return {"revoked": True, "referral_id": referral_id}
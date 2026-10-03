"""C 板塊「引薦鏈」API：老師引薦 / 學生引薦 / 查詢 / 撤回（前綴 `/api/referral`）。

對齊：docs/phase3-governance-design.md §9.1
  · POST /api/referral/teacher            老師引薦老師
  · POST /api/referral/student            學生引薦親友
  · GET  /api/referral/chain/{agent_id}   雙向引薦鏈查詢
  · GET  /api/referral/{referral_id}      單條查詢
  · POST /api/referral/{referral_id}/revoke  撤回背書

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

_REFEREE_TYPES = ("STUDENT", "DEPENDENT")


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


class StudentReferralInput(BaseModel):
    """`POST /student`：學生引薦親友（referee_type 默認 STUDENT）。"""
    referrer_id: str = ""
    referee_id: str = ""
    referee_type: str = "STUDENT"
    lineage_id: str = ""


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


@router.post("/student")
def create_student_referral(data: StudentReferralInput):
    """學生引薦親友 → 返回新 referral_id。"""
    import referral_service
    _guard()
    if not data.referrer_id:
        _fail_code("referrer_required", "referrer_id required")
    if not data.referee_id:
        _fail_code("referee_required", "referee_id required")
    if data.referee_type not in _REFEREE_TYPES:
        _fail_code("referee_type_invalid", "referee_type must be STUDENT or DEPENDENT")
    try:
        referral_id = referral_service.create_student_referral(
            referrer_id=data.referrer_id,
            referee_id=data.referee_id,
            referee_type=data.referee_type,
            lineage_id=data.lineage_id or None,
        )
    except ValueError as exc:
        msg = str(exc)
        if "額度" in msg or "额度" in msg or "quota" in msg.lower():
            _fail_code("quota_exceeded", msg)
        _fail_code("referral_invalid", msg)
    return {"referral_id": referral_id}


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
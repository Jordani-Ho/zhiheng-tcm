"""B 板塊 B5-b「數據封存 API」：封存事件查詢 + 手動觸發（前綴 `/api/seal`）。

對齊：docs/phase2-data-sovereignty-design.md §3.5（數據封存）
  §3.5.1（階段二只做「封存事件記錄 + 查詢 + 手動觸發」，不自動判定 / 不攔截 / 不實際上鏈）
  §3.5.4（`seal_events` DDL 唯一真相源 = 遷移 0007；本文件只調用 `database` 的增 / 讀原語）
  §3.5.5（`action` 取值只含 `seal` / `readmit`，**不含** `remove` —— 除名事件未定義）
  §3.5.6（API 契約：`GET /api/seal/events` + `POST /api/seal/trigger`；flag `SEAL_ENABLED` 默認 off）

落地分工（照 crypto_api / export_api 同款）：
  · 本文件只做四件事 —— 門衛 → 入參校驗 → 調用 `database` 原語 → 統一錯誤體；
    零 SQL、零 DDL、零業務判定；
  · feature flag `SEAL_ENABLED`（**默認 off**）：off → 兩個端點一律 404 `seal_disabled`，
    既有鏈路一字不改；flag **每次請求現讀**（便於灰度切換 / 測試，不必重啟）；
  · 錯誤體：`{"detail": {"error": code, "msg": ...}}`（與 learning_api §7.3 / crypto_api / export_api 同款）；
  · 本文件用 `HTTPException` 直出、**無**自定義異常類
    → main.py 不需要 `add_exception_handler`。

階段邊界（§3.5.7，留給階段四）：
  · `subject_mismatch`（403）/ `subject_not_found`（404）錯誤碼**已預留但本步不校驗** ——
    階段二不查 `patients` / `teachers` 存在性，也不做身份配對；
  · `chain_ready` / `chain_hash` 本步**不填值**（建表默認 FALSE / NULL），填充歸階段四。

啟用方式（本機 / 生產，PowerShell）：
    $env:SEAL_ENABLED = "on"    # 不設或 off = 全部 404
"""
from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/seal", tags=["seal"])

# 錯誤碼 → HTTP 狀態碼（照 export_api._EXPORT_ERROR_STATUS 同款形態）
_SEAL_ERROR_STATUS = {
    "seal_disabled": 404,
    "subject_required": 400,
    "subject_mismatch": 403,
    "action_invalid": 400,
    "subject_not_found": 404,
}

# flag 的「開啟」取值（與 crypto_api / export_api 同款口徑）
_ENABLED_VALUES = ("on", "1", "true", "yes")

# 主體類型 / 動作白名單（真相源在 §3.5.4 / §3.5.5，與 database 層同口徑）
_SUBJECT_TYPES = ("patient", "teacher")
_ACTIONS = ("seal", "readmit")


def _fail(status_code, code, msg):
    """統一錯誤體：`{"detail": {"error", "msg"}}`（照 export_api._fail）。"""
    raise HTTPException(status_code=status_code, detail={"error": code, "msg": msg})


def _fail_code(code, msg):
    """按 `_SEAL_ERROR_STATUS` 取真實 HTTP 狀態碼（表外的碼兜底 400）。"""
    _fail(_SEAL_ERROR_STATUS.get(code, 400), code, msg)


def _guard():
    """每個接口的第一道門：flag off → 404 `seal_disabled`（無任何其他副作用）。"""
    enabled = os.environ.get("SEAL_ENABLED", "off").strip().lower() in _ENABLED_VALUES
    if not enabled:
        _fail_code("seal_disabled", "seal api disabled")


# ---------------------------------------------------------------------------
# 請求體（**本文件自帶**：字段全給默認值 —— 缺字段走「校驗失敗」而非 422，
# 保證 flag 關閉態的 404 不被 FastAPI 的 422 蓋掉；照 crypto_api 同款口徑）
# ---------------------------------------------------------------------------
class SealTriggerInput(BaseModel):
    """`POST /trigger`：`reason` / `operator` 可省（空串 → 落 NULL）。"""

    subject_type: str = ""
    subject_name: str = ""
    action: str = ""
    reason: str = ""
    operator: str = ""


# ---------------------------------------------------------------------------
# 1. 封存事件查詢
# ---------------------------------------------------------------------------
@router.get("/events")
def get_events(subject_type: str = "", subject_name: str = ""):
    """§3.5.6：列出某主體（`patient` / `teacher`）的封存 / 重新接納歷史（`id` 倒序）。

    階段二只按 `subject_type` + `subject_name` 過濾，**不查存在性**（`subject_not_found`
    留給階段四）；無事件 → 200 + `{"events": [], "total": 0}`（空集不是錯誤）。
    """
    import database  # 延遲 import，參照 export_api.export_patient 風格

    _guard()
    if not subject_type or not subject_name:
        _fail_code("subject_required", "subject_type and subject_name required")
    if subject_type not in _SUBJECT_TYPES:
        _fail_code("action_invalid", "subject_type must be patient or teacher")
    events = database.get_seal_events(subject_type, subject_name)
    return {"events": events, "total": len(events)}


# ---------------------------------------------------------------------------
# 2. 手動觸發封存 / 重新接納
# ---------------------------------------------------------------------------
@router.post("/trigger")
def trigger_event(data: SealTriggerInput):
    """§3.5.6：手動追加一條封存事件（`seal` / `readmit`），返回新行 `id`。

    本步**只記錄**：不自動判定、不攔截、不實際上鏈（§3.5.1）；`chain_*` 兩列留空。
    """
    import database  # 延遲 import，參照 export_api.export_patient 風格

    _guard()
    if not data.subject_type or not data.subject_name:
        _fail_code("subject_required", "subject_type and subject_name required")
    if data.subject_type not in _SUBJECT_TYPES:
        _fail_code("action_invalid", "subject_type must be patient or teacher")
    if data.action not in _ACTIONS:
        _fail_code("action_invalid", "action must be seal or readmit")
    event_id = database.insert_seal_event(
        subject_type=data.subject_type,
        subject_name=data.subject_name,
        action=data.action,
        reason=data.reason or None,
        operator=data.operator or None,
    )
    return {"event_id": event_id}

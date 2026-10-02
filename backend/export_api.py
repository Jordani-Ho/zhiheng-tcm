"""B 板塊 B4-1「學生數據導出 API」：一次性打包某位學生的全部資料（前綴 `/api/export`）。

設計要點：
  · feature flag `EXPORT_ENABLED`（**默認 off**）：off → 端點一律 404 `export_disabled`，
    既有鏈路一字不改；flag **每次請求現讀**（便於灰度切換 / 測試，不必重啟）；
  · 身份校驗：`patient_name` + `patient_id` 必須**成對出現且相等**（與全庫鑑權口徑一致）；
  · 錯誤體：`{"detail": {"error": code, "msg": ...}}`（與 learning_api §7.3 / crypto_api 同款）；
  · 本文件用 `HTTPException` 直出、**無**自定義異常類
    → main.py 不需要 `add_exception_handler`（照 crypto_api 的落地分工）；
  · 純只讀：全部數據來自 `database.py` 的 `get_*_by_patient` 只讀原語，零寫入 / 零 DDL。

啟用方式（本機 / 生產，PowerShell）：
    $env:EXPORT_ENABLED = "on"    # 不設或 off = 全部 404
"""
from __future__ import annotations

import os
from datetime import datetime

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/export", tags=["export"])

# 錯誤碼 → HTTP 狀態碼（照 learning_api._LEARNING_ERROR_STATUS 同款形態）
_EXPORT_ERROR_STATUS = {
    "export_disabled": 404,
    "patient_required": 400,
    "patient_mismatch": 403,
    "patient_not_found": 404,
}

# flag 的「開啟」取值（與 crypto_api._ENABLED_VALUES 同款口徑）
_ENABLED_VALUES = ("on", "1", "true", "yes")


def _fail(status_code, code, msg):
    """統一錯誤體：`{"detail": {"error", "msg"}}`（照 learning_api._fail）。"""
    raise HTTPException(status_code=status_code, detail={"error": code, "msg": msg})


def _guard():
    """每個接口的第一道門：flag off → 404 `export_disabled`（無任何其他副作用）。"""
    enabled = os.environ.get("EXPORT_ENABLED", "off").strip().lower() in _ENABLED_VALUES
    if not enabled:
        _fail(_EXPORT_ERROR_STATUS["export_disabled"], "export_disabled", "export api disabled")


def _check_identity(patient_name, patient_id):
    """身份校驗：`patient_name` 與 `patient_id` 必須成對出現且一致（缺 → 400，不一致 → 403）。"""
    if not patient_name or not patient_id:
        _fail(_EXPORT_ERROR_STATUS["patient_required"], "patient_required",
              "patient_name and patient_id required")
    if patient_name != patient_id:
        _fail(_EXPORT_ERROR_STATUS["patient_mismatch"], "patient_mismatch",
              "patient_name != patient_id")


@router.get("/patient")
def export_patient(patient_name: str = "", patient_id: str = ""):
    """一次性導出某位學生的全部資料（唯讀）。

    返回 bundle（14 鍵）：`version` / `exported_at` / `patient_name` / `patient` /
    `profile` / `teachers` / `transcriptions` / `drafts` / `records` / `prescriptions` /
    `homework` / `appointments` / `record_tags` / `complaints`。
    """
    import database  # 延遲 import，參照 learning_service._db() 風格

    _guard()
    _check_identity(patient_name, patient_id)

    patient = database.get_patient_by_name(patient_name)
    if not patient:
        _fail(_EXPORT_ERROR_STATUS["patient_not_found"], "patient_not_found",
              "patient %s not found" % patient_name)

    return {
        "version": "1",
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "patient_name": patient_name,
        "patient": patient,
        "profile": database.get_patient_profile(patient_name),
        "teachers": database.get_patient_teachers(patient_name),
        "transcriptions": database.get_transcriptions_by_patient(patient_name),
        "drafts": database.get_drafts_by_patient(patient_name),
        "records": database.get_patient_records_by_patient(patient_name),
        "prescriptions": database.get_prescriptions_by_patient(patient_name),
        "homework": database.get_homework_by_patient(patient_name),
        "appointments": database.get_appointments_by_patient(patient_name),
        "record_tags": database.get_record_tags_by_patient(patient_name),
        "complaints": database.get_complaints_by_patient(patient_name),
    }

"""師門（lineage）接口層（Epic 4 · 設計 §4.1 / §4.3 / §4.4）

對齊：docs/epic4-lineage-design-v1.md
  §4.1  錯誤碼契約：8 個碼 → HTTP 狀態碼（映射的唯一真相源在 `lineage_service.LINEAGE_ERROR_STATUS`）
  §4.3  既有接口改造：老師端讀接口**路徑不變**，只新增可選查詢參數 `lineage_id`，
        缺 → 400 `lineage_required`（**不許**退化為全量）；flag off → 零行為變化
  §4.4  feature flag `LINEAGE_ENABLED` 默認 off

本文件當前職責（施工步驟 4.2「服務層隔離讀路徑」子步）：
  1. 把服務層拋出的 `LineageError` 翻譯成**真實 HTTP 狀態碼 + 統一錯誤體**
     （`{"detail": {"error", "msg", "errors", "warnings"}}`）—— 註冊點在 `main.py`
     （`app.add_exception_handler`，與 Epic 1 `template_error_handler` 同款）；
  2. 提供 `_fail()`：供後續 `/api/lineages*` / `/api/student-lineages*` 七個新接口
     （§4.2）復用同一錯誤體形狀。

**本子步尚未新增任何路由**：`router` 目前為空（掛載後等於無操作），
§4.2 的 7 個端點（全部 flag 門後、第一道 = 404 `lineage_disabled`）由 4.2 的後續子步在本文件落地。

啟用方式（本機 / 生產，PowerShell）：
    $env:LINEAGE_ENABLED = "on"    # 不設或 off = 隔離不生效，既有鏈路逐字節不變
"""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

import lineage_service

router = APIRouter(tags=["lineage"])


async def lineage_error_handler(request: Request, exc: lineage_service.LineageError):
    """服務層 `LineageError` → 真實 HTTP 狀態碼 + 統一 detail 包裝（§4.1）。

    狀態碼**不**在本文件另寫一份映射表：直接問服務層的 `lineage_error_status()`
    （8 個碼的唯一真相源在 `lineage_service.LINEAGE_ERROR_STATUS`，未知碼按 400）
    —— 這與 `template_api._TEMPLATE_ERROR_STATUS` 的「映射表放接口層」寫法形狀相同，
    但避免了 Epic 4 兩個文件各存一份碼表、改一處漏一處。
    """
    return JSONResponse(
        status_code=lineage_service.lineage_error_status(exc.code),
        content={"detail": exc.detail()},
    )


def _fail(status_code, code, msg, errors=None, warnings=None):
    """統一錯誤體（§4.1 首段）：真 HTTP 狀態碼 + `{error, msg, errors, warnings}` 四鍵。

    與 `template_api._fail` 同形狀（前端只認 `res.detail.error` 這一個鍵）。
    """
    raise HTTPException(
        status_code=status_code,
        detail={"error": code, "msg": msg, "errors": errors or [], "warnings": warnings or []},
    )

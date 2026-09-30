"""師門（lineage）接口層（Epic 4 · 設計 §4.1 / §4.3 / §4.4）

對齊：docs/epic4-lineage-design-v1.md
  §4.1  錯誤碼契約：8 個碼 → HTTP 狀態碼（映射的唯一真相源在 `lineage_service.LINEAGE_ERROR_STATUS`）
  §4.3  既有接口改造：老師端讀接口**路徑不變**，只新增可選查詢參數 `lineage_id`，
        缺 → 400 `lineage_required`（**不許**退化為全量）；flag off → 零行為變化
  §4.4  feature flag `LINEAGE_ENABLED` 默認 off

本文件當前職責（施工步驟 4.2 的「接口層」子步）：
  1. 把服務層拋出的 `LineageError` 翻譯成**真實 HTTP 狀態碼 + 統一錯誤體**
     （`{"detail": {"error", "msg", "errors", "warnings"}}`）—— 註冊點在 `main.py`
     （`app.add_exception_handler`，與 Epic 1 `template_error_handler` 同款）；
  2. `_fail()`：本文件內部的統一錯誤體出口；
  3. **§4.2 的 7 個新路由**（本子步落地，全部 flag 門後、第一道 = 404 `lineage_disabled`）：
       GET    /api/lineages                  （老師：自己開創的 / 學生：已加入的）
       POST   /api/lineages                  （開山門，A2 裁決：重複 → 200 冪等）
       POST   /api/lineages/{id}/archive      （封存；**不提供** DELETE）
       GET    /api/lineages/summary           （學生端跨師門只讀彙總）
       GET    /api/student-lineages           （我的師門，含退出歷史）
       POST   /api/student-lineages           （學生自加 / 老師拉入）
       DELETE /api/student-lineages           （退出：`status → inactive`，**不刪資料**）

本文件**只做 HTTP 轉譯**（照抄 `template_api.py` 的分層）：
  · 業務校驗、SQL、狀態碼映射全部在 `lineage_service`（本文件不 import `database` / `sqlite3`）；
  · 每個路由的**第一句**是 `_guard()`（flag → 存儲就緒），之後才做參數檢查 ——
    順序不可顛倒：倒過來的話 flag off 時「缺參數」請求會漏出 400，而 §4.4 要求全部 404
    `lineage_disabled`（`test_lineage.py` 的 ④ 組判據）。

啟用方式（本機 / 生產，PowerShell）：
    $env:LINEAGE_ENABLED = "on"    # 不設或 off = 隔離不生效，既有鏈路逐字節不變
"""
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

import lineage_service
from models import LineageCreateInput, LineageOwnerInput, StudentLineageInput

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


def _guard():
    """**每個路由的第一句**（§4.2 / §4.4）：flag → 存儲就緒，兩者都過才談業務校驗。

    只是轉發服務層的 `lineage_service.lineage_gate()`（**同一個實現口徑**，接口層不另寫一份
    flag 判斷），故服務層與接口層對「先 404 `lineage_disabled`、後 400 參數錯」的順序完全一致。
    """
    lineage_service.lineage_gate()


# ---------------------------------------------------------------------------
# ① / ② GET /api/lineages（老師視角 / 學生視角二選一）
# ---------------------------------------------------------------------------
@router.get("/api/lineages")
def list_lineages(teacher_name: Optional[str] = None, student_name: Optional[str] = None):
    """師門清單（§4.2）：`teacher_name` = 老師**開創**的；`student_name` = 學生**已加入**的。

    · 兩個都帶 → 400 `lineage_invalid`（接口語義二選一，不做「取交集」這種沒有定義的事）；
    · 兩個都不帶 → 400 `lineage_required`（**不許**退化成「全庫師門」）；
    · 參數用 `Optional[str] = None` 而非必填：缺參數要落到**統一錯誤體**（§4.1）的 400，
      而不是 FastAPI 自動的 422（那是另一種形狀，前端解不出 `detail.error`）；
    · 老師端含 `archived`（§7.2 要顯示「已封存」提示條）；學生端只含 active 歸屬
      （含退出歷史的完整清單在 `GET /api/student-lineages`）。
    """
    _guard()
    if teacher_name and student_name:
        _fail(
            400, lineage_service.LINEAGE_INVALID,
            "teacher_name 與 student_name 二選一，不可同時帶（設計 §4.2）",
        )
    if teacher_name:
        return {"lineages": lineage_service.list_lineages_by_teacher(teacher_name)}
    if student_name:
        return {"lineages": lineage_service.list_lineages_by_student(student_name)}
    _fail(
        400, lineage_service.LINEAGE_REQUIRED,
        "必須帶 teacher_name（老師視角）或 student_name（學生視角）之一",
    )


@router.get("/api/lineages/summary")
def get_lineage_summary(student_name: str = ""):
    """學生端跨師門**只讀彙總**（§3.4）：各師門就診數 / 未簽草案數 / 最近活動。

    **不做**單一合成等級（段位屬 Epic 5 §D5，§11-4）；`lineage_id` 一律作為並列過濾條件。
    """
    _guard()
    return lineage_service.lineage_summary(student_name)


# ---------------------------------------------------------------------------
# ③ POST /api/lineages（開山門，冪等）；④ POST /api/lineages/{id}/archive（封存）
# ---------------------------------------------------------------------------
@router.post("/api/lineages")
def create_lineage(input_data: LineageCreateInput):
    """開山門（§4.2 / 附錄 A2）：`teacher_name` + `teacher_id` 一致校驗。

    **重複開山門 → 200 + 既有行（冪等，不 409）** —— 階段一老師端沒有切換器，
    409 會造成「自己把自己鎖住」的困惑（A2 裁決原文）。
    """
    _guard()
    return lineage_service.create_lineage(
        input_data.teacher_name, input_data.teacher_id, input_data.name
    )


@router.post("/api/lineages/{lineage_id}/archive")
def archive_lineage(lineage_id: str, input_data: LineageOwnerInput):
    """封存（§4.2 / §10.1）：刪除語義 = `status='archived'`，**不提供** `DELETE /api/lineages/{id}`。

    只改 `lineage.status` / `updated_at`，不動學生歸屬與任何業務資料（§5.5-3 雙主權）。
    """
    _guard()
    return lineage_service.archive_lineage(
        lineage_id, input_data.teacher_name, input_data.teacher_id
    )


# ---------------------------------------------------------------------------
# ⑥ GET / ⑦ POST / ⑧ DELETE /api/student-lineages（歸屬生命週期）
# ---------------------------------------------------------------------------
@router.get("/api/student-lineages")
def list_student_lineages(student_name: str = ""):
    """我的師門（§3.4）：含退出歷史（`status='inactive'`）與未歸屬提示（`unassigned=true`）。"""
    _guard()
    return {"student_lineages": lineage_service.list_student_lineages(student_name)}


@router.post("/api/student-lineages")
def join_student_lineage(input_data: StudentLineageInput):
    """加入師門（§3.4）：`teacher_name` 空 = 學生自加；非空 = 老師拉入（同一個入口）。

    超上限（3 個在門師門）→ 409 `student_lineage_limit`；已在門內 → 200 冪等（`changed=false`）。
    """
    _guard()
    return lineage_service.join_student_lineage(
        input_data.student_name, input_data.lineage_id, input_data.teacher_name
    )


@router.delete("/api/student-lineages")
def leave_student_lineage(student_name: str = "", lineage_id: str = ""):
    """退出師門（§3.4）：`status → inactive`，**不刪資料**（雙主權 §1.4）。

    走 query 參數（`?student_name=&lineage_id=`，與 §4.2 表格的關鍵參數一致），
    不是 body —— `DELETE` 帶 body 在部分客戶端 / 代理上不可靠。
    """
    _guard()
    return lineage_service.leave_student_lineage(student_name, lineage_id)

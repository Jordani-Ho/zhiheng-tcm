"""智能體階段接口層（Epic 2 · 設計 §4.5-② / §4.6；施工步驟 4b-1「骨架 + 掛載」）

對齊：docs/epic2-agent-stage-design-v1.md
  §4.5-② 本文件職責與公開符號（`router` + `_enabled()` / `_fail(...)` / `_guard()` / `_check_identity()`）
  §4.6   7 個接口的入參 / 出參 / **主要錯誤碼**（本文件的映射表逐條對應那一列）
  §5.1   紅線 ①：`AGENT_STAGE_ENABLED` 未設置 / off → `/api/agent/stage*` 全部 **404
         `agent_stage_disabled`**，既有鏈路逐字節不變
  §7.1-⑫ 前端要能區分「功能沒開（整卡不渲染）」與「遷移沒跑（請運維）」→ 404 與 503 不得合併

本文件當前職責（4b-1 的邊界：**只做骨架與掛載，7 個 endpoint 屬 4b-2**）：
  1. `router`（前綴 `/api/agent/stage`，§4.5-② 已實測與 `/api/agent/tasks*`、`/api/agent/scan` 無重疊前綴）；
  2. 把服務層拋出的 `AgentStageError` 翻譯成**真實 HTTP 狀態碼 + 統一錯誤體**
     （`{"detail": {"error", "msg", "errors", "warnings"}}`）—— 註冊點在 `main.py`
     （`app.add_exception_handler`，與 Epic 1 `template_error_handler`、Epic 4 `lineage_error_handler` 同款）；
  3. `_enabled()` / `_fail()` / `_guard()` / `_check_identity()` 四個門衛與出口，供 4b-2 的 7 個 endpoint
     逐個按「第一句 `_guard()` → 第二句 `_check_identity(...)` → 業務校驗」取用。

本文件**只做 HTTP 轉譯**（照抄 `template_api.py` / `lineage_api.py` 的分層）：
  · 業務校驗、SQL、狀態碼映射的**業務側**全在 `agent_stage_service` —— 本文件不 import `database`、
    不 import `sqlite3`、不 import §2.1 六個禁忌符號（`create_prescription` /
    `sanitize_prescription_items` / `batch_deduct_herbs` / `sign_draft` / `update_draft_content` /
    `save_prescription`）；「AI 永不落庫 / 永不開方 / 永不簽字」由路由面直接保證（§4.6 末段）。
  · **檢查順序不可顛倒**（§4.5-② / §7.1-⑫）：每個 endpoint 第一句必須是 `_guard()`
    （flag → 404，再「存儲就緒」→ 503），之後才 `_check_identity()`（400 / 403），最後才是業務校驗。
    倒過來的話，flag off 時「缺參數」的請求會漏出 400 / 403，而 §5.1 紅線 ① 要求全部 404
    `agent_stage_disabled`（Epic 4 `lineage_api.py` 頭註同一條紀律，其 ④ 組判據同款）。

啟用方式（本機 / 生產，PowerShell）：
    $env:AGENT_STAGE_ENABLED = "on"    # 不設或 off = 全部 404，既有鏈路逐字節不變

【4b-1 的零改動承諾】`agent_stage_service.py` / `database.py` / 庫層 8 個新函數與既有 24+ 張表的
函數**一字不動**；本步本文件不含任何 `@router.*` 裝飾器，故掛載後 `/api/agent/stage*` 仍由 FastAPI
的默認 404 兜底（形狀是 `{"detail": "Not Found"}`，**不是**統一錯誤體）—— 階段卡前端（§4.5-⑤）尚未
落地、無消費者；7 個 endpoint 落地（4b-2）後才會出現 404 `agent_stage_disabled` 的統一體。
"""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

import agent_stage_service
from models import (
    AgentStageActionInput,
    AgentStageConfigInput,
    AgentStageSuggestInput,
)

router = APIRouter(prefix="/api/agent/stage", tags=["agent-stage"])

# ---------------------------------------------------------------------------
# 服務層錯誤碼 → HTTP 狀態碼（§4.6 的「主要錯誤碼」列）
# ---------------------------------------------------------------------------
# 寫法與 `template_api._TEMPLATE_ERROR_STATUS` 同形（映射表放接口層）。**不**照 `lineage_api` 那樣
# 轉發服務層的 `lineage_error_status()`：`agent_stage_service` 側**沒有**公開的狀態碼映射函數，
# 只有 §4.6 的碼字面量與模組私有的 `_REASON_*`（私有符號接口層不得 import）；本步也不新增服務層
# 符號（4b-1 對服務層零改動）。
# 表內多數碼同時也是服務層返回體 `reason` 的字面量（`_REASON_STAGE_TRANSITION_INVALID` /
# `_REASON_STAGE_INVALID_VALUE` / `_REASON_CONFIG_INVALID` …）—— 兩邊必須逐字節同字，改一處要同步另一處。
# 未列舉的碼一律 400（`.get(code, 400)`）：與 `template_api` 同款兜底 —— 新碼萬一忘了登記，
# 結果是「客戶端錯誤 + 可讀 code」而不是 500，便於灰度期間排查。
_AGENT_STAGE_ERROR_STATUS = {
    "stage_forbidden": 403,            # §2.2 / §4.6-⑥⑦：能力不足（服務層已帶越權審計），不是 404（§7.1-⑫）
    "stage_kind_invalid": 400,         # §4.6-⑥：`kind` 不是 pattern / formula
    "stage_invalid_value": 400,        # §4.6-⑤：非法階段 / 非法來源（降級入參）
    "stage_transition_invalid": 409,   # §4.6-⑤ / §6.1-8：同階段 / 高於當前 / 越級
    "stage_draft_not_found": 404,      # §4.6-⑥⑦：`draft_id` 反查不到草案
    "stage_config_invalid": 400,       # §3.4 第 5 條 / §4.6-④：配置校驗未過，帶 `errors:[{path,msg}]`
}


async def agent_stage_error_handler(request: Request, exc: agent_stage_service.AgentStageError):
    """服務層 `AgentStageError` → 真實 HTTP 狀態碼 + 統一 detail 包裝（§4.5-② / §0.3 錯誤體慣例）。

    與 `template_api.template_error_handler` 的唯一差別：`errors` / `warnings` **反射異常自帶的兩鍵**，
    不硬編碼 `[]` —— `AgentStageError` 的形狀設計就是「一次湊齊四鍵」（§4.5-①：配置校驗帶
    `[{path,msg}]`，階段門控 / 狀態機衝突帶 `[]`），接口層因此不必判斷某鍵是否存在、也不必補鍵；
    前端只認 `res.detail.error` 這一個鍵，四鍵永遠齊全。狀態碼映射見上方 `_AGENT_STAGE_ERROR_STATUS`
    （未列的碼 400）。
    """
    return JSONResponse(
        status_code=_AGENT_STAGE_ERROR_STATUS.get(exc.code, 400),
        content={"detail": {"error": exc.code, "msg": exc.msg,
                            "errors": exc.errors, "warnings": exc.warnings}},
    )


def _enabled():
    """總閘 `AGENT_STAGE_ENABLED` 每次請求現讀（便於灰度切換 / 測試，不必重啟 uvicorn）。**默認 off**。

    只**轉發**服務層的 `agent_stage_service.agent_stage_enabled()` —— 接口層**不自己讀 env**：
    flag 的真相源在服務層（CTO 裁決②「方案 B」，§4.5-①），既有生成鏈路的快照雙閘門
    （`database._agent_stage_snapshot_enabled()` 函數內延遲 import）問的是**同一個**函數；
    各讀一份就等於長出第二個總閘（§5.1 紅線 ① 的口徑只能有一處實現）。
    """
    return agent_stage_service.agent_stage_enabled()


def _fail(status_code, code, msg, errors=None, warnings=None):
    """統一錯誤體（§0.3 錯誤體慣例）：真 HTTP 狀態碼 + `{error, msg, errors, warnings}` 四鍵。

    與 `template_api._fail` / `lineage_api._fail` 同形狀（前端只讀 `res.detail.error`）。
    本文件**自身**的參數錯都走這裡：404 `agent_stage_disabled` / 503 `agent_stage_store_unavailable` /
    400 `teacher_required` / 403 `teacher_mismatch`；服務層拋出的業務碼則走
    `agent_stage_error_handler` —— 兩條路徑的錯誤體逐鍵相同，前端不必分兩套解析。
    """
    raise HTTPException(
        status_code=status_code,
        detail={"error": code, "msg": msg, "errors": errors or [], "warnings": warnings or []},
    )


def _guard():
    """**每個 endpoint 的第一句**（§4.5-② / §7.1-⑫）：flag → 存儲就緒，兩者都過才談鑑權與業務校驗。

    · flag off（默認）→ 404 `agent_stage_disabled`（功能沒開 → 前端整卡不渲染）；
    · flag on 但三張新表未就緒（`0003_add_agent_stage` 遷移沒跑 / 只跑一半 / 庫不可讀）→ 503
      `agent_stage_store_unavailable`（請運維；與 Epic 1 `template_store_unavailable` 同款先例）。

    兩件事**刻意不合併成一個布爾**（`agent_stage_store_ready()` 三條口徑第 1 條）：合併了前端就分不清
    「功能沒開（整卡不渲染）」與「遷移沒跑（請運維）」—— 這正是 §7.1-⑫ 要求區分 403 / 404 / 503 的同條理由。

    存儲探針只**轉發**服務層的 `agent_stage_service.agent_stage_store_ready()`：接口層不自己查
    `sqlite_master`、不 import `database` / `sqlite3`（分層紀律同上）；該函數自身已把 `sqlite3.Error`
    吞成 `False` 且**絕不建庫 / 建表 / 寫入**，故這裡可以無條件調用（§4.5-② / §4.6）。
    """
    if not _enabled():
        _fail(404, "agent_stage_disabled", "智能體階段接口未啟用（AGENT_STAGE_ENABLED=off）")
    if not agent_stage_service.agent_stage_store_ready():
        _fail(503, "agent_stage_store_unavailable", "智能體階段存儲未就緒，請先執行資料庫遷移")


def _check_identity(teacher_name, teacher_id):
    """老師身份雙欄位鑑權（§4.6 全表入參都是 `teacher_name` + `teacher_id` 成對）。

    · 缺一（含空串）→ 400 `teacher_required`；
    · 兩者不等 → 403 `teacher_mismatch`（與 Epic 1 / Epic 4 的 `require_teacher_identity()` 同一語義：
      名稱與 ID 是「同一個人」的雙因子，只帶一個不算）。

    **必須在 `_guard()` 之後調用**（理由見文件頭）：flag off 時請求要全部 404，不能漏出 400 / 403。
    「缺鍵」走到這裡而不是 FastAPI 的 422，靠的是三個請求體（`models.AgentStage*Input`）的鑑權欄位
    一律 `str = ""`（非必填，§4.5-② 錯誤體契約）。
    """
    if not teacher_name or not teacher_id:
        _fail(400, "teacher_required", "必須帶 teacher_name 與 teacher_id")
    if teacher_name != teacher_id:
        _fail(403, "teacher_mismatch", "teacher_name 與 teacher_id 不一致")


# ---------------------------------------------------------------------------
# 【施工步驟 4b-2 預留】7 個 endpoint（§4.6；本步**不落地** —— 避免「名字在、行為不在」的假實現）
#   #1 GET  /api/agent/stage          → agent_stage_service.stage_view(teacher_name)（18 鍵直出，§4.6-①）
#   #2 POST /api/agent/stage/evaluate → evaluate() + describe_stage()（結構同 #1 + `changed`，§4.6-②）
#   #3 GET  /api/agent/stage/config   → 配置讀取鏈（`load_stage_config()` / 來源三鍵，§4.6-③）
#   #4 PUT  /api/agent/stage/config   → save_stage_config(teacher_name, config)（400 帶 errors，§4.6-④）
#   #5 POST /api/agent/stage/demote   → demote(teacher_name, to_stage, reason)（§4.6-⑤）
#   #6 POST /api/agent/stage/suggest  → §4.6-⑥（服務側三個新能力入口隨 4b-2 落地）
#   #7 POST /api/agent/stage/predraft → §4.6-⑦（同上）
# 每個 endpoint 的固定開頭：`_guard()` → `_check_identity(data.teacher_name, data.teacher_id)`；
# 能力不足的 403 `stage_forbidden` 由接口層問 `agent_stage_service.require_capability()`（**唯一能力
# 閘門**，只是 `bool`、永不拋）後 `raise agent_stage_service.AgentStageError("stage_forbidden", ...)`，
# 再由 `agent_stage_error_handler` 統一出體（越權審計由服務層寫，接口層不碰庫）。
# 三個請求體已在 4b-1 落地於 `models.py`（`AgentStageConfigInput` / `AgentStageActionInput` /
# `AgentStageSuggestInput`，§4.5-② 表 + §4.6 入參列），本文件按**依賴面**先行 import：4b-2 直接取用，
# 不必再改文件頭的 import 段（import 本身不產生任何路由 / 行為，故不違反「本步零行為變化」）。

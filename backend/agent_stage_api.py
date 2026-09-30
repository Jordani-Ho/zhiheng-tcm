"""智能體階段接口層（Epic 2 · 設計 §4.5-② / §4.6；施工步驟 4b-2「#1–#5 五個 endpoint」）

對齊：docs/epic2-agent-stage-design-v1.md
  §4.5-② 本文件職責與公開符號（`router` + `_enabled()` / `_fail(...)` / `_guard()` / `_check_identity()`）
  §4.6   7 個接口的入參 / 出參 / **主要錯誤碼**（本文件的映射表逐條對應那一列；本步落地 #1–#5，
         #6 `suggest` / #7 `predraft` 屬 4c —— 見下方 §4.6 段頭的留白說明）
  §5.1   紅線 ①：`AGENT_STAGE_ENABLED` 未設置 / off → `/api/agent/stage*` 全部 **404
         `agent_stage_disabled`**，既有鏈路逐字節不變
  §7.1-⑫ 前端要能區分「功能沒開（整卡不渲染）」與「遷移沒跑（請運維）」→ 404 與 503 不得合併

本文件當前職責（4b-2 的邊界）：
  1. `router`（前綴 `/api/agent/stage`，§4.5-② 已實測與 `/api/agent/tasks*`、`/api/agent/scan` 無重疊前綴）
     + **§4.6 的 #1–#5 五個 endpoint**（下方 §4.6 段頭起，逐條對應那一行表格）。**#6 `suggest` / #7 `predraft`
     屬 4c**（服務側能力入口 `build_suggestion()` / `build_predraft()` 尚未落地）：本步**不註冊**這兩條
     路由 —— 「名字在、行為不在」的假實現比 404 更糟（理由見下方 §4.6 段頭）。
  2. 把服務層拋出的 `AgentStageError` 翻譯成**真實 HTTP 狀態碼 + 統一錯誤體**
     （`{"detail": {"error", "msg", "errors", "warnings"}}`）—— 註冊點在 `main.py`
     （`app.add_exception_handler`，與 Epic 1 `template_error_handler`、Epic 4 `lineage_error_handler` 同款）；
  3. `_enabled()` / `_fail()` / `_guard()` / `_check_identity()` 四個門衛與出口；
  4. 服務層「口徑 B（永不拋，只回 `reason` / `errors`）」的**翻譯器** `_reject_if_failed()`：寫入類返回體
     「這次算不算成功」只在一處判定（`_AGENT_STAGE_OK_REASONS`），狀態碼與繁體人話由
     `_AGENT_STAGE_ERROR_STATUS` / `_AGENT_STAGE_OUTCOME_MSG` 兩張表驅動。

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

【4b-2 的零改動承諾】`agent_stage_service.py` / `database.py` / `models.py` **一字不動**：本步只在
本文件加 5 條路由與轉譯輔助（兩張表 + 兩個小函數），服務層的業務判定一行都不在這裡重寫。
`/api/agent/stage/suggest` 與 `/api/agent/stage/predraft`（#6 / #7）**沒有**路由，仍由 FastAPI 的
默認 404 兜底（形狀是 `{"detail": "Not Found"}`，**不是**統一錯誤體）—— 4c 落地後才會出現
403 `stage_forbidden` / 404 `stage_draft_not_found` 那一族。
"""
import copy

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

import agent_stage_service
from models import (
    AgentStageActionInput,
    AgentStageConfigInput,
    AgentStageSuggestInput,   # 4c 的 #6 `suggest` 會用它；本步不註冊那條路由（不留空殼路由的紀律見文件頭）
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

    # ---- 4b-2：服務層**返回體**裡的失敗 `reason`（口徑 B：寫入函數永不拋，只回 reason + errors）----
    # 這些碼與上面 §4.6 的「主要錯誤碼」列同屬一份碼字面量詞彙表（服務層的 `_REASON_*` 與 §4.6 逐字節
    # 同字），故共用同一張表：4xx = 「請求不可能被滿足」（老師 / 前端要改請求）；5xx = 「服務側故障」
    # （請運維）。`_reject_if_failed()` 用它把「沒成功」的回答翻成真 HTTP 狀態碼。
    "stage_read_degraded": 503,        # §1.5 fail-closed：讀不到階段真值就拒絕改階段（服務側故障，不是入參錯）
    "demote_write_failed": 503,        # §4.6-⑤ 落庫失敗 = 服務不可用（與 400 / 409「老師填錯」嚴格分開）
    "config_write_failed": 503,        # §4.6-④ 同款（flag on 但寫不進庫 → 請運維，而不是假成功）
    "already_at_stage": 409,           # §1.1 冪等 no-op（規則源走到；#5 手動路徑由服務層直接判 409 拒絕）
    "agent_stage_disabled": 404,       # §5.1 紅線①（正常已被 `_guard()` 提前攔下；此處兜 flag 中途翻轉的競態）
    "teacher_required": 400,           # §4.6 入參（同上，正常已被 `_check_identity()` 提前攔下）
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
# 【施工步驟 4b-2】§4.6 的 #1–#5 五個 endpoint（#6 / #7 屬 4c，本步**不註冊**）
#   #1 GET  /api/agent/stage          → stage_view(teacher_name)（15 鍵直出；§4.6-①）
#   #2 POST /api/agent/stage/evaluate → evaluate(teacher_name)（18 鍵快照 + `changed` 直出；§4.6-②）
#   #3 GET  /api/agent/stage/config   → `{effective, source, defaults}` 三鍵（配置讀取鏈；§4.6-③）
#   #4 PUT  /api/agent/stage/config   → save_stage_config(...)（成功投影 `{effective, source, warnings}`；§4.6-④）
#   #5 POST /api/agent/stage/demote   → demote(...)（成功投影 `{stage, previous_stage, stage_since, stage_source}`；§4.6-⑤）
#
# 為什麼 #6 / #7 這一步**故意沒有路由**：服務側的能力入口（`build_suggestion()` / `build_predraft()`）
# 還沒落地，先註冊一條空殼路由 = 前端會拿到 200 並以為 AI 真的在產建議。4c 落地時本段的前兩條註釋
# 就是它的固定開頭（`_guard()` → `_check_identity(...)` → 能力閘門），其中能力閘門只許問
# `agent_stage_service.require_capability()`（§2.2 唯一能力閘門，只回 `bool`、永不拋）：
# 不過則 `raise agent_stage_service.AgentStageError("stage_forbidden", ...)`，由
# `agent_stage_error_handler` 統一出體（越權審計由**服務層**寫，接口層不碰庫；§4.6-⑥⑦）。
#
# 每個 endpoint 的**固定順序**（§4.5-② / §7.1-⑫）：第一句 `_guard()`（flag → 404、存儲未就緒 → 503）
# → 第二句 `_check_identity(...)`（缺欄位 400 / 名字與 ID 不一致 403）→ 最後才是業務。
# 本步三條業務線的**全部**判定都在服務層：接口層只做「直出 / 按 §4.6 出參列投影」與「失敗翻譯」，
# 一行判定都不重寫（否則同一份規則會出現第二個實現）。
# ---------------------------------------------------------------------------

# 服務層寫入類返回體裡「這次算成功」的 `reason`（其餘取值一律當拒絕 —— 理由見 `_reject_if_failed()`）：
# 只有真的落盤的那兩種 —— `stage_demoted`（#5）/ `config_saved`（#4）。
_AGENT_STAGE_OK_REASONS = ("stage_demoted", "config_saved")

# 失敗 `reason` 的繁體人話（統一錯誤體的 `msg`）。碼字面量與服務層的 `_REASON_*` / `_BLOCKER_*`
# 逐字節同字，改一處要同步另一處；沒登記的碼走兜底句式（照樣帶上可讀 code，灰度期仍能定位）。
_AGENT_STAGE_OUTCOME_MSG = {
    "stage_invalid_value": "降級目標不是五階段之一（to_stage 非法），本次階段不變",
    "stage_transition_invalid": "降級目標不低於當前階段（同階段 / 向上），本次階段不變",
    "already_at_stage": "當前已在目標階段（無可降層級），本次階段不變",
    "stage_read_degraded": "讀不到階段真值（降級態）：本次拒絕降級，階段保持不變",
    "demote_write_failed": "階段降級寫入失敗，階段保持不變（單條 upsert，無半寫）",
    "stage_config_invalid": "階段配置校驗未過，本次整體未寫入（一個字都沒改）",
    "config_write_failed": "階段配置寫入失敗，生效配置仍是寫入前那一份",
    "agent_stage_disabled": "智能體階段接口未啟用（AGENT_STAGE_ENABLED=off）",
    "teacher_required": "必須帶 teacher_name 與 teacher_id",
}


def _reject_if_failed(result):
    """服務層「口徑 B」返回體（**永不拋**）→ 統一錯誤體；成功則**原樣**返回，供調用方按 §4.6 投影。

    為什麼接口層必須自己判：`demote()` / `save_stage_config()`（以及 4c 的兩個能力入口）把成功與失敗
    放在**同一個 200 形狀**裡，差別只有 `reason` / `applied`（失敗另帶 `errors:[{path,msg}]`）。前端只認
    統一錯誤體（§0.3），所以「沒成功」必須在這裡翻成真 HTTP 狀態碼：
      · 狀態碼照 `_AGENT_STAGE_ERROR_STATUS`（未登記的碼兜底 400，同該表開頭的兜底口徑）；
      · `errors` / `warnings` **原樣**帶上（`errors[].path` 要能定位到是哪個鍵填錯了）；
      · 人話用 `_AGENT_STAGE_OUTCOME_MSG`（服務層只回 code，不替接口層寫繁體文案）。
    `result` 不是對象（違約）時也一樣按「沒有成功可言」拒絕 —— 不讓一個 None 變成 200。
    """
    data = result if isinstance(result, dict) else {}
    reason = data.get("reason") or ""
    if reason in _AGENT_STAGE_OK_REASONS:
        return data
    code = reason or "unknown"
    _fail(_AGENT_STAGE_ERROR_STATUS.get(code, 400), code,
          _AGENT_STAGE_OUTCOME_MSG.get(code, "智能體階段操作未完成（%s）" % code),
          errors=data.get("errors"), warnings=data.get("warnings"))


def _default_stage_config():
    """內置默認配置的**深拷貝**（§3.5 的 16 鍵）：唯一硬編碼點是服務層常量 `DEFAULT_STAGE_CONFIG`。

    接口層只把它原樣交給前端（#3 的 `defaults` 一節），故這裡只做複製 —— 免得請求處理過程中有人改到
    服務層那份字典（它在進程內是**共享**的；`load_stage_config()` 每次給的也是新建對象，這裡同款）。
    """
    return copy.deepcopy(agent_stage_service.DEFAULT_STAGE_CONFIG)


# ---------- 【#1】階段視圖（§4.6-①；只讀）----------

@router.get("")
def get_agent_stage(teacher_name: str = "", teacher_id: str = ""):
    """§4.6-①：階段視圖（`stage_view()` 的 15 鍵**直出**）。

    這是前端階段卡（§4.5-⑤）取「當前階段 + 權限面 + 上次指標」的唯一入口：`stage*` 一族的真值只從
    這裡讀、`capabilities` 是能力區的唯一數據來源（前端據此渲染三個新能力入口的可用 / 置灰與繁體原因），
    `stale` / `blockers` 只提示「再點一次評估」而**不阻斷**任何東西。

    **只讀契約由服務層保證**（§3.8：全程只發 SELECT、零寫入、零審計、`metrics` 回顯上次快照不重算）
    —— 本接口連點十次也不會在 `agent_stage_log` / `agent_stage_state` 上留下一行（⑳ 組有專項斷言）。
    本步**不投影**：多一個鍵 / 少一個鍵都是契約變更，前端與測試都按 15 鍵對表（§4.6-① 出參列）。
    """
    _guard()
    _check_identity(teacher_name, teacher_id)
    return agent_stage_service.stage_view(teacher_name)


# ---------- 【#2】跑一次評估（§4.6-②；寫快照 + 可能建請示單）----------

@router.post("/evaluate")
def evaluate_agent_stage(data: AgentStageActionInput):
    """§4.6-②：跑一次評估（`evaluate()` 的 18 鍵快照 + `changed` **直出**）。

    與 #1 的差異照**服務層契約**如實回，不在接口層補鍵：
      · 本接口**沒有** `capabilities` —— 能力區的唯一來源是 #1 的 `stage_view()`（§4.5-⑤ 的前端只從
        那裡讀權限面），評估快照本就不含它；
      · 多 `skipped` / `reason` / `metrics_reason` / `evaluated_at` / `metrics_ttl_hours` 五鍵
        （「這一次評估做了什麼 / 為什麼」才有的資訊），外加 `changed{stage_changed, recommended,
        demoted, reason}`（本次調用的結論，不落庫）。

    **刻意不用 `_reject_if_failed()`**：評估是「先算再判」而不是「寫入請求」——flag 中途翻轉、沒有有效
    樣本、十條判定不過、庫讀失敗，全部如實寫在 200 的 `reason` / `blockers` / `degraded` 裡（§3.6：
    老師要看到「為什麼沒推薦」）。把這些翻成 4xx 會讓前端拿不到理由，也讓「沒推薦」與「請求非法」混成
    一類。真正屬「請求錯」的只有兩個鑑權欄位（`_check_identity()` 已過）。
    """
    _guard()
    _check_identity(data.teacher_name, data.teacher_id)
    return agent_stage_service.evaluate(data.teacher_name)


# ---------- 【#3】讀配置（§4.6-③；只讀）----------

@router.get("/config")
def get_agent_stage_config(teacher_name: str = "", teacher_id: str = ""):
    """§4.6-③：`{effective, source, defaults}` —— 「接下來判定真正會用的那一份」+「它從哪來」。

    · `effective` = §3.4 的四層合併結果（內置默認 ← 全局行 ← 老師行 ← env）；
    · `source` = §3.4 第 4 條的三鍵（`global` / `teacher_override` / `env_override`），與 `effective`
      **同源**（服務層兩個函數走同一次讀取鏈，不各自查庫）；
    · `defaults` = §3.5 的 16 鍵內置默認（深拷貝）：前端「恢復默認」的基準，也是老師對照「我改了哪
      幾個鍵」的參照 —— 內置默認在全系統只有一個硬編碼點（服務層常量），接口層照讀不另抄一份。

    三者都是**現讀**（服務層不緩存任何一層）：`PUT` 完再 `GET`，看到的就是剛寫進去的那一份。
    本接口同樣**只讀**（全程只發 SELECT；不建行、不改行、不寫審計 —— ⑳ 組有專項斷言）。
    """
    _guard()
    _check_identity(teacher_name, teacher_id)
    return {
        "effective": agent_stage_service.load_stage_config(teacher_name),
        "source": agent_stage_service.stage_config_source(teacher_name),
        "defaults": _default_stage_config(),
    }


# ---------- 【#4】寫配置（§4.6-④；全量替換老師自己那一行）----------

@router.put("/config")
def put_agent_stage_config(data: AgentStageConfigInput):
    """§4.6-④：全量替換老師**自己那一行**階段配置（校驗未過 → 400 + `errors:[{path,msg}]`）。

    成功回 §4.6-④ 的三鍵 `{effective, source, warnings}`：
      · `effective` 是**寫完再讀一次**的四層合併結果（不是入參回顯）—— 老師看到的必須是「接下來判定
        真正會用的那一份」（env 覆蓋與上級層回落都在裡面）；
      · `source` 的三鍵回答「這份配置由哪幾層拼出來」；
      · `warnings` 是「這份配置有什麼要注意」（仍會被 env 覆蓋的鍵 / 不在 §3.5 鍵表內的鍵），**不阻斷**寫入。
    服務層返回體其餘的鍵（`skipped` / `applied` / `reason`）在成功路徑上恆為
    `False` / `True` / `config_saved`，故不下發；失敗那一路由 `_reject_if_failed()` 翻成統一錯誤體。

    校驗未過的形態是「**只攔不清**、整體不寫入」（§3.4 第 5 條）：該老師的生效配置仍是寫入前那一份，
    `errors[].path` 逐條指出是哪個鍵 —— 前端照原樣提示即可。
    寫入目標恆為該老師自己的行：空 `teacher_name` 在 `_check_identity()` 就被 400 攔下（**恰是**「誤寫
    全局行」的那種請求），全局行只能由運維直接改庫（§7.1-⑥）。
    """
    _guard()
    _check_identity(data.teacher_name, data.teacher_id)
    result = _reject_if_failed(agent_stage_service.save_stage_config(data.teacher_name, data.config))
    return {
        "effective": result["effective"],
        "source": result["source"],
        "warnings": result["warnings"],
    }


# ---------- 【#5】手動降級（§4.6-⑤；全系統唯一的向下寫路徑）----------

@router.post("/demote")
def demote_agent_stage(data: AgentStageActionInput):
    """§4.6-⑤：老師主動降級（`stage_source='manual_demote'`；單向 —— 智能體不會自動升回）。

    成功回 §4.6-⑤ 的四鍵 `{stage, previous_stage, stage_since, stage_source}`（工作台要顯示
    「見習期 → 觀察期」與「自何時起」；服務層返回體的其餘 9 鍵屬內部審計資訊，前端不必看）。
    `reason` 是老師選填的說明，**原樣**交給服務層寫進人話（缺省 → 審計只留固定句式；接口層不替老師
    編一句說明，審計裡的每一句話都要能追溯到一個人）。

    三類失敗（都由 `_reject_if_failed()` 出體，服務層永不拋）：
      · `to_stage` 不在五階段內（含空串 / 缺鍵）→ 400 `stage_invalid_value`；
      · 同階段 / 高於當前 → 409 `stage_transition_invalid`（「降級」指向不低於當前的位置 = 無法滿足的
        請求；假成功會讓老師以為真的降下去了）；
      · 讀不到階段真值 / 寫不進去 → 503（fail-closed：階段保持不變，單條 upsert，無半寫）。
    審計由服務層負責：降級成功寫 `stage_demoted` 事件 + 一行行動日誌（`action='manual_demote'`）；
    被拒 / 非法值**一行都不寫**（階段沒變就不該長出變更事件）。接口層不碰庫。
    """
    _guard()
    _check_identity(data.teacher_name, data.teacher_id)
    result = _reject_if_failed(
        agent_stage_service.demote(data.teacher_name, data.to_stage, data.reason))
    return {
        "stage": result["stage"],
        "previous_stage": result["previous_stage"],
        "stage_since": result["stage_since"],
        "stage_source": result["stage_source"],
    }

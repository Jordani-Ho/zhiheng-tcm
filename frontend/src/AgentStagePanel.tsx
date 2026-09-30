/**
 * 老師端首頁「🧭 智能體階段」卡（Epic 2 · 施工步驟 **6a + 6b + 6c + 6d**）
 *   6a：骨架 + 掛載探測 + 階段真值靜態區；6b：指標區（① ② ③）+ 閾值折疊區 + `config_source` 角標 + 「🔄 立即評估」；
 *   6c：「⬇ 降級」卡內二次確認（`to_stage` 只列低於當前 rank 者 + `reason` 輸入）+ 評估 / 降級成功後
 *       回調父級重拉「智能體工作台」（`onEvaluated`）；
 *   6d：能力區（按 `capabilities` 渲染 §4.5-⑤ 列的三顆：🧪 證型候選 / 📜 方劑建議 / 🧾 預處方預填）
 *       + `draftId` 前置條件 + 結果**只讀**展示（永不回填編輯框）。
 *
 * 對齊：docs/epic2-agent-stage-design-v1.md
 *   §4.5-⑤ 前端卡片（探測 / 展示 / 按鈕 / 能力區 / 鐵律文案 / 樣式復用）
 *   §4.6-① `GET /api/agent/stage`（服務層 `stage_view()` 直出 **15 鍵**，形狀即契約）
 *   §4.6-② `POST /api/agent/stage/evaluate`（`evaluate()` 的 **18 鍵**快照 + `changed`，**無** `capabilities`）
 *   §4.7   掛載點與施工循序
 *
 * 【已施工範圍】6a = 「掛載探測 + 階段真值靜態區 + 底部鐵律文案」；6b = 「指標區 + 閾值回顯 + 來源角標 + 手動評估」：
 *   ✓ 6a：徽章（後端 `stage_label` 直出，前端**不自己查**標籤表）、`stage_since`、`stage_source` 來源注記、
 *     `next_stage`、`pending_stage` / `pending_task_id`（引導去按既有的 ✅）、`blockers[]`、`degraded` 提示；
 *   ✓ 6b：① ② 指標（百分比 + 樣本數 / 樣本不足 / 違規紅字 / 近似樣本 / 最差樣本）、③ 佔位文案、
 *     13 鍵閾值折疊區（`matrix_enforced=false` 紅字）、`config_source` 來源角標、
 *     `stale` 提示（設計原句）+「🔄 立即評估」→ `POST …/evaluate` → **重拉 #1**；
 *   ✓ 6c：「⬇ 降級」（卡內二次確認區 + `reason` 輸入 + 目標階段只列**低於當前 rank** 者）→
 *     `POST …/demote` → **重拉 #1**（徽章翻新、來源變「老師主動降級」）；評估 / 降級成功後調
 *     `onEvaluated()` → 父級重拉工作台（新推薦 / 行動日誌立刻可見）；
 *   ✓ 6d：能力區（`capabilities` 五鍵逐格置灰 + `draftId` 前置條件 + 🧪/📜/🧾 三顆按鈕 →
 *     `POST …/suggest` / `POST …/predraft`）+ 結果**卡內只讀展示**（永不回填編輯框）；
 *   `capabilities` 的型別 6a 已按契約定好（形狀即契約）—— 6d 只加渲染、不改型別。
 *
 * 【6b 的三個施工口徑（偏離原句時的理由都寫在這裡）】
 *   1. 「🔄 立即評估」**常顯**（不只在 `stale` 時）：設計 §4.5-⑤ 的按鈕清單本就無條件列出，且服務層在
 *      「從沒評估過」時給的唯一 blocker 是 `evaluation_not_run`（`agent_stage_service.py:2568-2569`：
 *      「先告诉老师去点「立即評估」」）—— 若只在 `stale` 時才給按鈕，「有模板但樣本不足 / 指標沒達標」
 *      的老師就沒有手動重算的入口。`stale` 只負責那句提示（回復設計原句）。
 *   2. 評估後**只重拉 #1**（`GET /api/agent/stage`）：#2 的 18 鍵快照**不含 `capabilities`**
 *      （接口層註釋 `agent_stage_api.py:281-282` 明說「能力區的唯一來源是 #1」）→ 拿 #2 的 body
 *      整體 `setView` 會把能力區的依據抹掉。本卡因此**只**認 #1 為 `view` 的唯一來源。
 *   3. 評估成功只留一行時間戳回執；`changed{stage_changed, recommended, demoted, reason}` **不在本卡渲染**。
 *      【6c 已補】`evaluate` / `demote` 成功後調 `onEvaluated()` → 父級 `fetchAgentWorkbench()`（末尾已自增
 *      `agentStageRefreshKey`）→ 下方「智能體工作台」卡（⏳ 待你確認 / 📜 行動日誌）立刻跟上。
 *      副作用：`refreshKey` 自增會讓本卡的**探測 effect 再跑一次**（`probing` 期間整卡短暫不渲染）——
 *      這是 **6a 既有**行為（老師點 ✅/❌/🔍 走的就是同一條路），本步刻意不動探測口徑（見 §6c 口徑 6）。
 *
 * 【6c 的六條施工口徑】
 *   1. 降級區**追加在 6b 按鈕行下方**（新開一個 div），6b 那一行的 JSX 一字不改 ——「不改已驗收區」
 *      比「兩顆按鈕擠一行」重要。
 *   2. 下拉的目標階段只列**低於當前 rank** 者：rank 用 `AGENT_STAGE_ORDER`（§0.4 展示順序 = 後端
 *      `STAGES` 的鏡像）現算。這是**展示所需的最小本地計算**，不是第二份判定 —— 接受 / 拒絕
 *      （非法值 400 `stage_invalid_value`、同階段或向上 409 `stage_transition_invalid`）永遠只在
 *      後端 `_demote()`（`agent_stage_service.py:2947-2958`）。
 *   3. 卡內二次確認 = **防誤點**的 UI 護欄，與 §1.1「降級立即生效、無需確認」不矛盾：那句講的是
 *      **狀態機**不需要「待老師確認」那道閘（只有升級才有 `pending_*`），不是講 UI 不許問一次。
 *      全程不彈窗、不阻塞其它卡片（§4.5-⑤ 原句「先弹卡内二次确认区，不打断页面」）。
 *   4. 失敗分級（**不假成功**：任何非 2xx 都不改徽章、不收起二次確認區）：
 *      · 404 `agent_stage_disabled`（flag 中途被關）→ 整卡退場；
 *      · 503 `agent_stage_store_unavailable`（遷移沒跑）→ 走 6a 的「階段表未就緒」紅字；
 *      · 其餘（400 `stage_invalid_value` / 409 `stage_transition_invalid` / 503 `demote_write_failed` /
 *        503 `stage_read_degraded` / 403 `teacher_mismatch` / 網絡異常）→ **卡內紅字** + 保留舊畫面，
 *        文案直接用後端統一錯誤體的 `msg`（`agent_stage_api.py:207-222` 逐條已是繁體人話）。
 *        ⚠ 503 **不能**一律當「遷移沒跑」：`demote_write_failed` 是「寫不進去、階段保持原值」，
 *        與 `agent_stage_store_unavailable` 的處置完全不同 → 本卡按 `failure.code` 分，不看狀態碼。
 *   5. `degraded=true` 時**不禁用**降級按鈕：本卡的 `view` 只是一份快照，快照說降級態不代表此刻還是 ——
 *      判定權只有後端一處（後端 fail-closed 會回 503 `stage_read_degraded`，卡內照實顯示）。
 *      與 6b「按鈕常顯」同一條理由：前端不長出第二個判定。
 *   6. 降級成功**也**調 `onEvaluated()`：降級會寫一行行動日誌（`action='manual_demote'`）+ 清掉
 *      `pending_stage` / `pending_task_id`（`agent_stage_service.py:2972-2981`）→ 工作台那兩塊
 *      要立刻跟上。這是**超出 requirement 字面**的一處（requirement 只寫了 evaluate 後調）；
 *      如要嚴格照字面，把 `handleDemote` 末尾那一行刪掉即可（其餘邏輯不受影響）。
 *
 * 【6d 的八條施工口徑】
 *   1. 能力區**追加在 6b 按鈕行下方、6c 降級區上方**（新開一個 div）：兩區的 JSX 一字不改
 *      ——「不改已驗收區」比「三行按鈕擠在一起」重要。
 *   2. 五鍵 `capabilities` 是**唯一門控來源**（§2.3 矩陣 / §4.5-⑤「按 capabilities 渲染」）：
 *      `predict_pattern` / `suggest_prescription` / `generate_predraft` 各渲染一顆按鈕（🧪 / 📜 / 🧾）
 *      並逐格置灰，置灰理由用 `CAPABILITY_MIN_STAGE_LABELS`（能力 → 最低階段的鏡像）說成
 *      「尚未開放（需「見習期」）」（§4.5-⑤ 的逐字理由文案）。`record_observation` / `generate_draft`
 *      **不渲染按鈕**：它們是老師本來就在用的既有鏈路（§5.2 / §5.3），本卡多給一個入口只會
 *      長出第二條到達路徑（§4.5-⑤ 的按鈕清單也只有這三顆）。
 *   3. `draftId` 是執行能力的**前置條件**（服務端只信 DB：`draft_id` 在該老師名下最新的未簽草案裡
 *      反查，反查不到就不調模型 → 404 `stage_draft_not_found`）。缺省 → 三顆一起置灰 + 一句提示；
 *      負 id（`App.tsx` 第 59 天的**本地佔位草案**，老師還沒按「保存病歷修改」落庫）同樣置灰 ——
 *      那個值送到後端是 100% 的 404，擋在請求前只是把「必然的失敗」換成一句可行的提示。
 *      **這不是第二個能力判定**：能力只有 `capabilities` 一處；草案是否屬於該老師 / 是否已簽字，
 *      仍由後端反查（`_suggestion_draft()`）判，本卡連「查一下」都不做。
 *   4. 單飛（一次一顆）：結果區只有一份，且沒有理由讓老師同時打兩條 LLM → 有一顆在飛時另兩顆一起置灰。
 *   5. 失敗分級（**不假成功**：任何非 2xx 都**不顯示任何產出**、也不留舊結果 —— 一份陳舊的候選貼在
 *      「能力不足」旁邊會被讀成「他給了候選」）：
 *      · 404 `agent_stage_disabled` → 整卡退場；503 `agent_stage_store_unavailable` → 6a「表未就緒」紅字；
 *      · 403 `stage_forbidden` → 「能力不足：需「見習期」」+（本卡快照可能已過時，可點「🔄 立即評估」重讀）。
 *        這條只會出現在「按鈕是亮的、後端卻說不行」的情形 = 快照過時；判定權在後端，本卡不覆核、不自行改徽章；
 *      · 404 `stage_draft_not_found` → 「草案不存在」+ 後端 `msg`；400 `stage_kind_invalid` /
 *        503 `suggestion_failed` / `predraft_failed` → 各自繁體人話；其餘（含網絡異常）沿用後端 `msg`。
 *        這些失敗一律 `⚠` 前綴 → **紅字**；「成功但沒有內容」那一句不帶 `⚠` → **灰字**（口徑 6）。
 *   6. 解析失敗是**成功**（200 + `payload.error='parse_failed'` + 空結果）→ 顯示「模型這次沒給出可用內容」
 *      （§4.3「絕不編造」），**不是**紅字故障（與 503 嚴格分開）—— 畫面上用**灰字**，紅字只給真失敗；
 *      顏色由 `⚠` 前綴決定（同 6b `evaluateNote` / 6c `demoteNote`），這條契約因此看得見。
 *      ⚠ #7 的四鍵投影**不含 `warnings`**（`agent_stage_api.py:447-452`）→ 預處方的解析失敗在前端
 *      看不出來，只能按「三鍵全空 = 本次沒有產出」判，文案與 #6 同一句。
 *   7. **不調 `onEvaluated()`**（與 6c 口徑 6 的取捨方向相反，理由是同一個「有沒有東西要刷新」）：
 *      `suggest` / `predraft` 寫的是 `agent_stage_log`（階段審計），**從不寫** `agent_action_log`
 *      （「建議」不是「動作」：`applied` 恆 False，`test_agent_stage.py:5836-5839` 釘住）→
 *      工作台「⏳ 待你確認 / 📜 行動日誌」兩塊**沒有新行**可顯示 ⇒ 沒有可刷新的東西。
 *   8. 結果**只在本卡展示**，不自動回填任何編輯框（§4.6 全族只讀：接口層不 import 六個禁忌符號，
 *      「AI 永不落庫 / 永不開方 / 永不簽字」由路由面直接保證）→ 預處方要採用，仍須老師在診室逐項操作。
 *      `formulas[]` 的 `usage` 前端**不渲染**：值恆為常量「僅供參考」（`agent.py:990`，不採用模型給的值），
 *      與 `disclaimer` 同一句話，印兩次只是噪音。
 *
 * 【探測（§4.5-⑤ 首條；與 `TemplateStudio` 同一套口徑）】
 *   `GET /api/agent/stage?teacher_name=&teacher_id=`
 *     · 2xx → `on`（渲染）；
 *     · 404 `agent_stage_disabled` → `off`（**整卡不渲染**：flag off 時 DOM 與 Epic 2 之前逐字面一致）；
 *     · 503 `agent_stage_store_unavailable` → `no_store`（**卡內紅字**「遷移沒跑」；§7.1-⑫：
 *       「功能沒開」與「遷移沒跑」**不得合併**，故本卡刻意不共用一個布爾）；
 *     · 其餘（400 `teacher_required` / 403 `teacher_mismatch` / 網絡異常）→ `off`：不渲染、不彈窗、
 *       不阻塞其它卡片（同 `TemplateStudio` 的降級姿態）。
 *
 * 【flag off 零變化】`probeState !== 'on'` 且非 `no_store` → `return null`：零 DOM、零彈窗、
 *   不動其它卡片；唯一新增副作用是掛載期一次**只讀**探測請求（`stage_view()` 全程只發 SELECT，
 *   零寫入 / 零審計 —— ⑲ 組 `test_api_stage_view_is_read_only_across_ten_calls` 釘住）。
 *   本卡**不**參與 `lineageEnabled` / `lineageReady` 就緒門（理由見下）。
 *
 * 【Epic 4 §5.3：本卡刻意不帶師門上下文】
 *   階段是**老師的能力畫像**（`agent_stage_state` 以 `teacher_name` 為唯一 PK、`lineage_id` 恒空、
 *   不參與師門過濾）→ 本卡既不拼 `lineage_id` 參數、也不收 `lineageId` prop。因此
 *   「flag on 但老師尚未開山門」**不會**讓本卡消失：這是與 `TemplateStudio` 的 `no_lineage` 分支的
 *   **刻意差異**（模板歸屬師門，階段不歸屬師門），不是漏做。
 *
 * 樣式：不新增任何 npm 依賴、不引 UI 庫；內聯 style + 主色 #8b4513 / #fdfcf0 + serif（§4.5-⑤）。
 */
import { useEffect, useState } from 'react'
import type { CSSProperties } from 'react'

/* ============================ 型別（= §4.6-① 的 15 鍵，形狀即契約） ============================ */

export type StageProbeState = 'probing' | 'on' | 'off' | 'no_store'

/** ① 模板匹配度（9 鍵）：空集 → `value=null`（**不是 0**；前端必須顯示「樣本不足」而不是 0%）。 */
export interface StageTemplateMatchMetric {
  value: number | null
  samples: number
  violations: number
  skipped_no_template: number
  skipped_stale_template: number
  skipped_empty: number
  hit_rate: number | null
  order_rate: number | null
  blockers: string[]
}

/** ② 病歷修改一致率（6 鍵）。 */
export interface StageModificationMetric {
  value: number | null
  samples: number
  approx_samples: number
  skipped_empty: number
  min: number | null
  blockers: string[]
}

/** ① ② ③ 三鍵；③ **恆為 `null`**（Epic 2 不計算；`deferred_to_epic3` 的理由只在 #2 的 `metrics_reason`）。 */
export interface StageMetrics {
  template_match: StageTemplateMatchMetric
  modification_consistency: StageModificationMetric
  inquiry_preference_consistency: null
}

/** 門檻回顯（13 鍵 = 服務層 `_THRESHOLD_KEYS` 逐鍵；`matrix_enforced=false` = 臨時放寬，6b 顯紅字）。 */
export interface StageThresholds {
  window_days: number
  max_samples: number
  min_samples: number
  min_template_match: number
  min_modification_consistency: number
  max_violations: number
  max_permission_denials: number
  recommend_cooldown_hours: number
  demote_consistency_floor: number
  demote_streak: number
  truncate_chars: number
  metrics_ttl_hours: number
  matrix_enforced: boolean
}

/** 五鍵權限面（6d 渲染能力區的**唯一**依據；判定本身仍只在服務層 `require_capability()`）。 */
export interface StageCapabilities {
  record_observation: boolean
  generate_draft: boolean
  predict_pattern: boolean
  suggest_prescription: boolean
  generate_predraft: boolean
}

/** 配置來源（§3.4 第 4 條）：兩層配置行是否存在 + 本次**真被採納**的 env 鍵（6b 顯示來源角標）。 */
export interface StageConfigSource {
  global: boolean
  teacher_override: boolean
  env_override: string[]
}

/** §4.6-① 直出的 15 鍵（`GET /api/agent/stage`；短路體逐鍵同形）。 */
export interface StageView {
  teacher_name: string
  stage: string
  stage_label: string
  stage_since: string
  stage_source: string
  pending_stage: string
  pending_task_id: number
  capabilities: StageCapabilities
  metrics: StageMetrics
  thresholds: StageThresholds
  next_stage: string | null
  blockers: string[]
  config_source: StageConfigSource
  stale: boolean
  degraded: boolean
}

/* ---------- 【6d】能力區的三個回包形狀（§4.6-⑥⑦ 的出參列，形狀即契約） ---------- */

/**
 * 🧪 證型候選的一條（§4.3 白名單四鍵：`name` / `confidence` / `basis` / `note`）。
 *
 * 逐鍵可選（`?`）**不是**型別悲觀：服務層 `_result_list()` 只投影鍵集、**不補默認值**
 * （`agent_stage_service.py:3612-3615`「原条目里没有的键就不出现（不补默认值）」）
 * → 契約形狀本來就允許缺鍵；前端按缺鍵退化顯示，壞形狀不該炸掉老師首頁（同 6b 的 `Partial` 取態）。
 * `confidence` 的白名單是 `high|medium|low`（AI 層歸一化：`agent.py:844` / `agent.py:973-976`），
 * 本卡只翻譯、不校驗。
 */
export interface StagePatternCandidate {
  name?: string
  confidence?: string
  basis?: string[]
  note?: string
}

/** 📜 方劑建議的一條（§4.3 白名單四鍵；**無劑量、無煎服法**：`usage` 恆為常量「僅供參考」）。 */
export interface StageFormulaSuggestion {
  name?: string
  modification?: string
  composition?: string[]
  usage?: string
}

/** 🧾 預處方預填的藥味一條（§4.6-⑦ 三鍵；`dose` 是 §4.2 唯一合法的劑量位）。 */
export interface StagePredraftItem {
  herb?: string
  dose?: string
  role?: string
}

/** 🧾 預處方預填的內層三鍵（服務層 `_blank_predraft()` 保證恆在場：非 dict / 缺鍵 → 空值兜底）。 */
export interface StagePredraftPayload {
  formula_name?: string
  items?: StagePredraftItem[]
  decoction?: string
}

/** `POST /api/agent/stage/suggest` 的**五鍵**投影（`payload` 內層隨 `kind`：`candidates[]` / `formulas[]`）。 */
export interface StageSuggestResponse {
  kind?: string
  draft_id?: number
  payload?: {
    candidates?: StagePatternCandidate[]
    formulas?: StageFormulaSuggestion[]
    /** 解析失敗標記（**成功**回應才會有它：`payload` 的頂層鍵，見檔頭 §6d 口徑 6）。 */
    error?: string
  }
  disclaimer?: string
  generated_at?: string
}

/** `POST /api/agent/stage/predraft` 的**四鍵**投影（`predraft` 內層三鍵恆在場；`note` 是 §4.6-⑦ 逐字文案）。 */
export interface StagePredraftResponse {
  draft_id?: number
  predraft?: StagePredraftPayload
  disclaimer?: string
  note?: string
}

/**
 * 【6d】結果區的預處方：與 `StagePredraftPayload` 同形，但 `items` **保證非空**
 * （空藥味表不進結果區 → 走 `capNote` 的「模型這次沒給出可用內容」）→ 渲染端不必再判空。
 */
export type StagePredraftResult = Omit<StagePredraftPayload, 'items'> & { items: StagePredraftItem[] }

/**
 * 【6d】能力區的**結果狀態**（判別聯合：`kind` 決定渲染哪一種；一次只有一份 —— 單飛，見檔頭 §6d 口徑 4）。
 *
 * 只裝「成功且有產出」的回包：失敗與解析失敗走 `capNote`，**不進這裡**（檔頭 §6d 口徑 5/6）。
 * `disclaimer` / `note` 一律用後端給的那一份（`僅供參考，非診斷` / `非處方` / `須老師確認並自行開方`
 * 與 §4.6-⑦ 的預填提示）—— 鐵律文案前端**不重寫**，只轉運。
 */
export type StageCapabilityResult =
  | { kind: 'pattern'; items: StagePatternCandidate[]; disclaimer: string; generatedAt: string }
  | { kind: 'formula'; items: StageFormulaSuggestion[]; disclaimer: string; generatedAt: string }
  | { kind: 'predraft'; predraft: StagePredraftResult; disclaimer: string; note: string }

/** 接口失敗（不拋異常，用返回值表達 —— 與 `TemplateStudio` 的 `TemplateApiFailure` 同款）。 */
export interface StageApiFailure {
  status: number
  code: string
  msg: string
}

type StageApiResult<T> = { ok: true; data: T } | { ok: false; failure: StageApiFailure }

export interface AgentStagePanelProps {
  teacherName: string
  teacherId: string
  /** 刷新信號：`App.tsx` 的 `fetchAgentWorkbench()` 末尾自增（老師點 ✅/❌/掃描後本卡重探一次）。 */
  refreshKey: number
  /** 【6d】當前就診學生的**未簽草案 id**（`App.tsx` 傳 `clinicPatientDrafts[0]?.id`）。無值 / 非正數
   *  （`App.tsx` 第 59 天的本地佔位草案是**負 id**）→ 能力區三顆一起置灰；見檔頭 §6d 口徑 3：
   *  這是「執行能力的前置條件」，不是第二個能力判定。 */
  draftId?: number
  /**
   * 【6c】本卡剛剛**寫入了階段真值**（`evaluate` 或 `demote` 成功）→ 請父級重拉「智能體工作台」卡：
   * 可能剛產生新推薦（⏳ 待你確認）、也可能剛多一行降級行動日誌（📜 行動日誌）。
   * 可選（`?`）：本卡單獨使用時不傳也能跑 —— 缺省 = 不通知（卡片自身照常刷新）。
   */
  onEvaluated?: () => void
}

/* ============================ 契約鏡像常量（前端唯一允許硬編碼的一塊） ============================ */

/**
 * 五階段徽章（**鏡像**：`backend/agent_stage_service.py:59-65` `STAGE_LABELS`）。
 *
 * 【重要】當前階段的徽章**不走這張表** —— 後端 #1 直出 `stage_label`（§1.5「真值只有一個來源」）。
 * 本表只服務**只有 key 沒有 label** 的兩處：`next_stage`、`pending_stage`（兩者都只是 stage key）。
 * 漂移風險：本倉前端無測試基建，後端改 `STAGE_LABELS` 時必須同步這裡（review 覆蓋）。
 *
 * 【6d 已落地】`CAPABILITY_MIN_STAGE_LABELS` 定義在下面 —— 6a 當時刻意不定義它：能力區不渲染 →
 * 常量無人讀 → `tsc -b`（`noUnusedLocals`）直接報錯；它與它的消費者在 6d 一起落地。
 */
const AGENT_STAGE_LABELS: Record<string, string> = {
  observation: '觀察期',
  learning: '學習期',
  apprentice: '見習期',
  assistant: '助手期',
  authorized: '授權期'
}

/**
 * 【6d】能力 → 最低階段的**繁體階段名**（置灰理由的鏡像來源：§4.5-⑤「未开放时按钮置灰 +
 * 繁体原因文案（`尚未開放（需「見習期」）`）」）。
 *
 * 合成自後端兩張表：`agent_stage_service.py:79-85` `CAPABILITY_MIN_STAGE`（能力 → 階段 key）
 *   × 上面那份 `AGENT_STAGE_LABELS`（階段 key → 繁體名）。本表**只服務展示**：
 * 按鈕亮不亮由 `view.capabilities` 決定（後端唯一判定，見檔頭 §6d 口徑 2/3），
 * 這張表**不**參與任何放行 / 拒絕 —— 它連一個 `require` 的味道都沒有。
 * 漂移風險與 `AGENT_STAGE_LABELS` 同款（本倉前端無測試基建）：後端改
 * `CAPABILITY_MIN_STAGE` / `STAGE_LABELS` 時必須同步這裡（review 覆蓋）。
 */
const CAPABILITY_MIN_STAGE_LABELS: Record<string, string> = {
  predict_pattern: '見習期',
  suggest_prescription: '助手期',
  generate_predraft: '授權期'
}

/**
 * 【6d】能力區的三顆按鈕（§4.5-⑤ 的按鈕清單逐顆對應一個能力鍵）。
 *
 * · `cap` 是 `view.capabilities` 的鍵 = **唯一門控來源**（不見第二個判定）；
 * · `kind` 是 #6 `POST …/suggest` 的 `kind` 欄位（`pattern` / `formula`）；`generate_predraft`
 *   走 #7 `POST …/predraft` —— 契約裡 #7 **整條忽略** `kind`（`agent_stage_api.py:428-429`）→
 *   這一格是空串，且**不會**進請求體（送了也只是噪音）；
 * · `busyText` 只換字面（在飛的那一顆用置灰姿態，同 6b「評估中…」）。
 */
const AGENT_STAGE_CAPABILITY_BUTTONS: Array<{
  cap: keyof StageCapabilities
  text: string
  busyText: string
  kind: string
}> = [
  { cap: 'predict_pattern', text: '🧪 證型候選', busyText: '🧪 生成中…', kind: 'pattern' },
  { cap: 'suggest_prescription', text: '📜 方劑建議', busyText: '📜 生成中…', kind: 'formula' },
  { cap: 'generate_predraft', text: '🧾 預處方預填', busyText: '🧾 生成中…', kind: '' }
]

/** 【6d】`confidence` 的繁體譯名（AI 層白名單 `high|medium|low`；未登記的值原樣顯示，不猜、不譯）。 */
const AGENT_STAGE_CONFIDENCE_LABELS: Record<string, string> = {
  high: '高',
  medium: '中',
  low: '低'
}

/**
 * 【6d】`draftId` 缺省（沒選中學生 / 該學生沒有任何草案）時的提示：三顆一起置灰，理由就這一句
 * （需求逐字給的句子，**不加尾巴**）。「為什麼」由檔頭 §6d 口徑 3 交代，不塞進老師看的句子裡。
 */
const AGENT_STAGE_CAPABILITY_NO_DRAFT_HINT = '請先在診室選中學生並有一份未簽草案'

/**
 * 【6d】本地佔位草案的提示：`App.tsx` 第 59 天的機制會給「還沒落庫的草案」一個**負 id**
 * （`localDrafts`）→ 後端 `_suggestion_draft()` 必然反查不到。擋在請求前並說清怎麼解，
 * 比送出去換一個 404 好（見檔頭 §6d 口徑 3：這不是能力判定）。
 */
const AGENT_STAGE_CAPABILITY_UNSAVED_DRAFT_HINT =
  '這份草案還在本機暫存（尚未落庫）：請先在診室按「保存病歷修改」，再回到本卡'

/**
 * 【6d】「模型這次沒給出可用內容」的**統一文案**：`parse_failed`（#6 有明確標記）與「有標記但空殼」
 * / #7 三鍵全空（投影不含 `warnings`，看不見標記）**共用同一句** —— 兩者對老師的處置完全一樣
 * （稍後再試 or 自行判斷），分兩句話只是把後端的鍵名講給老師聽（檔頭 §6d 口徑 6）。
 * **不帶 `⚠` 前綴**：它是 200 成功，渲染成灰字（前綴即顏色開關，見 `ASP_CAP_EMPTY`）。
 */
const AGENT_STAGE_CAPABILITY_EMPTY_TEXT =
  '模型這次沒給出可用內容：已按「絕不編造」返回空結果，請稍後再試或自行判斷'

/** 【6d】置灰理由（§4.5-⑤ 逐字句式）：能力 → 「尚未開放（需「見習期」）」；未登記的能力不退化成空白。 */
const capabilityClosedText = (cap: string) => {
  const stage = CAPABILITY_MIN_STAGE_LABELS[cap]
  return stage ? `尚未開放（需「${stage}」）` : '尚未開放（階段不足）'
}

/** 五階段的**展示順序**（§0.4「不可跳級」；純展示用 —— 任何判定一律在後端，前端不重複實現）。 */
const AGENT_STAGE_ORDER = ['observation', 'learning', 'apprentice', 'assistant', 'authorized']

/** 階段來源（§1.2 的五個字面量；空串 = flag off / 讀異常的短路體 → 不顯示來源注記）。 */
const AGENT_STAGE_SOURCE_LABELS: Record<string, string> = {
  default: '系統預設（尚未經老師確認）',
  teacher_confirm: '老師確認升級',
  manual_demote: '老師主動降級',
  rule_demote: '規則自動降級（表現回退）',
  rule_reset: '規則回退至觀察期（觸及鐵律禁區）'
}

/**
 * `blockers[]` 的英文碼 → 繁體文案。服務層註釋原話就是「英文鍵，**前端逐條翻譯展示**」
 * （`agent_stage_service.py:1536`）→ 這張表是契約要求的，不是前端自造。
 * 17 個碼 = §3.2/§3.3 的三條（`…_no_samples` / `no_active_record_template`）
 *   + §3.6 十三條 + `evaluation_not_run`（`agent_stage_service.py:2569`）。
 * **未登記的碼不靜默吞掉**：原樣顯示 + 標記「未登記文案」（灰度期便於定位後端新增的碼）。
 * 文案**不帶數值**：閾值 / 實際值屬 6b（指標區上線後可按後端快照補上「62% < 75%」這種寫法）。
 */
const AGENT_STAGE_BLOCKER_LABELS: Record<string, string> = {
  evaluation_not_run: '尚未評估過：本卡顯示「還沒有數」，而不是「0 分」',
  template_match_no_samples: '① 模板匹配度無樣本（沒有可與當前模板比對的已簽病歷）',
  modification_consistency_no_samples: '② 病歷修改一致率無樣本（沒有可與 AI 原稿比對的已簽病歷）',
  no_active_record_template: '尚無生效中的病歷模板（請先在「📜 模板傳承」發佈一版病歷模板）',
  agent_stage_disabled: '智能體階段功能未啟用（AGENT_STAGE_ENABLED off）',
  matrix_relaxed: '權限矩陣已由管理員臨時放寬：放寬態不推薦升級',
  already_authorized: '已在最高階段（授權期），無可再升',
  upgrade_pending: '已有待你確認的升級推薦：請在下方「⏳ 待你確認」按 ✅（本次不重複推薦）',
  cooldown_active: '距上次推薦 / 上次被拒未滿冷卻期，暫不重複推薦',
  template_match_below_threshold: '① 模板匹配度未達升級門檻',
  modification_consistency_below_threshold: '② 病歷修改一致率未達升級門檻',
  samples_below_minimum: '樣本數不足（兩個指標都要各自達到最小樣本數）',
  violations_exceeded: '鐵律違規次數超出上限（智能體填了「留待老師」的段落）',
  permission_denied_in_window: '統計窗口內越權拒絕次數過多',
  recommend_task_write_failed: '升級推薦單建立 / 寫回失敗：本次未做任何階段變更',
  evaluate_failed: '階段評估失敗：階段保持不變，請稍後重試',
  teacher_required: '缺少 teacher_name（無效調用）'
}

/**
 * `stale=true` 的提示（**6b 已接回設計原句**）。
 *
 *   · 設計 §4.5-⑤ 原句（`docs/epic2-agent-stage-design-v1.md:537`）＝ `指標可能已過時，可點「立即評估」`；
 *   · 本卡 ＝ 6a 的前半段（把「過時」講清楚：上次快照已超出 `metrics_ttl_hours`）+ 設計的尾半段。
 *     `「立即評估」` 四字現在**真有控件可指**（6b 落了按鈕）；6a 當時只寫前半段，正是因為
 *     「指向不存在的控件」比不提示更糟。
 */
const AGENT_STAGE_STALE_HINT =
  '指標可能已過時：上次評估快照已超出有效期，可點「立即評估」'

/* ============================ 【6b】指標區的文案與工具 ============================ */

/** 三個指標的標題（編號 ①②③ 與設計 §3.1 的定義一一對應，不重排、不合併）。 */
const AGENT_STAGE_METRIC_LABELS = {
  template_match: '① 模板匹配度',
  modification_consistency: '② 病歷修改一致率',
  inquiry_preference_consistency: '③ 問診偏好一致率'
}

/**
 * ③ 的固定文案：`inquiry_preference_consistency` 在 **Epic 2 恆為 `null`**
 * （服務層 `_METRICS_DEFERRED = {"inquiry_preference_consistency": "deferred_to_epic3"}`，
 * `agent_stage_service.py:1555-1556`；測試 `test_inquiry_metric_is_null_placeholder` 釘住）。
 * 刻意**不**顯示「0%」也**不**顯示「—」：占位鍵要一眼看出是「還沒算」而不是「算出來是零」。
 */
const AGENT_STAGE_INQUIRY_PLACEHOLDER = '待 Epic 3（尚未計算）'

/**
 * 「樣本不足」的括號寫法：`樣本不足（2/5）` = 有效樣本 2 份 / 門檻 5 份（設計 §6.6：「样本 2/5 份」）。
 * `min_samples` 缺失（後端違約，契約上不可能）時退化為「樣本 N 份」—— **不**印「3/0」這種假分數。
 */
const samplesShortText = (samples: number, minSamples: number) =>
  minSamples > 0 ? `樣本不足（${samples}/${minSamples}）` : `樣本不足（樣本 ${samples} 份）`

/** 比率 → 百分比（`null` / 非數字 → 空串；呼叫端據此分支到「樣本不足」）。 */
const ratioPercentText = (value: number | null | undefined) =>
  typeof value === 'number' ? `${Math.round(value * 100)}%` : ''

/* ---------- 【6b】閾值折疊區（13 鍵；順序 = 服務層 `_THRESHOLD_KEYS`，逐鍵不移位） ---------- */

/** 值型別只影響**顯示**（整數 / 比率→百分比 / 布爾→是・否）：任何判定都不在前端做。 */
type StageThresholdKind = 'int' | 'ratio' | 'bool'

const AGENT_STAGE_THRESHOLD_ROWS: Array<{
  key: keyof StageThresholds
  label: string
  kind: StageThresholdKind
}> = [
  { key: 'window_days', label: '指標統計窗口（天）', kind: 'int' },
  { key: 'max_samples', label: '每指標最多取樣本數（性能上限）', kind: 'int' },
  { key: 'min_samples', label: '允許推薦升級的最少樣本數', kind: 'int' },
  { key: 'min_template_match', label: '① 模板匹配度達標門檻', kind: 'ratio' },
  { key: 'min_modification_consistency', label: '② 病歷修改一致率達標門檻', kind: 'ratio' },
  { key: 'max_violations', label: '窗口內允許的鐵律違規樣本數', kind: 'int' },
  { key: 'max_permission_denials', label: '窗口內允許的越權次數', kind: 'int' },
  { key: 'recommend_cooldown_hours', label: '推薦／被拒後的冷卻（小時）', kind: 'int' },
  { key: 'demote_consistency_floor', label: '規則降級水位（一致率）', kind: 'ratio' },
  { key: 'demote_streak', label: '連續命中幾次才降級', kind: 'int' },
  { key: 'truncate_chars', label: '相似度計算前的文字截斷長度（字）', kind: 'int' },
  { key: 'metrics_ttl_hours', label: '指標快照「新鮮」窗口（小時）', kind: 'int' },
  { key: 'matrix_enforced', label: '權限矩陣強制（關 = 臨時放寬）', kind: 'bool' }
]

/**
 * 單鍵顯示值。比率鍵顯示「百分比（原值 0.75）」：**兩個都給**，老師看得懂、運維能與後端 / 日誌對賬
 * （`config_changed` 的 `detail` 寫的就是原值）。
 */
const thresholdValueText = (
  thresholds: Partial<StageThresholds>,
  row: { key: keyof StageThresholds; kind: StageThresholdKind }
) => {
  const value = thresholds[row.key]
  if (row.kind === 'bool') return value === true ? '是（矩陣生效）' : '否（已臨時放寬）'
  if (row.kind === 'ratio') {
    return typeof value === 'number' ? `${Math.round(value * 100)}%（原值 ${value}）` : String(value)
  }
  return String(value)
}

/**
 * 【6b】`config_source` 角標（§3.4 第 4 條「來源必須可回答」）：只在「老師自訂」/「env 真有覆蓋」時出現。
 *
 *   · `global`（全局行存在）**刻意不進角標**：那是運維視角，寫給老師只會多一個看不懂的詞；
 *   · env 鍵名**原樣列出**（`min_template_match` 這種審計識別碼不翻譯 —— 翻譯會妨礙與後端、日誌對賬）；
 *   · 三鍵全空 → 返回空串 → 呼叫端不渲染任何東西（節點預設 / 全局配置下不該有角標）。
 */
const configSourceBadge = (source: StageConfigSource | undefined | null) => {
  if (!source) return ''
  const envKeys = Array.isArray(source.env_override) ? source.env_override : []
  const parts: string[] = []
  if (source.teacher_override) parts.push('老師自訂')
  if (envKeys.length > 0) parts.push('環境覆蓋')
  if (parts.length === 0) return ''
  const envText = envKeys.length > 0 ? `（鍵：${envKeys.join('、')}）` : ''
  return `閾值來源：${parts.join(' + ')}${envText}`
}

/** 評估回執的時間戳（「剛剛那次評估」的肉眼憑證；要精確時刻時以後端 `last_evaluated_at` 為準）。 */
const clockText = () => new Date().toLocaleTimeString('zh-TW', { hour12: false })


/** 卡片底部固定文案（§4.5-⑤：**逐字**，不可省略、不可改寫、不可簡繁轉換）。 */
const AGENT_STAGE_IRON_RULE =
  '智能體永不診斷、永不開方、永不簽字；一切建議僅供參考，採用即為你的決定。'

/* ============================ 樣式（沿用存量視覺；不引 UI 庫） ============================ */

const ASP_BOX: CSSProperties = {
  background: '#fdfcf0', border: '1px solid #d4c8a8', borderRadius: '12px', padding: '24px',
  marginBottom: '20px', boxShadow: '0 4px 12px rgba(0,0,0,0.06)'
}
const ASP_TITLE: CSSProperties = { fontSize: '18px', color: '#8b4513', fontWeight: 'bold' }
const ASP_HINT: CSSProperties = { fontSize: '12px', color: '#999', lineHeight: '1.7' }
const ASP_SECTION_TITLE: CSSProperties = {
  fontSize: '14px', color: '#8b4513', fontWeight: 'bold', marginBottom: '6px'
}
/** 階段徽章（繁文字面量由後端給；這裡只管視覺）。 */
const ASP_BADGE: CSSProperties = {
  display: 'inline-block', padding: '4px 16px', borderRadius: '20px', background: '#8b4513',
  color: '#fdfcf0', fontFamily: 'serif', fontSize: '14px', fontWeight: 'bold'
}
/** `pending_stage` 引導條（淺黃底強調，與 App.tsx 的「⏳ 待你確認」區塊同色系）。 */
const ASP_PENDING: CSSProperties = {
  background: '#fffbe8', border: '1px solid #f0e2b6', color: '#8b4513', borderRadius: '8px',
  padding: '8px 12px', fontSize: '13px', marginTop: '12px', lineHeight: '1.8'
}
const ASP_ERROR: CSSProperties = {
  background: '#fdecea', border: '1px solid #f5c6c0', color: '#c0392b', borderRadius: '8px',
  padding: '10px', fontSize: '13px', marginTop: '12px', lineHeight: '1.8'
}
const ASP_FOOTER: CSSProperties = {
  fontSize: '12px', color: '#999', lineHeight: '1.7', marginTop: '14px',
  borderTop: '1px dashed #d4c8a8', paddingTop: '10px'
}

/* ---------- 【6b】指標區 / 閾值折疊區 / 按鈕 / 角標的樣式 ---------- */

/** `config_source` 角標：小字 + 淺底，**不搶**階段徽章的焦點。 */
const ASP_CHIP: CSSProperties = {
  display: 'inline-block', padding: '2px 10px', borderRadius: '12px', background: '#f5efe0',
  border: '1px solid #e2d6b8', color: '#8b4513', fontSize: '12px'
}
/** 指標行：三行同一套網格（標籤定寬 → 三個百分比左緣對齊，方便掃視）。 */
const ASP_METRIC_ROW: CSSProperties = {
  display: 'flex', gap: '10px', flexWrap: 'wrap', alignItems: 'baseline', padding: '4px 0',
  fontSize: '13px', color: '#333'
}
const ASP_METRIC_LABEL: CSSProperties = { minWidth: '132px', color: '#5a4633', fontWeight: 'bold' }
const ASP_METRIC_VALUE: CSSProperties = { fontWeight: 'bold' }
const ASP_METRIC_HINT: CSSProperties = { fontSize: '12px', color: '#999' }
/** 指標區的紅字（違規 > 0 / 矩陣放寬）：只紅不換行背景，避免與 `ASP_ERROR` 的「真錯誤」混淆。 */
const ASP_ALERT_TEXT: CSSProperties = { fontSize: '12px', color: '#c0392b', fontWeight: 'bold' }
/** 閾值折疊區的開關（折疊是**視覺**選擇：13 鍵對老師是備查資訊，不該一開場就占滿卡片）。 */
const ASP_FOLD_BUTTON: CSSProperties = {
  background: 'none', border: 'none', padding: 0, color: '#8b4513', fontSize: '12px',
  textDecoration: 'underline', cursor: 'pointer'
}
/** 「🔄 立即評估」（主色實心；不用 `:hover` 偽狀態 —— 內聯 style 表達不了，也不值得引 CSS 檔）。 */
const ASP_BUTTON: CSSProperties = {
  padding: '6px 16px', borderRadius: '20px', border: '1px solid #8b4513', background: '#8b4513',
  color: '#fdfcf0', fontSize: '13px', cursor: 'pointer'
}
/** 評估進行中的按鈕（置灰 + 不可點；文案改「評估中…」，見 JSX）。 */
const ASP_BUTTON_OFF: CSSProperties = {
  ...ASP_BUTTON, background: '#c9b79c', borderColor: '#c9b79c', cursor: 'not-allowed'
}

/* ---------- 【6c】降級區：樣式與文案常量（按鈕沿用 6b 的 `ASP_BUTTON` / `ASP_BUTTON_OFF`） ---------- */

/**
 * `reason` 輸入框的**默認值**（§4.5-⑤ 原句：默认 `由老師主動降級`）。
 * 老師可改可清空；清空後審計只留服務層的固定句式（`_demote_note()` 把空白串當「沒填」）。
 */
const AGENT_STAGE_DEMOTE_REASON_DEFAULT = '由老師主動降級'
/**
 * `reason` 輸入框字數上限：這是**輸入框護欄**（防手滑把一整段話貼進審計），不是校驗 ——
 * 後端 `AgentStageActionInput.reason` 沒有任何長度限制（`models.py:138`），本卡不新增第二道規則。
 */
const AGENT_STAGE_DEMOTE_REASON_MAX_LENGTH = 120

/** 「⬇ 降級」：描邊白底（**不**與「🔄 立即評估」搶主色 —— 收窄權限的動作，點之前先看清二次確認）。 */
const ASP_BUTTON_OUTLINE: CSSProperties = {
  padding: '6px 16px', borderRadius: '20px', border: '1px solid #8b4513', background: '#fffdf5',
  color: '#8b4513', fontSize: '13px', cursor: 'pointer'
}
/** 無可降層級 / 降級進行中的描邊按鈕（置灰不可點，與 `ASP_BUTTON_OFF` 同款姿態）。 */
const ASP_BUTTON_OUTLINE_OFF: CSSProperties = {
  ...ASP_BUTTON_OUTLINE, borderColor: '#c9b79c', color: '#a8977c', cursor: 'not-allowed'
}
/** 卡內二次確認區（淺黃底 + 金邊：與 `ASP_PENDING` 的「提醒」色系一致，但一眼看得出是「要按下去」的區）。 */
const ASP_DEMOTE_BOX: CSSProperties = {
  background: '#fffbe8', border: '1px solid #f0e2b6', borderRadius: '8px', padding: '10px 12px',
  marginTop: '8px', fontSize: '13px', color: '#333'
}
/** 原生 `select` / `input` + 棕色描邊（**不引 UI 庫**；配色與卡片一致）。 */
const ASP_SELECT: CSSProperties = {
  padding: '4px 8px', borderRadius: '6px', border: '1px solid #e2d6b8', background: '#fffdf5',
  color: '#333', fontSize: '13px', fontFamily: 'inherit'
}
const ASP_INPUT: CSSProperties = { ...ASP_SELECT, flex: '1 1 240px', minWidth: '200px' }

/* ---------- 【6d】能力區：樣式（按鈕直接沿用 6b/6c 的 `ASP_BUTTON_OUTLINE` / `…_OFF`） ---------- */

/** 能力區外框：虛線上緣 + 內距，與 6b 指標區 / 6c 降級區視覺同族（不引 UI 庫、不新增色值）。 */
const ASP_CAP_BOX: CSSProperties = {
  marginTop: '12px', borderTop: '1px dashed #ece3cd', paddingTop: '10px'
}
/** 三顆按鈕的橫排容器（`flex-start` + 換行：窄螢幕自然堆疊，不做響應式判斷）。 */
const ASP_CAP_ROW: CSSProperties = {
  display: 'flex', gap: '14px', flexWrap: 'wrap', alignItems: 'flex-start'
}
/** 一顆按鈕 + 它的置灰理由（縱向一欄：理由永遠貼著自己那顆按鈕，不集中成一段看圖猜謎）。 */
const ASP_CAP_CELL: CSSProperties = {
  display: 'flex', flexDirection: 'column', gap: '4px', maxWidth: '260px'
}
/** 結果區：淺底 + 金邊的「展示」容器（比 `ASP_DEMOTE_BOX` 寬：要放藥味清單與原文依據）。 */
const ASP_CAP_RESULT: CSSProperties = {
  background: '#fffdf5', border: '1px solid #e2d6b8', borderRadius: '8px', padding: '10px 12px',
  marginTop: '10px', fontSize: '13px', color: '#333', lineHeight: '1.9'
}
/** 能力區的紅字（失敗 / 解析失敗）：整行一句話，**不**用 `ASP_ALERT_TEXT` 的粗體（那是「指標壞了」的語氣）。 */
const ASP_CAP_ALERT: CSSProperties = {
  fontSize: '12px', color: '#c0392b', lineHeight: '1.8', marginTop: '8px'
}
/**
 * 能力區的**非故障**一行（解析失敗 / 本次沒產出）：灰字 —— 那是 **200 成功**（只是模型沒給出內容），
 * 紅字只留給真失敗。顏色由「`⚠` 前綴」決定（與 6b `evaluateNote` / 6c `demoteNote` 同一套判法），
 * 於是「解析失敗是成功」這條契約在畫面上就看得出來，不必為它多開一個 state。
 */
const ASP_CAP_EMPTY: CSSProperties = {
  fontSize: '12px', color: '#999', lineHeight: '1.8', marginTop: '8px'
}
/** 預處方藥味表的三欄寬（`herb` / `dose` / `role` 左緣對齊，方便老師逐列核對）。 */
const ASP_CAP_HERB_CELL: CSSProperties = { minWidth: '104px', fontWeight: 'bold' }
const ASP_CAP_DOSE_CELL: CSSProperties = { minWidth: '76px' }
const ASP_CAP_ROLE_CELL: CSSProperties = { minWidth: '44px' }

/* ============================ 工具（與 TemplateStudio 同款；不改既有的兩個文件） ============================ */

/**
 * 身份參數：`teacher_name == teacher_id`（否則後端 403 `teacher_mismatch`）。
 * 【Epic 4 §5.3】**刻意不拼 `lineage_id`**：階段是老師的能力畫像，與師門無關（見檔頭說明）。
 */
const identityQuery = (teacherName: string, teacherId: string) =>
  `teacher_name=${encodeURIComponent(teacherName)}&teacher_id=${encodeURIComponent(teacherId)}`

/** 接口調用包裝：讀 `{detail:{error,msg,errors,warnings}}`，網絡異常統一成 `network_error`。 */
async function callStageApi<T>(path: string, init?: RequestInit): Promise<StageApiResult<T>> {
  try {
    const res = await fetch(path, init)
    let body: any = null
    try { body = await res.json() } catch { body = null }
    if (!res.ok) {
      const detail = (body && body.detail) || {}
      return {
        ok: false,
        failure: {
          status: res.status,
          code: String(detail.error || 'http_error'),
          msg: String(detail.msg || '請求失敗，請稍後再試')
        }
      }
    }
    return { ok: true, data: body as T }
  } catch {
    return {
      ok: false,
      failure: { status: 0, code: 'network_error', msg: '網絡異常，請確認後端服務是否在運行' }
    }
  }
}

/**
 * 【6d】白名單欄位（`basis` / `composition`）→ 非空字串陣列：形狀不對（後端違約 / 舊快照 / 非字串項）
 * 一律退化為空陣列 —— 同 6b 取 `Partial` 的取態（不猜、不轉型、不白屏）；空陣列由呼叫端給兜底文案。
 */
const stringList = (value: unknown): string[] =>
  Array.isArray(value)
    ? value.filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
    : []

/** stage key → 繁體徽章（後端只給 key 的兩處用：`next_stage` / `pending_stage`；未知 key 原樣顯示）。 */
const stageKeyLabel = (key: string) => AGENT_STAGE_LABELS[key] || key

/**
 * 【6c】低於 `current` 的階段 key（**由低到高**；`current` 未知 / 已在最低階 → 空陣列）。
 *
 * rank 用 `AGENT_STAGE_ORDER` 現算（= 後端 `STAGES` 的鏡像，見檔頭 §6c 口徑 2）：這只回答「下拉裡該列出
 * 哪幾個選項」的**展示**問題，不是第二份判定 —— 同階段 / 向上的請求自有後端回 409
 * `stage_transition_invalid`（檔案內**唯一**的階段方向判定在 `_demote()`）。
 */
const lowerStageKeys = (current: string) => {
  const rank = AGENT_STAGE_ORDER.indexOf(current)
  return rank > 0 ? AGENT_STAGE_ORDER.slice(0, rank) : []
}

/**
 * 【6c】實際送出的降級目標：state 裡記的 `picked` 若已不在候選內（剛降級成功 → `view.stage` 已變、
 * 換了老師、後端階段 key 漂移），就回退到「退一級」；候選為空則回空串（呼叫方據此停手，不送空 `to_stage`）。
 * 用「推導」而不是 `useEffect` 同步：降級成功後的那一次重繪就會自動修正，不留中間態。
 */
const resolveDemoteTarget = (current: string, picked: string) => {
  const targets = lowerStageKeys(current)
  return targets.includes(picked) ? picked : (targets[targets.length - 1] || '')
}

/** blocker 英文碼 → 繁體一句話（未登記的碼原樣顯示 + 標記，見常量註釋）。 */
const blockerText = (code: string) => AGENT_STAGE_BLOCKER_LABELS[code] || `${code}（未登記文案）`

/** ISO 串 → 「YYYY-MM-DD」（`stage_since` 空串 = 從未確認過升階 → 返回空串表示整段不顯示）。 */
const stageSinceText = (value: string) => {
  const text = (value || '').trim()
  if (!text) return ''
  return text.length >= 10 ? text.slice(0, 10) : text
}

/* ============================ 【6d】能力區：純函數（不改 state、不發請求、不碰徽章） ============================ */

/**
 * 【6d】回包陣列 → 只留 dict 條目（服務層 `_result_list()` 也是這麼篩的：非 dict 條目直接跳過，
 * 不包殼、不補默認值）—— 前端不重複實現業務，只是**不讓一個壞條目炸掉整張卡**。
 * 這裡刻意用**函數宣告**而不是泛型箭頭：`.tsx` 裡的 `<T>(…) => …` 會被解析成 JSX 元素（TS17008）。
 */
function objectList<T>(value: unknown): T[] {
  return Array.isArray(value)
    ? value.filter((item): item is T => !!item && typeof item === 'object')
    : []
}

/** 【6d】`draftId` 可否送去後端反查：無值 / 非正數（本地佔位草案是**負 id**）→ false（檔頭 §6d 口徑 3）。 */
const draftIdUsable = (draftId: number | undefined) =>
  typeof draftId === 'number' && Number.isFinite(draftId) && draftId > 0

/** 【6d】`draftId` 不可用時的那一句提示（「沒選中」與「還沒落庫」分開說：兩者的解法不同）。 */
const draftUnusableHint = (draftId: number | undefined) =>
  draftId ? AGENT_STAGE_CAPABILITY_UNSAVED_DRAFT_HINT : AGENT_STAGE_CAPABILITY_NO_DRAFT_HINT

/**
 * 【6d】🧪 `suggest(kind='pattern')` 的成功回包 → 結果區狀態；`null` = 本次沒有可用產出。
 *
 * 三種「沒有產出」共用一個結論（檔頭 §6d 口徑 6）：`payload.error='parse_failed'`（後端明確標記）、
 * `candidates` 空陣列、`candidates` 型別不是陣列 —— 對老師都是「這次沒有內容」，不留半截結果。
 */
const patternResultOf = (data: StageSuggestResponse): StageCapabilityResult | null => {
  const items = objectList<StagePatternCandidate>(data.payload?.candidates)
  if (data.payload?.error === 'parse_failed' || items.length === 0) return null
  return { kind: 'pattern', items, disclaimer: data.disclaimer || '', generatedAt: data.generated_at || '' }
}

/** 【6d】📜 `suggest(kind='formula')` 的成功回包 → 結果區狀態（判空口徑同 `patternResultOf()`）。 */
const formulaResultOf = (data: StageSuggestResponse): StageCapabilityResult | null => {
  const items = objectList<StageFormulaSuggestion>(data.payload?.formulas)
  if (data.payload?.error === 'parse_failed' || items.length === 0) return null
  return { kind: 'formula', items, disclaimer: data.disclaimer || '', generatedAt: data.generated_at || '' }
}

/**
 * 【6d】🧾 `predraft` 的成功回包 → 結果區狀態；`null` = 本次沒有可用產出。
 *
 * 判空**只能**看資料本身（藥味陣列為空）：#7 的四鍵投影不含 `warnings`（`agent_stage_api.py:447-452`）
 * → 後端那句「本次未產出可用的預處方預填（解析失敗）」到不了前端（檔頭 §6d 口徑 6）。
 */
const predraftResultOf = (data: StagePredraftResponse): StageCapabilityResult | null => {
  const predraft = data.predraft || {}
  const items = objectList<StagePredraftItem>(predraft.items)
  if (items.length === 0) return null
  return {
    kind: 'predraft', predraft: { ...predraft, items },
    disclaimer: data.disclaimer || '', note: data.note || ''
  }
}

/**
 * 【6d】能力區的失敗碼 → 卡內一行繁體人話（**純字串映射**：不改 state、不發請求、不碰徽章）。
 *
 * `403 stage_forbidden` 用 `CAPABILITY_MIN_STAGE_LABELS` 說「需哪一階」—— 與置灰理由同一份鏡像，
 * 老師看到的兩種狀態（置灰 / 被拒）用的是同一個階段名。這條只可能出現在「按鈕是亮的、後端卻說
 * 不行」= 快照已過時，所以順帶把重讀入口寫出來（判定權在後端，本卡**不**自行翻徽章）。
 * 文案裡的 `msg` 逐字用後端統一錯誤體（`agent_stage_api.py:207-222` 已是繁體人話）。
 */
const capabilityFailureText = (failure: StageApiFailure, cap: string) => {
  if (failure.code === 'stage_forbidden') {
    return `⚠ 能力不足：需「${CAPABILITY_MIN_STAGE_LABELS[cap] || '更高階段'}」`
      + '（本卡顯示的階段快照可能已過時，可點「🔄 立即評估」重讀）'
  }
  if (failure.code === 'stage_draft_not_found') return `⚠ 草案不存在：${failure.msg}`
  if (failure.code === 'stage_kind_invalid') return `⚠ 請求參數不合法：${failure.msg}`
  if (failure.code === 'suggestion_failed') return `⚠ 建議生成失敗（服務側故障）：${failure.msg}`
  if (failure.code === 'predraft_failed') return `⚠ 預處方預填失敗（服務側故障）：${failure.msg}`
  return `⚠ 生成未完成：${failure.msg}`
}

/* ============================ 主組件 ============================ */

export default function AgentStagePanel({
  teacherName, teacherId, refreshKey, draftId, onEvaluated
}: AgentStagePanelProps) {
  const [probeState, setProbeState] = useState<StageProbeState>('probing')
  const [view, setView] = useState<StageView | null>(null)
  // 【6b】手動評估：`evaluating` = 請求在飛（按鈕置灰防連點，也防兩次評估交錯寫快照）；
  // `evaluateNote` = 卡內回執（成功顯示時間戳、失敗顯示繁體人話）—— **不 alert**。
  const [evaluating, setEvaluating] = useState(false)
  const [evaluateNote, setEvaluateNote] = useState('')
  // 【6b】13 鍵閾值折疊區的展開態（預設收起：老師的日常視線是徽章 + 指標，閾值是備查）。
  const [showThresholds, setShowThresholds] = useState(false)
  // 【6c】手動降級（§4.5-⑤「先弹卡内二次确认区，不打断页面」）：
  //   `showDemote` = 二次確認區展開態（卡內、**不彈窗**）；`demoteTarget` = 選中的目標階段 key
  //   （空串 = 未選 → 由 `resolveDemoteTarget()` 推導出「退一級」）；`demoteReason` = 審計說明
  //   （預設見常量，老師可改可清空）；`demoting` = 請求在飛（置灰防連點）；
  //   `demoteNote` = 一行回執（成功 `✅` / 失敗 `⚠`），成功後顯示在按鈕旁、失敗時顯示在區內。
  const [showDemote, setShowDemote] = useState(false)
  const [demoteTarget, setDemoteTarget] = useState('')
  const [demoteReason, setDemoteReason] = useState(AGENT_STAGE_DEMOTE_REASON_DEFAULT)
  const [demoting, setDemoting] = useState(false)
  const [demoteNote, setDemoteNote] = useState('')
  // 【6d】能力區（`capabilities` 五鍵 → 三顆按鈕）：`capBusy` = 在飛的那顆能力鍵（空串 = 沒在飛；
  // **單飛**：另兩顆一起置灰，理由見檔頭 §6d 口徑 4）；`capNote` = 一行紅字（失敗 / 解析失敗）；
  // `capResult` = 本次**成功**的產出（三個能力共用這一份展示區；失敗時清空）。
  const [capBusy, setCapBusy] = useState('')
  const [capNote, setCapNote] = useState('')
  const [capResult, setCapResult] = useState<StageCapabilityResult | null>(null)

  // 掛載探測（§4.5-⑤ 首條）：結果緩存於 state，不重複探測；換老師 / 刷新信號變化才重探。
  // 重置與抓取都放在 async 閉包內（不在 effect 內同步 setState，避免級聯渲染）。
  useEffect(() => {
    if (!teacherName || !teacherId) return
    let cancelled = false
    const run = async () => {
      setProbeState('probing')
      setView(null)
      const result = await callStageApi<StageView>(
        `/api/agent/stage?${identityQuery(teacherName, teacherId)}`)
      if (cancelled) return
      if (!result.ok) {
        // 503「遷移沒跑」→ 卡內紅字（§7.1-⑫：不與 404 合併）；其餘（404 flag off / 400 / 403 /
        // 網絡異常）→ 整卡不渲染：不彈窗、不阻塞其它卡片。
        setProbeState(result.failure.status === 503 ? 'no_store' : 'off')
        return
      }
      setView(result.data)
      setProbeState('on')
    }
    run()
    return () => { cancelled = true }
  }, [teacherName, teacherId, refreshKey])

  /**
   * 【6b】「🔄 立即評估」：`POST /api/agent/stage/evaluate`（body 只有兩個鑑權欄位；#2 會寫評估快照、
   * 可能建一張升級推薦單）→ 成功後**重拉 #1** 取新快照與新的 `capabilities`（檔頭口徑 2：拿 #2 的
   * body 整體 `setView` 會把能力區的依據抹掉）。
   *
   * 失敗一律**卡內**呈現（不 alert、不彈窗）：404 = flag 中途被關 → 整卡退場；503 = 存儲掉了 →
   * 換成「遷移沒跑」紅字；其餘（400 / 403 / 網絡）→ 一行紅字說明並**保留舊畫面**（舊快照對老師仍有價值，
   * 不因為一次點擊失敗就白屏）。`#2` 的 200 回應體整份未讀（連 `changed` 都不讀）—— 本卡只認 #1 為 `view`。
   */
  const handleEvaluate = async () => {
    if (evaluating) return
    setEvaluating(true)
    setEvaluateNote('')
    const evaluated = await callStageApi<unknown>('/api/agent/stage/evaluate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ teacher_name: teacherName, teacher_id: teacherId })
    })
    if (!evaluated.ok) {
      setEvaluating(false)
      if (evaluated.failure.status === 404) { setProbeState('off'); return }
      if (evaluated.failure.status === 503) { setProbeState('no_store'); return }
      setEvaluateNote(`⚠ 評估未完成：${evaluated.failure.msg}`)
      return
    }
    const refreshed = await callStageApi<StageView>(
      `/api/agent/stage?${identityQuery(teacherName, teacherId)}`)
    setEvaluating(false)
    if (!refreshed.ok) {
      if (refreshed.failure.status === 404) { setProbeState('off'); return }
      if (refreshed.failure.status === 503) { setProbeState('no_store'); return }
      setEvaluateNote(`⚠ 評估已送出，但重讀階段視圖失敗（畫面仍是舊快照）：${refreshed.failure.msg}`)
      return
    }
    setView(refreshed.data)
    setProbeState('on')
    setEvaluateNote(`✅ 已重新評估（${clockText()}）`)
    // 【6c】通知父級重拉「智能體工作台」卡（檔頭口徑 3）：本輪可能剛建了一張升級推薦單
    // （⏳ 待你確認）或翻了階段 —— 老師不該還要等別的操作才看到。缺省不傳（獨立使用）時這行是 no-op。
    onEvaluated?.()
  }

  /**
   * 【6c】「確認降級」：`POST /api/agent/stage/demote`（body = 鑑權兩欄 + `to_stage` + `reason`；
   * §4.6-⑤）→ 成功**重拉 #1**：徽章翻新、`stage_source='manual_demote'`、`pending_*` 被清空
   * （服務層那一條 upsert 同時清待確認對，`agent_stage_service.py:2972-2973`）。
   *
   * 失敗一律**卡內**（檔頭 §6c 口徑 4）：
   *   · 404 `agent_stage_disabled`（flag 中途被關）→ 整卡退場；
   *   · 503 `agent_stage_store_unavailable`（遷移沒跑）→ 走 6a 的「階段表未就緒」紅字；
   *   · 其餘（400 / 409 / 503 `demote_write_failed` / 503 `stage_read_degraded` / 403 / 網絡）→ 紅字 +
   *     **保留舊畫面 + 二次確認區不關**（老師可改目標 / 改說明直接再試）。
   * 任何非 2xx 都**不改徽章**：假成功會讓老師以為真的降下去了（§4.6-⑤ 的設計意圖）。
   * ⚠ 503 按 `failure.code` 分而非狀態碼：`demote_write_failed` 是「寫不進去、階段保持原值」，
   * 與「表沒建」完全是兩回事（後者已有專門畫面）。
   */
  const handleDemote = async () => {
    if (demoting) return
    // 目標用**推導值**（不是 state 原值）：降級成功後 `view.stage` 已變，state 可能還記著舊選擇。
    const target = resolveDemoteTarget(view ? view.stage : '', demoteTarget)
    if (!target) {
      // 兜底：候選為空時按鈕已置灰，正常走不到這裡；不讓一個空 `to_stage` 送去換 400。
      setDemoteNote('⚠ 沒有可選的降級目標（當前階段未知或已在最低階段）')
      return
    }
    setDemoting(true)
    setDemoteNote('')
    const demoted = await callStageApi<unknown>('/api/agent/stage/demote', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        teacher_name: teacherName,
        teacher_id: teacherId,
        to_stage: target,
        reason: demoteReason
      })
    })
    if (!demoted.ok) {
      setDemoting(false)
      if (demoted.failure.code === 'agent_stage_disabled') { setProbeState('off'); return }
      if (demoted.failure.code === 'agent_stage_store_unavailable') { setProbeState('no_store'); return }
      setDemoteNote(`⚠ 降級未完成：${demoted.failure.msg}`)
      return
    }
    const refreshed = await callStageApi<StageView>(
      `/api/agent/stage?${identityQuery(teacherName, teacherId)}`)
    setDemoting(false)
    setShowDemote(false)
    setDemoteReason(AGENT_STAGE_DEMOTE_REASON_DEFAULT)
    if (!refreshed.ok) {
      if (refreshed.failure.code === 'agent_stage_disabled') { setProbeState('off'); return }
      if (refreshed.failure.code === 'agent_stage_store_unavailable') { setProbeState('no_store'); return }
      setDemoteNote(`⚠ 降級已送出，但重讀階段視圖失敗（畫面仍是舊快照）：${refreshed.failure.msg}`)
      return
    }
    setView(refreshed.data)
    setProbeState('on')
    // 文案用**降級前**選中的 key：重讀後 `view.stage` 已經是目標階段，拿它反推「降去哪」會繞一圈。
    setDemoteNote(`✅ 已降級至「${stageKeyLabel(target)}」（已寫入階段審計與行動日誌）`)
    // 檔頭 §6c 口徑 6：降級會寫一行行動日誌 + 清待確認對 → 工作台那兩塊要立刻跟上。
    onEvaluated?.()
  }

  /**
   * 【6d】能力區三顆按鈕的**共用**處理器（`cap` = 能力鍵，按鈕清單見 `AGENT_STAGE_CAPABILITY_BUTTONS`）。
   *
   * 送出的路由只有兩條（§4.6-⑥⑦）：
   *   · 🧪 / 📜 → `POST /api/agent/stage/suggest`（body = 鑑權兩欄 + `draft_id` + `kind`）；
   *   · 🧾      → `POST /api/agent/stage/predraft`（body = 鑑權兩欄 + `draft_id` + `formula_name`
   *     —— 契約裡 #7 **整條忽略** `kind`，故不送；`formula_name` 留空 = 由模型按材料自擬方名）。
   * `draft_id` 是服務端反查的唯一鑰匙（**只信 DB**，不收客戶端上傳的病歷文本）：本卡只負責把它確認好，
   * 至於「這份草案算不算數」（屬於該老師？已簽字？已被新草案取代？）永遠由後端反查判定（404 照實顯示）。
   *
   * 失敗一律**卡內**呈現（檔頭 §6d 口徑 5）：任何非 2xx 都不顯示任何產出、也**清掉上一次的結果**
   * （一份陳舊的候選貼在「能力不足」旁邊會被讀成「他給了候選」）；404 / 503 表未就緒照 6a 的分級
   * （整卡退場 / 「階段表未就緒」紅字）。成功但空殼（`parse_failed` / 藥味全空）走同一句
   * 「模型這次沒給出可用內容」—— 解析失敗是**成功**，不是紅字故障（檔頭 §6d 口徑 6）。
   * 本處理器**不調** `onEvaluated()`：本族只寫 `agent_stage_log`，工作台兩塊沒有新行（§6d 口徑 7）。
   */
  const handleCapability = async (cap: keyof StageCapabilities) => {
    if (capBusy) return
    // 門控只有 `capabilities` 一處（按鈕就是按它置灰的）：這裡再問一次只是防鍵盤 / 程序觸發，
    // 不是第二個判定 —— 它與按鈕用的是同一格布爾。
    if (!view || view.capabilities?.[cap] !== true) return
    if (!draftIdUsable(draftId)) {          // 【6d 口徑 3】前置條件：無值 / 本地佔位草案（負 id）
      setCapResult(null)
      setCapNote(`⚠ ${draftUnusableHint(draftId)}`)
      return
    }
    const button = AGENT_STAGE_CAPABILITY_BUTTONS.find(item => item.cap === cap)
    const init: RequestInit = {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(cap === 'generate_predraft'
        ? { teacher_name: teacherName, teacher_id: teacherId, draft_id: draftId, formula_name: '' }
        : { teacher_name: teacherName, teacher_id: teacherId, draft_id: draftId, kind: button?.kind || '' })
    }
    /** 失敗 → 卡內紅字：404 = flag 中途被關（整卡退場）；503 表沒建 → 6a 的「階段表未就緒」。 */
    const noteFailure = (failure: StageApiFailure) => {
      if (failure.code === 'agent_stage_disabled') { setProbeState('off'); return }
      if (failure.code === 'agent_stage_store_unavailable') { setProbeState('no_store'); return }
      setCapNote(capabilityFailureText(failure, cap))
    }
    setCapBusy(cap)
    setCapNote('')
    setCapResult(null)
    if (cap === 'generate_predraft') {
      const asked = await callStageApi<StagePredraftResponse>('/api/agent/stage/predraft', init)
      setCapBusy('')
      if (!asked.ok) { noteFailure(asked.failure); return }
      const produced = predraftResultOf(asked.data)
      if (!produced) { setCapNote(AGENT_STAGE_CAPABILITY_EMPTY_TEXT); return }
      setCapResult(produced)
      return
    }
    const asked = await callStageApi<StageSuggestResponse>('/api/agent/stage/suggest', init)
    setCapBusy('')
    if (!asked.ok) { noteFailure(asked.failure); return }
    // 走哪一種結果由**送出的那一格** `kind` 決定（不拿回包裡的 `kind` 當分支依據：它只是回聲）。
    const produced = cap === 'suggest_prescription' ? formulaResultOf(asked.data) : patternResultOf(asked.data)
    if (!produced) { setCapNote(AGENT_STAGE_CAPABILITY_EMPTY_TEXT); return }
    setCapResult(produced)
  }

  // §4.5-⑤ / 裁決②：503 = 運維故障（遷移沒跑）→ **卡內紅字**說清楚，不靜默消失
  if (probeState === 'no_store') {
    return (
      <div style={ASP_BOX}>
        <div style={{ ...ASP_TITLE, marginBottom: '12px' }}>🧭 智能體階段</div>
        <div style={ASP_ERROR}>階段表未就緒，請聯絡管理員（遷移未跑）</div>
      </div>
    )
  }
  // flag off（404）/ 身份缺失 / 探測進行中 / 其它失敗 → 整卡不渲染（DOM 與 Epic 2 之前逐字面一致）
  if (probeState !== 'on' || !view) return null

  const blockers = Array.isArray(view.blockers)
    ? view.blockers.filter(code => typeof code === 'string' && code.trim().length > 0)
    : []
  const sinceText = stageSinceText(view.stage_since)
  const sourceLabel = AGENT_STAGE_SOURCE_LABELS[view.stage_source] || ''
  const nextLabel = view.next_stage ? stageKeyLabel(view.next_stage) : ''
  const pendingLabel = view.pending_stage ? stageKeyLabel(view.pending_stage) : ''

  // 【6b】指標 / 閾值**全部取自 #1 的上次快照**（本卡不重算、不補算）。用 `Partial` 不是型別悲觀：
  // 後端違約（少一個鍵）時退化為「樣本不足」而不是把老師首頁整頁炸掉 —— 白屏的代價遠大於一次顯示兜底。
  const metrics: Partial<StageMetrics> = view.metrics || {}
  const thresholds: Partial<StageThresholds> = view.thresholds || {}
  const templateMatch = metrics.template_match
  const modification = metrics.modification_consistency
  const minSamples = typeof thresholds.min_samples === 'number' ? thresholds.min_samples : 0
  const configBadge = configSourceBadge(view.config_source)
  // 【6d】能力區的五鍵：`Partial` 兜底（理由同 `metrics` / `thresholds` —— 後端違約時退化成
  // 「全部置灰」而不是把老師首頁炸掉）。置灰是**唯一保守方向**：寧可不給按鈕，也不放行一個沒依據的請求。
  const capabilities: Partial<StageCapabilities> = view.capabilities || {}
  // §2.5 的臨時運維閘：放寬態下**不推荐升级** → 必須當場可見（不能只藏在折疊區裡）。
  const matrixRelaxed = thresholds.matrix_enforced === false
  // 【6c】降級候選（由低到高的前幾階）與「實際會送出的目標」：兩者都隨 `view.stage` 推導
  // （見檔頭 §6c 口徑 2/5 —— 候選只是下拉的選項清單；方向判定在後端）。
  const currentRank = AGENT_STAGE_ORDER.indexOf(view.stage)
  const demoteTargets = lowerStageKeys(view.stage)
  const demoteTargetValue = resolveDemoteTarget(view.stage, demoteTarget)

  return (
    <div style={ASP_BOX}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '10px', flexWrap: 'wrap', marginBottom: '12px' }}>
        <div style={ASP_TITLE}>🧭 智能體階段</div>
        <span style={{ ...ASP_HINT, flex: '1 1 240px', textAlign: 'right' }}>
          五階段：{AGENT_STAGE_ORDER.map(stageKeyLabel).join(' → ')}（只看表現，不看人情）
        </span>
      </div>

      {/* 階段徽章：繁文字面量**直接用後端 `stage_label`**（真值只有一個來源，本卡不自己查標籤表）。
          僅在後端也沒給（空 = flag off / 讀異常的短路體）時，才退回 key 的鏡像文案。 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
        <span style={ASP_BADGE}>{view.stage_label || stageKeyLabel(view.stage)}</span>
        {sinceText && <span style={ASP_HINT}>自 {sinceText} 起</span>}
        <span style={ASP_HINT}>{nextLabel ? `下一階段：${nextLabel}` : '已達最高階段'}</span>
        {/* 【6b】`config_source` 角標：`marginLeft:'auto'` 推到行尾（「角標」的位置語義），窄屏換行時自然回落。 */}
        {configBadge && <span style={{ ...ASP_CHIP, marginLeft: 'auto' }}>{configBadge}</span>}
      </div>

      {sourceLabel && <div style={{ ...ASP_HINT, marginTop: '6px' }}>階段來源：{sourceLabel}</div>}

      {/* `pending_stage` 有值 = 智能體已推薦升級、等老師確認。
          **不新增升階按鈕**（§4.7-㉑）：確認動作只有一個入口，就是下方既有的「⏳ 待你確認」區塊。 */}
      {pendingLabel && (
        <div style={ASP_PENDING}>
          ⏳ 已推薦升級至「{pendingLabel}」，請在下方「⏳ 待你確認」按 ✅
          {view.pending_task_id ? `（任務 #${view.pending_task_id}）` : ''}
        </div>
      )}

      {/* `degraded=true` = 階段真值讀取異常（fail-closed 兜底體）：必須明說，
          不能讓老師把兜底值當成真值。 */}
      {view.degraded && (
        <div style={ASP_ERROR}>
          階段真值讀取異常（降級態）：上面的階段與來源是系統兜底值，請聯絡管理員核對後再參考。
        </div>
      )}

      {/* ---------- 【6b】指標區（① ② ③；數值取自上次快照，本卡**不重算**） ---------- */}
      <div style={{ borderTop: '1px dashed #ece3cd', marginTop: '12px', paddingTop: '10px' }}>
        <div style={ASP_SECTION_TITLE}>📊 指標（取自上次評估快照）</div>
        {/* ① 模板匹配度：`value === null` = **空集**（不是 0 分）→ 必須顯示「樣本不足（N/M）」，
            顯示 0% 會讓「樣本不夠」看起來像「表現很差」。違規 > 0 = 鐵律信號 → 紅字如實報。 */}
        <div style={ASP_METRIC_ROW}>
          <span style={ASP_METRIC_LABEL}>{AGENT_STAGE_METRIC_LABELS.template_match}</span>
          <span style={ASP_METRIC_VALUE}>
            {templateMatch && typeof templateMatch.value === 'number'
              ? `${ratioPercentText(templateMatch.value)}（樣本 ${templateMatch.samples} 份）`
              : samplesShortText(templateMatch ? templateMatch.samples : 0, minSamples)}
          </span>
          {templateMatch && templateMatch.violations > 0 && (
            <span style={ASP_ALERT_TEXT}>⚠ 鐵律違規 {templateMatch.violations} 次</span>
          )}
        </div>
        {/* ② 病歷修改一致率：同樣「無樣本 ≠ 0%」；近似樣本（舊數據只有 `ai_draft`）與最差一份
            都要標出來 —— 平均值好看但有一份爛，老師有權知道。 */}
        <div style={ASP_METRIC_ROW}>
          <span style={ASP_METRIC_LABEL}>{AGENT_STAGE_METRIC_LABELS.modification_consistency}</span>
          <span style={ASP_METRIC_VALUE}>
            {modification && typeof modification.value === 'number'
              ? `${ratioPercentText(modification.value)}（樣本 ${modification.samples} 份）`
              : samplesShortText(modification ? modification.samples : 0, minSamples)}
          </span>
          {modification && modification.approx_samples > 0 && (
            <span style={ASP_METRIC_HINT}>含 {modification.approx_samples} 份近似樣本（舊數據）</span>
          )}
          {modification && typeof modification.min === 'number' && (
            <span style={ASP_METRIC_HINT}>最差樣本 {ratioPercentText(modification.min)}</span>
          )}
        </div>
        {/* ③ 問診偏好一致率：Epic 2 恆為 `null`（佔位）→ **固定文案**，不顯示 0% / 不顯示破折號。 */}
        <div style={ASP_METRIC_ROW}>
          <span style={ASP_METRIC_LABEL}>{AGENT_STAGE_METRIC_LABELS.inquiry_preference_consistency}</span>
          <span style={ASP_METRIC_HINT}>{AGENT_STAGE_INQUIRY_PLACEHOLDER}</span>
        </div>

        {/* 13 鍵閾值：預設收起（老師的日常視線是徽章 + 指標；閾值是備查 / 對賬用）。
            展開後逐鍵「標籤 : 值」，比率鍵附原值 → 能與後端配置、`config_changed` 日誌逐字對上。 */}
        <div style={{ marginTop: '10px' }}>
          <button type="button" style={ASP_FOLD_BUTTON} onClick={() => setShowThresholds(open => !open)}>
            {showThresholds ? '▾' : '▸'} ⚙ 判定閾值（{AGENT_STAGE_THRESHOLD_ROWS.length} 項）
          </button>
          {showThresholds && (
            <div style={{ marginTop: '6px' }}>
              {AGENT_STAGE_THRESHOLD_ROWS.map(row => (
                <div key={row.key} style={ASP_METRIC_ROW}>
                  <span style={{ ...ASP_METRIC_LABEL, fontWeight: 'normal', minWidth: '220px' }}>
                    {row.label}
                  </span>
                  <span style={ASP_METRIC_VALUE}>{thresholdValueText(thresholds, row)}</span>
                </div>
              ))}
              <div style={{ ...ASP_HINT, marginTop: '6px' }}>
                閾值可由管理員（全局行）/ 老師（專屬行）/ 環境變數覆蓋；每次評估都現讀，改完下一次評估即生效。
              </div>
            </div>
          )}
        </div>
        {/* 矩陣放寬的紅字**不藏進折疊區**：收起狀態下也要看得見（§2.5：放寬態不推薦升級）。 */}
        {matrixRelaxed && (
          <div style={{ ...ASP_ALERT_TEXT, marginTop: '6px' }}>⚠ 權限矩陣已由管理員放寬（臨時）</div>
        )}
      </div>

      {/* ---------- 【6b】手動評估（§4.5-⑤ 按鈕 / §4.6-② 接口） ---------- */}
      {/* 按鈕**常顯**（檔頭口徑 1）；`stale` 只負責那句設計原句的提示（§4.5-⑤：提示不阻斷任何東西）。 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap', marginTop: '12px' }}>
        <button
          type="button"
          style={evaluating ? ASP_BUTTON_OFF : ASP_BUTTON}
          onClick={handleEvaluate}
          disabled={evaluating}
        >
          {evaluating ? '評估中…' : '🔄 立即評估'}
        </button>
        {view.stale && <span style={ASP_HINT}>⏳ {AGENT_STAGE_STALE_HINT}</span>}
        {/* 回執（成功 = 時間戳 / 失敗 = ⚠ 開頭）；以 `⚠` 前綴決定顏色 —— 只有這兩種回執，不值得為它多開一個 state。 */}
        {evaluateNote && (
          <span style={evaluateNote.startsWith('⚠') ? ASP_ALERT_TEXT : ASP_METRIC_HINT}>{evaluateNote}</span>
        )}
      </div>

      {/* ---------- 【6d】能力區（§4.5-⑤「按 capabilities 渲染」；唯一門控來源 = 後端 #1 的五鍵） ---------- */}
      {/* 放在 6b 按鈕行**下方**、6c 降級區**上方**（新開一個 div）→ 那兩區的 JSX 一字不改（檔頭 §6d 口徑 1）。 */}
      {/* 三顆按鈕**常顯**（同 6b「🔄 立即評估」的理由）：置灰時理由就貼在自己那顆下面，不讓老師猜。 */}
      <div style={ASP_CAP_BOX}>
        <div style={ASP_SECTION_TITLE}>
          🧠 智能體能力（{view.stage_label || stageKeyLabel(view.stage)}）
        </div>
        {/* 沒有可引用的草案時，先把「怎麼才能用」說在最上面（三顆都置灰，理由同一件事）。 */}
        {!draftIdUsable(draftId) && (
          <div style={{ ...ASP_HINT, marginBottom: '6px' }}>{draftUnusableHint(draftId)}</div>
        )}
        <div style={ASP_CAP_ROW}>
          {AGENT_STAGE_CAPABILITY_BUTTONS.map(item => {
            const allowed = capabilities[item.cap] === true
            const busy = capBusy === item.cap
            const ready = allowed && draftIdUsable(draftId) && capBusy === ''
            return (
              <div key={item.cap} style={ASP_CAP_CELL}>
                <button
                  type="button"
                  style={ready ? ASP_BUTTON_OUTLINE : ASP_BUTTON_OUTLINE_OFF}
                  onClick={() => handleCapability(item.cap)}
                  disabled={!ready}
                >
                  {busy ? item.busyText : item.text}
                </button>
                {/* 置灰理由逐顆說（不集中成一段）：能力沒開 → 「尚未開放（需「見習期」）」；
                    能力開了但沒有可引用的草案 → 前置條件；另一顆在飛 → 單飛說明。 */}
                {!allowed && <span style={ASP_METRIC_HINT}>{capabilityClosedText(item.cap)}</span>}
                {allowed && !draftIdUsable(draftId) && (
                  <span style={ASP_METRIC_HINT}>需先選中未簽草案</span>
                )}
                {allowed && draftIdUsable(draftId) && !busy && capBusy !== '' && (
                  <span style={ASP_METRIC_HINT}>另一項生成中，完成後再試</span>
                )}
              </div>
            )
          })}
        </div>
        {/* 一行回執：`⚠` 開頭 = 失敗（紅字）；否則 = 解析失敗 / 本次沒產出（**灰字**，它是 200）。
            兩種互斥：有產出就顯示下面的結果區，不會同時出現。 */}
        {capNote && (
          <div style={capNote.startsWith('⚠') ? ASP_CAP_ALERT : ASP_CAP_EMPTY}>{capNote}</div>
        )}

        {/* 🧪 證型候選：**原文依據逐條列出**（`basis` 是 AI 層的硬契約：沒有原文片段就不產出這條）——
            老師要能自己核對「這句話出自病歷哪一段」，否則一個候選證型只是猜測。 */}
        {capResult?.kind === 'pattern' && (
          <div style={ASP_CAP_RESULT}>
            <div style={ASP_METRIC_HINT}>
              證型候選 {capResult.items.length} 條
              {capResult.generatedAt ? `（產生於 ${capResult.generatedAt}）` : ''}
            </div>
            {capResult.items.map((item, index) => {
              const basis = stringList(item.basis)
              return (
                <div key={`pattern-${index}`} style={{ marginTop: '6px' }}>
                  <div>
                    <span style={ASP_METRIC_VALUE}>{item.name || '（模型未給證型名）'}</span>
                    <span style={{ ...ASP_METRIC_HINT, marginLeft: '8px' }}>
                      信心：{AGENT_STAGE_CONFIDENCE_LABELS[item.confidence || ''] || item.confidence || '未給'}
                    </span>
                  </div>
                  <div style={ASP_METRIC_HINT}>
                    原文依據：{basis.length > 0 ? basis.join('；') : '未給'}
                  </div>
                  {item.note && <div style={ASP_METRIC_HINT}>提示：{item.note}</div>}
                </div>
              )
            })}
            <div style={{ ...ASP_METRIC_HINT, marginTop: '6px' }}>
              {capResult.disclaimer || '僅供參考'}；以上內容只在本卡顯示，不會自動填入病歷 —— 採用與否由你判斷。
            </div>
          </div>
        )}

        {/* 📜 方劑建議：**無劑量**（AI 層逐項去劑量、服務層白名單只留四鍵）→ 照實說明，
            免得老師讀成「模型忘了寫劑量」。 */}
        {capResult?.kind === 'formula' && (
          <div style={ASP_CAP_RESULT}>
            <div style={ASP_METRIC_HINT}>
              方劑建議 {capResult.items.length} 條
              {capResult.generatedAt ? `（產生於 ${capResult.generatedAt}）` : ''}
            </div>
            {capResult.items.map((item, index) => {
              const herbs = stringList(item.composition)
              return (
                <div key={`formula-${index}`} style={{ marginTop: '6px' }}>
                  <div>
                    <span style={ASP_METRIC_VALUE}>{item.name || '（模型未給方名）'}</span>
                    {item.modification && (
                      <span style={{ ...ASP_METRIC_HINT, marginLeft: '8px' }}>加減：{item.modification}</span>
                    )}
                  </div>
                  <div style={ASP_METRIC_HINT}>
                    藥味（本建議不含劑量）：{herbs.length > 0 ? herbs.join('、') : '未給'}
                  </div>
                </div>
              )
            })}
            <div style={{ ...ASP_METRIC_HINT, marginTop: '6px' }}>
              {capResult.disclaimer || '僅供參考'}；劑量與煎服法須由你判定；以上只在本卡顯示，不會自動開方。
            </div>
          </div>
        )}

        {/* 🧾 預處方預填：**唯一帶劑量**的能力（授權期專屬）→ 逐列列出「劑量 / 角色」，空值顯示「—」，
            並把 §4.6-⑦ 的 `note`（儲存處方仍須老師操作）逐字帶上 —— 前端不重寫這句鐵律文案。 */}
        {capResult?.kind === 'predraft' && (
          <div style={ASP_CAP_RESULT}>
            <div style={{ ...ASP_METRIC_VALUE, marginBottom: '4px' }}>
              預處方預填：{capResult.predraft.formula_name || '（模型未給方名）'}
            </div>
            <div style={{ ...ASP_METRIC_ROW, ...ASP_METRIC_HINT }}>
              <span style={ASP_CAP_HERB_CELL}>藥味</span>
              <span style={ASP_CAP_DOSE_CELL}>劑量</span>
              <span style={ASP_CAP_ROLE_CELL}>角色</span>
            </div>
            {capResult.predraft.items.map((item, index) => (
              <div key={`predraft-${index}`} style={ASP_METRIC_ROW}>
                <span style={ASP_CAP_HERB_CELL}>{item.herb || '—'}</span>
                <span style={ASP_CAP_DOSE_CELL}>{item.dose || '—'}</span>
                <span style={ASP_CAP_ROLE_CELL}>{item.role || '—'}</span>
              </div>
            ))}
            {capResult.predraft.decoction && (
              <div style={ASP_METRIC_ROW}>
                <span style={{ ...ASP_METRIC_LABEL, minWidth: '84px', fontWeight: 'normal' }}>煎服法</span>
                <span>{capResult.predraft.decoction}</span>
              </div>
            )}
            <div style={{ ...ASP_METRIC_HINT, marginTop: '6px' }}>
              「—」= 模型拿不準（請自行判定）；{capResult.note || '僅供預填，儲存處方仍須老師操作'}；
              以上只在本卡顯示，不會自動填入開方區 —— 要採用請你自己在診室逐項核對後操作。
            </div>
            <div style={ASP_METRIC_HINT}>{capResult.disclaimer || '僅供參考'}</div>
          </div>
        )}
      </div>

      {/* ---------- 【6c】手動降級（§4.5-⑤：卡內二次確認，不彈窗、不阻斷其它卡片） ---------- */}
      {/* 刻意放在 6b 按鈕行**下方**（新開一個 div）→ 6b 那一行的 JSX 一字不改（檔頭 §6c 口徑 1）。 */}
      <div style={{ marginTop: '10px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
          <button
            type="button"
            style={demoteTargets.length === 0 || demoting ? ASP_BUTTON_OUTLINE_OFF : ASP_BUTTON_OUTLINE}
            onClick={() => { setShowDemote(open => !open); setDemoteNote('') }}
            disabled={demoteTargets.length === 0 || demoting}
          >
            ⬇ 降級
          </button>
          {/* 無可降層級時把**原因**說在按鈕旁（置灰按鈕不給理由 = 讓老師自己猜）。 */}
          {demoteTargets.length === 0 && (
            <span style={ASP_HINT}>
              {currentRank < 0
                ? '當前階段未知（後端回傳的 stage 不在五階段內），無法降級；請先「🔄 立即評估」或聯絡管理員'
                : '已在最低階段（觀察期），無可降級'}
            </span>
          )}
          {/* 成功回執顯示在按鈕旁（此時二次確認區已收起）；失敗的紅字顯示在區內（二次確認區不關）。 */}
          {!showDemote && demoteNote && (
            <span style={demoteNote.startsWith('⚠') ? ASP_ALERT_TEXT : ASP_METRIC_HINT}>{demoteNote}</span>
          )}
        </div>

        {showDemote && demoteTargets.length > 0 && (
          <div style={ASP_DEMOTE_BOX}>
            <div style={{ color: '#8b4513', fontWeight: 'bold', marginBottom: '6px' }}>
              確定要降級嗎？降級立即生效（不必等任何人確認），且智能體不會自動幫你升回。
            </div>
            <div style={ASP_METRIC_ROW}>
              <span style={{ ...ASP_METRIC_LABEL, minWidth: '84px' }}>降級到</span>
              <select
                style={ASP_SELECT}
                value={demoteTargetValue}
                onChange={event => setDemoteTarget(event.target.value)}
              >
                {demoteTargets.map(key => (
                  <option key={key} value={key}>{stageKeyLabel(key)}</option>
                ))}
              </select>
              <span style={ASP_METRIC_HINT}>當前：{view.stage_label || stageKeyLabel(view.stage)}</span>
            </div>
            <div style={ASP_METRIC_ROW}>
              <span style={{ ...ASP_METRIC_LABEL, minWidth: '84px' }}>降級說明</span>
              <input
                style={ASP_INPUT}
                value={demoteReason}
                maxLength={AGENT_STAGE_DEMOTE_REASON_MAX_LENGTH}
                placeholder="可留空（審計只留固定句式）"
                onChange={event => setDemoteReason(event.target.value)}
              />
            </div>
            <div style={{ ...ASP_HINT, lineHeight: '1.7' }}>
              這裡寫的說明會原文寫進階段變更審計（下方工作台的「📜 行動日誌」也會多一行）；
              審計裡的每一句話都要能追溯到一個人，所以接口層不替你編說明。
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap', marginTop: '8px' }}>
              <button
                type="button"
                style={demoting ? ASP_BUTTON_OFF : ASP_BUTTON}
                onClick={handleDemote}
                disabled={demoting}
              >
                {demoting ? '降級中…' : '確認降級'}
              </button>
              <button
                type="button"
                style={ASP_BUTTON_OUTLINE}
                onClick={() => { setShowDemote(false); setDemoteNote('') }}
                disabled={demoting}
              >
                取消
              </button>
              {demoting && <span style={ASP_METRIC_HINT}>寫入階段真值中，請勿關閉頁面…</span>}
            </div>
            {demoteNote && (
              <div style={{ ...(demoteNote.startsWith('⚠') ? ASP_ALERT_TEXT : ASP_METRIC_HINT), marginTop: '6px' }}>
                {demoteNote}
              </div>
            )}
          </div>
        )}
      </div>

      {/* `blockers[]` 逐條繁體展示；`[]` 是**有意義的空**（上一輪真的不卡任何一條）→ 整段不顯示 */}
      {blockers.length > 0 && (
        <div style={{ borderTop: '1px dashed #ece3cd', marginTop: '12px', paddingTop: '10px' }}>
          <div style={ASP_SECTION_TITLE}>🚧 距下一階段的阻礙（{blockers.length}）</div>
          {blockers.map((code, index) => (
            <div key={`${code}-${index}`} style={{ fontSize: '13px', color: '#333', lineHeight: '1.8' }}>
              · {blockerText(code)}
            </div>
          ))}
        </div>
      )}

      {/* 鐵律文案：固定顯示在卡片底部，逐字、不可省略（§4.5-⑤） */}
      <div style={ASP_FOOTER}>{AGENT_STAGE_IRON_RULE}</div>
    </div>
  )
}

/**
 * 老師端首頁「🧭 智能體階段」卡（Epic 2 · 施工步驟 **6a + 6b + 6c**）
 *   6a：骨架 + 掛載探測 + 階段真值靜態區；6b：指標區（① ② ③）+ 閾值折疊區 + `config_source` 角標 + 「🔄 立即評估」；
 *   6c：「⬇ 降級」卡內二次確認（`to_stage` 只列低於當前 rank 者 + `reason` 輸入）+ 評估 / 降級成功後
 *       回調父級重拉「智能體工作台」（`onEvaluated`）。
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
 *   ✗ 6d 能力區（`capabilities` → 🧪 證型候選 / 📜 方劑建議 / 🧾 預處方預填；需 `draftId`）。
 *   `capabilities` 的型別已按契約定好（形狀即契約），6d 只加渲染、不改型別。
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
  /** 【6d · 已裁決①】當前就診學生的未簽草案 id；無值 → 能力區三按鈕置灰。6a 不渲染能力區，故不讀。 */
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
 * 【6d 待補】`CAPABILITY_MIN_STAGE_LABELS`（能力 → 最低階段，用於置灰原因「尚未開放（需「見習期」）」）
 * 刻意**不在本步定義**：6a 不渲染能力區 → 常量無人讀 → `tsc -b`（`noUnusedLocals`）直接報錯。
 * 它與它的消費者在 6d 一起落地（鏡像來源：`agent_stage_service.py:79-85` `CAPABILITY_MIN_STAGE`）。
 */
const AGENT_STAGE_LABELS: Record<string, string> = {
  observation: '觀察期',
  learning: '學習期',
  apprentice: '見習期',
  assistant: '助手期',
  authorized: '授權期'
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

/* ============================ 主組件 ============================ */

export default function AgentStagePanel({ teacherName, teacherId, refreshKey, onEvaluated }: AgentStagePanelProps) {
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

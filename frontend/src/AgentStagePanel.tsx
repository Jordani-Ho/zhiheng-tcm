/**
 * 老師端首頁「🧭 智能體階段」卡（Epic 2 · 施工步驟 **6a**：骨架 + 掛載探測 + 靜態區）
 *
 * 對齊：docs/epic2-agent-stage-design-v1.md
 *   §4.5-⑤ 前端卡片（探測 / 展示 / 按鈕 / 能力區 / 鐵律文案 / 樣式復用）
 *   §4.6-① `GET /api/agent/stage`（服務層 `stage_view()` 直出 **15 鍵**，形狀即契約）
 *   §4.7   掛載點與施工循序
 *
 * 【本步（6a）的邊界】只做「掛載探測 + 階段真值靜態區 + 底部鐵律文案」：
 *   ✓ 徽章（後端 `stage_label` 直出，前端**不自己查**標籤表）、`stage_since`、`stage_source` 來源注記、
 *     `next_stage`、`pending_stage` / `pending_task_id`（引導去按既有的 ✅）、`blockers[]`、
 *     `stale` / `degraded` 提示；
 *   ✗ 6b 指標區（① ② ③ + 閾值回顯 + `config_source` 角標）與「🔄 立即評估」；
 *   ✗ 6c 「⬇ 降級」（卡內二次確認 + `reason` 輸入）與確認升級後的完整刷新鏈路；
 *   ✗ 6d 能力區（`capabilities` → 🧪 證型候選 / 📜 方劑建議 / 🧾 預處方預填；需 `draftId`）。
 *   `metrics` / `thresholds` / `capabilities` / `config_source` 的型別本步已按契約定好（形狀即契約），
 *   只是**不渲染** —— 6b/6c/6d 只加渲染，不改型別。
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
 * `stale=true` 的提示。設計 §4.5-⑤ 的原句尾半段是「可點「立即評估」」——那個按鈕屬 6b，
 * **6a 不指向不存在的控件**（UI 說謊比不提示更糟）；6b 落地按鈕時把本句接成設計原句即可。
 */
const AGENT_STAGE_STALE_HINT = '指標可能已過時：上次評估快照已超出有效期，建議重算'

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

/** blocker 英文碼 → 繁體一句話（未登記的碼原樣顯示 + 標記，見常量註釋）。 */
const blockerText = (code: string) => AGENT_STAGE_BLOCKER_LABELS[code] || `${code}（未登記文案）`

/** ISO 串 → 「YYYY-MM-DD」（`stage_since` 空串 = 從未確認過升階 → 返回空串表示整段不顯示）。 */
const stageSinceText = (value: string) => {
  const text = (value || '').trim()
  if (!text) return ''
  return text.length >= 10 ? text.slice(0, 10) : text
}

/* ============================ 主組件 ============================ */

export default function AgentStagePanel({ teacherName, teacherId, refreshKey }: AgentStagePanelProps) {
  const [probeState, setProbeState] = useState<StageProbeState>('probing')
  const [view, setView] = useState<StageView | null>(null)

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

      {view.stale && <div style={{ ...ASP_HINT, marginTop: '8px' }}>⏳ {AGENT_STAGE_STALE_HINT}</div>}

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

/**
 * 老師端「📜 模板傳承（四類）」配置頁
 *
 * 對齊：docs/epic1-template-design-v1.md §13（前端：老師端模板配置頁）
 *   §13.1 掛載點與開關：掛在「管理」頁籤；`GET /api/templates` 探測（404 → 整卡不渲染；503 → 卡內紅字）
 *   §13.2 組件結構：本檔＝TemplateStudio + 子組件（四類 Tab / 列表 / 編輯器 / 四個表單 / 版本鏈 / 只讀預覽）
 *   §13.3 交互流轉：新建 → 存草稿 → 發佈（自動歸檔舊 active，灰條提示）→ 檢視 → 基於此版本修訂 → 歸檔 → 重新啟用
 *   §13.4 文案規範：一律繁體古字；**炁 / 氣 按語義區分**（先天之炁、後天之氣、調理氣機），禁止全局簡繁轉換
 *   §13.5 狀態與數據流：只用 useState，不引狀態庫
 *   §13.6 二次確認文案：歸檔 / 發佈頂替 / 重新啟用三條
 *
 * 後端契約（本檔只讀不改，接口一字不動）：
 *   GET    /api/templates?teacher_name&teacher_id&type?&status?&include_schema?  → {templates, counts}
 *   GET    /api/templates/{id}                                                   → {template, chain, generated_count}
 *   GET    /api/templates/active?type=                                           → {template|null}
 *   POST   /api/templates                    body {teacher_name, teacher_id, type, name?, schema_json?}
 *   PUT    /api/templates/{id}                body {teacher_name, teacher_id, name?, schema_json?}
 *   POST   /api/templates/{id}/publish         body {teacher_name, teacher_id} → {template, archived_ids, changed}
 *   POST   /api/templates/{id}/archive         body {teacher_name, teacher_id} → {template, changed}
 *   POST   /api/templates/{id}/activate        body {teacher_name, teacher_id} → {template, archived_ids, changed}
 *   POST   /api/templates/{id}/derive          body {teacher_name, teacher_id} → {template, reused_draft}
 *   錯誤體：{detail: {error, msg, errors:[{path,msg}], warnings:[]}}（讀 res.detail.error / .msg）
 *   flag off → 404 templates_disabled；表未就緒 → 503 template_store_unavailable
 *
 * 樣式：不新增任何 npm 依賴；沿用存量內聯 style + serif 字體 + 主色 #8b4513（與 App.tsx 視覺一致）。
 */
import { useEffect, useState } from 'react'
import type { CSSProperties } from 'react'

/* ============================ 型別與契約常量 ============================ */

export type TemplateType = 'inquiry' | 'record' | 'treatment' | 'prescription'
export type TemplateStatus = 'draft' | 'active' | 'archived'

/** §10.1 模板對象（所有模板類響應共用；`schema_json` 是解析後的對象，不是 JSON 字串）。 */
export interface TemplateRow {
  id: number
  type: TemplateType
  teacher_id: string
  lineage_id: string
  name: string
  schema_json: Record<string, any>
  version: number
  parent_template_id: number | null
  status: TemplateStatus
  created_at: string
  updated_at: string
  is_legacy: boolean
}

/** §10.2 #2 的 `chain`：同 scope 全部版本（version 降序）。 */
export interface ChainItem { id: number; version: number; status: TemplateStatus; updated_at: string }

/** 校驗層 `errors[]`（§9.0：path 用 JS 風格，如 fields[2].label）。 */
export interface SchemaIssue { path?: string; msg?: string }

/** 保存 / 發佈響應裡的 `warnings`（§9.4 目前只有 prescription 的「未入庫藥材」）。 */
export interface TemplateWarning { code?: string; herb_name?: string; msg?: string }

/** 接口失敗（不拋異常，用返回值表達，避免 throw 非 Error 對象）。 */
export interface TemplateApiFailure {
  status: number
  code: string
  msg: string
  details: SchemaIssue[]
  warnings: TemplateWarning[]
}

type ApiResult<T> = { ok: true; data: T } | { ok: false; failure: TemplateApiFailure }

/* ============================ 契約常量（本檔內部使用） ============================ */

/** §13.2 四類切換：問診 / 病歷 / 施治 / 開方。 */
const TEMPLATE_TYPE_TABS: { key: TemplateType; label: string }[] = [
  { key: 'inquiry', label: '問診' },
  { key: 'record', label: '病歷' },
  { key: 'treatment', label: '施治' },
  { key: 'prescription', label: '開方' }
]

/** §13.4 狀態徽章：草稿 / 生效中 / 已歸檔。 */
const TEMPLATE_STATUS_LABELS: Record<TemplateStatus, string> = {
  draft: '草稿',
  active: '生效中',
  archived: '已歸檔'
}

/** 卡片底部固定展示的邊界聲明（§13.4）。 */
const TEMPLATE_BOUNDARY_NOTICE = '智能體永不診斷、永不開方、永不簽字'

/**
 * 君臣佐使 / 煎法白名單：`value` 必須與後端一字不差
 * （`database.PRESCRIPTION_ROLES` / `PRESCRIPTION_COOKING_METHODS`，與 `App.tsx` 的
 * `HERB_ROLES` / `COOKING_METHODS` 同源；模板校驗對不在白名單的值直接 400 `schema_invalid`）。
 * 這裡 `value` 是落庫原文（不可改），`label` 才是繁體顯示文案（§13.4）。
 */
const TEMPLATE_ROLE_OPTIONS: { value: string; label: string }[] = [
  { value: '君', label: '君' },
  { value: '臣', label: '臣' },
  { value: '佐', label: '佐' },
  { value: '使', label: '使' }
]
const TEMPLATE_ROLE_UNMARKED_LABEL = '未標註'
const TEMPLATE_COOKING_OPTIONS: { value: string; label: string }[] = [
  { value: '常规', label: '常規' },
  { value: '先煎', label: '先煎' },
  { value: '后下', label: '後下' },
  { value: '包煎', label: '包煎' },
  { value: '烊化', label: '烊化' },
  { value: '另煎', label: '另煎' },
  { value: '冲服', label: '沖服' }
]
const TEMPLATE_DEFAULT_COOKING = '常规'

/** §9.1 inquiry fields[].answer_type 的三個合法值（顯示文案繁體化）。 */
const ANSWER_TYPE_OPTIONS: { value: string; label: string }[] = [
  { value: 'text', label: '文字' },
  { value: 'number', label: '數字' },
  { value: 'choice', label: '單選' }
]

/** §9.2 record sections[].writable_by：ai = 智能體可填 / teacher = 留待老師。 */
const WRITABLE_BY_OPTIONS: { value: string; label: string }[] = [
  { value: 'ai', label: '智能體可填' },
  { value: 'teacher', label: '留待老師（智能體永不填）' }
]

/** §9 數量邊界（前端先攔，避免白跑一趟拿 400）。 */
const INQUIRY_MIN_FIELDS = 3
const INQUIRY_MAX_FIELDS = 20
const RECORD_MIN_SECTIONS = 2
const RECORD_MAX_SECTIONS = 12
const TREATMENT_MAX_CONTENT = 2000
const TREATMENT_MAX_PLACEHOLDERS = 8
const PRESCRIPTION_MAX_HERBS = 40
const MAX_FORBIDDEN_WORDS = 20

/* ============================ 樣式（沿用存量視覺） ============================ */

const TS_BOX: CSSProperties = {
  background: '#fdfcf0', border: '1px solid #d4c8a8', borderRadius: '12px', padding: '24px',
  marginBottom: '20px', boxShadow: '0 4px 12px rgba(0,0,0,0.06)'
}
const TS_INPUT: CSSProperties = {
  width: '100%', padding: '8px', borderRadius: '6px', border: '1px solid #d4c8a8',
  fontFamily: 'serif', marginBottom: '8px', boxSizing: 'border-box'
}
const TS_SELECT: CSSProperties = { ...TS_INPUT, marginBottom: 0 }
const TS_SMALL_INPUT: CSSProperties = { ...TS_SELECT, padding: '6px', fontSize: '13px' }
const TS_PRIMARY_BTN: CSSProperties = {
  padding: '6px 14px', borderRadius: '20px', border: 'none', background: '#8b4513',
  color: '#fdfcf0', cursor: 'pointer', fontFamily: 'serif', fontSize: '13px'
}
const TS_GREEN_BTN: CSSProperties = { ...TS_PRIMARY_BTN, background: '#5a7d5a' }
const TS_GHOST_BTN: CSSProperties = {
  padding: '6px 14px', borderRadius: '20px', border: '1px solid #8b4513', background: 'transparent',
  color: '#8b4513', cursor: 'pointer', fontFamily: 'serif', fontSize: '13px'
}
const TS_GRAY_BTN: CSSProperties = { ...TS_GHOST_BTN, border: '1px solid #bbb', color: '#777' }
const TS_TINY_BTN: CSSProperties = {
  padding: '2px 8px', borderRadius: '12px', border: '1px solid #d4c8a8', background: '#fffdf6',
  color: '#8b4513', cursor: 'pointer', fontFamily: 'serif', fontSize: '12px', lineHeight: '1.6'
}
const TS_TAB_BTN = (selected: boolean): CSSProperties => ({
  padding: '8px 18px', borderRadius: '20px', border: '1px solid #d4c8a8', cursor: 'pointer',
  fontFamily: 'serif', fontSize: '14px', backgroundColor: selected ? '#8b4513' : '#fdfcf0',
  color: selected ? '#fff' : '#8b4513', transition: 'all 0.2s'
})
const TS_SECTION_TITLE: CSSProperties = {
  fontSize: '15px', color: '#8b4513', fontWeight: 'bold', marginBottom: '8px'
}
const TS_HINT: CSSProperties = { fontSize: '12px', color: '#999', lineHeight: '1.7' }
const TS_ERROR: CSSProperties = {
  background: '#fdecea', border: '1px solid #f5c6c0', color: '#c0392b', borderRadius: '8px',
  padding: '10px', fontSize: '13px', marginBottom: '12px', lineHeight: '1.8'
}
const TS_NOTICE: CSSProperties = {
  background: '#eef5ee', border: '1px solid #b8d8c0', color: '#3f6b46', borderRadius: '8px',
  padding: '10px', fontSize: '13px', marginBottom: '12px'
}
const TS_GRAY_BAR: CSSProperties = {
  background: '#f2f0ea', border: '1px solid #dcd6c6', color: '#6b6b6b', borderRadius: '8px',
  padding: '8px 10px', fontSize: '12px', marginBottom: '12px'
}
const TS_WARN: CSSProperties = { color: '#e67e22', fontSize: '13px', lineHeight: '1.8' }
const TS_BADGE = (status: TemplateStatus): CSSProperties => ({
  display: 'inline-block', padding: '1px 8px', borderRadius: '10px', fontSize: '12px',
  border: '1px solid ' + (status === 'active' ? '#5a7d5a' : status === 'draft' ? '#8b4513' : '#bbb'),
  color: status === 'active' ? '#3f6b46' : status === 'draft' ? '#8b4513' : '#888',
  background: status === 'active' ? '#eef5ee' : status === 'draft' ? '#fff8e7' : '#f2f0ea'
})
const TS_LEGACY_TAG: CSSProperties = {
  display: 'inline-block', marginLeft: '6px', padding: '1px 6px', borderRadius: '8px', fontSize: '11px',
  color: '#8b4513', background: '#fff8e7', border: '1px dashed #d4c8a8'
}
const TS_PREVIEW: CSSProperties = {
  background: '#fffdf6', border: '1px dashed #d4c8a8', borderRadius: '8px', padding: '12px',
  fontFamily: 'serif', fontSize: '13px', color: '#4a3b2a', whiteSpace: 'pre-wrap', lineHeight: '1.9'
}

/* ============================ 小工具（僅本檔使用） ============================ */

/** ISO → `MM-DD HH:mm`（沿用 App.tsx `formatAgentTime` 的顯示慣例；異常值不拋錯）。 */
const formatTime = (value?: string | null) => {
  if (!value) return '—'
  const s = String(value)
  if (s.length < 16) return s
  return `${s.slice(5, 10)} ${s.slice(11, 16)}`
}

const typeLabel = (type: TemplateType) => TEMPLATE_TYPE_TABS.find(t => t.key === type)?.label || String(type)

/** 身份參數（GET 走 query、POST/PUT 走 body；`teacher_name == teacher_id` 否則後端 403）。 */
const identityQuery = (teacherName: string, teacherId: string) =>
  `teacher_name=${encodeURIComponent(teacherName)}&teacher_id=${encodeURIComponent(teacherId)}`

/** 接口調用包裝：讀 `{detail:{error,msg,errors,warnings}}`，網絡異常統一成 `network_error`。 */
async function callTemplateApi<T>(path: string, init?: RequestInit): Promise<ApiResult<T>> {
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
          msg: String(detail.msg || '請求失敗，請稍後再試'),
          details: Array.isArray(detail.errors) ? detail.errors : [],
          warnings: Array.isArray(detail.warnings) ? detail.warnings : []
        }
      }
    }
    return { ok: true, data: body as T }
  } catch {
    return {
      ok: false,
      failure: {
        status: 0, code: 'network_error', msg: '網絡異常，請確認後端服務是否在運行',
        details: [], warnings: []
      }
    }
  }
}

/**
 * `schema_json` 可能是存量回填行（缺 `version` 等鍵）→ 讀取時一律「缺鍵 = 默認值」，
 * 並且**只在編輯器裡以展開原物件的副本**改寫自己管的鍵（未知鍵 / `formulas` / `meta` 原樣保留，§9.0）。
 */
const asArray = (value: any): any[] => (Array.isArray(value) ? value : [])
const asRecord = (value: any): Record<string, any> =>
  value && typeof value === 'object' && !Array.isArray(value) ? value : {}
const asText = (value: any) => (typeof value === 'string' ? value : '')

/** 該類型當前生效版本（列表已由後端按 `type asc, version desc` 排序）。 */
const activeOf = (rows: TemplateRow[]) => rows.find(r => r.status === 'active')

/** §9.4 / §13.3 #9 的黃字提示。 */
const herbWarningText = (herbName: string) => `「${herbName}」未入庫，開方時將無法扣減庫存`

/* ============================ 子組件：四類 Tab ============================ */

interface TypeTabsProps {
  activeTabType: TemplateType
  rowsByType: Record<TemplateType, TemplateRow[]>
  counts: Record<string, number>
  onSelect: (type: TemplateType) => void
}

/** §13.2 `TemplateTypeTabs`：四類切換 + 各類 active 版本號徽章（資料來自列表，不打接口）。 */
export function TemplateTypeTabs({ activeTabType, rowsByType, counts, onSelect }: TypeTabsProps) {
  return (
    <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '14px' }}>
      {TEMPLATE_TYPE_TABS.map(tab => {
        const active = activeOf(rowsByType[tab.key] || [])
        return (
          <button key={tab.key} style={TS_TAB_BTN(activeTabType === tab.key)} onClick={() => onSelect(tab.key)}>
            {tab.label}
            <span style={{ marginLeft: '6px', fontSize: '12px', opacity: 0.9 }}>
              {active ? `v${active.version}` : '未發佈'}
            </span>
            <span style={{ marginLeft: '4px', fontSize: '11px', opacity: 0.7 }}>（共 {counts[tab.key] || 0} 版）</span>
          </button>
        )
      })}
    </div>
  )
}

/* ============================ 子組件：四個表單 ============================ */

interface SchemaFormProps { schema: Record<string, any>; onSchemaChange: (next: Record<string, any>) => void }

/** §9.1 `InquiryForm`：十問項列表（上下移排序 / 增刪 3–20 / label / ask / required / answer_type / choices）。 */
export function InquiryForm({ schema, onSchemaChange }: SchemaFormProps) {
  const fields = asArray(schema.fields)
  const write = (next: any[]) => onSchemaChange({
    ...schema,
    fields: next.map((item, index) => ({ ...asRecord(item), order: index + 1 }))
  })
  const patch = (index: number, key: string, value: any) =>
    write(fields.map((item, i) => (i === index ? { ...asRecord(item), [key]: value } : item)))
  const move = (index: number, delta: number) => {
    const target = index + delta
    if (target < 0 || target >= fields.length) return
    const next = fields.slice()
    const moved = next.splice(index, 1)[0]
    next.splice(target, 0, moved)
    write(next)
  }
  const removeAt = (index: number) => write(fields.filter((_, i) => i !== index))
  const addField = () => {
    const usedKeys = fields.map(item => asText(asRecord(item).key))
    let seq = fields.length + 1
    while (usedKeys.includes(`field_${seq}`)) seq += 1
    write([...fields, {
      key: `field_${seq}`, label: '', ask: '', required: false, answer_type: 'text', choices: [], follow_up: ''
    }])
  }
  return (
    <div>
      <div style={TS_SECTION_TITLE}>問診項（{fields.length} / 上限 {INQUIRY_MAX_FIELDS}，至少 {INQUIRY_MIN_FIELDS} 項）</div>
      <div style={TS_HINT}>順序即提問順序；『必問』未答不允許「已問全」。發布時至少 1 項標為必問。</div>
      {fields.map((raw, index) => {
        const field = asRecord(raw)
        const answerType = asText(field.answer_type) || 'text'
        return (
          <div key={`${index}-${asText(field.key)}`} style={{ border: '1px dashed #d4c8a8', borderRadius: '8px', padding: '10px', marginTop: '10px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap', marginBottom: '8px' }}>
              <span style={{ fontFamily: 'serif', fontWeight: 'bold', color: '#8b4513', minWidth: '28px' }}>{index + 1}.</span>
              <input style={{ ...TS_SMALL_INPUT, width: '120px' }} placeholder="顯示名（≤16 字）" maxLength={16}
                value={asText(field.label)} onChange={e => patch(index, 'label', e.target.value)} />
              <input style={{ ...TS_SMALL_INPUT, width: '140px' }} placeholder="機器鍵（如 cold_heat）"
                value={asText(field.key)} onChange={e => patch(index, 'key', e.target.value)} />
              <select style={{ ...TS_SMALL_INPUT, width: '96px' }} value={answerType}
                onChange={e => patch(index, 'answer_type', e.target.value)}>
                {ANSWER_TYPE_OPTIONS.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
              <label style={{ fontFamily: 'serif', fontSize: '13px', color: '#5a7d5a', cursor: 'pointer' }}>
                <input type="checkbox" checked={!!field.required} style={{ marginRight: '4px' }}
                  onChange={e => patch(index, 'required', e.target.checked)} />必問
              </label>
              <button style={TS_TINY_BTN} disabled={index === 0} onClick={() => move(index, -1)}>↑ 上移</button>
              <button style={TS_TINY_BTN} disabled={index === fields.length - 1} onClick={() => move(index, 1)}>↓ 下移</button>
              <button style={TS_TINY_BTN} disabled={fields.length <= INQUIRY_MIN_FIELDS} onClick={() => removeAt(index)}>刪除項</button>
            </div>
            <input style={TS_SMALL_INPUT} placeholder="老師口徑的問法（≤120 字，留空=沿用預設問法）" maxLength={120}
              value={asText(field.ask)} onChange={e => patch(index, 'ask', e.target.value)} />
            {answerType === 'choice' && (
              <textarea style={{ ...TS_SMALL_INPUT, height: '58px' }} placeholder="選項（每行一個，2–12 項，自動去重）"
                value={asArray(field.choices).map(item => asText(item)).join('\n')}
                onChange={e => patch(index, 'choices', e.target.value.split('\n').map(s => s.trim()).filter(Boolean))} />
            )}
            <input style={TS_SMALL_INPUT} placeholder="追問觸發條件（≤120 字，Epic 1 只存不執行）" maxLength={120}
              value={asText(field.follow_up)} onChange={e => patch(index, 'follow_up', e.target.value)} />
          </div>
        )
      })}
      <button style={{ ...TS_GHOST_BTN, marginTop: '10px' }} disabled={fields.length >= INQUIRY_MAX_FIELDS}
        onClick={addField}>
        + 新增問診項{fields.length >= INQUIRY_MAX_FIELDS ? '（已達上限 20）' : ''}
      </button>
    </div>
  )
}


/**
 * §9.2 `RecordForm`：段落列表（title / hint / order / writable_by）+ `tone.forbidden` 詞表。
 * `writable_by='teacher'` 的段（舌象 / 脈象 / 辨證 / 施治方案）智能體永不填內容（§9.2 硬約束）。
 */
export function RecordForm({ schema, onSchemaChange }: SchemaFormProps) {
  const [newWord, setNewWord] = useState('')
  const sections = asArray(schema.sections)
  const tone = asRecord(schema.tone)
  const forbidden = asArray(tone.forbidden).map(item => asText(item)).filter(Boolean)
  const teacherCount = sections.filter(item => asText(asRecord(item).writable_by) === 'teacher').length
  const write = (next: any[]) => onSchemaChange({
    ...schema,
    sections: next.map((item, index) => ({ ...asRecord(item), order: index + 1 }))
  })
  const patch = (index: number, key: string, value: any) =>
    write(sections.map((item, i) => (i === index ? { ...asRecord(item), [key]: value } : item)))
  const move = (index: number, delta: number) => {
    const target = index + delta
    if (target < 0 || target >= sections.length) return
    const next = sections.slice()
    const moved = next.splice(index, 1)[0]
    next.splice(target, 0, moved)
    write(next)
  }
  const removeAt = (index: number) => write(sections.filter((_, i) => i !== index))
  const addSection = () => {
    const usedKeys = sections.map(item => asText(asRecord(item).key))
    let seq = sections.length + 1
    while (usedKeys.includes(`section_${seq}`)) seq += 1
    write([...sections, { key: `section_${seq}`, title: '', hint: '', required: false, writable_by: 'ai' }])
  }
  const writeTone = (next: Record<string, any>) => onSchemaChange({ ...schema, tone: { ...tone, ...next } })
  return (
    <div>
      <div style={TS_SECTION_TITLE}>病歷段落（{sections.length} / 上限 {RECORD_MAX_SECTIONS}，至少 {RECORD_MIN_SECTIONS} 段）</div>
      <div style={TS_HINT}>留待老師的段落共 {teacherCount} 段（發布時至少 1 段，保證「待老師補充」語義不被抹掉）。</div>
      {sections.map((raw, index) => {
        const section = asRecord(raw)
        const writableBy = asText(section.writable_by) === 'teacher' ? 'teacher' : 'ai'
        return (
          <div key={`${index}-${asText(section.key)}`} style={{ border: '1px dashed #d4c8a8', borderRadius: '8px', padding: '10px', marginTop: '10px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap', marginBottom: '8px' }}>
              <span style={{ fontFamily: 'serif', fontWeight: 'bold', color: '#8b4513', minWidth: '28px' }}>{index + 1}.</span>
              <input style={{ ...TS_SMALL_INPUT, width: '160px' }} placeholder="段落標題（≤20 字）" maxLength={20}
                value={asText(section.title)} onChange={e => patch(index, 'title', e.target.value)} />
              <input style={{ ...TS_SMALL_INPUT, width: '150px' }} placeholder="機器鍵（如 chief_complaint）"
                value={asText(section.key)} onChange={e => patch(index, 'key', e.target.value)} />
              <select style={{ ...TS_SMALL_INPUT, width: '190px' }} value={writableBy}
                onChange={e => patch(index, 'writable_by', e.target.value)}>
                {WRITABLE_BY_OPTIONS.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
              <label style={{ fontFamily: 'serif', fontSize: '13px', color: '#5a7d5a', cursor: 'pointer' }}>
                <input type="checkbox" checked={!!section.required} style={{ marginRight: '4px' }}
                  onChange={e => patch(index, 'required', e.target.checked)} />必須出現
              </label>
              <button style={TS_TINY_BTN} disabled={index === 0} onClick={() => move(index, -1)}>↑ 上移</button>
              <button style={TS_TINY_BTN} disabled={index === sections.length - 1} onClick={() => move(index, 1)}>↓ 下移</button>
              <button style={TS_TINY_BTN} disabled={sections.length <= RECORD_MIN_SECTIONS} onClick={() => removeAt(index)}>刪除段</button>
            </div>
            <input style={TS_SMALL_INPUT} placeholder="給智能體的填充提示（≤120 字，缺失留空、禁止編造）" maxLength={120}
              value={asText(section.hint)} onChange={e => patch(index, 'hint', e.target.value)} />
          </div>
        )
      })}
      <button style={{ ...TS_GHOST_BTN, marginTop: '10px' }} disabled={sections.length >= RECORD_MAX_SECTIONS}
        onClick={addSection}>
        + 新增段落{sections.length >= RECORD_MAX_SECTIONS ? '（已達上限 12）' : ''}
      </button>

      <div style={{ marginTop: '16px', borderTop: '1px dashed #d4c8a8', paddingTop: '12px' }}>
        <div style={TS_SECTION_TITLE}>措辭偏好（tone）</div>
        <input style={TS_SMALL_INPUT} placeholder="口語 / 文言（≤120 字）" maxLength={120}
          value={asText(tone.style)} onChange={e => writeTone({ style: e.target.value })} />
        <div style={{ ...TS_HINT, marginTop: '8px' }}>禁用詞（原文保留、不許換近義詞；上限 {MAX_FORBIDDEN_WORDS} 項）</div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', margin: '8px 0' }}>
          {forbidden.map((word, index) => (
            <span key={`${word}-${index}`} style={{ ...TS_LEGACY_TAG, marginLeft: 0 }}>
              {word}
              <button style={{ border: 'none', background: 'transparent', color: '#8b4513', cursor: 'pointer', padding: '0 0 0 4px' }}
                onClick={() => writeTone({ forbidden: forbidden.filter((_, i) => i !== index) })}>✕</button>
            </span>
          ))}
        </div>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <input style={{ ...TS_SMALL_INPUT, maxWidth: '220px' }} placeholder="新增禁用詞（如：脈象）" maxLength={20}
            value={newWord} onChange={e => setNewWord(e.target.value)} />
          <button style={TS_GHOST_BTN} disabled={forbidden.length >= MAX_FORBIDDEN_WORDS}
            onClick={() => {
              const word = newWord.trim()
              if (!word || forbidden.includes(word)) return
              writeTone({ forbidden: [...forbidden, word] })
              setNewWord('')
            }}>
            + 新增
          </button>
        </div>
      </div>
    </div>
  )
}

/**
 * §9.3 `TreatmentForm`：大文本域（`content`，計數器 / 2000 字）+ `placeholders` 列表 + 「存量遷移」標籤。
 * `format` Epic 1 恆為 `text`，界面不提供切換。
 */
export function TreatmentForm({ schema, onSchemaChange }: SchemaFormProps) {
  const [newPlaceholder, setNewPlaceholder] = useState('')
  const content = asText(schema.content)
  const placeholders = asArray(schema.placeholders).map(item => asText(item)).filter(Boolean)
  return (
    <div>
      <div style={TS_SECTION_TITLE}>施治方案正文（{content.length} / {TREATMENT_MAX_CONTENT} 字）</div>
      <div style={TS_HINT}>發布時正文不可為空；正文即舊通道 `plan_templates.content` 的同一份內容（§9.3，雙寫不回寫舊表）。</div>
      <textarea style={{ ...TS_INPUT, height: '140px', whiteSpace: 'pre-wrap' }} maxLength={TREATMENT_MAX_CONTENT}
        placeholder="例：先調其脾胃，再理其氣機；三日後複診，依脈證加減。"
        value={content} onChange={e => onSchemaChange({ ...schema, content: e.target.value })} />

      <div style={{ ...TS_SECTION_TITLE, marginTop: '10px' }}>
        待補空位 placeholders（{placeholders.length} / {TREATMENT_MAX_PLACEHOLDERS}）
      </div>
      <div style={TS_HINT}>生成時提醒老師補的位置（Epic 1 只存不執行）。</div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', margin: '8px 0' }}>
        {placeholders.map((item, index) => (
          <span key={`${item}-${index}`} style={{ ...TS_LEGACY_TAG, marginLeft: 0 }}>
            {item}
            <button style={{ border: 'none', background: 'transparent', color: '#8b4513', cursor: 'pointer', padding: '0 0 0 4px' }}
              onClick={() => onSchemaChange({
                ...schema,
                placeholders: placeholders.filter((_, i) => i !== index)
              })}>✕</button>
          </span>
        ))}
      </div>
      <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
        <input style={{ ...TS_SMALL_INPUT, maxWidth: '320px' }} placeholder="新增空位（≤60 字，如：待填複診日期）" maxLength={60}
          value={newPlaceholder} onChange={e => setNewPlaceholder(e.target.value)} />
        <button style={TS_GHOST_BTN} disabled={placeholders.length >= TREATMENT_MAX_PLACEHOLDERS}
          onClick={() => {
            const item = newPlaceholder.trim()
            if (!item || placeholders.includes(item)) return
            onSchemaChange({ ...schema, placeholders: [...placeholders, item] })
            setNewPlaceholder('')
          }}>
          + 新增空位
        </button>
      </div>

      {/* §13.4 術語示範：炁 / 氣 按語義區分，禁止全局簡繁轉換（一律人工術語表） */}
      <div style={{ ...TS_HINT, marginTop: '14px' }}>
        術語示範（炁 / 氣 分用）：先天之炁（先天稟賦）、後天之氣（後天水穀）、調理氣機。
      </div>
    </div>
  )
}

interface PrescriptionFormProps extends SchemaFormProps { herbs: any[]; herbsLoaded: boolean }

/**
 * §9.4 `PrescriptionForm`：藥材預選（首字過濾的九宮格，與診室開方同語義）+ 每味 `default_amount` / `role` /
 * `cooking_method`；未入庫藥材顯示黃字（200 通過 + warnings，不硬拒，§15 待確認 2 已定）。
 */
export function PrescriptionForm({ schema, onSchemaChange, herbs, herbsLoaded }: PrescriptionFormProps) {
  const [keyword, setKeyword] = useState('')
  const herbRows = asArray(schema.herbs)
  const defaults = asRecord(schema.defaults)
  const defaultCooking = TEMPLATE_COOKING_OPTIONS.some(option => option.value === asText(defaults.cooking_method))
    ? asText(defaults.cooking_method)
    : TEMPLATE_DEFAULT_COOKING
  const keywordText = keyword.trim()
  const gridList = keywordText
    ? herbs.filter(item => String(item.herb_name || '').startsWith(keywordText))
    : herbs
  const inventoryNames = herbs.map(item => asText(item.herb_name))
  const selectedNames = herbRows.map(item => asText(asRecord(item).herb_name))
  const missingNames = herbsLoaded ? selectedNames.filter(name => name && !inventoryNames.includes(name)) : []
  const writeHerbs = (next: any[]) => onSchemaChange({
    ...schema,
    herbs: next.map((item, index) => ({ ...asRecord(item), order: index + 1 }))
  })
  const patchHerb = (index: number, key: string, value: any) =>
    writeHerbs(herbRows.map((item, i) => (i === index ? { ...asRecord(item), [key]: value } : item)))
  const toggleHerb = (herbName: string) => {
    if (selectedNames.includes(herbName)) {
      writeHerbs(herbRows.filter(item => asText(asRecord(item).herb_name) !== herbName))
      return
    }
    if (herbRows.length >= PRESCRIPTION_MAX_HERBS) return
    writeHerbs([...herbRows, { herb_name: herbName, default_amount: 0, role: '', cooking_method: defaultCooking }])
  }
  return (
    <div>
      <div style={TS_SECTION_TITLE}>預選藥材（{herbRows.length} / 上限 {PRESCRIPTION_MAX_HERBS} 味）</div>
      <div style={TS_HINT}>點格子選藥（再點一次取消）；`role` / `cooking_method` 選項與診室開方九宮格一致。</div>
      <input style={{ ...TS_INPUT, marginTop: '8px' }} placeholder="輸入藥材名首字（只看首字，與 /api/herbs/search 同語義）"
        value={keyword} onChange={e => setKeyword(e.target.value)} />
      {!herbsLoaded ? (
        <div style={TS_HINT}>庫存載入中…（若長時間無變化，請點右上角「🔄 重新載入」再試）</div>
      ) : gridList.length === 0 ? (
        <div style={TS_HINT}>
          {herbs.length === 0 ? '暫無藥材庫存記錄，請先到「管理 · 中藥材庫存」添加藥材' : '沒有匹配的藥材，換個首字試試'}
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '8px', maxHeight: '240px', overflowY: 'auto', padding: '2px', margin: '8px 0' }}>
          {gridList.map(item => {
            const herbName = asText(item.herb_name)
            const selected = selectedNames.includes(herbName)
            return (
              <button key={item.id} onClick={() => toggleHerb(herbName)}
                title={`${herbName} 庫存 ${item.stock_amount}${item.unit}`}
                style={{
                  padding: '8px 4px', borderRadius: '6px', cursor: 'pointer', fontFamily: 'serif', fontSize: '13px',
                  lineHeight: 1.4, boxSizing: 'border-box', textAlign: 'center',
                  background: selected ? '#8b4513' : '#f7f5ef',
                  color: selected ? '#fdfcf0' : '#5a4a3a',
                  border: selected ? '1px solid #8b4513' : '1px solid #d4c8a8'
                }}>
                <div style={{ fontWeight: 'bold' }}>{herbName}</div>
                <div style={{ fontSize: '12px', opacity: 0.85 }}>{item.stock_amount}{item.unit}</div>
              </button>
            )
          })}
        </div>
      )}

      {herbRows.length > 0 && (
        <div style={{ marginTop: '10px' }}>
          {herbRows.map((raw, index) => {
            const herb = asRecord(raw)
            const cooking = TEMPLATE_COOKING_OPTIONS.some(option => option.value === asText(herb.cooking_method))
              ? asText(herb.cooking_method)
              : defaultCooking
            return (
              <div key={asText(herb.herb_name)} style={{ display: 'flex', gap: '8px', alignItems: 'center', marginBottom: '8px', flexWrap: 'wrap' }}>
                <span style={{ flex: '0 0 84px', fontFamily: 'serif', fontWeight: 'bold', color: '#8b4513' }}>
                  {asText(herb.herb_name)}
                </span>
                <input style={{ ...TS_SMALL_INPUT, flex: '0 0 90px' }} type="number" min={0} max={1000} placeholder="預填克數"
                  value={Number(herb.default_amount) > 0 ? String(herb.default_amount) : ''}
                  onChange={e => {
                    const rawText = e.target.value.trim()
                    const num = rawText === '' ? 0 : Number(rawText)
                    patchHerb(index, 'default_amount', Number.isFinite(num) ? num : 0)
                  }} />
                <span style={{ color: '#999', fontSize: '13px', fontFamily: 'serif' }}>克</span>
                <select style={{ ...TS_SMALL_INPUT, flex: '0 0 100px' }} title="君臣佐使" value={asText(herb.role)}
                  onChange={e => patchHerb(index, 'role', e.target.value)}>
                  <option value="">{TEMPLATE_ROLE_UNMARKED_LABEL}</option>
                  {TEMPLATE_ROLE_OPTIONS.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
                </select>
                <select style={{ ...TS_SMALL_INPUT, flex: '0 0 100px' }} title="煎法" value={cooking}
                  onChange={e => patchHerb(index, 'cooking_method', e.target.value)}>
                  {TEMPLATE_COOKING_OPTIONS.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
                </select>
                <button style={TS_TINY_BTN} onClick={() => writeHerbs(herbRows.filter((_, i) => i !== index))}>刪除</button>
              </div>
            )
          })}
        </div>
      )}

      {missingNames.length > 0 && (
        <div style={TS_WARN}>{missingNames.map(name => <div key={name}>{herbWarningText(name)}</div>)}</div>
      )}

      <div style={{ marginTop: '12px', display: 'flex', gap: '16px', alignItems: 'center', flexWrap: 'wrap' }}>
        <label style={{ fontFamily: 'serif', fontSize: '13px', color: '#8b4513' }}>
          默認煎法：
          <select style={{ ...TS_SMALL_INPUT, display: 'inline-block', width: '110px', marginLeft: '6px' }} value={defaultCooking}
            onChange={e => onSchemaChange({ ...schema, defaults: { ...defaults, cooking_method: e.target.value } })}>
            {TEMPLATE_COOKING_OPTIONS.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
        </label>
        <label style={{ fontFamily: 'serif', fontSize: '13px', color: '#5a7d5a', cursor: 'pointer' }}>
          <input type="checkbox" checked={!!defaults.remote} style={{ marginRight: '4px' }}
            onChange={e => onSchemaChange({ ...schema, defaults: { ...defaults, remote: e.target.checked } })} />
          默認遠程診療（學生自採，不扣庫存）
        </label>
      </div>
      <div style={{ ...TS_HINT, marginTop: '8px' }}>
        模板只產出「九宮格預選 + 預填分量」；`prescriptions` 落庫仍必須老師在診室點「保存藥方」（智能體永不自動開方）。
      </div>
    </div>
  )
}

/* ============================ 子組件：版本鏈 ============================ */

interface VersionsProps {
  chain: ChainItem[]
  currentId: number
  busy: boolean
  onView: (id: number) => void
  onDerive: (id: number) => void
}

/** §13.2 `TemplateVersions`：版本鏈時間線（`GET /api/templates/{id}` 的 `chain`）。 */
export function TemplateVersions({ chain, currentId, busy, onView, onDerive }: VersionsProps) {
  if (chain.length === 0) return null
  return (
    <div style={{ marginTop: '16px' }}>
      <div style={TS_SECTION_TITLE}>版本鏈（同類型全部版本，共 {chain.length} 版）</div>
      {chain.map(item => (
        <div key={item.id} style={{
          display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap',
          padding: '6px 0', borderBottom: '1px dashed #ece3cd'
        }}>
          <span style={{ fontFamily: 'serif', fontWeight: 'bold', color: '#8b4513', minWidth: '46px' }}>v{item.version}</span>
          <span style={TS_BADGE(item.status)}>{TEMPLATE_STATUS_LABELS[item.status]}</span>
          {item.id === currentId && <span style={TS_HINT}>（當前）</span>}
          <span style={{ ...TS_HINT, flex: '1 1 160px' }}>更新於 {formatTime(item.updated_at)}</span>
          <button style={TS_TINY_BTN} disabled={busy || item.id === currentId} onClick={() => onView(item.id)}>檢視</button>
          <button style={TS_TINY_BTN} disabled={busy || item.status === 'draft'} onClick={() => onDerive(item.id)}>
            基於此版本修訂
          </button>
        </div>
      ))}
    </div>
  )
}

/* ============================ 子組件：版本列表 ============================ */

interface ListProps {
  rows: TemplateRow[]
  templateType: TemplateType
  busy: boolean
  onCreate: () => void
  onEditDraft: (row: TemplateRow) => void
  onView: (row: TemplateRow) => void
  onPublish: (row: TemplateRow) => void
  onArchive: (row: TemplateRow) => void
  onActivate: (row: TemplateRow) => void
  onDerive: (row: TemplateRow) => void
}

/** §13.2 `TemplateList`：該類型全部版本 + 狀態徽章 + 操作按鈕（按狀態分派）。 */
export function TemplateList({
  rows, templateType, busy, onCreate, onEditDraft, onView, onPublish, onArchive, onActivate, onDerive
}: ListProps) {
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap', marginBottom: '10px' }}>
        <span style={TS_SECTION_TITLE}>{typeLabel(templateType)}模板（{rows.length} 版）</span>
        <button style={TS_PRIMARY_BTN} disabled={busy} onClick={onCreate}>+ 新建模板</button>
        <span style={TS_HINT}>同類型已有草稿時，新建會回到該草稿（不產生第二份）</span>
      </div>
      {rows.length === 0 ? (
        <div style={TS_HINT}>尚無{typeLabel(templateType)}模板，點「新建模板」開始（系統會預填該類型的預設骨架）。</div>
      ) : rows.map(row => (
        <div key={row.id} style={{
          display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap',
          padding: '8px 0', borderBottom: '1px dashed #ece3cd'
        }}>
          <span style={{ fontFamily: 'serif', fontWeight: 'bold', color: '#8b4513', minWidth: '46px' }}>v{row.version}</span>
          <span style={TS_BADGE(row.status)}>{TEMPLATE_STATUS_LABELS[row.status]}</span>
          <span style={{ fontFamily: 'serif', fontSize: '14px', color: '#4a3b2a' }}>{row.name}</span>
          {row.is_legacy && <span style={TS_LEGACY_TAG}>存量遷移</span>}
          <span style={{ ...TS_HINT, flex: '1 1 150px' }}>更新於 {formatTime(row.updated_at)}</span>
          {row.status === 'draft' && (
            <>
              <button style={TS_GHOST_BTN} disabled={busy} onClick={() => onEditDraft(row)}>編輯草稿</button>
              <button style={TS_GREEN_BTN} disabled={busy} onClick={() => onPublish(row)}>發佈</button>
              <button style={TS_GRAY_BTN} disabled={busy} onClick={() => onArchive(row)}>歸檔</button>
            </>
          )}
          {row.status === 'active' && (
            <>
              <button style={TS_GHOST_BTN} disabled={busy} onClick={() => onView(row)}>檢視</button>
              <button style={TS_GHOST_BTN} disabled={busy} onClick={() => onDerive(row)}>基於此版本修訂</button>
              <button style={TS_GRAY_BTN} disabled={busy} onClick={() => onArchive(row)}>歸檔</button>
            </>
          )}
          {row.status === 'archived' && (
            <>
              <button style={TS_GHOST_BTN} disabled={busy} onClick={() => onView(row)}>檢視</button>
              <button style={TS_GREEN_BTN} disabled={busy} onClick={() => onActivate(row)}>重新啟用</button>
              <button style={TS_GHOST_BTN} disabled={busy} onClick={() => onDerive(row)}>基於此版本修訂</button>
            </>
          )}
        </div>
      ))}
    </div>
  )
}

/* ============================ 子組件：編輯器 ============================ */

interface EditorProps {
  row: TemplateRow
  readOnly: boolean
  name: string
  schema: Record<string, any>
  warnings: TemplateWarning[]
  herbs: any[]
  herbsLoaded: boolean
  busy: boolean
  onNameChange: (value: string) => void
  onSchemaChange: (next: Record<string, any>) => void
  onSave: () => void
  onPublish: () => void
  onClose: () => void
}

/** 服務端 `warnings` → 黃字（§9.4 目前只有 `herb_not_in_inventory`）。 */
const warningText = (warning: TemplateWarning) =>
  warning.code === 'herb_not_in_inventory' && warning.herb_name
    ? herbWarningText(warning.herb_name)
    : (warning.msg || '模板保存成功，但有一項提醒')

/** §13.2 `TemplateEditor`：按 `type` 分派四個表單 + 統一「儲存草稿 / 發佈 / 取消」。 */
export function TemplateEditor({
  row, readOnly, name, schema, warnings, herbs, herbsLoaded, busy,
  onNameChange, onSchemaChange, onSave, onPublish, onClose
}: EditorProps) {
  return (
    <div style={{ border: '1px solid #d4c8a8', borderRadius: '10px', padding: '14px', background: '#fffdf6' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap', marginBottom: '10px' }}>
        <span style={TS_SECTION_TITLE}>
          {readOnly ? '檢視模板' : '編輯草稿'}：{typeLabel(row.type)} · v{row.version}
        </span>
        <span style={TS_BADGE(row.status)}>{TEMPLATE_STATUS_LABELS[row.status]}</span>
        {row.is_legacy && <span style={TS_LEGACY_TAG}>存量遷移</span>}
        <span style={{ ...TS_HINT, flex: '1 1 120px' }}>更新於 {formatTime(row.updated_at)}</span>
      </div>

      {readOnly ? (
        <div style={{ ...TS_HINT, marginBottom: '10px' }}>
          已發佈的版本不可直接修改，請用「基於此版本修訂」開啟新草稿（歷史病歷不受影響）。
        </div>
      ) : (
        <input style={TS_INPUT} placeholder={`模板名（如：${typeLabel(row.type)}）`} maxLength={60}
          value={name} onChange={e => onNameChange(e.target.value)} />
      )}

      {warnings.length > 0 && (
        <div style={TS_WARN}>{warnings.map((warning, index) => <div key={index}>{warningText(warning)}</div>)}</div>
      )}

      {!readOnly && (
        row.type === 'inquiry' ? <InquiryForm schema={schema} onSchemaChange={onSchemaChange} />
          : row.type === 'record' ? <RecordForm schema={schema} onSchemaChange={onSchemaChange} />
            : row.type === 'treatment' ? <TreatmentForm schema={schema} onSchemaChange={onSchemaChange} />
              : <PrescriptionForm schema={schema} onSchemaChange={onSchemaChange} herbs={herbs} herbsLoaded={herbsLoaded} />
      )}

      <TemplatePreview templateType={row.type} schema={schema} />

      <div style={{ display: 'flex', gap: '8px', marginTop: '14px', flexWrap: 'wrap', alignItems: 'center' }}>
        {!readOnly && <button style={TS_PRIMARY_BTN} disabled={busy} onClick={onSave}>儲存草稿</button>}
        {!readOnly && <button style={TS_GREEN_BTN} disabled={busy} onClick={onPublish}>發佈</button>}
        <button style={TS_GRAY_BTN} disabled={busy} onClick={onClose}>{readOnly ? '關閉' : '取消'}</button>
        {!readOnly && <span style={TS_HINT}>發布後舊版本將自動歸檔，歷史病歷不受影響</span>}
      </div>
    </div>
  )
}

/* ============================ 子組件：只讀預覽 ============================ */

interface PreviewProps { templateType: TemplateType; schema: Record<string, any> }

/**
 * §13.2 `TemplatePreview`：record → 提交後草案骨架文本；treatment → 套用後文本；
 * prescription → 藥單草表（**僅預覽，不落庫**）；inquiry → 提問順序。
 */
function previewLines(templateType: TemplateType, schema: Record<string, any>): string[] {
  if (templateType === 'inquiry') {
    const fields = asArray(schema.fields)
      .slice()
      .sort((a, b) => Number(asRecord(a).order || 0) - Number(asRecord(b).order || 0))
    if (fields.length === 0) return ['（尚未配置問診項）']
    return fields.map((raw, index) => {
      const field = asRecord(raw)
      const parts = [`${index + 1}. ${asText(field.label) || asText(field.key)}${field.required ? '（必問）' : ''}`]
      if (asText(field.ask)) parts.push(`   問法：${asText(field.ask)}`)
      const answerType = asText(field.answer_type) || 'text'
      const choices = asArray(field.choices).map(item => asText(item)).filter(Boolean)
      parts.push(`   作答：${ANSWER_TYPE_OPTIONS.find(o => o.value === answerType)?.label || answerType}` +
        (answerType === 'choice' && choices.length ? `（${choices.join(' / ')}）` : ''))
      if (asText(field.follow_up)) parts.push(`   追問：${asText(field.follow_up)}`)
      return parts.join('\n')
    })
  }
  if (templateType === 'record') {
    const sections = asArray(schema.sections)
      .slice()
      .sort((a, b) => Number(asRecord(a).order || 0) - Number(asRecord(b).order || 0))
    if (sections.length === 0) return ['（尚未配置段落）']
    const lines = sections.map(raw => {
      const section = asRecord(raw)
      const title = asText(section.title) || asText(section.key)
      if (asText(section.writable_by) === 'teacher') {
        // §9.2 硬約束：`teacher` 段智能體永不填，只留 `標題：`
        return `${title}：　← 留待老師（智能體永不填）`
      }
      const hint = asText(section.hint)
      return `${title}：${hint ? `　← ${hint}` : ''}`
    })
    const tone = asRecord(schema.tone)
    const forbidden = asArray(tone.forbidden).map(item => asText(item)).filter(Boolean)
    if (asText(tone.style)) lines.push(`── 措辭偏好：${asText(tone.style)}`)
    if (forbidden.length) lines.push(`── 禁用詞（原文保留）：${forbidden.join('、')}`)
    return lines
  }
  if (templateType === 'treatment') {
    const content = asText(schema.content).trim()
    const lines = content ? [content] : ['（尚未填寫內容；發佈時不可為空）']
    const placeholders = asArray(schema.placeholders).map(item => asText(item)).filter(Boolean)
    if (placeholders.length) lines.push(`── 待補空位：${placeholders.join('、')}`)
    return lines
  }
  const herbs = asArray(schema.herbs)
  const defaults = asRecord(schema.defaults)
  const lines = ['藥單草表（僅預覽，不落庫）']
  if (herbs.length === 0) {
    lines.push('（尚未預選藥材）')
  } else {
    herbs.forEach((raw, index) => {
      const herb = asRecord(raw)
      const role = asText(herb.role)
      const amount = Number(herb.default_amount) > 0 ? `${Number(herb.default_amount)}克` : '未預填分量'
      const cooking = asText(herb.cooking_method) || TEMPLATE_DEFAULT_COOKING
      lines.push(`${index + 1}. ${role ? role + ' ' : ''}${asText(herb.herb_name)}　${amount}　${cooking}`)
    })
    lines.push(`共 ${herbs.length} 味（上限 ${PRESCRIPTION_MAX_HERBS} 味）`)
  }
  const defaultCooking = TEMPLATE_COOKING_OPTIONS.find(o => o.value === asText(defaults.cooking_method))
  lines.push(`默認煎法：${defaultCooking ? defaultCooking.label : TEMPLATE_COOKING_OPTIONS[0].label}` +
    `　遠程診療預設：${defaults.remote ? '是（自採，不扣庫存）' : '否'}`)
  return lines
}

/** §13.2 `TemplatePreview`：只讀展示當前編輯中的骨架（純前端渲染）。 */
export function TemplatePreview({ templateType, schema }: PreviewProps) {
  return (
    <div style={{ marginTop: '14px' }}>
      <div style={TS_SECTION_TITLE}>🔍 只讀預覽（僅前端渲染，不落庫）</div>
      <div style={TS_PREVIEW}>{previewLines(templateType, schema).join('\n')}</div>
    </div>
  )
}

/* ============================ 主組件：TemplateStudio ============================ */

interface TemplateStudioProps {
  /** 老師身份（老師端「管理」頁籤傳入；目前 `teacher_name` 與 `teacher_id` 同值）。 */
  teacherName: string
  teacherId: string
}

type ProbeState = 'unknown' | 'on' | 'off' | 'unavailable'
type LoadState = 'idle' | 'loading' | 'ready' | 'error'

interface PanelState { mode: 'edit' | 'view'; row: TemplateRow }

const TEMPLATE_KEY_RE = /^[a-z][a-z0-9_]{0,31}$/

/**
 * 前端先行校驗（§9 全量邊界）：返回 `null` = 通過；否則為繁體提示 → **不提交、不打接口**。
 * 後端仍會二次校驗（400 `schema_invalid`），這裡只是省一趟往返並把提示說清楚（§14.2 #11）。
 */
function validateDraft(templateType: TemplateType, schema: Record<string, any>, forPublish: boolean): string | null {
  if (templateType === 'inquiry') {
    const fields = asArray(schema.fields)
    if (fields.length < INQUIRY_MIN_FIELDS || fields.length > INQUIRY_MAX_FIELDS) {
      return `問診項數量需在 ${INQUIRY_MIN_FIELDS}–${INQUIRY_MAX_FIELDS} 之間（目前 ${fields.length} 項）`
    }
    const usedKeys: string[] = []
    for (let index = 0; index < fields.length; index += 1) {
      const field = asRecord(fields[index])
      const where = `第 ${index + 1} 項`
      const key = asText(field.key)
      if (!TEMPLATE_KEY_RE.test(key)) return `${where}的機器鍵不合法（小寫字母開頭，僅小寫字母/數字/下劃線）`
      if (usedKeys.includes(key)) return `${where}的機器鍵「${key}」與其他項重複`
      usedKeys.push(key)
      const label = asText(field.label)
      if (label.length < 1 || label.length > 16) return `${where}的顯示名需為 1–16 字`
      if (asText(field.ask).length > 120) return `${where}的問法需 ≤120 字`
      if (asText(field.follow_up).length > 120) return `${where}的追問條件需 ≤120 字`
      const answerType = asText(field.answer_type) || 'text'
      if (!ANSWER_TYPE_OPTIONS.some(option => option.value === answerType)) return `${where}的作答類型不合法`
      if (answerType === 'choice') {
        const choices = Array.from(new Set(asArray(field.choices).map(item => asText(item)).filter(Boolean)))
        if (choices.length < 2 || choices.length > 12) return `${where}為單選時需 2–12 個不重複選項`
      }
    }
    if (forPublish && !fields.some(item => asRecord(item).required)) return '發布時至少 1 項需標為「必問」'
    return null
  }
  if (templateType === 'record') {
    const sections = asArray(schema.sections)
    if (sections.length < RECORD_MIN_SECTIONS || sections.length > RECORD_MAX_SECTIONS) {
      return `段落數量需在 ${RECORD_MIN_SECTIONS}–${RECORD_MAX_SECTIONS} 之間（目前 ${sections.length} 段）`
    }
    const usedKeys: string[] = []
    for (let index = 0; index < sections.length; index += 1) {
      const section = asRecord(sections[index])
      const where = `第 ${index + 1} 段`
      const key = asText(section.key)
      if (!TEMPLATE_KEY_RE.test(key)) return `${where}的機器鍵不合法（小寫字母開頭，僅小寫字母/數字/下劃線）`
      if (usedKeys.includes(key)) return `${where}的機器鍵「${key}」與其他段重複`
      usedKeys.push(key)
      const title = asText(section.title)
      if (title.length < 1 || title.length > 20) return `${where}的標題需為 1–20 字`
      if (asText(section.hint).length > 120) return `${where}的填充提示需 ≤120 字`
      const writableBy = asText(section.writable_by) || 'ai'
      if (!WRITABLE_BY_OPTIONS.some(option => option.value === writableBy)) return `${where}的可填寫方不合法`
    }
    if (forPublish && !sections.some(item => asText(asRecord(item).writable_by) === 'teacher')) {
      return '發布時至少 1 段需為「留待老師（智能體永不填）」'
    }
    const tone = asRecord(schema.tone)
    if (asText(tone.style).length > 120) return '措辭偏好需 ≤120 字'
    if (asArray(tone.forbidden).length > MAX_FORBIDDEN_WORDS) return `禁用詞上限 ${MAX_FORBIDDEN_WORDS} 項`
    return null
  }
  if (templateType === 'treatment') {
    const content = asText(schema.content)
    if (content.length > TREATMENT_MAX_CONTENT) return `施治正文需 ≤${TREATMENT_MAX_CONTENT} 字（目前 ${content.length} 字）`
    if (forPublish && !content.trim()) return '發布時施治正文不可為空'
    if (asArray(schema.placeholders).length > TREATMENT_MAX_PLACEHOLDERS) {
      return `待補空位上限 ${TREATMENT_MAX_PLACEHOLDERS} 項`
    }
    return null
  }
  const herbsList = asArray(schema.herbs)
  if (herbsList.length > PRESCRIPTION_MAX_HERBS) return `預選藥材上限 ${PRESCRIPTION_MAX_HERBS} 味（目前 ${herbsList.length} 味）`
  const usedNames: string[] = []
  for (let index = 0; index < herbsList.length; index += 1) {
    const herb = asRecord(herbsList[index])
    const where = `第 ${index + 1} 味藥`
    const herbName = asText(herb.herb_name)
    if (herbName.length < 1 || herbName.length > 20) return `${where}的藥材名需為 1–20 字`
    if (usedNames.includes(herbName)) return `${where}「${herbName}」與其他味重複`
    usedNames.push(herbName)
    const amount = Number(herb.default_amount)
    if (!Number.isFinite(amount) || amount < 0 || amount > 1000) return `${where}的預填克數需為 0–1000`
    const role = asText(herb.role)
    if (role && !TEMPLATE_ROLE_OPTIONS.some(option => option.value === role)) return `${where}的君臣佐使只能是君 / 臣 / 佐 / 使（或留空）`
    const cooking = asText(herb.cooking_method)
    if (cooking && !TEMPLATE_COOKING_OPTIONS.some(option => option.value === cooking)) return `${where}的煎法不在白名單內`
  }
  return null
}

/**
 * §13.1 掛載點：老師端「管理」頁籤的一張卡片（`App.tsx` 只做 import + 掛載，不改原有頁面結構）。
 * flag off → 本組件返回 `null`（卡片整體不渲染）；表未就緒 → 卡內紅字。
 */
export default function TemplateStudio({ teacherName, teacherId }: TemplateStudioProps) {
  const [probeState, setProbeState] = useState<ProbeState>('unknown')
  const [loadState, setLoadState] = useState<LoadState>('idle')
  const [rows, setRows] = useState<TemplateRow[]>([])
  const [counts, setCounts] = useState<Record<string, number>>({})
  const [activeTabType, setActiveTabType] = useState<TemplateType>('inquiry')
  const [panel, setPanel] = useState<PanelState | null>(null)
  const [draftName, setDraftName] = useState('')
  const [draftSchema, setDraftSchema] = useState<Record<string, any>>({})
  const [chain, setChain] = useState<ChainItem[]>([])
  const [warnings, setWarnings] = useState<TemplateWarning[]>([])
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [grayBar, setGrayBar] = useState('')
  const [busy, setBusy] = useState(false)
  const [herbs, setHerbs] = useState<any[]>([])
  const [herbsLoaded, setHerbsLoaded] = useState(false)

  const identity = { teacher_name: teacherName, teacher_id: teacherId }
  const rowsByType: Record<TemplateType, TemplateRow[]> = { inquiry: [], record: [], treatment: [], prescription: [] }
  rows.forEach(row => { if (rowsByType[row.type]) rowsByType[row.type].push(row) })

  /** §13.5 列表數據：`GET /api/templates`（含四類總數 counts）。 */
  const loadList = async () => {
    setLoadState('loading')
    const result = await callTemplateApi<{ templates: TemplateRow[]; counts: Record<string, number> }>(
      `/api/templates?${identityQuery(teacherName, teacherId)}`)
    if (!result.ok) {
      if (result.failure.status === 404) { setProbeState('off'); setLoadState('idle'); return }
      if (result.failure.status === 503) { setProbeState('unavailable'); setLoadState('idle'); return }
      setLoadState('error')
      setError(result.failure.msg)
      return
    }
    setRows(Array.isArray(result.data.templates) ? result.data.templates : [])
    setCounts(result.data.counts || {})
    setLoadState('ready')
  }

  /** 打開編輯 / 檢視面板：先拉該模板最新詳情與版本鏈（`GET /api/templates/{id}`）。 */
  const openPanel = async (mode: 'edit' | 'view', row: TemplateRow) => {
    setError('')
    setGrayBar('')
    setPanel({ mode, row })
    setDraftName(row.name)
    setDraftSchema(row.schema_json || {})
    setChain([])
    const result = await callTemplateApi<{ template: TemplateRow; chain: ChainItem[] }>(
      `/api/templates/${row.id}?${identityQuery(teacherName, teacherId)}`)
    if (!result.ok) {
      if (result.failure.status === 404) {
        setError('該模板已不存在，請重新載入列表')
        setPanel(null)
        await loadList()
        return
      }
      setError(result.failure.msg)
      return
    }
    setPanel({ mode, row: result.data.template })
    setDraftName(result.data.template.name)
    setDraftSchema(result.data.template.schema_json || {})
    setChain(Array.isArray(result.data.chain) ? result.data.chain : [])
  }

  // 掛載探測 + 首次列表（§13.1：結果緩存於 state，不重複探測）。
  // 注：列表抓取內聯在本 effect 內（只依賴 teacherName / teacherId），避免 exhaustive-deps 的刻意忽略。
  useEffect(() => {
    // 身份缺失（理論上不會發生）：維持 'unknown' → 組件不渲染，不報錯、不阻塞其它頁籤
    if (!teacherName || !teacherId) return
    let cancelled = false
    const run = async () => {
      // 重置與抓取都放在 async 閉包內（不在 effect 內同步 setState，避免級聯渲染）
      setProbeState('unknown')
      setLoadState('loading')
      setError('')
      const probe = await callTemplateApi<unknown>(
        `/api/templates?include_schema=0&type=inquiry&${identityQuery(teacherName, teacherId)}`)
      if (cancelled) return
      if (!probe.ok) {
        setLoadState('idle')
        // 404 templates_disabled → 視為關閉（不渲染）；503 → 卡內紅字；其它（含網絡異常 / 身份缺失）→ 一律不渲染，不阻塞其它頁籤
        setProbeState(probe.failure.status === 503 ? 'unavailable' : 'off')
        return
      }
      setProbeState('on')
      const list = await callTemplateApi<{ templates: TemplateRow[]; counts: Record<string, number> }>(
        `/api/templates?${identityQuery(teacherName, teacherId)}`)
      if (cancelled) return
      if (!list.ok) {
        if (list.failure.status === 404) { setProbeState('off'); setLoadState('idle'); return }
        if (list.failure.status === 503) { setProbeState('unavailable'); setLoadState('idle'); return }
        setLoadState('error')
        setError(list.failure.msg)
        return
      }
      setRows(Array.isArray(list.data.templates) ? list.data.templates : [])
      setCounts(list.data.counts || {})
      setLoadState('ready')
    }
    run()
    return () => { cancelled = true }
  }, [teacherName, teacherId])

  // 開方模板才需要庫存清單（懶載入，避免無謂請求）；來源與診室開方同一份 `GET /api/herbs`。
  useEffect(() => {
    if (probeState !== 'on' || herbsLoaded) return
    if (activeTabType !== 'prescription' && panel?.row.type !== 'prescription') return
    let cancelled = false
    const run = async () => {
      const result = await callTemplateApi<any[]>(`/api/herbs?teacher_name=${encodeURIComponent(teacherName)}`)
      if (cancelled || !result.ok || !Array.isArray(result.data)) return
      setHerbs(result.data)
      setHerbsLoaded(true)
    }
    run()
    return () => { cancelled = true }
  }, [probeState, activeTabType, panel, herbsLoaded, teacherName])

  /** 後端錯誤（含 `errors[].path`）→ 一句話紅字；不暴露原始堆疊。 */
  const showFailure = (failure: TemplateApiFailure) => {
    const details = failure.details
      .map(issue => `${issue.path ? issue.path + '：' : ''}${issue.msg || ''}`)
      .filter(text => text.trim().length > 0)
    setError(`（${failure.code}）${failure.msg}${details.length ? '　' + details.join('；') : ''}`)
  }

  /** 「新建模板」＝ `POST /api/templates`（同 scope 已有草稿則後端複用並回 `reused=true`）。 */
  const handleCreate = async () => {
    setBusy(true)
    setError('')
    setNotice('')
    setGrayBar('')
    setWarnings([])
    const result = await callTemplateApi<{ template: TemplateRow; reused?: boolean; warnings?: TemplateWarning[] }>(
      '/api/templates', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...identity, type: activeTabType })
      })
    setBusy(false)
    if (!result.ok) { showFailure(result.failure); return }
    await loadList()
    await openPanel('edit', result.data.template)
    setWarnings(result.data.warnings || [])
    setNotice(result.data.reused
      ? '同類型已有未發佈草稿，已回到該草稿'
      : `已建立 v${result.data.template.version} 草稿（預設骨架）`)
  }

  /** 「儲存草稿」＝ `PUT /api/templates/{id}`（只改 `name` / `schema_json`）；返回是否成功。 */
  const handleSave = async (row: TemplateRow, silent = false) => {
    const invalid = validateDraft(row.type, draftSchema, false)
    if (invalid) { setError(invalid); return false }
    setBusy(true)
    setError('')
    const result = await callTemplateApi<{ template: TemplateRow; warnings?: TemplateWarning[] }>(
      `/api/templates/${row.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...identity, name: draftName.trim() || row.name, schema_json: draftSchema })
      })
    setBusy(false)
    if (!result.ok) {
      if (result.failure.code === 'template_published_immutable') {
        // §13.3 #6：不向老師暴露 409，自動改走「基於此版本修訂」並提示
        await handleDerive(row, '已發佈的版本不可直接修改，已為你開啟修訂版')
        return false
      }
      showFailure(result.failure)
      return false
    }
    await loadList()
    await openPanel('edit', result.data.template)
    setWarnings(result.data.warnings || [])
    if (!silent) setNotice('草稿已儲存（未發佈）')
    return true
  }

  /** 「發佈」＝ `POST /api/templates/{id}/publish`（後端同事務歸檔舊 active 並回 `archived_ids`）。 */
  const handlePublish = async (row: TemplateRow) => {
    const editingThis = panel !== null && panel.row.id === row.id && panel.mode === 'edit'
    const schemaForValidate = editingThis ? draftSchema : (row.schema_json || {})
    const invalid = validateDraft(row.type, schemaForValidate, true)
    if (invalid) { setError(invalid); return }
    const activeBefore = activeOf(rowsByType[row.type] || [])
    if (activeBefore && activeBefore.id !== row.id) {
      // §13.6 二次確認（同 scope 已有生效版本）
      if (!confirm(`發佈後「v${activeBefore.version}」將自動歸檔，新病歷改用 v${row.version}，歷史病歷不受影響。`)) return
    }
    // 編輯器裡有未保存改動 → 先存再發（否則發佈的是舊內容）
    if (editingThis) {
      const dirty = JSON.stringify(draftSchema) !== JSON.stringify(row.schema_json || {}) || draftName !== row.name
      if (dirty) {
        const saved = await handleSave(row, true)
        if (!saved) return
      }
    }
    setBusy(true)
    setError('')
    setNotice('')
    setGrayBar('')
    setWarnings([])
    const result = await callTemplateApi<{
      template: TemplateRow; archived_ids?: number[]; changed?: boolean; warnings?: TemplateWarning[]
    }>(`/api/templates/${row.id}/publish`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(identity)
    })
    setBusy(false)
    if (!result.ok) { showFailure(result.failure); return }
    const archivedIds = Array.isArray(result.data.archived_ids) ? result.data.archived_ids : []
    if (panel !== null && panel.row.id === row.id) setPanel(null)
    await loadList()
    setWarnings(result.data.warnings || [])
    setNotice(`已發佈：v${result.data.template.version} 生效中`)
    if (archivedIds.length > 0) {
      const labels = archivedIds.map(id => {
        const found = rows.find(item => item.id === id)
        return found ? `v${found.version}` : `#${id}`
      })
      setGrayBar(`舊版本 ${labels.join('、')} 已歸檔（歷史病歷不受影響）`)
    }
  }

  /** 「歸檔」＝ `POST /api/templates/{id}/archive`（§13.6：二次確認）。 */
  const handleArchive = async (row: TemplateRow) => {
    if (!confirm(`歸檔「${typeLabel(row.type)} · v${row.version}」？歸檔後不再用於新病歷，歷史病歷不受影響。`)) return
    setBusy(true)
    setError('')
    setGrayBar('')
    const result = await callTemplateApi<{ template: TemplateRow; changed?: boolean }>(
      `/api/templates/${row.id}/archive`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(identity)
      })
    setBusy(false)
    if (!result.ok) { showFailure(result.failure); return }
    if (panel !== null && panel.row.id === row.id) setPanel(null)
    await loadList()
    setNotice(result.data.changed === false ? '該版本已是已歸檔' : '已歸檔：不再用於新病歷，歷史病歷不受影響')
  }

  /** 「重新啟用」＝ `POST /api/templates/{id}/activate`（§13.6：二次確認；不校驗 schema）。 */
  const handleActivate = async (row: TemplateRow) => {
    if (!confirm(`重新啟用「${typeLabel(row.type)} · v${row.version}」？若該類型已有生效版本，將一併歸檔。`)) return
    setBusy(true)
    setError('')
    setGrayBar('')
    const result = await callTemplateApi<{ template: TemplateRow; archived_ids?: number[]; changed?: boolean }>(
      `/api/templates/${row.id}/activate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(identity)
      })
    setBusy(false)
    if (!result.ok) { showFailure(result.failure); return }
    const archivedIds = Array.isArray(result.data.archived_ids) ? result.data.archived_ids : []
    if (panel !== null && panel.row.id === row.id) setPanel(null)
    await loadList()
    setNotice(result.data.changed === false ? '該版本已在生效中' : '已重新啟用')
    setGrayBar(archivedIds.length > 0 ? '已有生效版本被一併歸檔（歷史病歷不受影響）' : '')
  }

  /** 「基於此版本修訂」＝ `POST /api/templates/{id}/derive`（同鏈已有草稿則後端複用）。 */
  const handleDerive = async (row: TemplateRow, customNotice?: string) => {
    setBusy(true)
    setError('')
    setGrayBar('')
    setWarnings([])
    const result = await callTemplateApi<{ template: TemplateRow; reused_draft?: boolean }>(
      `/api/templates/${row.id}/derive`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(identity)
      })
    setBusy(false)
    if (!result.ok) { showFailure(result.failure); return }
    await loadList()
    await openPanel('edit', result.data.template)
    setNotice(customNotice || (result.data.reused_draft
      ? '已回到未發佈的修訂版'
      : `已建立 v${result.data.template.version} 草稿（基於 v${row.version}）`))
  }

  // §13.1：flag off → 整卡不渲染（不阻塞其它頁籤）；探測未完成前也不渲染，避免閃一下
  if (probeState === 'unknown' || probeState === 'off') return null

  return (
    <div style={TS_BOX}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap', marginBottom: '12px' }}>
        <span style={{ fontSize: '18px', color: '#8b4513', fontWeight: 'bold' }}>📜 模板傳承（四類）</span>
        <button style={TS_GHOST_BTN} disabled={busy || probeState !== 'on'}
          onClick={() => {
            setError('')
            setNotice('')
            setGrayBar('')
            setPanel(null)
            setChain([])
            setHerbsLoaded(false)
            loadList()
          }}>
          🔄 重新載入
        </button>
        <span style={{ ...TS_HINT, flex: '1 1 220px' }}>
          模板只提供骨架與參考，診斷、辨證、開方、簽字皆由老師決定（不改舊通道行為，歷史病歷零回溯）
        </span>
      </div>

      {probeState === 'unavailable' && (
        <div style={TS_ERROR}>模板表未就緒，請聯絡管理員（遷移未跑 / templates 表缺失）</div>
      )}

      {probeState === 'on' && loadState === 'error' && (
        <div style={TS_ERROR}>載入失敗：{error || '請稍後重試'}</div>
      )}

      {probeState === 'on' && loadState !== 'error' && (
        <>
          {error && <div style={TS_ERROR}>{error}</div>}
          {notice && <div style={TS_NOTICE}>{notice}</div>}
          {grayBar && <div style={TS_GRAY_BAR}>{grayBar}</div>}
          {loadState === 'loading' && <div style={TS_HINT}>載入中…</div>}
          {loadState === 'ready' && (
            <>
              <TemplateTypeTabs
                activeTabType={activeTabType}
                rowsByType={rowsByType}
                counts={counts}
                onSelect={type => {
                  setActiveTabType(type)
                  setPanel(null)
                  setChain([])
                  setError('')
                  setWarnings([])
                }}
              />
              {panel ? (
                <>
                  <TemplateEditor
                    row={panel.row}
                    readOnly={panel.mode === 'view'}
                    name={draftName}
                    schema={draftSchema}
                    warnings={warnings}
                    herbs={herbs}
                    herbsLoaded={herbsLoaded}
                    busy={busy}
                    onNameChange={setDraftName}
                    onSchemaChange={setDraftSchema}
                    onSave={() => handleSave(panel.row)}
                    onPublish={() => handlePublish(panel.row)}
                    onClose={() => { setPanel(null); setChain([]) }}
                  />
                  <TemplateVersions
                    chain={chain}
                    currentId={panel.row.id}
                    busy={busy}
                    onView={id => {
                      const target = rows.find(item => item.id === id)
                      if (target) openPanel('view', target)
                    }}
                    onDerive={id => {
                      const target = rows.find(item => item.id === id)
                      if (target) handleDerive(target)
                    }}
                  />
                </>
              ) : (
                <TemplateList
                  rows={rowsByType[activeTabType]}
                  templateType={activeTabType}
                  busy={busy}
                  onCreate={handleCreate}
                  onEditDraft={row => openPanel('edit', row)}
                  onView={row => openPanel('view', row)}
                  onPublish={handlePublish}
                  onArchive={handleArchive}
                  onActivate={handleActivate}
                  onDerive={row => handleDerive(row)}
                />
              )}
            </>
          )}
        </>
      )}

      <div style={{ ...TS_HINT, marginTop: '14px', borderTop: '1px dashed #d4c8a8', paddingTop: '10px' }}>
        {TEMPLATE_BOUNDARY_NOTICE}　｜　模板變更只影響新病歷；歷史病歷與舊通道（`/api/plan_template`）行為不變。
      </div>
    </div>
  )
}


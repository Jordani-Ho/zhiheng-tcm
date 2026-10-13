/**
 * 【D-072】师门上下文派生 —— 从 App.tsx 抽出的可测部分。
 *
 * 为什么值得抽（这是**所有师门相关请求的咽喉**）：
 *   · `withLineage()` 是全站**唯一**的 `lineage_id` 拼参出口（Epic 4 §7.2 明文要求
 *     「集中在一处拼参」）；它一旦多拼 / 少拼 / 改参数顺序，会同时打歪所有师门请求；
 *   · 项目有多条测试守护「**flag off 时 URL 逐字节一致**」（`test_lineage.py` 的
 *     `test_flag_off_sql_bytes_and_payload_identical` 等）——前端这一侧此前**零测试**；
 *   · 空上下文必须产出「原样 URL」（不产生 `?lineage_id=`、不改变参数顺序），
 *     这个条件很容易在后续改动中被写坏。
 *
 * 两条派生规则（与抽取前逐字一致）：
 *   1. `currentLineageId`：flag off → 恒空串；老师端 → 自己的唯一师门 id；
 *      学生端 → 当前咨询老师对应的活跃师门，取不到再回落显式选中的视图。
 *   2. `withLineage(url)`：空上下文原样返回；非空则按「已有 `?` 用 `&`，否则用 `?`」追加，
 *      且值经 `encodeURIComponent`。
 */

export type LineageStatusRow = {
  teacher_name?: string
  lineage_id?: string
  status?: string
  unassigned?: boolean
}

export type DeriveLineageContextInput = {
  /** flag 探测结果（false → 一切归零） */
  lineageEnabled: boolean
  /** 当前是否老师端身份 */
  lineageIsTeacher: boolean
  /** 老师端自己的师门（可能为 null） */
  teacherLineage: { id?: string } | null
  /** 学生端归属清单 */
  studentLineages: LineageStatusRow[]
  /** 当前咨询的老师 */
  selectedTeacher: string
  /** 学生端显式选中的视图（可能是「全部师门」汇总） */
  lineageView: string
  /** 「全部师门（汇总）」的特殊值 */
  allView: string
}

/** 规则 1：算出当前师门上下文 id（空串 = 无上下文）。 */
export function deriveCurrentLineageId(input: DeriveLineageContextInput): string {
  const {
    lineageEnabled, lineageIsTeacher, teacherLineage,
    studentLineages, selectedTeacher, lineageView, allView,
  } = input

  // flag off → 恒空串：于是所有请求 URL 与 Epic 4 之前逐字面一致（§4.4 零行为变化）
  if (!lineageEnabled) return ''

  if (lineageIsTeacher) return teacherLineage?.id || ''

  const row = (studentLineages || []).find(
    r => r.teacher_name === selectedTeacher && r.status === 'active' && !!r.lineage_id,
  )
  if (row && row.lineage_id) return row.lineage_id

  return lineageView && lineageView !== allView ? lineageView : ''
}

/** 规则 2：把 `lineage_id` 拼进 URL（**全站唯一出口**）。空上下文 → 原样返回。 */
export function withLineageParam(url: string, lineageId: string): string {
  if (!lineageId) return url
  return `${url}${url.includes('?') ? '&' : '?'}lineage_id=${encodeURIComponent(lineageId)}`
}

/** 便捷组合：给定输入直接拿拼好参数的 URL。 */
export function buildLineageUrl(url: string, input: DeriveLineageContextInput): string {
  return withLineageParam(url, deriveCurrentLineageId(input))
}

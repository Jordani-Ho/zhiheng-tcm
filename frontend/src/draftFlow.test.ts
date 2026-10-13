import { describe, it, expect } from 'vitest'
import {
  buildTranscribeBody,
  buildOnsitePlaceholder,
  decideDraftFallback,
  evaluateTranscribeResult,
} from './draftFlow'

/**
 * 【D-076】病历草案落库兜底路径守护（内测场景 3「非预约面诊」的关键路径）。
 *
 * 缺陷背景：老师现场录入的兜底 `createDraftViaTranscribe` 原先
 *   ① 请求体**不带 `lineage_id`** → flag on 时后端 400 `lineage_required`
 *   ② `.then(() => findDraftIdByPatient(...))` **完全不看响应** → 400 也当成功
 *   结果：老师看到「落库失败：没能生成病历草案，无法签字」，且说不清原因。
 *
 * 本文件把这两点钉住：请求体必须带非空 lineage_id；非 2xx 必须显式判失败。
 */

const D = new Date(2026, 9, 4)   // 2026-10-04（月从 0 计）

describe('buildTranscribeBody（/api/transcribe 请求体）', () => {
  it('**必须带非空 lineage_id**（flag on 时缺它 -> 400 lineage_required）', () => {
    const body = buildTranscribeBody('学生B', '王医生', 'lin-uabc123', D)
    expect(body.lineage_id).toBe('lin-uabc123')
  })

  it('lineage_id 为 undefined/null 时落成空串（而非缺字段，便于后端统一判）', () => {
    expect(buildTranscribeBody('学生B', '王医生', undefined as unknown as string, D).lineage_id).toBe('')
    expect(buildTranscribeBody('学生B', '王医生', null as unknown as string, D).lineage_id).toBe('')
  })

  it('字段齐全且类型正确（后端按 data_type 分流）', () => {
    const body = buildTranscribeBody('学生B', '王医生', 'lin-x', D)
    expect(Object.keys(body).sort()).toEqual(['content', 'data_type', 'lineage_id', 'patient_name', 'teacher_name'])
    expect(body.data_type).toBe('text')
    expect(body.patient_name).toBe('学生B')
    expect(body.teacher_name).toBe('王医生')
  })

  it('正文是「老师现场录入」占位（后端据此自动生成草案）', () => {
    const body = buildTranscribeBody('学生B', '王医生', 'lin-x', D)
    expect(body.content).toContain('老师现场录入')
    expect(body.content).toContain('学生B')
  })
})

describe('buildOnsitePlaceholder（现场录入占位正文）', () => {
  it('含学生名与本地日期，并说明学生未提交线上陈述', () => {
    const t = buildOnsitePlaceholder('学生B', D)
    expect(t).toContain('学生B')
    expect(t).toContain('2026年10月4日')
    expect(t).toContain('学生未提交线上陈述')
  })

  it('日期按本地时区取（不出现时区偏移差一天）', () => {
    expect(buildOnsitePlaceholder('X', new Date(2026, 0, 1))).toContain('2026年1月1日')
    expect(buildOnsitePlaceholder('X', new Date(2026, 11, 31))).toContain('2026年12月31日')
  })
})

describe('decideDraftFallback（兜底分支）', () => {
  it('没有未处理陈述 -> 走「老师现场录入」兜底', () => {
    expect(decideDraftFallback(null, false)).toEqual({ step: 'create-via-transcribe' })
    expect(decideDraftFallback(undefined, false)).toEqual({ step: 'create-via-transcribe' })
  })

  it('有陈述但 generate-draft 没给出 id（已被处理过）-> 同样走兜底', () => {
    expect(decideDraftFallback(77, false)).toEqual({ step: 'create-via-transcribe' })
  })

  it('有陈述且 generate-draft 成功 -> 直接用该陈述', () => {
    expect(decideDraftFallback(77, true)).toEqual({ step: 'generate-from-transcript', transcriptId: 77 })
  })

  it('transcriptId = 0 视为「有」（不得用 falsy 判断把它当成没有）', () => {
    expect(decideDraftFallback(0, true)).toEqual({ step: 'generate-from-transcript', transcriptId: 0 })
  })
})

describe('evaluateTranscribeResult（**显式**判定兜底是否成功）', () => {
  it('2xx -> 成功', () => {
    expect(evaluateTranscribeResult(200, { message: '转述成功' }).ok).toBe(true)
    expect(evaluateTranscribeResult(201, {}).ok).toBe(true)
  })

  it('**400 lineage_required -> 失败且带出错误码**（这正是本次缺陷的真实返回）', () => {
    const r = evaluateTranscribeResult(400, {
      detail: { error: 'lineage_required', msg: '缺少師門上下文（lineage_id）', errors: [], warnings: [] },
    })
    expect(r.ok).toBe(false)
    expect(r.errorCode).toBe('lineage_required')
    expect(r.message).toContain('lineage_id')
  })

  it('500 无结构化 detail -> 失败，错误码回落 http_500', () => {
    const r = evaluateTranscribeResult(500, {})
    expect(r.ok).toBe(false)
    expect(r.errorCode).toBe('http_500')
  })

  it('detail 是字符串（FastAPI 默认校验错误形态）-> 带上该文案', () => {
    const r = evaluateTranscribeResult(422, { detail: '字段缺失' })
    expect(r.ok).toBe(false)
    expect(r.errorCode).toBe('http_422')
    expect(r.message).toBe('字段缺失')
  })

  it('body 为 null / 非对象也不抛错', () => {
    expect(evaluateTranscribeResult(400, null).ok).toBe(false)
    expect(evaluateTranscribeResult(400, 'oops').ok).toBe(false)
  })
})

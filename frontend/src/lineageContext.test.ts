import { describe, it, expect } from 'vitest'
import {
  deriveCurrentLineageId,
  withLineageParam,
  buildLineageUrl,
  type DeriveLineageContextInput,
} from './lineageContext'

/**
 * 【D-072】师门上下文派生守护。
 *
 * 这是**所有师门相关请求的咽喉**：`withLineage` 是全站唯一的 `lineage_id` 拼参出口。
 * 它多拼 / 少拼 / 改了参数顺序，会同时打歪全部师门请求。
 * 而后端侧有多条「flag off 时 URL 逐字节一致」的守护（`test_lineage.py`）——
 * 前端这一侧此前零测试，本文件补上。
 */

const ALL = '__all__'

function input(over: Partial<DeriveLineageContextInput> = {}): DeriveLineageContextInput {
  return {
    lineageEnabled: true,
    lineageIsTeacher: false,
    teacherLineage: null,
    studentLineages: [],
    selectedTeacher: '王医生',
    lineageView: '',
    allView: ALL,
    ...over,
  }
}

describe('deriveCurrentLineageId（师门上下文）', () => {
  it('**flag off -> 恒空串**（保证 URL 与 Epic 4 之前逐字面一致）', () => {
    expect(deriveCurrentLineageId(input({
      lineageEnabled: false,
      lineageIsTeacher: true,
      teacherLineage: { id: 'lin-x' },
      studentLineages: [{ teacher_name: '王医生', lineage_id: 'lin-y', status: 'active' }],
      lineageView: 'lin-z',
    }))).toBe('')
  })

  it('老师端 -> 取自己的师门 id', () => {
    expect(deriveCurrentLineageId(input({ lineageIsTeacher: true, teacherLineage: { id: 'lin-t' } }))).toBe('lin-t')
  })

  it('老师端但师门为空 / null -> 空串（不猜）', () => {
    expect(deriveCurrentLineageId(input({ lineageIsTeacher: true, teacherLineage: null }))).toBe('')
    expect(deriveCurrentLineageId(input({ lineageIsTeacher: true, teacherLineage: {} }))).toBe('')
  })

  it('学生端 -> 取**当前咨询老师**对应的活跃师门', () => {
    expect(deriveCurrentLineageId(input({
      studentLineages: [
        { teacher_name: '李医生', lineage_id: 'lin-l', status: 'active' },
        { teacher_name: '王医生', lineage_id: 'lin-w', status: 'active' },
      ],
      selectedTeacher: '王医生',
    }))).toBe('lin-w')
  })

  it('学生端：非 active 的归属**不算**（如已退出/封存）', () => {
    expect(deriveCurrentLineageId(input({
      studentLineages: [{ teacher_name: '王医生', lineage_id: 'lin-w', status: 'left' }],
      lineageView: '',
    }))).toBe('')
  })

  it('学生端：归属行的 lineage_id 为空 -> 不算（回落视图）', () => {
    expect(deriveCurrentLineageId(input({
      studentLineages: [{ teacher_name: '王医生', lineage_id: '', status: 'active' }],
      lineageView: 'lin-v',
    }))).toBe('lin-v')
  })

  it('学生端：老师对不上 -> 回落显式选中的视图', () => {
    expect(deriveCurrentLineageId(input({
      studentLineages: [{ teacher_name: '李医生', lineage_id: 'lin-l', status: 'active' }],
      selectedTeacher: '王医生',
      lineageView: 'lin-v',
    }))).toBe('lin-v')
  })

  it('学生端：视图是「全部师门（汇总）」-> 回落也不能用它当上下文（否则会按汇总 id 过滤）', () => {
    expect(deriveCurrentLineageId(input({
      studentLineages: [],
      selectedTeacher: '王医生',
      lineageView: ALL,
    }))).toBe('')
  })

  it('学生端：无归属且无视图 -> 空串', () => {
    expect(deriveCurrentLineageId(input())).toBe('')
  })
})

describe('withLineageParam（**全站唯一**拼参出口）', () => {
  it('空上下文 -> **原样返回**（不产生 ?lineage_id=，不改参数顺序）', () => {
    expect(withLineageParam('/api/drafts', '')).toBe('/api/drafts')
    expect(withLineageParam('/api/drafts?teacher_name=X', '')).toBe('/api/drafts?teacher_name=X')
  })

  it('无 query 的 URL -> 用 `?`', () => {
    expect(withLineageParam('/api/drafts', 'lin-a')).toBe('/api/drafts?lineage_id=lin-a')
  })

  it('已有 query -> 用 `&`（且**保留原有参数与顺序**）', () => {
    expect(withLineageParam('/api/drafts?teacher_name=X', 'lin-a'))
      .toBe('/api/drafts?teacher_name=X&lineage_id=lin-a')
  })

  it('值经 encodeURIComponent（lineage id 含特殊字符也不破 URL）', () => {
    expect(withLineageParam('/api/x', 'lin a/b&c')).toBe('/api/x?lineage_id=lin%20a%2Fb%26c')
  })

  it('**幂等风险显式化**：同一 URL 连拼两次会重复（调用方不得重复拼）', () => {
    const once = withLineageParam('/api/x', 'lin-a')
    const twice = withLineageParam(once, 'lin-a')
    expect(twice).toBe('/api/x?lineage_id=lin-a&lineage_id=lin-a')
  })
})

describe('buildLineageUrl（组合）', () => {
  it('flag off -> URL 与不调本函数完全一致（逐字节）', () => {
    const url = '/api/teacher-patients?teacher_name=%E7%8E%8B%E5%8C%BB%E7%94%9F'
    expect(buildLineageUrl(url, input({ lineageEnabled: false }))).toBe(url)
  })

  it('老师端带上自己的师门 id', () => {
    expect(buildLineageUrl('/api/teacher-patients?teacher_name=X', input({
      lineageIsTeacher: true, teacherLineage: { id: 'lin-t' },
    }))).toBe('/api/teacher-patients?teacher_name=X&lineage_id=lin-t')
  })

  it('学生端带上当前老师对应的师门 id', () => {
    expect(buildLineageUrl('/api/drafts?patient_name=P', input({
      studentLineages: [{ teacher_name: '王医生', lineage_id: 'lin-w', status: 'active' }],
    }))).toBe('/api/drafts?patient_name=P&lineage_id=lin-w')
  })
})

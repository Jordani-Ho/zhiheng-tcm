import { describe, it, expect, vi } from 'vitest'
import { bootstrapIdentity } from './identityBootstrap'

/**
 * 【D-069】身份引导守护。
 *
 * 这段逻辑是「去掉单例锁」的核心（D-059）：它决定**当前是谁**。
 * 此前它嵌在 App.tsx 的 App() 里、**零测试覆盖** —— 而它一旦出错，
 * 后果是「老师端看不到学生」或「学生被当成老师」，比白屏更难发现。
 */

type Route = { match: (url: string) => boolean; body?: unknown; ok?: boolean }
function stubFetch(routes: Route[]) {
  const calls: string[] = []
  const fn = vi.fn(async (input: string) => {
    calls.push(input)
    const hit = routes.find(r => r.match(input))
    return {
      ok: hit?.ok ?? true,
      status: hit?.ok === false ? 500 : 200,
      json: async () => {
        if (hit?.body === '__BAD_JSON__') throw new Error('bad json')
        return hit?.body ?? {}
      },
    } as unknown as Response
  })
  return { fn, calls }
}

const isPatientTeachers = (u: string) => u.includes('/api/patient-teachers')
const isTeachers = (u: string) => u.endsWith('/api/teachers') || u.includes('/api/teachers?')
const isTeacherPatients = (u: string) => u.includes('/api/teacher-patients')

describe('bootstrapIdentity（身份引导）', () => {
  it('学生归属有老师 -> 用第一个，且不再问老师列表', async () => {
    const { fn, calls } = stubFetch([
      { match: isPatientTeachers, body: ['王医生', '李医生'] },
      { match: isTeacherPatients, body: [{ name: '学生甲' }] },
    ])
    const r = await bootstrapIdentity('', '', fn)

    expect(r.teacherName).toBe('王医生')
    expect(r.patientName).toBe('学生甲')
    expect(r.source).toBe('patient-teachers')
    expect(r.fellBackToTeachers).toBe(false)
    expect(calls.some(isTeachers)).toBe(false)   // 不该问老师列表
  })

  it('学生归属为空 -> 兜底取老师列表第一个，teachers 回传给 UI', async () => {
    const { fn, calls } = stubFetch([
      { match: isPatientTeachers, body: [] },
      { match: isTeachers, body: [{ name: '张医生', description: '内科' }] },
      { match: isTeacherPatients, body: [{ name: '学生乙' }] },
    ])
    const r = await bootstrapIdentity('', '', fn)

    expect(r.source).toBe('teachers')
    expect(r.fellBackToTeachers).toBe(true)
    expect(r.teacherName).toBe('张医生')
    expect(r.patientName).toBe('学生乙')
    expect(r.teachers).toEqual([{ name: '张医生', description: '内科' }])
    expect(calls.some(isTeachers)).toBe(true)
  })

  it('调用方已选定老师 -> 沿用，不被列表第一个覆盖', async () => {
    const { fn } = stubFetch([
      { match: isPatientTeachers, body: ['王医生', '李医生'] },
      { match: isTeacherPatients, body: [{ name: '学生甲' }] },
    ])
    const r = await bootstrapIdentity('李医生', '', fn)
    expect(r.teacherName).toBe('李医生')
  })

  it('调用方已选定学生 -> 沿用，不再问该老师名下学生', async () => {
    const { fn, calls } = stubFetch([
      { match: isPatientTeachers, body: ['王医生'] },
    ])
    const r = await bootstrapIdentity('', '学生丙', fn)
    expect(r.patientName).toBe('学生丙')
    expect(calls.some(isTeacherPatients)).toBe(false)
  })

  it('老师列表为空 -> 保持空值，不炸', async () => {
    const { fn } = stubFetch([
      { match: isPatientTeachers, body: [] },
      { match: isTeachers, body: [] },
    ])
    const r = await bootstrapIdentity('', '', fn)
    expect(r.teacherName).toBe('')
    expect(r.patientName).toBe('')
    // 语义约定：`source` = **走了哪个分支**（此处确实走了老师列表分支）；
    // 「有没有解析出结果」看 `teacherName` 是否为空 —— 两者是不同问题，不混用。
    expect(r.source).toBe('teachers')
    expect(r.fellBackToTeachers).toBe(true)
    expect(r.teachers).toEqual([])
  })

  it('所有请求都失败 -> 全部退化，**不抛错**（首屏不白屏）', async () => {
    const { fn } = stubFetch([
      { match: isPatientTeachers, body: {}, ok: false },
      { match: isTeachers, body: {}, ok: false },
    ])
    await expect(bootstrapIdentity('', '', fn)).resolves.toMatchObject({
      teacherName: '', patientName: '', source: 'none',
    })
  })

  it('JSON 解析失败 -> 不抛错，退化为空', async () => {
    const { fn } = stubFetch([
      { match: isPatientTeachers, body: '__BAD_JSON__' },
      { match: isTeachers, body: '__BAD_JSON__' },
    ])
    await expect(bootstrapIdentity('', '', fn)).resolves.toMatchObject({ teacherName: '' })
  })

  it('老师名下无学生 -> patientName 保持空，不抛错', async () => {
    const { fn } = stubFetch([
      { match: isPatientTeachers, body: ['王医生'] },
      { match: isTeacherPatients, body: [] },
    ])
    const r = await bootstrapIdentity('', '', fn)
    expect(r.teacherName).toBe('王医生')
    expect(r.patientName).toBe('')
  })

  it('URL 参数正确编码（含空格的老师名 / 空的学生名不报错）', async () => {
    const { fn, calls } = stubFetch([
      { match: isPatientTeachers, body: [] },
      { match: isTeachers, body: [{ name: '王 医生' }] },
      { match: isTeacherPatients, body: [] },
    ])
    await bootstrapIdentity('', '', fn)

    expect(calls[0]).toContain('patient_name=')                    // 空学生名也照常发（保持原行为）
    expect(calls.some(c => c.includes('/api/teacher-patients?teacher_name=%E7%8E%8B%20%E5%8C%BB%E7%94%9F'))).toBe(true)
  })

  it('老师列表若为对象数组 -> 取 name（兼容两种返回形态）', async () => {
    const { fn } = stubFetch([
      { match: isPatientTeachers, body: [{ name: '王医生' }, { name: '李医生' }] },
    ])
    const r = await bootstrapIdentity('', '', fn)
    expect(r.teacherName).toBe('王医生')
  })

  it('**永不抛错**：fetch 自身抛异常也退化为空', async () => {
    const fn = vi.fn(async () => { throw new Error('network down') })
    await expect(bootstrapIdentity('', '', fn)).resolves.toMatchObject({
      teacherName: '', patientName: '', source: 'none',
    })
  })
})

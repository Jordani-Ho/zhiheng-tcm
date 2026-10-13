import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import LearningPanel from './LearningPanel'

/**
 * 【D-067】学习闭环面板守护。
 *
 * 存在理由：A 板块后端已闭环（3 只读端点 + 哈希链 + 70 条测试），但前端**零消费**。
 * 本面板是它的界面入口；这批用例钉住三件事：
 *   ① flag off（404 learning_disabled）→ **整卡不渲染**（与 AgentStagePanel / SealPanel 同款）
 *   ② 正常响应 → 链节按后端返回渲染，链状态正确显示
 *   ③ **链断（409）不是服务故障** —— 后端把「链断」定义为数据事实，面板须如实展示而不是当成错误崩掉
 */

let container: HTMLDivElement
let root: Root

function mount(ui: React.ReactElement) {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  act(() => { root.render(ui) })
}

function stubFetch(routes: Array<{ match: (url: string) => boolean; body?: unknown; ok?: boolean; status?: number }>) {
  const calls: string[] = []
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    calls.push(url)
    const hit = routes.find(r => r.match(url))
    const ok = hit?.ok ?? true
    const status = hit?.status ?? (ok ? 200 : 400)
    return { ok, status, json: async () => hit?.body ?? {} } as unknown as Response
  }))
  return calls
}

async function flush() {
  await act(async () => { await Promise.resolve(); await Promise.resolve(); await Promise.resolve() })
}

beforeEach(() => {
  vi.spyOn(console, 'error').mockImplementation(() => {})
})
afterEach(() => {
  act(() => { root?.unmount() })
  container?.remove()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('LearningPanel（学习闭环）', () => {
  it('flag off（404 learning_disabled）-> **整卡不渲染**', async () => {
    stubFetch([{ match: u => u.includes('/api/agent/learning/events'), body: { detail: { error: 'learning_disabled' } }, ok: false, status: 404 }])
    mount(<LearningPanel teacherName="王医生" />)
    await flush()
    expect(container.textContent).toBe('')
  })

  it('teacherName 为空 -> 不发请求，也不渲染', async () => {
    const calls = stubFetch([{ match: u => u.includes('/api/agent/learning/events'), body: {} }])
    mount(<LearningPanel teacherName="" />)
    await flush()
    expect(calls.length).toBe(0)
    expect(container.textContent).toBe('')
  })

  it('正常响应 -> 渲染链节数、事件类型、链校验通过标记', async () => {
    stubFetch([{
      match: u => u.includes('/api/agent/learning/events'),
      body: {
        total: 2, verified: true,
        events: [
          { seq: 2, event_type: 'draft_generated', payload_hash: 'a'.repeat(64), prev_hash: 'b'.repeat(64), created_at: '2026-10-04T10:00:00' },
          { seq: 1, event_type: 'template_configured', payload_hash: 'c'.repeat(64), prev_hash: '0'.repeat(64), created_at: '2026-10-04T09:00:00' },
        ],
      },
    }])
    mount(<LearningPanel teacherName="王医生" />)
    await flush()

    const text = container.textContent || ''
    expect(text).toContain('学习闭环')
    expect(text).toContain('2 条链节')
    expect(text).toContain('链校验通过')
    expect(text).toContain('draft_generated')
    expect(text).toContain('template_configured')
    expect(text).toContain('#2')
    expect(text).toContain('#1')
  })

  it('请求带双因子且一致（teacher_name == teacher_id，编码正确）', async () => {
    const calls = stubFetch([{ match: u => u.includes('/api/agent/learning/events'), body: { total: 0, verified: true, events: [] } }])
    mount(<LearningPanel teacherName="王 医生" />)
    await flush()

    expect(calls.length).toBeGreaterThan(0)
    const url = calls[0]
    expect(url).toContain('teacher_name=%E7%8E%8B%20%E5%8C%BB%E7%94%9F')
    expect(url).toContain('teacher_id=%E7%8E%8B%20%E5%8C%BB%E7%94%9F')
  })

  it('空链 -> 显示引导文案，不炸', async () => {
    stubFetch([{ match: u => u.includes('/api/agent/learning/events'), body: { total: 0, verified: true, events: [] } }])
    mount(<LearningPanel teacherName="王医生" />)
    await flush()
    expect(container.textContent).toContain('暂无学习事件')
  })

  it('**链断（409）是数据事实，不是服务故障** -> 如实展示「链已断」，不抛错', async () => {
    stubFetch([{
      match: u => u.includes('/api/agent/learning/events'),
      body: { detail: { error: 'chain_broken', msg: '学习链校验未通过' } },
      ok: false, status: 409,
    }])
    mount(<LearningPanel teacherName="王医生" />)
    await flush()

    const text = container.textContent || ''
    expect(text).toContain('链已断')
    expect(text).not.toBe('')                      // 卡片仍在（链断也要能看到）
    expect(console.error).not.toHaveBeenCalled()
  })

  it('服务异常（500）-> 显示错误但不白屏', async () => {
    stubFetch([{ match: u => u.includes('/api/agent/learning/events'), body: { detail: { msg: '内部错误' } }, ok: false, status: 500 }])
    mount(<LearningPanel teacherName="王医生" />)
    await flush()
    const text = container.textContent || ''
    expect(text).toContain('学习闭环')
    expect(text).toContain('内部错误')
  })

  it('整轮挂载 + 渲染 console.error 零调用（防白屏）', async () => {
    stubFetch([{ match: u => u.includes('/api/agent/learning/events'), body: { total: 1, verified: true, events: [{ seq: 1, event_type: 'x' }] } }])
    mount(<LearningPanel teacherName="王医生" />)
    await flush()
    expect(console.error).not.toHaveBeenCalled()
  })
})

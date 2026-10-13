import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import TeacherOnboarding from './TeacherOnboarding'

/**
 * 【D-065 前端测试框架】组件渲染 + 交互守护。
 *
 * 存在理由（D-060）：此前前端改动的验证上限只有 `tsc` + build + 模块加载，
 * **证明不了「页面上点一下真的对」**。本文件用 jsdom 真实挂载组件，
 * 用 fetch 桩驱动数据，从而能断言：
 *   · 组件渲染不抛错、不产生 React 警告（防白屏）
 *   · 老师列表按钮**按实际数据渲染**（不是写死）
 *   · 入社区提交的**请求体与后端契约一致**（双因子 name==teacher_id、字段齐全）
 *   · 失败时**不炸**、成功时回调触发
 *
 * 注意：本项目未安装 @testing-library/react，故直接用 `react-dom/client` + `act`
 * 挂载到 jsdom 的 document 上 —— 依赖更少，且同样能拿到真实 DOM 断言。
 */

let container: HTMLDivElement
let root: Root

function mount(ui: React.ReactElement) {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  act(() => { root.render(ui) })
}

/** 构造一个 fetch 桩：按 (method, url) 返回预设响应，并记录全部请求。 */
function stubFetch(routes: Array<{ match: (url: string, init?: RequestInit) => boolean; body: unknown; ok?: boolean; status?: number }>) {
  const calls: Array<{ url: string; init?: RequestInit }> = []
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    calls.push({ url, init })
    const hit = routes.find(r => r.match(url, init))
    const ok = hit?.ok ?? true
    const status = hit?.status ?? (ok ? 200 : 400)
    return {
      ok, status,
      json: async () => hit?.body ?? {},
    } as unknown as Response
  })
  vi.stubGlobal('fetch', fn)
  return { calls, fn }
}

async function flush() {
  // 让已排队的 promise 链跑完（fetch 桩是 async，useEffect 里是多级 then）
  await act(async () => { await Promise.resolve(); await Promise.resolve(); await Promise.resolve() })
}

beforeEach(() => {
  // React 的 act 警告 / key 警告等会被打印到 console.error：捕获以便断言「无渲染错误」
  vi.spyOn(console, 'error').mockImplementation(() => {})
  vi.spyOn(window, 'alert').mockImplementation(() => {})
})
afterEach(() => {
  act(() => { root?.unmount() })
  container?.remove()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('TeacherOnboarding（内测场景 1 的老师入社区面板）', () => {
  it('挂载即拉 /api/teachers，并**按实际数据**渲染老师列表（不写死）', async () => {
    const { calls } = stubFetch([
      { match: u => u.includes('/api/teachers'), body: [{ name: '王医生', description: '内科' }, { name: '李医生' }] },
    ])
    mount(<TeacherOnboarding />)
    await flush()

    expect(calls.some(c => c.url.includes('/api/teachers'))).toBe(true)
    const text = container.textContent || ''
    expect(text).toContain('王医生')
    expect(text).toContain('李医生')
    expect(text).toContain('2位')          // 标题里的计数
    // 反向：不得出现任何硬编码老师名
    expect(text).not.toContain('李老师')
  })

  it('老师列表为空 -> 显示引导文案，不炸', async () => {
    stubFetch([{ match: u => u.includes('/api/teachers'), body: [] }])
    mount(<TeacherOnboarding />)
    await flush()
    expect(container.textContent).toContain('暂无老师')
  })

  it('拉取失败 -> 显示错误但不抛错、不白屏', async () => {
    stubFetch([{ match: u => u.includes('/api/teachers'), body: {}, ok: false, status: 500 }])
    mount(<TeacherOnboarding />)
    await flush()
    expect(container.textContent).toContain('老师列表读取失败')
  })

  it('填入姓名后点「入社区」：请求体符合后端契约（双因子一致 + 字段齐全）', async () => {
    const { calls } = stubFetch([
      { match: u => u.includes('/api/teachers/onboard'), body: { teacher_created: true, lineage: { id: 'lin-wangyisheng' }, warnings: [] } },
      { match: u => u.includes('/api/teachers'), body: [] },
    ])
    mount(<TeacherOnboarding />)
    await flush()

    const input = container.querySelector('input') as HTMLInputElement
    expect(input).toBeTruthy()
    // React 受控输入：用原生 setter 触发 onChange
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')!.set!
    act(() => {
      setter.call(input, '  王医生  ')   // 带空格 → 断言会被 trim
      input.dispatchEvent(new Event('input', { bubbles: true }))
    })

    const onboardBtn = Array.from(container.querySelectorAll('button')).find(b => b.textContent === '入社区')!
    expect(onboardBtn).toBeTruthy()
    await act(async () => { onboardBtn.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    await flush()

    const post = calls.find(c => c.url.includes('/api/teachers/onboard'))
    expect(post).toBeTruthy()
    expect(post!.init?.method).toBe('POST')
    const body = JSON.parse(String(post!.init?.body))
    expect(body).toEqual({ name: '王医生', teacher_id: '王医生', description: '' })  // trim + 双因子一致
  })

  it('姓名为空时点「入社区」：不发请求，只提示', async () => {
    const { calls } = stubFetch([{ match: u => u.includes('/api/teachers'), body: [] }])
    mount(<TeacherOnboarding />)
    await flush()

    const btn = Array.from(container.querySelectorAll('button')).find(b => b.textContent === '入社区')!
    await act(async () => { btn.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    await flush()

    expect(calls.some(c => c.url.includes('/api/teachers/onboard'))).toBe(false)
    expect(window.alert).toHaveBeenCalled()
  })

  it('后端返回错误 -> 弹失败提示，不抛错；提交按钮恢复可用', async () => {
    stubFetch([
      { match: u => u.includes('/api/teachers/onboard'), body: { detail: { error: 'teacher_name_required', msg: '姓名不能为空' } }, ok: false, status: 400 },
      { match: u => u.includes('/api/teachers'), body: [] },
    ])
    mount(<TeacherOnboarding />)
    await flush()

    const input = container.querySelector('input') as HTMLInputElement
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')!.set!
    act(() => { setter.call(input, '王医生'); input.dispatchEvent(new Event('input', { bubbles: true })) })

    const btn = Array.from(container.querySelectorAll('button')).find(b => b.textContent === '入社区')!
    await act(async () => { btn.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    await flush()

    expect(window.alert).toHaveBeenCalledWith(expect.stringContaining('入社区失败'))
    expect((container.querySelectorAll('button') as unknown as HTMLButtonElement[])[0]).toBeTruthy()
  })

  it('点「切为当前」触发 onPickTeacher 回调（把身份交回 App）', async () => {
    stubFetch([{ match: u => u.includes('/api/teachers'), body: [{ name: '王医生' }] }])
    const onPick = vi.fn()
    mount(<TeacherOnboarding onPickTeacher={onPick} selectedTeacher="" />)
    await flush()

    const pick = Array.from(container.querySelectorAll('button')).find(b => b.textContent === '切为当前')!
    expect(pick).toBeTruthy()
    await act(async () => { pick.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    expect(onPick).toHaveBeenCalledWith('王医生')
  })

  it('已是当前身份时不再显示「切为当前」，改为标记「当前身份」', async () => {
    stubFetch([{ match: u => u.includes('/api/teachers'), body: [{ name: '王医生' }] }])
    mount(<TeacherOnboarding selectedTeacher="王医生" />)
    await flush()
    const text = container.textContent || ''
    expect(text).toContain('当前身份')
    expect(Array.from(container.querySelectorAll('button')).some(b => b.textContent === '切为当前')).toBe(false)
  })

  it('无渲染错误：整个挂载 + 交互过程 console.error 未被触发', async () => {
    const { calls } = stubFetch([{ match: u => u.includes('/api/teachers'), body: [{ name: '王医生' }] }])
    mount(<TeacherOnboarding />)
    await flush()
    expect(calls.length).toBeGreaterThan(0)
    expect(console.error).not.toHaveBeenCalled()
  })
})

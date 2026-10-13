import { useState, useEffect } from 'react'

/**
 * 【D-067 / 内测补缺入口】学习闭环面板。
 *
 * 背景：A 板块（Epic 3 学习闭环）**后端已闭环**（3 个只读端点 + 完整哈希链 + 70 条测试），
 * 但**前端零消费** —— `frontend/src` 里检索 `/api/agent/learning` **零命中**，
 * 界面上完全看不到「学习链」。本组件是它的界面入口。
 *
 * 后端契约（backend/learning_api.py）：
 *   GET /api/agent/learning/events?teacher_name=&teacher_id=&limit=&order=
 *       -> { events: [...], total, verified }        链断时为 409（数据事实，非服务故障）
 *   GET /api/agent/learning/chain/verify?teacher_name=&teacher_id=
 *       -> 链校验结果（ok / 断点信息）
 *   GET /api/agent/learning/metrics?teacher_name=&teacher_id=&window_days=
 *
 * 口径：
 *   · **只读**：本面板不提供任何写操作（学习事件由后端在签字/生成路径上自动写）
 *   · flag off（`LEARNING_ENABLED` 未开）→ 端点 404 `learning_disabled` → 整卡不渲染
 *   · 双因子：`teacher_name` 与 `teacher_id` 必须一致（阶段一无账号体系，沿后端既有口径）
 */

type LearningEvent = {
  id?: number
  seq?: number
  event_type?: string
  patient_name_hash?: string
  payload_hash?: string
  prev_hash?: string
  created_at?: string
}

type EventsResp = { events: LearningEvent[]; total: number; verified: boolean }

type Props = {
  /** 当前身份的老师名（空则不渲染任何请求） */
  teacherName: string
}

const boxStyle: React.CSSProperties = {
  background: '#fff',
  border: '1px solid #d4c8a8',
  borderRadius: '12px',
  padding: '20px',
  marginBottom: '20px',
  boxShadow: '0 4px 12px rgba(0,0,0,0.06)',
}

/** 哈希缩略：只显示前 12 位 + 后 4 位，避免撑破卡片 */
const shortHash = (h?: string) => {
  const s = String(h || '')
  if (!s) return '—'
  return s.length > 20 ? `${s.slice(0, 12)}…${s.slice(-4)}` : s
}

export default function LearningPanel({ teacherName }: Props) {
  // null=探测中 / true=可用 / false=flag off 或不可用（整卡不渲染）
  const [enabled, setEnabled] = useState<boolean | null>(null)
  const [data, setData] = useState<EventsResp | null>(null)
  const [chainOk, setChainOk] = useState<boolean | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const name = (teacherName || '').trim()

  const qs = (extra = '') =>
    `teacher_name=${encodeURIComponent(name)}&teacher_id=${encodeURIComponent(name)}${extra}`

  // 拉事件流 + 链状态；flag off → 整卡不渲染
  useEffect(() => {
    if (!name) { setEnabled(false); return }
    let alive = true
    setLoading(true)
    setError(null)

    fetch(`/api/agent/learning/events?${qs('&limit=50&order=desc')}`)
      .then(async res => {
        if (res.status === 404) { if (alive) setEnabled(false); return null }  // flag off
        const body = await res.json().catch(() => ({}))
        if (res.status === 409) {
          // 链断是**数据事实**：不是故障，如实展示「链已断」+ 事件仍可读
          if (alive) { setEnabled(true); setChainOk(false); setError(body?.detail?.msg || '学习链校验未通过（链已断）') }
          return null
        }
        if (!res.ok) throw new Error(body?.detail?.msg || `HTTP ${res.status}`)
        return body as EventsResp
      })
      .then(body => {
        if (!alive || !body) return
        setEnabled(true)
        setData(body)
        setChainOk(body.verified)
      })
      .catch(e => { if (alive) { setEnabled(true); setError(String(e.message || e)) } })
      .finally(() => { if (alive) setLoading(false) })

    return () => { alive = false }
  }, [name])

  // 探测未定 / 不可用 → 不渲染（与 AgentStagePanel / SealPanel 同款：flag off 整卡消失）
  if (enabled !== true) return null

  const events = data?.events || []

  return (
    <div style={boxStyle}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
        <div style={{ fontSize: '18px', color: '#8b4513', fontWeight: 'bold' }}>
          🔗 学习闭环（{data?.total ?? 0} 条链节）
        </div>
        <div style={{ fontSize: '12px' }}>
          {chainOk === true && <span style={{ color: '#5a7d5a', border: '1px solid #5a7d5a', borderRadius: '10px', padding: '2px 10px' }}>✓ 链校验通过</span>}
          {chainOk === false && <span style={{ color: '#c0392b', border: '1px solid #c0392b', borderRadius: '10px', padding: '2px 10px' }}>✗ 链已断</span>}
        </div>
      </div>
      <div style={{ fontSize: '12px', color: '#999', marginBottom: '14px' }}>
        每条学习事件按 <code>prev_hash + payload_hash</code> 串成可校验的链；本卡**只读**，事件由后端在生成/签字路径上自动写入。
      </div>

      {loading && <div style={{ fontSize: '12px', color: '#999' }}>加载中…</div>}
      {error && <div style={{ fontSize: '12px', color: '#c0392b', marginBottom: '10px' }}>{error}</div>}

      {!loading && events.length === 0 && !error && (
        <div style={{ fontSize: '12px', color: '#999' }}>
          暂无学习事件 —— 学生完成一次「录音 → 草案 → 签字」后，这里会出现链节。
        </div>
      )}

      {events.map((ev, i) => (
        <div
          key={`${ev.seq ?? i}-${ev.payload_hash ?? i}`}
          style={{ padding: '8px 10px', borderTop: '1px solid #f0f0f0', fontSize: '12px' }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', color: '#333' }}>
            <span style={{ fontWeight: 'bold' }}>#{ev.seq ?? '—'} · {ev.event_type || '（未知事件）'}</span>
            <span style={{ color: '#999' }}>{ev.created_at || '—'}</span>
          </div>
          <div style={{ color: '#888', marginTop: '2px', fontFamily: 'monospace' }}>
            payload: {shortHash(ev.payload_hash)} ｜ prev: {shortHash(ev.prev_hash)}
          </div>
        </div>
      ))}
    </div>
  )
}

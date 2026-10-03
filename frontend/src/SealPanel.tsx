import { useState, useEffect } from 'react'

type SealEvent = {
  id: number
  subject_type: string
  subject_name: string
  action: string
  reason: string | null
  operator: string | null
  created_at: string
}

type Props = {
  selectedTeacher: string
  selectedPatient: string
}

const boxStyle: React.CSSProperties = {
  background: '#fff',
  border: '1px solid #d4c8a8',
  borderRadius: '12px',
  padding: '20px',
  marginBottom: '20px',
  boxShadow: '0 4px 12px rgba(0,0,0,0.06)',
}

export default function SealPanel({ selectedTeacher, selectedPatient }: Props) {
  const [enabled, setEnabled] = useState<boolean | null>(null)
  const [subjectType, setSubjectType] = useState<'patient' | 'teacher'>('patient')
  const [subjectName, setSubjectName] = useState<string>(selectedPatient || '')
  const [reason, setReason] = useState<string>('')
  const [events, setEvents] = useState<SealEvent[]>([])
  const [loading, setLoading] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  // 切换患者时同步 subjectName
  useEffect(() => {
    if (subjectType === 'patient' && selectedPatient) setSubjectName(selectedPatient)
  }, [selectedPatient, subjectType])

  // 探测 flag（一次）
  useEffect(() => {
    fetch('/api/seal/events?subject_type=patient&subject_name=__probe__')
      .then(res => setEnabled(res.ok))
      .catch(() => setEnabled(false))
  }, [])

  // 加载事件（按当前主体）
  const loadEvents = () => {
    if (!subjectType || !subjectName.trim()) {
      setEvents([])
      return
    }
    setLoading(true)
    fetch(`/api/seal/events?subject_type=${encodeURIComponent(subjectType)}&subject_name=${encodeURIComponent(subjectName.trim())}`)
      .then(res => (res.ok ? res.json() : null))
      .then((data: { events?: SealEvent[] } | null) => {
        setEvents(data && Array.isArray(data.events) ? data.events : [])
      })
      .catch(() => setEvents([]))
      .finally(() => setLoading(false))
  }

  // subjectName 变化后自动加载
  useEffect(() => {
    if (enabled) loadEvents()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, subjectType, subjectName])

  const trigger = (action: 'seal' | 'readmit') => {
    const label = action === 'seal' ? '封存' : '重新接纳'
    if (!subjectName.trim()) {
      alert('请填写主体名称。')
      return
    }
    if (!confirm(`确定要${label}【${subjectName.trim()}】吗？`)) return
    setSubmitting(true)
    fetch('/api/seal/trigger', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        subject_type: subjectType,
        subject_name: subjectName.trim(),
        action,
        reason: reason.trim(),
        operator: selectedTeacher || '',
      }),
    })
      .then(res => res.json().then(body => ({ ok: res.ok, body })).catch(() => ({ ok: res.ok, body: {} as any })))
      .then(({ ok, body }) => {
        if (!ok) {
          const msg = body?.detail?.msg || body?.detail || `${label}失败`
          throw new Error(typeof msg === 'string' ? msg : `${label}失败`)
        }
        alert(`${label}成功`)
        setReason('')
        loadEvents()
      })
      .catch(err => alert(err?.message || `${label}失败`))
      .finally(() => setSubmitting(false))
  }

  // flag off / 探测中 → 不渲染
  if (enabled !== true) return null

  const actionLabel = (a: string) => (a === 'seal' ? '🔒 封存' : a === 'readmit' ? '🔓 重新接纳' : a)

  return (
    <div style={boxStyle}>
      <div style={{ textAlign: 'center', fontSize: '18px', color: '#8b4513', fontWeight: 'bold', marginBottom: '12px' }}>
        🔒 封存管理
      </div>

      {/* 触发区 */}
      <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center', marginBottom: '12px' }}>
        <select
          value={subjectType}
          onChange={e => setSubjectType(e.target.value as 'patient' | 'teacher')}
          style={{ padding: '6px 10px', borderRadius: '8px', border: '1px solid #8b4513', fontFamily: 'serif', fontSize: '13px' }}
        >
          <option value="patient">学生</option>
          <option value="teacher">老师</option>
        </select>
        <input
          value={subjectName}
          onChange={e => setSubjectName(e.target.value)}
          placeholder="主体名称"
          style={{ padding: '6px 10px', borderRadius: '8px', border: '1px solid #8b4513', fontFamily: 'serif', fontSize: '13px', flex: '1 1 140px' }}
        />
        <input
          value={reason}
          onChange={e => setReason(e.target.value)}
          placeholder="原因（可选）"
          style={{ padding: '6px 10px', borderRadius: '8px', border: '1px solid #d4c8a8', fontFamily: 'serif', fontSize: '13px', flex: '1 1 180px' }}
        />
        <button
          onClick={() => trigger('seal')}
          disabled={submitting}
          style={{ padding: '6px 16px', borderRadius: '20px', border: 'none', background: '#c0392b', color: '#fff', fontSize: '13px', cursor: submitting ? 'wait' : 'pointer', fontFamily: 'serif' }}
        >
          封存
        </button>
        <button
          onClick={() => trigger('readmit')}
          disabled={submitting}
          style={{ padding: '6px 16px', borderRadius: '20px', border: 'none', background: '#5a7d5a', color: '#fff', fontSize: '13px', cursor: submitting ? 'wait' : 'pointer', fontFamily: 'serif' }}
        >
          重新接纳
        </button>
      </div>

      {/* 列表区 */}
      <div style={{ background: '#fff', borderRadius: '8px', border: '1px solid #d4e8d4', overflow: 'hidden' }}>
        <div style={{ display: 'flex', padding: '10px', background: '#e8f4e8', fontSize: '13px', fontWeight: 'bold', color: '#5a7d5a' }}>
          <div style={{ flex: 1 }}>动作</div>
          <div style={{ flex: 2 }}>原因</div>
          <div style={{ flex: 1 }}>操作者</div>
          <div style={{ flex: 2, textAlign: 'right' }}>时间</div>
        </div>
        {loading ? (
          <div style={{ padding: '20px', textAlign: 'center', color: '#999', fontSize: '13px' }}>加载中…</div>
        ) : events.length === 0 ? (
          <div style={{ padding: '20px', textAlign: 'center', color: '#999', fontSize: '13px' }}>暂无封存记录</div>
        ) : (
          events.map(ev => (
            <div key={ev.id} style={{ display: 'flex', alignItems: 'center', padding: '10px', borderTop: '1px solid #f0f0f0', fontSize: '13px' }}>
              <div style={{ flex: 1 }}>{actionLabel(ev.action)}</div>
              <div style={{ flex: 2, color: '#666' }}>{ev.reason || '—'}</div>
              <div style={{ flex: 1, color: '#666' }}>{ev.operator || '—'}</div>
              <div style={{ flex: 2, textAlign: 'right', color: '#999', fontSize: '12px' }}>{ev.created_at}</div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
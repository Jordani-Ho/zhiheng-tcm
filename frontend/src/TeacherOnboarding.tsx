import { useState, useEffect } from 'react'

/**
 * 【D-062 / 内测场景 1】老师入社区面板。
 *
 * 背景：后端 `POST /api/teachers/onboard` 已实现（D-051），但**前端零入口** ——
 * `teachers` 原是 `init_db()` 的种子数据，界面上无法把一位新老师放进社区。
 * 本组件是内测场景 1「老师入社区」的界面入口。
 *
 * 设计取舍：
 * · 独立文件而非写进 App.tsx（App.tsx 已约 4300 行；拆分为 D-058 / D-061 的既定方向）
 * · 组件只负责「入社区 + 列出已有老师」，不接管全站身份切换（那是 App.tsx 的 selectedTeacher）
 * · `onOnboarded` 回调把新老师名交回 App.tsx，由其决定是否切为当前老师
 */

type Teacher = { name: string; description?: string; status?: string }

type Props = {
  /** 入社区成功后回调（App.tsx 用它刷新老师列表 / 可选切换当前身份） */
  onOnboarded?: (teacherName: string) => void
  /** 把某位已有老师设为当前身份 */
  onPickTeacher?: (teacherName: string) => void
  /** 当前身份的老师名（用于高亮） */
  selectedTeacher?: string
}

const boxStyle: React.CSSProperties = {
  background: '#fff',
  border: '1px solid #d4c8a8',
  borderRadius: '12px',
  padding: '20px',
  marginBottom: '20px',
  boxShadow: '0 4px 12px rgba(0,0,0,0.06)',
}

const inputStyle: React.CSSProperties = {
  width: '100%', padding: '8px', borderRadius: '6px',
  border: '1px solid #d4c8a8', fontFamily: 'serif', fontSize: '13px', boxSizing: 'border-box',
}

export default function TeacherOnboarding({ onOnboarded, onPickTeacher, selectedTeacher }: Props) {
  const [teachers, setTeachers] = useState<Teacher[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)

  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const loadTeachers = () => {
    fetch('/api/teachers')
      .then(r => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((d: Teacher[]) => { setTeachers(Array.isArray(d) ? d : []); setLoadError(null) })
      .catch(e => { setTeachers([]); setLoadError(String(e.message || e)) })
  }

  useEffect(() => { loadTeachers() }, [])

  const handleOnboard = () => {
    const trimName = name.trim()
    if (!trimName) { alert('请填写老师姓名'); return }
    setSubmitting(true)
    fetch('/api/teachers/onboard', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      // 阶段一无账号体系：双因子一致性 = name 与 teacher_id 相同（沿后端既有口径）
      body: JSON.stringify({ name: trimName, teacher_id: trimName, description: description.trim() }),
    })
      .then(async r => {
        const body = await r.json().catch(() => ({}))
        if (!r.ok) throw new Error(body?.detail?.msg || body?.detail?.error || `HTTP ${r.status}`)
        return body
      })
      .then((body: any) => {
        const created = body?.teacher_created
        const warnings: string[] = body?.warnings || []
        setName(''); setDescription('')
        loadTeachers()
        onOnboarded?.(trimName)
        alert(
          (created ? `✅ 老师「${trimName}」已入社区` : `ℹ️ 老师「${trimName}」已在社区（幂等，未重复创建）`)
          + (body?.lineage ? `\n师门：${body.lineage.id}` : '')
          + (warnings.length ? `\n\n⚠️ ${warnings.join('\n')}` : '')
        )
      })
      .catch(e => alert(`入社区失败：${e.message || e}`))
      .finally(() => setSubmitting(false))
  }

  return (
    <div style={boxStyle}>
      <div style={{ fontSize: '18px', color: '#8b4513', fontWeight: 'bold', marginBottom: '6px' }}>
        🧑‍⚕️ 老师入社区（{teachers.length}位）
      </div>
      <div style={{ fontSize: '12px', color: '#999', marginBottom: '14px' }}>
        入社区 = 建立该老师的账号与默认师门。幂等：同名重复提交不会重复创建。
      </div>

      {/* ---- 已入社区的老师 ---- */}
      <div style={{ marginBottom: '16px' }}>
        {loadError && (
          <div style={{ fontSize: '12px', color: '#c0392b' }}>老师列表读取失败：{loadError}</div>
        )}
        {!loadError && teachers.length === 0 && (
          <div style={{ fontSize: '12px', color: '#999' }}>暂无老师 —— 请在下方添加第一位。</div>
        )}
        {teachers.map(t => (
          <div key={t.name} style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: '8px 10px', borderTop: '1px solid #f0f0f0', fontSize: '13px',
          }}>
            <div style={{ flex: 1 }}>
              <span style={{ color: '#333', fontWeight: 'bold' }}>👤 {t.name}</span>
              {t.description ? <span style={{ color: '#999', marginLeft: '8px' }}>{t.description}</span> : null}
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              {selectedTeacher === t.name && (
                <span style={{ fontSize: '11px', color: '#5a7d5a', border: '1px solid #5a7d5a', borderRadius: '10px', padding: '1px 8px' }}>
                  当前身份
                </span>
              )}
              {onPickTeacher && selectedTeacher !== t.name && (
                <button
                  onClick={() => onPickTeacher(t.name)}
                  style={{ padding: '3px 12px', borderRadius: '12px', border: '1px solid #8b4513', background: 'transparent', color: '#8b4513', cursor: 'pointer', fontSize: '12px' }}
                >切为当前</button>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* ---- 新增老师 ---- */}
      <div style={{ padding: '12px', background: '#fffaf0', borderRadius: '8px', border: '1px dashed #d4c8a8' }}>
        <div style={{ fontSize: '13px', color: '#8b4513', fontWeight: 'bold', marginBottom: '8px' }}>➕ 添加老师</div>
        <input
          placeholder="老师姓名（必填）"
          value={name}
          onChange={e => setName(e.target.value)}
          style={{ ...inputStyle, marginBottom: '8px' }}
        />
        <input
          placeholder="简介（可选，如：内科 / 民间中医高手）"
          value={description}
          onChange={e => setDescription(e.target.value)}
          style={{ ...inputStyle, marginBottom: '10px' }}
        />
        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <button
            onClick={handleOnboard}
            disabled={submitting}
            style={{
              padding: '6px 20px', borderRadius: '20px', border: 'none',
              background: submitting ? '#bbb' : '#8b4513', color: '#fff',
              cursor: submitting ? 'default' : 'pointer', fontSize: '13px',
            }}
          >{submitting ? '提交中…' : '入社区'}</button>
        </div>
      </div>
    </div>
  )
}

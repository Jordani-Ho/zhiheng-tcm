import { useEffect, useState } from 'react'

interface HuangliData {
  date: string
  lunar: string
  solar_term: string
  health_trend: string
  homework: string
}

interface RoleData {
  id: string
  name: string
  role_type: string
  description: string
}

export default function App() {
  const [huangli, setHuangli] = useState<HuangliData | null>(null)
  const [roles, setRoles] = useState<RoleData[]>([])
  const [activeRole, setActiveRole] = useState<string>('')

  useEffect(() => {
    fetch('/api/huangli').then(r => r.json()).then(d => setHuangli(d))
    fetch('/api/roles').then(r => r.json()).then(d => setRoles(d))
  }, [])

  const boxStyle = { background: '#fdfcf0', border: '1px solid #d4c8a8', borderRadius: '8px', padding: '20px', marginBottom: '15px', boxShadow: '0 2px 4px rgba(0,0,0,0.05)' }

  const roleColors: Record<string, string> = {
    teacher: '#8b4513',
    teacher_agent: '#b8860b',
    patient: '#2e8b57',
    patient_agent: '#4682b4'
  }

  return (
    <div style={{ minHeight: '100vh', background: '#f5f1e6', padding: '20px', fontFamily: 'serif' }}>
      <div style={{ maxWidth: '600px', margin: '0 auto' }}>
        <h1 style={{ textAlign: 'center', color: '#8b4513', borderBottom: '2px solid #8b4513', paddingBottom: '10px' }}>
          知衡 · 中医治未病社区
        </h1>

        {/* 黄历部分 */}
        {huangli && (
          <div style={boxStyle}>
            <div style={{ fontSize: '20px', fontWeight: 'bold' }}>{huangli.date} · {huangli.lunar}</div>
            <div style={{ marginTop: '10px' }}>🌿 {huangli.solar_term}：{huangli.health_trend}</div>
            <div style={{ marginTop: '5px', color: '#666' }}>📝 作业：{huangli.homework}</div>
          </div>
        )}

        {/* 角色切换与展示 */}
        <div style={boxStyle}>
          <div style={{ fontSize: '18px', color: '#8b4513', fontWeight: 'bold', marginBottom: '10px' }}>👥 角色切换</div>
          <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', marginBottom: '15px' }}>
            {roles.map(r => (
              <button
                key={r.id}
                onClick={() => setActiveRole(r.id)}
                style={{
                  padding: '8px 12px',
                  background: activeRole === r.id ? roleColors[r.role_type] : '#eee',
                  color: activeRole === r.id ? '#fff' : '#333',
                  border: 'none', borderRadius: '4px', cursor: 'pointer'
                }}
              >
                {r.name}
              </button>
            ))}
          </div>

          {/* 当前角色详情 */}
          {roles.filter(r => r.id === activeRole).map(r => (
            <div key={r.id} style={{ padding: '15px', background: '#fff8e7', borderRadius: '4px', borderLeft: `4px solid ${roleColors[r.role_type]}` }}>
              <div style={{ fontWeight: 'bold', color: roleColors[r.role_type] }}>{r.name}</div>
              <div style={{ fontSize: '12px', color: '#999', margin: '5px 0' }}>类型：{r.role_type}</div>
              <div>{r.description}</div>
            </div>
          ))}
        </div>

        <div style={{ textAlign: 'center', color: '#999', fontSize: '12px', marginTop: '20px' }}>数据主权归你所有 · 阅后即焚</div>
      </div>
    </div>
  )
}
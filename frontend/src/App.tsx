import { useEffect, useState } from 'react'

interface HuangliData {
  date: string
  lunar: string
  solar_term: string
  health_trend: string
  homework: string
}

interface RoleData {
  title: string
  content: string
  color: string
}

export default function App() {
  const [huangli, setHuangli] = useState<HuangliData | null>(null)
  const [roles, setRoles] = useState<any[]>([])
  const [activeRole, setActiveRole] = useState<string>('patient_zhang')
  const [roleData, setRoleData] = useState<RoleData | null>(null)

  useEffect(() => {
    fetch('/api/huangli').then(r => r.json()).then(d => setHuangli(d))
    fetch('/api/roles').then(r => r.json()).then(d => setRoles(d))
  }, [])

  useEffect(() => {
    if (activeRole) {
      fetch(`/api/role/${activeRole}`).then(r => r.json()).then(d => setRoleData(d))
    }
  }, [activeRole])

  const boxStyle = {
    background: '#fdfcf0',
    border: '1px solid #d4c8a8',
    borderRadius: '8px',
    padding: '20px',
    marginBottom: '15px',
    boxShadow: '0 2px 4px rgba(0,0,0,0.05)'
  }

  return (
    <div style={{ minHeight: '100vh', background: '#f5f1e6', padding: '20px', fontFamily: 'serif' }}>
      <div style={{ maxWidth: '500px', margin: '0 auto' }}>
        <h1 style={{ textAlign: 'center', color: '#8b4513', borderBottom: '2px solid #8b4513', paddingBottom: '10px' }}>
          知衡 · 中医治未病社区
        </h1>
        
        {huangli && (
          <div style={boxStyle}>
            <div style={{ fontSize: '18px', fontWeight: 'bold', color: '#333' }}>{huangli.date} · {huangli.lunar}</div>
            <div style={{ marginTop: '8px', color: '#8b4513' }}>🌿 {huangli.solar_term}：{huangli.health_trend}</div>
            <div style={{ marginTop: '8px', color: '#333' }}>📝 作业：{huangli.homework}</div>
          </div>
        )}

        <div style={boxStyle}>
          <div style={{ fontSize: '18px', color: '#8b4513', fontWeight: 'bold', marginBottom: '10px' }}>👥 角色切换</div>
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            {roles.map((r) => (
              <button
                key={r.id}
                onClick={() => setActiveRole(r.id)}
                style={{
                  padding: '6px 12px',
                  background: activeRole === r.id ? '#8b4513' : '#eee',
                  color: activeRole === r.id ? '#fff' : '#333',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: 'pointer'
                }}
              >
                {r.name}
              </button>
            ))}
          </div>
        </div>

        {roleData && (
          <div style={{ ...boxStyle, background: roleData.color }}>
            <div style={{ fontSize: '18px', fontWeight: 'bold', color: '#8b4513' }}>{roleData.title}</div>
            <div style={{ marginTop: '10px', lineHeight: '1.6' }}>{roleData.content}</div>
          </div>
        )}

        <div style={{ textAlign: 'center', color: '#999', fontSize: '12px', marginTop: '20px' }}>
          数据主权归你所有 · 阅后即焚
        </div>
      </div>
    </div>
  )
}

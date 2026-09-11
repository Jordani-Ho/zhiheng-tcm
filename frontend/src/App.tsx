import { useEffect, useState } from 'react'

interface RoleData {
  role_name: string
  role_type: string
  view_title: string
  view_content: string
  can_check_in: boolean
  privacy_notice: string
}

export default function App() {
  const [data, setData] = useState<any>(null)
  const [currentRole, setCurrentRole] = useState('patient_zhangsan')
  const [roleData, setRoleData] = useState<RoleData | null>(null)

  // 获取黄历数据
  useEffect(() => {
    fetch('/api/huangli')
      .then(r => r.json())
      .then(d => setData(d))
      .catch(() => setData(null))
  }, [])

  // 切换角色时，获取对应角色的数据
  useEffect(() => {
    fetch(`/api/role/${currentRole}`)
      .then(r => r.json())
      .then(d => setRoleData(d))
      .catch(() => setRoleData(null))
  }, [currentRole])

  const boxStyle = {
    background: '#fdfcf0',
    border: '1px solid #d4c8a8',
    borderRadius: '12px',
    padding: '24px',
    marginBottom: '20px',
    boxShadow: '0 4px 12px rgba(0,0,0,0.06)'
  }

  const roleBtnStyle = (roleKey: string) => ({
    padding: '8px 16px',
    margin: '5px',
    borderRadius: '20px',
    border: '1px solid #8b4513',
    cursor: 'pointer',
    fontFamily: 'serif',
    fontSize: '14px',
    backgroundColor: currentRole === roleKey ? '#8b4513' : '#fdfcf0',
    color: currentRole === roleKey ? '#fff' : '#8b4513',
    transition: 'all 0.2s'
  })

  const roles = [
    { key: 'teacher_li', name: '李老师' },
    { key: 'teacher_agent', name: '李老师智能体' },
    { key: 'patient_zhangsan', name: '患者张三' },
    { key: 'patient_agent', name: '张三智能体' },
  ]

  return (
    <div style={{ minHeight: '100vh', background: '#f5f1e6', padding: '40px 20px', fontFamily: 'serif' }}>
      <div style={{ maxWidth: '600px', margin: '0 auto' }}>
        
        <h1 style={{ textAlign: 'center', color: '#8b4513', borderBottom: '2px solid #d4c8a8', paddingBottom: '15px', marginBottom: '30px', fontSize: '28px', letterSpacing: '2px' }}>
          知衡 · 中医治未病社区
        </h1>
        
        {/* 黄历卡片 */}
        {data && (
          <div style={boxStyle}>
            <div style={{ textAlign: 'center', fontSize: '18px', color: '#333', marginBottom: '15px' }}>
              <span style={{ fontWeight: 'bold' }}>{data.date}</span> · {data.lunar}
            </div>
            <div style={{ textAlign: 'center', color: '#5a7d5a', fontSize: '16px', marginBottom: '10px' }}>
              🌿 {data.solar_term}：{data.health_trend}
            </div>
            <div style={{ textAlign: 'center', background: '#fff8e7', padding: '15px', borderRadius: '8px', color: '#8b4513' }}>
              📝 今日作业：{data.homework}
            </div>
          </div>
        )}

        {/* 角色切换区 */}
        <div style={boxStyle}>
          <div style={{ textAlign: 'center', marginBottom: '15px', color: '#8b4513', fontWeight: 'bold' }}>
            🧑‍⚕️ 角色切换
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'center' }}>
            {roles.map((role) => (
              <button 
                key={role.key} 
                style={roleBtnStyle(role.key)} 
                onClick={() => setCurrentRole(role.key)}
              >
                {role.name}
              </button>
            ))}
          </div>
        </div>

        {/* 角色专属数据区 */}
        {roleData && (
          <div style={{ ...boxStyle, background: roleData.role_type.includes('teacher') ? '#e8f0e8' : '#fdfcf0' }}>
            <div style={{ textAlign: 'center', fontSize: '18px', color: '#8b4513', marginBottom: '10px' }}>
              {roleData.view_title}
            </div>
            <div style={{ textAlign: 'center', color: '#555', lineHeight: '1.8' }}>
              {roleData.view_content}
            </div>
            {roleData.can_check_in && (
              <div style={{ textAlign: 'center', marginTop: '20px' }}>
                <button style={{ padding: '10px 24px', borderRadius: '30px', border: 'none', background: '#8b4513', color: '#fff', fontSize: '16px', cursor: 'pointer', fontFamily: 'serif' }}>
                  立即打卡
                </button>
              </div>
            )}
          </div>
        )}

        {/* 底部隐私提示 */}
        <div style={{ textAlign: 'center', marginTop: '30px', padding: '12px', borderTop: '1px dashed #d4c8a8', color: '#8b4513', fontSize: '14px', fontWeight: 'bold' }}>
          {roleData?.privacy_notice || '🔒 数据主权归你所有 · 阅后即焚'}
        </div>
      </div>
    </div>
  )
}
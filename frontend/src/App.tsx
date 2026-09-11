import { useEffect, useState } from 'react'

interface HuangliData {
  date: string
  lunar: string
  solar_term: string
  health_trend: string
  homework: string
}

export default function App() {
  const [data, setData] = useState<HuangliData | null>(null)
  const [currentRole, setCurrentRole] = useState('患者张三')

  useEffect(() => {
    fetch('/api/huangli')
      .then(r => r.json())
      .then(d => setData(d))
      .catch(() => setData(null))
  }, [])

  const boxStyle = {
    background: '#fdfcf0',
    border: '1px solid #d4c8a8',
    borderRadius: '12px',
    padding: '24px',
    marginBottom: '20px',
    boxShadow: '0 4px 12px rgba(0,0,0,0.06)'
  }

  const roleBtnStyle = (role: string) => ({
    padding: '8px 16px',
    margin: '5px',
    borderRadius: '20px',
    border: '1px solid #8b4513',
    cursor: 'pointer',
    fontFamily: 'serif',
    fontSize: '14px',
    backgroundColor: currentRole === role ? '#8b4513' : '#fdfcf0',
    color: currentRole === role ? '#fff' : '#8b4513',
    transition: 'all 0.2s'
  })

  return (
    <div style={{ minHeight: '100vh', background: '#f5f1e6', padding: '40px 20px', fontFamily: 'serif' }}>
      <div style={{ maxWidth: '600px', margin: '0 auto' }}>
        
        <h1 style={{ textAlign: 'center', color: '#8b4513', borderBottom: '2px solid #d4c8a8', paddingBottom: '15px', marginBottom: '30px', fontSize: '28px', letterSpacing: '2px' }}>
          知衡 · 中医治未病社区
        </h1>
        
        {!data ? (
          <div style={{ textAlign: 'center', padding: '50px', color: '#8b4513' }}>正在推算黄历数据...</div>
        ) : (
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

        <div style={boxStyle}>
          <div style={{ textAlign: 'center', marginBottom: '15px', color: '#8b4513', fontWeight: 'bold' }}>
            🧑‍⚕️ 角色切换
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'center' }}>
            {['李老师', '李老师智能体', '患者张三', '张三智能体'].map((role) => (
              <button 
                key={role} 
                style={roleBtnStyle(role)} 
                onClick={() => setCurrentRole(role)}
              >
                {role}
              </button>
            ))}
          </div>
        </div>

        <div style={{ ...boxStyle, background: currentRole.includes('老师') ? '#e8f0e8' : '#fdfcf0' }}>
          <div style={{ textAlign: 'center', fontSize: '18px', color: '#8b4513', marginBottom: '10px' }}>
            {currentRole.includes('老师') ? '📋 患者作业审核' : '📝 我的作业'}
          </div>
          <div style={{ textAlign: 'center', color: '#555', lineHeight: '1.8' }}>
            {currentRole.includes('老师') 
              ? '张三：已完成白露节气穴位按摩，等待老师签字确认。' 
              : '今日作业：按揉太渊穴5分钟。请记得在酉时完成。'}
          </div>
          {!currentRole.includes('老师') && (
            <div style={{ textAlign: 'center', marginTop: '20px' }}>
              <button style={{ padding: '10px 24px', borderRadius: '30px', border: 'none', background: '#8b4513', color: '#fff', fontSize: '16px', cursor: 'pointer', fontFamily: 'serif' }}>
                立即打卡
              </button>
            </div>
          )}
        </div>

        {/* 这里是改版后的“阅后即焚”提示条 */}
        <div style={{ textAlign: 'center', marginTop: '30px', padding: '12px', borderTop: '1px dashed #d4c8a8', color: '#8b4513', fontSize: '14px', fontWeight: 'bold' }}>
          🔒 数据主权归你所有 · 阅后即焚
        </div>
      </div>
    </div>
  )
}
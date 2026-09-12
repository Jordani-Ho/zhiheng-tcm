import { useEffect, useState } from 'react'

interface HuangliData {
  date: string
  lunar: string
  solar_term: string
  health_trend: string
  homework: string
}

interface RoleData {
  role_type: string
  name: string
  task: string
  detail: string
}

export default function App() {
  const [huangli, setHuangli] = useState<HuangliData | null>(null)
  const [currentRole, setCurrentRole] = useState('患者张三')
  const [roleData, setRoleData] = useState<RoleData | null>(null)

  // 获取黄历
  useEffect(() => {
    fetch('/api/huangli')
      .then(r => r.json())
      .then(d => setHuangli(d))
      .catch(() => setHuangli(null))
  }, [])

  // 获取角色数据（角色切换时重新获取）
  const fetchRoleData = () => {
    fetch(`/api/role-data?role=${currentRole}`)
      .then(r => r.json())
      .then(d => setRoleData(d))
      .catch(() => setRoleData(null))
  }

  useEffect(() => {
    fetchRoleData()
  }, [currentRole])

  // 患者打卡动作
  const handleCheckIn = () => {
    fetch('/api/check-in', { method: 'POST' })
      .then(() => fetchRoleData()) // 打卡后刷新数据
  }

  // 老师审核动作
  const handleApprove = () => {
    fetch('/api/approve', { method: 'POST' })
      .then(() => fetchRoleData()) // 审核后刷新数据
  }

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
        
        {!huangli ? (
          <div style={{ textAlign: 'center', padding: '50px', color: '#8b4513' }}>正在推算黄历数据...</div>
        ) : (
          <div style={boxStyle}>
            <div style={{ textAlign: 'center', fontSize: '18px', color: '#333', marginBottom: '15px' }}>
              <span style={{ fontWeight: 'bold' }}>{huangli.date}</span> · {huangli.lunar}
            </div>
            <div style={{ textAlign: 'center', color: '#5a7d5a', fontSize: '16px', marginBottom: '10px' }}>
              🌿 {huangli.solar_term}：{huangli.health_trend}
            </div>
            <div style={{ textAlign: 'center', background: '#fff8e7', padding: '15px', borderRadius: '8px', color: '#8b4513' }}>
              📝 今日作业：{huangli.homework}
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
            {roleData ? `📋 ${roleData.name} 的任务` : '加载中...'}
          </div>
          <div style={{ textAlign: 'center', color: '#555', lineHeight: '1.8' }}>
            {roleData ? roleData.detail : '正在获取数据...'}
          </div>
          
          {/* 患者打卡按钮 */}
          {currentRole === '患者张三' && roleData?.detail.includes('请记得') && (
            <div style={{ textAlign: 'center', marginTop: '20px' }}>
              <button 
                onClick={handleCheckIn}
                style={{ padding: '10px 24px', borderRadius: '30px', border: 'none', background: '#8b4513', color: '#fff', fontSize: '16px', cursor: 'pointer', fontFamily: 'serif' }}>
                立即打卡
              </button>
            </div>
          )}

          {/* 老师签字按钮 */}
          {currentRole === '李老师' && roleData?.task === '待审核' && roleData?.detail.includes('已打卡') && (
            <div style={{ textAlign: 'center', marginTop: '20px' }}>
              <button 
                onClick={handleApprove}
                style={{ padding: '10px 24px', borderRadius: '30px', border: 'none', background: '#5a7d5a', color: '#fff', fontSize: '16px', cursor: 'pointer', fontFamily: 'serif' }}>
                签字确认
              </button>
            </div>
          )}
        </div>

      </div>
    </div>
  )
}
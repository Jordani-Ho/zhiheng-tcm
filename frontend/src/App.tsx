import { useEffect, useState } from 'react'

interface UserState {
  points: number
  today_checked: boolean
  checkin_time: string
}

export default function App() {
  const [user, setUser] = useState<UserState | null>(null)
  const [msg, setMsg] = useState('')

  const fetchUser = () => {
    fetch('/api/user/status')
      .then(r => r.json())
      .then(d => setUser(d))
  }

  useEffect(() => {
    fetchUser()
  }, [])

  const handleCheckin = () => {
    fetch('/api/user/checkin', { method: 'POST' })
      .then(r => r.json())
      .then(d => {
        setMsg(d.message)
        fetchUser() // 刷新积分
      })
  }

  const boxStyle = {
    background: '#fdfcf0',
    border: '1px solid #d4c8a8',
    borderRadius: '12px',
    padding: '24px',
    marginBottom: '20px',
    boxShadow: '0 4px 12px rgba(0,0,0,0.06)'
  }

  return (
    <div style={{ minHeight: '100vh', background: '#f5f1e6', padding: '40px 20px', fontFamily: 'serif' }}>
      <div style={{ maxWidth: '600px', margin: '0 auto' }}>
        
        <h1 style={{ textAlign: 'center', color: '#8b4513', borderBottom: '2px solid #d4c8a8', paddingBottom: '15px', marginBottom: '30px', fontSize: '28px' }}>
          知衡 · 治未病打卡台
        </h1>

        {/* 积分展示 */}
        <div style={{ ...boxStyle, textAlign: 'center' }}>
          <div style={{ fontSize: '18px', color: '#8b4513' }}>我的积分</div>
          <div style={{ fontSize: '36px', fontWeight: 'bold', color: '#5a7d5a', margin: '10px 0' }}>
            {user?.points ?? '...'} <span style={{ fontSize: '16px', color: '#999' }}>分</span>
          </div>
          <div style={{ fontSize: '14px', color: '#666' }}>
            （积分可用于支付学费）
          </div>
        </div>

        {/* 打卡作业区 */}
        <div style={boxStyle}>
          <div style={{ textAlign: 'center', fontSize: '18px', color: '#8b4513', marginBottom: '15px' }}>
            📝 今日作业
          </div>
          <div style={{ textAlign: 'center', background: '#fff8e7', padding: '15px', borderRadius: '8px', color: '#8b4513', marginBottom: '20px' }}>
            今日酉时（17-19点）按揉太渊穴5分钟
          </div>
          <div style={{ textAlign: 'center' }}>
            <button 
              onClick={handleCheckin}
              disabled={user?.today_checked}
              style={{ 
                padding: '12px 32px', 
                borderRadius: '30px', 
                border: 'none', 
                background: user?.today_checked ? '#ccc' : '#8b4513', 
                color: '#fff', 
                fontSize: '16px', 
                cursor: user?.today_checked ? 'not-allowed' : 'pointer',
                fontFamily: 'serif'
              }}
            >
              {user?.today_checked ? '✅ 今日已打卡' : '立即打卡'}
            </button>
          </div>
          {msg && <div style={{ textAlign: 'center', color: '#5a7d5a', marginTop: '15px' }}>{msg}</div>}
        </div>

        <div style={{ textAlign: 'center', marginTop: '20px', padding: '10px', borderTop: '1px dashed #d4c8a8', color: '#8b4513', fontSize: '13px', fontWeight: 'bold' }}>
          🔒 数据主权归你所有 · 阅后即焚
        </div>
      </div>
    </div>
  )
}
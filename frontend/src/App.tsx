import { useState, useEffect } from 'react'

export default function App() {
  const [role, setRole] = useState<string | null>(null)
  const [name, setName] = useState<string | null>(null)
  const [inviteCode, setInviteCode] = useState('')
  const [loginMsg, setLoginMsg] = useState('')

  // 页面加载时，检查本地是否已有登录状态
  useEffect(() => {
    const savedRole = localStorage.getItem('zhiheng_role')
    const savedName = localStorage.getItem('zhiheng_name')
    if (savedRole) {
      setRole(savedRole)
      setName(savedName)
    }
  }, [])

  // 登录逻辑
  const handleLogin = () => {
    if (!inviteCode.trim()) return setLoginMsg('请输入邀请码')
    fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code: inviteCode })
    })
      .then(r => r.json())
      .then(d => {
        if (d.error) {
          setLoginMsg(d.error)
        } else {
          setRole(d.role)
          setName(d.name)
          localStorage.setItem('zhiheng_role', d.role)
          localStorage.setItem('zhiheng_name', d.name)
          setLoginMsg('')
        }
      })
  }

  // 退出登录
  const handleLogout = () => {
    localStorage.clear()
    setRole(null)
    setName(null)
    setInviteCode('')
    setLoginMsg('')
  }

  const boxStyle = {
    background: '#fdfcf0',
    border: '1px solid #d4c8a8',
    borderRadius: '12px',
    padding: '24px',
    marginBottom: '20px',
    boxShadow: '0 4px 12px rgba(0,0,0,0.06)'
  }

  // -------------- 页面 1：登录门禁 ----------------
  if (!role) {
    return (
      <div style={{ minHeight: '100vh', background: '#f5f1e6', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'serif', padding: '20px' }}>
        <div style={{ ...boxStyle, maxWidth: '400px', width: '100%', textAlign: 'center' }}>
          <h1 style={{ color: '#8b4513', fontSize: '24px', marginBottom: '10px' }}>知衡 · 治未病社区</h1>
          <p style={{ color: '#666', fontSize: '14px', marginBottom: '20px' }}>封闭式邀请制 · 请凭邀请码进入</p>
          
          <input 
            type="text" 
            placeholder="请输入邀请码（老师: TEACHER888 / 患者: PATIENT666）"
            value={inviteCode}
            onChange={(e) => setInviteCode(e.target.value)}
            style={{ width: '100%', padding: '12px', boxSizing: 'border-box', borderRadius: '8px', border: '1px solid #d4c8a8', marginBottom: '15px', fontFamily: 'serif', textAlign: 'center' }}
          />
          
          <button 
            onClick={handleLogin}
            style={{ width: '100%', padding: '12px', borderRadius: '30px', border: 'none', background: '#8b4513', color: '#fff', fontSize: '16px', cursor: 'pointer', fontFamily: 'serif' }}
          >
            进入社区
          </button>
          
          {loginMsg && <div style={{ color: '#c0392b', marginTop: '15px', fontSize: '14px' }}>{loginMsg}</div>}
        </div>
      </div>
    )
  }

  // -------------- 页面 2：已登录工作台 ----------------
  return (
    <div style={{ minHeight: '100vh', background: '#f5f1e6', padding: '30px 20px', fontFamily: 'serif' }}>
      <div style={{ maxWidth: '600px', margin: '0 auto' }}>
        
        {/* 头部欢迎栏 */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', borderBottom: '2px solid #d4c8a8', paddingBottom: '10px' }}>
          <div style={{ color: '#8b4513', fontSize: '20px', fontWeight: 'bold' }}>
            {role === 'teacher' ? '👨‍⚕️ 老师工作台' : '🧑‍🦱 患者端'}
          </div>
          <div style={{ fontSize: '14px', color: '#666' }}>
            欢迎，{name} | <span onClick={handleLogout} style={{ color: '#8b4513', cursor: 'pointer', textDecoration: 'underline' }}>退出</span>
          </div>
        </div>

        {/* 演示：根据角色显示不同的卡片 */}
        {role === 'patient' ? (
          <div style={boxStyle}>
            <div style={{ color: '#8b4513', fontWeight: 'bold', marginBottom: '10px' }}>📝 今日作业</div>
            <div style={{ textAlign: 'center', background: '#fff8e7', padding: '15px', borderRadius: '8px', color: '#8b4513', marginBottom: '15px' }}>
              今日酉时（17-19点）按揉太渊穴5分钟
            </div>
            <div style={{ textAlign: 'center' }}>
              <button style={{ padding: '10px 24px', borderRadius: '30px', border: 'none', background: '#8b4513', color: '#fff', cursor: 'pointer' }}>立即打卡</button>
            </div>
          </div>
        ) : (
          <div style={boxStyle}>
            <div style={{ color: '#8b4513', fontWeight: 'bold', marginBottom: '10px' }}>📋 患者作业审核</div>
            <div style={{ color: '#555', marginBottom: '15px' }}>张三：已完成白露节气穴位按摩，等待老师签字确认。</div>
            <button style={{ padding: '8px 16px', borderRadius: '20px', border: 'none', background: '#8b4513', color: '#fff', cursor: 'pointer' }}>审核并签字</button>
          </div>
        )}

        <div style={{ textAlign: 'center', marginTop: '20px', padding: '10px', borderTop: '1px dashed #d4c8a8', color: '#8b4513', fontSize: '13px', fontWeight: 'bold' }}>
          🔒 数据主权归患者 · 老师端阅后即焚
        </div>
      </div>
    </div>
  )
}
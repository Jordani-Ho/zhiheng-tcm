import { useState, useEffect } from 'react'

export default function App() {
  const [role, setRole] = useState<string | null>(null)
  const [name, setName] = useState<string | null>(null)
  const [inviteCode, setInviteCode] = useState('')
  const [loginMsg, setLoginMsg] = useState('')
  
  // 核心数据：病历
  const [patientData, setPatientData] = useState('')
  const [aiDraft, setAiDraft] = useState('')
  const [actionMsg, setActionMsg] = useState('')

  // 登录状态初始化
  useEffect(() => {
    const savedRole = localStorage.getItem('zhiheng_role')
    const savedName = localStorage.getItem('zhiheng_name')
    if (savedRole) {
      setRole(savedRole)
      setName(savedName)
    }
  }, [])

  // 登录
  const handleLogin = () => {
    if (!inviteCode.trim()) return setLoginMsg('请输入邀请码')
    fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code: inviteCode })
    })
      .then(r => r.json())
      .then(d => {
        if (d.error) setLoginMsg(d.error)
        else {
          setRole(d.role); setName(d.name)
          localStorage.setItem('zhiheng_role', d.role)
          localStorage.setItem('zhiheng_name', d.name)
          setLoginMsg('')
        }
      })
  }

  // 退出
    // 退出
  const handleLogout = () => {
    // 只清除身份信息，保留本地病历数据，方便演示角色切换
    localStorage.removeItem('zhiheng_role')
    localStorage.removeItem('zhiheng_name')
    // 注意：这里绝对不要写 localStorage.clear()，不然数据全没了

    setRole(null); setName(null); setInviteCode(''); setActionMsg('')
    
    // 重新加载页面，保证状态干净切换
    window.location.reload()
  }

  // 患者提交病历（存入本地 localStorage）
  const handlePatientSubmit = () => {
    if (!patientData.trim()) return setActionMsg('请输入病历内容')
    localStorage.setItem('zhiheng_record', patientData) // 真实数据存在患者本地！
    setActionMsg('病历已安全存入本地，并发送给老师智能体')
    // 模拟通知老师智能体
    fetch('/api/agent/teacher/draft', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ raw_data: patientData })
    }).then(r => r.json()).then(d => {
      if (d.draft) {
        localStorage.setItem('zhiheng_draft', d.draft)
        setAiDraft(d.draft)
      }
    })
  }

  // 老师阅后即焚（清空本地存储）
  const handleBurn = () => {
    localStorage.removeItem('zhiheng_record')
    localStorage.removeItem('zhiheng_draft')
    setPatientData('')
    setAiDraft('')
    setActionMsg('🔥 病历已阅后即焚，本地数据已物理清除')
  }

  const boxStyle = {
    background: '#fdfcf0',
    border: '1px solid #d4c8a8',
    borderRadius: '12px',
    padding: '24px',
    marginBottom: '20px',
    boxShadow: '0 4px 12px rgba(0,0,0,0.06)'
  }

  // -------------- 登录门禁 ----------------
  if (!role) {
    return (
      <div style={{ minHeight: '100vh', background: '#f5f1e6', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'serif', padding: '20px' }}>
        <div style={{ ...boxStyle, maxWidth: '400px', width: '100%', textAlign: 'center' }}>
          <h1 style={{ color: '#8b4513', fontSize: '24px' }}>知衡 · 治未病社区</h1>
          <p style={{ color: '#666', fontSize: '14px', marginBottom: '20px' }}>封闭式邀请制 · 请凭邀请码进入</p>
          <input 
            type="text" placeholder="邀请码（老师: TEACHER888 / 患者: PATIENT666）"
            value={inviteCode} onChange={(e) => setInviteCode(e.target.value)}
            style={{ width: '100%', padding: '12px', boxSizing: 'border-box', borderRadius: '8px', border: '1px solid #d4c8a8', marginBottom: '15px', fontFamily: 'serif', textAlign: 'center' }}
          />
          <button onClick={handleLogin} style={{ width: '100%', padding: '12px', borderRadius: '30px', border: 'none', background: '#8b4513', color: '#fff', fontSize: '16px', cursor: 'pointer' }}>进入社区</button>
          {loginMsg && <div style={{ color: '#c0392b', marginTop: '15px', fontSize: '14px' }}>{loginMsg}</div>}
        </div>
      </div>
    )
  }

  // -------------- 工作台 ----------------
  return (
    <div style={{ minHeight: '100vh', background: '#f5f1e6', padding: '30px 20px', fontFamily: 'serif' }}>
      <div style={{ maxWidth: '600px', margin: '0 auto' }}>
        
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '20px', borderBottom: '2px solid #d4c8a8', paddingBottom: '10px' }}>
          <div style={{ color: '#8b4513', fontSize: '20px', fontWeight: 'bold' }}>{role === 'teacher' ? '👨‍⚕️ 老师工作台' : '🧑‍🦱 患者端'}</div>
          <div style={{ fontSize: '14px', color: '#666' }}>欢迎，{name} | <span onClick={handleLogout} style={{ color: '#8b4513', cursor: 'pointer', textDecoration: 'underline' }}>退出</span></div>
        </div>

        {role === 'patient' ? (
          <div style={boxStyle}>
            <div style={{ color: '#8b4513', fontWeight: 'bold', marginBottom: '10px' }}>📝 我的病历（数据存在本机）</div>
            <textarea 
              value={patientData} onChange={(e) => setPatientData(e.target.value)}
              placeholder="例如：今日舌苔偏白，脉细，畏寒..."
              style={{ width: '100%', height: '80px', padding: '10px', boxSizing: 'border-box', borderRadius: '8px', border: '1px solid #d4c8a8', marginBottom: '10px', fontFamily: 'serif' }}
            />
            <button onClick={handlePatientSubmit} style={{ padding: '8px 16px', borderRadius: '20px', border: 'none', background: '#8b4513', color: '#fff', cursor: 'pointer' }}>提交给老师智能体</button>
          </div>
        ) : (
          <div style={boxStyle}>
            <div style={{ color: '#8b4513', fontWeight: 'bold', marginBottom: '10px' }}>👨‍⚕️ 老师端（阅后即焚）</div>
            <div style={{ color: '#333', padding: '10px', background: '#fff', borderRadius: '8px', minHeight: '40px', marginBottom: '10px' }}>
              患者病历（临时显示，阅后即焚）：{localStorage.getItem('zhiheng_record') || '暂无'}
            </div>
            {localStorage.getItem('zhiheng_draft') && (
              <div style={{ color: '#5a7d5a', padding: '10px', background: '#e8f0e8', borderRadius: '8px', marginBottom: '10px' }}>
                🤖 智能体草案：{localStorage.getItem('zhiheng_draft')}
              </div>
            )}
            <button onClick={handleBurn} disabled={!localStorage.getItem('zhiheng_record')} style={{ padding: '8px 16px', borderRadius: '20px', border: '1px solid #8b4513', background: '#fdfcf0', color: '#8b4513', cursor: 'pointer' }}>🔥 一键阅后即焚</button>
          </div>
        )}

        {actionMsg && <div style={{ textAlign: 'center', color: '#5a7d5a', marginTop: '15px', fontWeight: 'bold' }}>{actionMsg}</div>}
        <div style={{ textAlign: 'center', marginTop: '20px', padding: '10px', borderTop: '1px dashed #d4c8a8', color: '#8b4513', fontSize: '13px', fontWeight: 'bold' }}>🔒 数据主权归患者 · 老师端阅后即焚</div>
      </div>
    </div>
  )
}
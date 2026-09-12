import { useEffect, useState } from 'react'

export default function App() {
  const [role, setRole] = useState<string | null>(null)
  const [name, setName] = useState<string | null>(null)
  const [inviteCode, setInviteCode] = useState('')
  const [loginMsg, setLoginMsg] = useState('')
  
  const [state, setState] = useState<any>(null)
  const [inputVal, setInputVal] = useState('')
  const [actionMsg, setActionMsg] = useState('')

  const fetchStatus = () => {
    fetch('/api/status').then(r => r.json()).then(d => setState(d))
  }

  useEffect(() => {
    const savedRole = localStorage.getItem('zhiheng_role')
    const savedName = localStorage.getItem('zhiheng_name')
    if (savedRole) { setRole(savedRole); setName(savedName) }
    fetchStatus()
    const interval = setInterval(fetchStatus, 3000)
    return () => clearInterval(interval)
  }, [])

  const handleLogin = () => {
    if (!inviteCode.trim()) return setLoginMsg('请输入邀请码')
    fetch('/api/auth/login', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code: inviteCode })
    }).then(r => r.json()).then(d => {
      if (d.error) setLoginMsg(d.error)
      else {
        setRole(d.role); setName(d.name)
        localStorage.setItem('zhiheng_role', d.role)
        localStorage.setItem('zhiheng_name', d.name)
        setLoginMsg('')
      }
    })
  }

  const handleLogout = () => {
    localStorage.removeItem('zhiheng_role'); localStorage.removeItem('zhiheng_name')
    window.location.reload()
  }

  // 患者动作
  const handleCollect = () => {
    if (!inputVal.trim()) return setActionMsg('请输入健康数据')
    fetch('/api/patient/collect', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ data: inputVal })
    }).then(r => r.json()).then(d => { setState(d); setActionMsg('患者智能体采集完成，已上报'); })
  }

  // 老师动作
  const handleGenerate = () => {
    fetch('/api/teacher/generate', { method: 'POST' }).then(r => r.json()).then(d => { setState(d); setActionMsg('老师智能体已生成草案'); })
  }
  const handleSign = () => {
    fetch('/api/teacher/sign', { method: 'POST' }).then(r => r.json()).then(d => { setState(d); setActionMsg('老师已签字生效！'); })
  }

  // 阅后即焚
  const handleBurn = () => {
    fetch('/api/burn', { method: 'POST' }).then(r => r.json()).then(d => { setState(d); setActionMsg('🔥 病历已物理清除'); })
  }

  const boxStyle = { background: '#fdfcf0', border: '1px solid #d4c8a8', borderRadius: '12px', padding: '20px', marginBottom: '15px', boxShadow: '0 4px 12px rgba(0,0,0,0.06)' }

  if (!role) {
    return (
      <div style={{ minHeight: '100vh', background: '#f5f1e6', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'serif', padding: '20px' }}>
        <div style={{ ...boxStyle, maxWidth: '400px', width: '100%', textAlign: 'center' }}>
          <h1 style={{ color: '#8b4513' }}>知衡 · 治未病社区</h1>
          <input type="text" placeholder="邀请码（老师: TEACHER888 / 患者: PATIENT666）" value={inviteCode} onChange={e => setInviteCode(e.target.value)} style={{ width: '100%', padding: '12px', boxSizing: 'border-box', borderRadius: '8px', border: '1px solid #d4c8a8', marginBottom: '15px', fontFamily: 'serif', textAlign: 'center' }} />
          <button onClick={handleLogin} style={{ width: '100%', padding: '12px', borderRadius: '30px', border: 'none', background: '#8b4513', color: '#fff', cursor: 'pointer' }}>进入社区</button>
          {loginMsg && <div style={{ color: '#c0392b', marginTop: '15px' }}>{loginMsg}</div>}
        </div>
      </div>
    )
  }

  return (
    <div style={{ minHeight: '100vh', background: '#f5f1e6', padding: '30px 20px', fontFamily: 'serif' }}>
      <div style={{ maxWidth: '600px', margin: '0 auto' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '20px', borderBottom: '2px solid #d4c8a8', paddingBottom: '10px' }}>
          <div style={{ color: '#8b4513', fontSize: '20px', fontWeight: 'bold' }}>{role === 'teacher' ? '👨‍⚕️ 老师工作台' : '🧑‍🦱 患者端'}</div>
          <div style={{ fontSize: '14px', color: '#666' }}>欢迎，{name} | <span onClick={handleLogout} style={{ color: '#8b4513', cursor: 'pointer', textDecoration: 'underline' }}>退出</span></div>
        </div>

        {/* 状态栏 */}
        <div style={boxStyle}>
          <div style={{ color: '#8b4513', fontWeight: 'bold' }}>📡 流转状态：<span style={{ color: '#5a7d5a' }}>{state?.status || '加载中...'}</span></div>
          {state?.current_shi && <div style={{ fontSize: '14px', color: '#666', marginTop: '5px' }}>当前时辰：{state.current_shi}</div>}
        </div>

        {role === 'patient' ? (
          <div style={boxStyle}>
            <div style={{ color: '#8b4513', fontWeight: 'bold', marginBottom: '10px' }}>🧑‍🦱 患者智能体（仅采集上报）</div>
            {state?.is_signed && state?.signed_content ? (
              <div style={{ padding: '10px', background: '#e8f0e8', borderRadius: '8px', color: '#333', marginBottom: '15px' }}>
                ✅ 老师已签字反馈：{state.signed_content}
              </div>
            ) : null}
            <textarea value={inputVal} onChange={e => setInputVal(e.target.value)} placeholder="例如：今日苔白，畏寒..." style={{ width: '100%', height: '80px', padding: '10px', boxSizing: 'border-box', borderRadius: '8px', border: '1px solid #d4c8a8', marginBottom: '10px', fontFamily: 'serif' }} />
            <button onClick={handleCollect} style={{ padding: '8px 16px', borderRadius: '20px', border: 'none', background: '#8b4513', color: '#fff', cursor: 'pointer' }}>采集并上报</button>
          </div>
        ) : (
          <div style={boxStyle}>
            <div style={{ color: '#8b4513', fontWeight: 'bold', marginBottom: '10px' }}>👨‍⚕️ 老师端（审核签字）</div>
            {state?.patient_data && <div style={{ color: '#333', marginBottom: '10px' }}>患者数据：{state.patient_data}</div>}
            {state?.ai_draft && (
              <div style={{ padding: '10px', background: '#fdfcf0', border: '1px dashed #d4c8a8', borderRadius: '8px', marginBottom: '10px', whiteSpace: 'pre-wrap' }}>
                🤖 智能体草案：{state.ai_draft}
              </div>
            )}
            <div style={{ display: 'flex', gap: '10px' }}>
              <button onClick={handleGenerate} disabled={!state?.patient_data || state.is_signed} style={{ padding: '8px 16px', borderRadius: '20px', border: '1px solid #8b4513', background: state?.patient_data && !state.is_signed ? '#8b4513' : '#ccc', color: '#fff', cursor: state?.patient_data && !state.is_signed ? 'pointer' : 'not-allowed' }}>生成草案</button>
              <button onClick={handleSign} disabled={!state?.ai_draft || state.is_signed} style={{ padding: '8px 16px', borderRadius: '20px', border: 'none', background: state?.ai_draft && !state.is_signed ? '#5a7d5a' : '#ccc', color: '#fff', cursor: state?.ai_draft && !state.is_signed ? 'pointer' : 'not-allowed' }}>审核并签字</button>
            </div>
          </div>
        )}

        {actionMsg && <div style={{ textAlign: 'center', color: '#5a7d5a', marginTop: '15px', fontWeight: 'bold' }}>{actionMsg}</div>}

        {/* 焚毁按钮 */}
        <div style={{ textAlign: 'center', marginTop: '20px' }}>
          <button onClick={handleBurn} style={{ padding: '6px 16px', borderRadius: '20px', border: '1px dashed #8b4513', background: 'transparent', color: '#8b4513', cursor: 'pointer', fontSize: '12px' }}>🔥 一键阅后即焚（清空所有数据）</button>
        </div>

        <div style={{ textAlign: 'center', marginTop: '20px', padding: '10px', borderTop: '1px dashed #d4c8a8', color: '#8b4513', fontSize: '13px', fontWeight: 'bold' }}>🔒 数据主权归患者 · 老师端阅后即焚</div>
      </div>
    </div>
  )
}
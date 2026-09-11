import { useEffect, useState, useRef } from 'react'

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
  const [localRecord, setLocalRecord] = useState('')
  const [points, setPoints] = useState(0)
  const [simulateYoushi, setSimulateYoushi] = useState(false)
  const [agentDraft, setAgentDraft] = useState('')
  const [isDraftApproved, setIsDraftApproved] = useState(false)
  const [hasCheckedIn, setHasCheckedIn] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const savedPoints = localStorage.getItem('tcm_patient_points')
    if (savedPoints) setPoints(Number(savedPoints))
    const savedRecord = localStorage.getItem('tcm_patient_record')
    if (savedRecord) setLocalRecord(savedRecord)
    const savedDraft = localStorage.getItem('tcm_agent_draft')
    if (savedDraft) setAgentDraft(savedDraft)
    const savedApproved = localStorage.getItem('tcm_draft_approved')
    if (savedApproved === 'true') setIsDraftApproved(true)
    const savedCheckIn = localStorage.getItem('tcm_has_checked_in')
    if (savedCheckIn === 'true') setHasCheckedIn(true)
  }, [])

  useEffect(() => {
    fetch('/api/huangli').then(r => r.json()).then(d => setData(d)).catch(() => setData(null))
  }, [])

  useEffect(() => {
    fetch(`/api/role/${currentRole}`).then(r => r.json()).then(d => setRoleData(d)).catch(() => setRoleData(null))
  }, [currentRole])

  const saveRecordToLocal = () => {
    localStorage.setItem('tcm_patient_record', localRecord)
    alert('✅ 病历已保存在您的设备本地（数据主权归您所有）')
  }

  const handleExport = () => {
    const exportData = { record: localRecord, points, checkInStatus: hasCheckedIn, timestamp: new Date().toISOString() }
    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `zhiheng_record_${new Date().toISOString().slice(0, 10)}.json`
    document.body.appendChild(link); link.click(); document.body.removeChild(link)
    URL.revokeObjectURL(url)
  }

  const handleImport = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = (e) => {
      try {
        const parsed = JSON.parse(e.target?.result as string)
        if (parsed.record !== undefined) setLocalRecord(parsed.record)
        if (parsed.points !== undefined) setPoints(parsed.points)
        if (parsed.checkInStatus !== undefined) setHasCheckedIn(parsed.checkInStatus)
        localStorage.setItem('tcm_patient_record', parsed.record || '')
        localStorage.setItem('tcm_patient_points', (parsed.points || 0).toString())
        localStorage.setItem('tcm_has_checked_in', parsed.checkInStatus ? 'true' : 'false')
        alert('✅ 病历与积分数据已成功导入本地设备！数据主权已转移。')
      } catch (err) { alert('❌ 导入失败：文件格式不正确。') }
    }
    reader.readAsText(file); event.target.value = ''
  }

  const currentHour = new Date().getHours()
  const isYoushi = (currentHour >= 17 && currentHour < 19) || simulateYoushi

  const handleCheckIn = () => {
    if (!isYoushi) { alert('❌ 当前非酉时（17:00-19:00），子午流注未至，暂不可打卡。'); return }
    const newPoints = points + 10
    setPoints(newPoints); setHasCheckedIn(true)
    localStorage.setItem('tcm_patient_points', newPoints.toString()); localStorage.setItem('tcm_has_checked_in', 'true')
    alert('✅ 酉时打卡成功！\n肾经当令，太渊穴按摩已记录。\n积分 +10')
  }

  const handleAgentCollect = () => { alert('✅ 张三智能体已采集今日打卡与病历数据，已加密上报给李老师智能体。') }

  const handleGenerateDraft = () => {
    const draft = `根据张三白露节气打卡记录，建议：继续按揉太渊穴，并增加百合粥食疗。`;
    setAgentDraft(draft); localStorage.setItem('tcm_agent_draft', draft)
    alert('✅ 李老师智能体已根据数据生成回复草案，等待老师审核签字。')
  }

  const handleTeacherSign = () => {
    setIsDraftApproved(true); localStorage.setItem('tcm_draft_approved', 'true')
    alert('✅ 已审核签字并发送给张三。\n系统后台已自动执行阅后即焚：该记录已从老师端内存中彻底擦除。')
  }

  const resetAll = () => {
    localStorage.clear(); setPoints(0); setLocalRecord(''); setAgentDraft(''); setIsDraftApproved(false); setHasCheckedIn(false);
    alert('已重置所有本地数据')
  }

  // --- 统一全局样式，提升质感 ---
  const cardStyle: React.CSSProperties = {
    background: '#fdfcf0',
    border: '1px solid #d4c8a8',
    borderRadius: '12px',
    padding: '24px',
    marginBottom: '20px',
    boxShadow: '0 4px 16px rgba(139, 69, 19, 0.08)',
    transition: 'all 0.3s ease'
  }

  const btnBase: React.CSSProperties = {
    padding: '10px 24px', borderRadius: '30px', border: 'none',
    fontSize: '15px', cursor: 'pointer', fontFamily: 'serif',
    transition: 'all 0.2s', fontWeight: 'bold'
  }

  const btnPrimary: React.CSSProperties = { ...btnBase, background: '#8b4513', color: '#fff' }
  const btnSecondary: React.CSSProperties = { ...btnBase, background: '#5a7d5a', color: '#fff' }
  const btnOutline: React.CSSProperties = { ...btnBase, background: '#fff', color: '#8b4513', border: '1px solid #8b4513' }
  const btnDisabled: React.CSSProperties = { ...btnBase, background: '#ccc', color: '#fff', cursor: 'not-allowed' }

  const roleBtnStyle = (roleKey: string): React.CSSProperties => ({
    ...btnBase, padding: '8px 16px', fontSize: '14px',
    backgroundColor: currentRole === roleKey ? '#8b4513' : '#fdfcf0',
    color: currentRole === roleKey ? '#fff' : '#8b4513',
    border: '1px solid #8b4513'
  })

  const roles = [
    { key: 'teacher_li', name: '李老师' }, { key: 'teacher_agent', name: '李老师智能体' },
    { key: 'patient_zhangsan', name: '患者张三' }, { key: 'patient_agent', name: '张三智能体' },
  ]

  return (
    <div style={{ minHeight: '100vh', background: '#f5f1e6', padding: '40px 20px', fontFamily: 'serif', color: '#333' }}>
      <div style={{ maxWidth: '600px', margin: '0 auto' }}>
        
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '2px solid #d4c8a8', paddingBottom: '15px', marginBottom: '30px' }}>
          <h1 style={{ color: '#8b4513', fontSize: '24px', letterSpacing: '2px', margin: 0, fontWeight: 'bold' }}>知衡 · 中医治未病社区</h1>
          <div style={{ background: '#fff8e7', border: '1px solid #8b4513', borderRadius: '20px', padding: '6px 14px', color: '#8b4513', fontWeight: 'bold', fontSize: '14px' }}>🏆 积分：{points}</div>
        </div>
        
        {data && (
          <div style={cardStyle}>
            <div style={{ textAlign: 'center', fontSize: '18px', color: '#333', marginBottom: '15px' }}>
              <span style={{ fontWeight: 'bold' }}>{data.date}</span> · {data.lunar}
            </div>
            <div style={{ textAlign: 'center', color: '#5a7d5a', fontSize: '16px', marginBottom: '15px' }}>🌿 {data.solar_term}：{data.health_trend}</div>
            <div style={{ textAlign: 'center', background: hasCheckedIn ? '#e8f4ea' : '#fff8e7', padding: '15px', borderRadius: '8px', color: hasCheckedIn ? '#5a7d5a' : '#8b4513', fontWeight: 'bold' }}>
              {hasCheckedIn ? '✅ 今日作业已完成（酉时打卡成功）' : `📝 今日作业：${data.homework}`}
            </div>
          </div>
        )}

        <div style={cardStyle}>
          <div style={{ textAlign: 'center', marginBottom: '15px', color: '#8b4513', fontWeight: 'bold' }}>🧑‍⚕️ 角色切换（演示用）</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'center' }}>
            {roles.map((role) => (
              <button key={role.key} style={roleBtnStyle(role.key)} onClick={() => setCurrentRole(role.key)}>{role.name}</button>
            ))}
          </div>
          <div style={{ textAlign: 'center', marginTop: '20px', fontSize: '12px', color: '#999', borderTop: '1px dashed #d4c8a8', paddingTop: '15px' }}>
            <label style={{ cursor: 'pointer', marginRight: '15px' }}>
              <input type="checkbox" checked={simulateYoushi} onChange={(e) => setSimulateYoushi(e.target.checked)} style={{ marginRight: '5px' }} />
              时光模拟(强行酉时)
            </label>
            <button onClick={resetAll} style={{ background: 'none', border: 'none', color: '#b22222', cursor: 'pointer', textDecoration: 'underline', fontSize: '12px' }}>重置演示数据</button>
          </div>
        </div>

        {currentRole === 'patient_zhangsan' && (
          <>
            <div style={cardStyle}>
              <div style={{ textAlign: 'center', fontSize: '18px', color: '#8b4513', marginBottom: '10px', fontWeight: 'bold' }}>📝 我的作业</div>
              <div style={{ textAlign: 'center', color: '#555', lineHeight: '1.8', marginBottom: '20px' }}>今日作业：按揉太渊穴5分钟。请记得在酉时完成。</div>
              <div style={{ textAlign: 'center' }}>
                <button onClick={handleCheckIn} disabled={hasCheckedIn} style={hasCheckedIn ? btnDisabled : (isYoushi ? btnPrimary : btnDisabled)}>
                  {hasCheckedIn ? '已打卡' : (isYoushi ? '立即打卡（酉时）' : '未至酉时（17-19点）')}
                </button>
              </div>
            </div>
            <div style={cardStyle}>
              <div style={{ textAlign: 'center', marginBottom: '15px', color: '#8b4513', fontWeight: 'bold' }}>📁 我的病历本</div>
              <textarea value={localRecord} onChange={(e) => setLocalRecord(e.target.value)} placeholder="请记录您今天的身体感受..." style={{ width: '100%', height: '80px', padding: '12px', borderRadius: '8px', border: '1px solid #d4c8a8', fontFamily: 'serif', fontSize: '14px', boxSizing: 'border-box', background: '#fffdf8', outline: 'none' }} />
              <div style={{ display: 'flex', justifyContent: 'center', gap: '10px', marginTop: '15px', flexWrap: 'wrap' }}>
                <button onClick={saveRecordToLocal} style={btnSecondary}>🔒 保存在本地</button>
                <button onClick={handleExport} style={btnOutline}>📤 导出病历</button>
                <button onClick={() => fileInputRef.current?.click()} style={btnOutline}>📥 导入病历</button>
                <input type="file" accept=".json" ref={fileInputRef} style={{ display: 'none' }} onChange={handleImport} />
              </div>
            </div>
            {isDraftApproved && (
              <div style={{ ...cardStyle, background: '#e8f4ea', border: '1px solid #5a7d5a' }}>
                <div style={{ textAlign: 'center', color: '#5a7d5a', fontWeight: 'bold', marginBottom: '10px' }}>📩 收到李老师的新医嘱</div>
                <div style={{ textAlign: 'center', color: '#333', lineHeight: '1.8' }}>{agentDraft}</div>
              </div>
            )}
          </>
        )}

        {currentRole === 'patient_agent' && (
          <div style={cardStyle}>
            <div style={{ textAlign: 'center', fontSize: '18px', color: '#8b4513', marginBottom: '10px', fontWeight: 'bold' }}>🤖 智能体采集</div>
            <div style={{ textAlign: 'center', color: '#555', lineHeight: '1.8', marginBottom: '20px' }}>仅采集上报，不做独立分析。</div>
            <div style={{ textAlign: 'center' }}><button onClick={handleAgentCollect} style={btnPrimary}>📤 采集并上报数据</button></div>
          </div>
        )}

        {currentRole === 'teacher_agent' && (
          <div style={{ ...cardStyle, background: '#e8f0e8' }}>
            <div style={{ textAlign: 'center', fontSize: '18px', color: '#8b4513', marginBottom: '10px', fontWeight: 'bold' }}>🤖 智能体草案</div>
            <div style={{ textAlign: 'center', color: '#555', lineHeight: '1.8', marginBottom: '20px' }}>已根据张三的打卡生成回复草案。</div>
            {!agentDraft ? (
              <div style={{ textAlign: 'center' }}><button onClick={handleGenerateDraft} style={btnPrimary}>⚙️ 生成草案</button></div>
            ) : (
              <div style={{ padding: '15px', background: '#fff', borderRadius: '8px', border: '1px dashed #8b4513', color: '#333' }}><strong>草案内容：</strong>{agentDraft}</div>
            )}
          </div>
        )}

        {currentRole === 'teacher_li' && (
          <div style={{ ...cardStyle, background: '#e8f0e8' }}>
            <div style={{ textAlign: 'center', fontSize: '18px', color: '#8b4513', marginBottom: '10px', fontWeight: 'bold' }}>📋 患者记录审核</div>
            <div style={{ textAlign: 'center', color: '#666', padding: '15px', background: '#fce4e4', borderRadius: '8px', fontSize: '14px', marginBottom: '15px' }}>
              {localRecord ? `患者记录：${localRecord}` : '暂无患者临时记录。'}
            </div>
            {agentDraft && !isDraftApproved && (
              <div style={{ padding: '15px', background: '#fff', borderRadius: '8px', border: '1px dashed #8b4513', marginBottom: '15px', color: '#333' }}>
                <strong>智能体草案：</strong>{agentDraft}
              </div>
            )}
            {isDraftApproved ? (
              <div style={{ textAlign: 'center', color: '#5a7d5a', fontWeight: 'bold' }}>✅ 已签字生效，阅后即焚。</div>
            ) : (
              <div style={{ textAlign: 'center' }}><button onClick={handleTeacherSign} style={btnPrimary}>✍️ 审核签字，发送给张三</button></div>
            )}
          </div>
        )}

        <div style={{ textAlign: 'center', marginTop: '30px', padding: '12px', borderTop: '1px dashed #d4c8a8', color: '#8b4513', fontSize: '14px', fontWeight: 'bold' }}>
          {roleData?.privacy_notice || '🔒 数据主权归你所有 · 阅后即焚'}
        </div>
      </div>
    </div>
  )
}
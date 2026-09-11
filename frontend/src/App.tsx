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
  const [localRecord, setLocalRecord] = useState('')
  
  // 积分与时差模拟
  const [points, setPoints] = useState(0)
  const [simulateYoushi, setSimulateYoushi] = useState(false)

  // 智能体草案与签字状态
  const [agentDraft, setAgentDraft] = useState('')
  const [isDraftApproved, setIsDraftApproved] = useState(false)

  // 核心新增：今日打卡状态
  const [hasCheckedIn, setHasCheckedIn] = useState(false)

  // 初始化：从本地读取状态
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
    fetch('/api/huangli')
      .then(r => r.json())
      .then(d => setData(d))
      .catch(() => setData(null))
  }, [])

  useEffect(() => {
    fetch(`/api/role/${currentRole}`)
      .then(r => r.json())
      .then(d => setRoleData(d))
      .catch(() => setRoleData(null))
  }, [currentRole])

  const saveRecordToLocal = () => {
    localStorage.setItem('tcm_patient_record', localRecord)
    alert('✅ 病历已保存在您的设备本地（数据主权归您所有）')
  }

  const currentHour = new Date().getHours()
  const isYoushi = (currentHour >= 17 && currentHour < 19) || simulateYoushi

  const handleCheckIn = () => {
    if (!isYoushi) {
      alert('❌ 当前非酉时（17:00-19:00），子午流注未至，暂不可打卡。')
      return
    }
    const newPoints = points + 10
    setPoints(newPoints)
    setHasCheckedIn(true)
    localStorage.setItem('tcm_patient_points', newPoints.toString())
    localStorage.setItem('tcm_has_checked_in', 'true')
    alert('✅ 酉时打卡成功！\n肾经当令，太渊穴按摩已记录。\n积分 +10')
  }

  const handleAgentCollect = () => {
    alert('✅ 张三智能体已采集今日打卡与病历数据，已加密上报给李老师智能体。')
  }

  const handleGenerateDraft = () => {
    const draft = `根据张三白露节气打卡记录，建议：继续按揉太渊穴，并增加百合粥食疗。`;
    setAgentDraft(draft);
    localStorage.setItem('tcm_agent_draft', draft);
    alert('✅ 李老师智能体已根据数据生成回复草案，等待老师审核签字。')
  }

  const handleTeacherSign = () => {
    setIsDraftApproved(true);
    localStorage.setItem('tcm_draft_approved', 'true');
    alert('✅ 已审核签字并发送给张三。\n系统后台已自动执行阅后即焚：该记录已从老师端内存中彻底擦除。')
  }

  const resetAll = () => {
    localStorage.clear()
    setPoints(0); setLocalRecord(''); setAgentDraft(''); setIsDraftApproved(false); setHasCheckedIn(false);
    alert('已重置所有本地数据')
  }

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
        
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '2px solid #d4c8a8', paddingBottom: '15px', marginBottom: '30px' }}>
          <h1 style={{ color: '#8b4513', fontSize: '24px', letterSpacing: '2px', margin: 0 }}>
            知衡 · 中医治未病社区
          </h1>
          <div style={{ background: '#fff8e7', border: '1px solid #8b4513', borderRadius: '20px', padding: '6px 14px', color: '#8b4513', fontWeight: 'bold', fontSize: '14px' }}>
            🏆 积分：{points}
          </div>
        </div>
        
        {data && (
          <div style={boxStyle}>
            <div style={{ textAlign: 'center', fontSize: '18px', color: '#333', marginBottom: '15px' }}>
              <span style={{ fontWeight: 'bold' }}>{data.date}</span> · {data.lunar}
            </div>
            <div style={{ textAlign: 'center', color: '#5a7d5a', fontSize: '16px', marginBottom: '10px' }}>
              🌿 {data.solar_term}：{data.health_trend}
            </div>
            {/* 核心优化：动态显示今日作业状态 */}
            <div style={{ textAlign: 'center', background: hasCheckedIn ? '#e8f4ea' : '#fff8e7', padding: '15px', borderRadius: '8px', color: hasCheckedIn ? '#5a7d5a' : '#8b4513', transition: 'all 0.3s' }}>
              {hasCheckedIn ? '✅ 今日作业已完成（酉时打卡成功）' : `📝 今日作业：${data.homework}`}
            </div>
          </div>
        )}

        <div style={boxStyle}>
          <div style={{ textAlign: 'center', marginBottom: '15px', color: '#8b4513', fontWeight: 'bold' }}>
            🧑‍⚕️ 角色切换（演示用）
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'center' }}>
            {roles.map((role) => (
              <button key={role.key} style={roleBtnStyle(role.key)} onClick={() => setCurrentRole(role.key)}>
                {role.name}
              </button>
            ))}
          </div>
          <div style={{ textAlign: 'center', marginTop: '15px', fontSize: '12px', color: '#999' }}>
            <label style={{ cursor: 'pointer', marginRight: '15px' }}>
              <input type="checkbox" checked={simulateYoushi} onChange={(e) => setSimulateYoushi(e.target.checked)} style={{ marginRight: '5px' }} />
              时光模拟(强行酉时)
            </label>
            <button onClick={resetAll} style={{ background: 'none', border: 'none', color: '#b22222', cursor: 'pointer', textDecoration: 'underline' }}>重置演示数据</button>
          </div>
        </div>

        {currentRole === 'patient_zhangsan' && (
          <>
            <div style={{ ...boxStyle, background: '#fdfcf0' }}>
              <div style={{ textAlign: 'center', fontSize: '18px', color: '#8b4513', marginBottom: '10px' }}>📝 我的作业</div>
              <div style={{ textAlign: 'center', color: '#555', lineHeight: '1.8' }}>今日作业：按揉太渊穴5分钟。请记得在酉时完成。</div>
              <div style={{ textAlign: 'center', marginTop: '20px' }}>
                <button onClick={handleCheckIn} disabled={hasCheckedIn} style={{ padding: '10px 24px', borderRadius: '30px', border: 'none', background: hasCheckedIn ? '#ccc' : (isYoushi ? '#8b4513' : '#ccc'), color: '#fff', fontSize: '16px', cursor: hasCheckedIn ? 'not-allowed' : (isYoushi ? 'pointer' : 'not-allowed'), fontFamily: 'serif' }}>
                  {hasCheckedIn ? '已打卡' : (isYoushi ? '立即打卡（酉时）' : '未至酉时（17-19点）')}
                </button>
              </div>
            </div>
            <div style={boxStyle}>
              <div style={{ textAlign: 'center', marginBottom: '15px', color: '#8b4513', fontWeight: 'bold' }}>📁 我的病历本</div>
              <textarea value={localRecord} onChange={(e) => setLocalRecord(e.target.value)} placeholder="请记录您今天的身体感受..." style={{ width: '100%', height: '80px', padding: '10px', borderRadius: '8px', border: '1px solid #d4c8a8', fontFamily: 'serif', fontSize: '14px', boxSizing: 'border-box' }} />
              <div style={{ textAlign: 'center', marginTop: '15px' }}>
                <button onClick={saveRecordToLocal} style={{ padding: '8px 20px', borderRadius: '30px', border: 'none', background: '#5a7d5a', color: '#fff', fontSize: '14px', cursor: 'pointer', fontFamily: 'serif' }}>🔒 保存在本地</button>
              </div>
            </div>
            {isDraftApproved && (
              <div style={{ ...boxStyle, background: '#e8f4ea', border: '1px solid #5a7d5a' }}>
                <div style={{ textAlign: 'center', color: '#5a7d5a', fontWeight: 'bold' }}>📩 收到李老师的新医嘱</div>
                <div style={{ textAlign: 'center', marginTop: '10px' }}>{agentDraft}</div>
              </div>
            )}
          </>
        )}

        {currentRole === 'patient_agent' && (
          <div style={boxStyle}>
            <div style={{ textAlign: 'center', fontSize: '18px', color: '#8b4513', marginBottom: '10px' }}>🤖 智能体采集</div>
            <div style={{ textAlign: 'center', color: '#555', lineHeight: '1.8' }}>仅采集上报，不做独立分析。</div>
            <div style={{ textAlign: 'center', marginTop: '20px' }}>
              <button onClick={handleAgentCollect} style={{ padding: '10px 24px', borderRadius: '30px', border: 'none', background: '#8b4513', color: '#fff', fontSize: '16px', cursor: 'pointer', fontFamily: 'serif' }}>📤 采集并上报数据</button>
            </div>
          </div>
        )}

        {currentRole === 'teacher_agent' && (
          <div style={{ ...boxStyle, background: '#e8f0e8' }}>
            <div style={{ textAlign: 'center', fontSize: '18px', color: '#8b4513', marginBottom: '10px' }}>🤖 智能体草案</div>
            <div style={{ textAlign: 'center', color: '#555', lineHeight: '1.8' }}>已根据张三的打卡生成回复草案。</div>
            {!agentDraft ? (
              <div style={{ textAlign: 'center', marginTop: '20px' }}>
                <button onClick={handleGenerateDraft} style={{ padding: '10px 24px', borderRadius: '30px', border: 'none', background: '#8b4513', color: '#fff', fontSize: '16px', cursor: 'pointer', fontFamily: 'serif' }}>⚙️ 生成草案</button>
              </div>
            ) : (
              <div style={{ marginTop: '20px', padding: '15px', background: '#fff', borderRadius: '8px', border: '1px dashed #8b4513' }}>
                <strong>草案内容：</strong>{agentDraft}
              </div>
            )}
          </div>
        )}

        {currentRole === 'teacher_li' && (
          <div style={{ ...boxStyle, background: '#e8f0e8' }}>
            <div style={{ textAlign: 'center', fontSize: '18px', color: '#8b4513', marginBottom: '10px' }}>📋 患者记录审核</div>
            <div style={{ textAlign: 'center', color: '#666', padding: '15px', background: '#fce4e4', borderRadius: '8px', fontSize: '14px', marginBottom: '15px' }}>
              {localRecord ? `患者记录：${localRecord}` : '暂无患者临时记录。'}
            </div>
            {agentDraft && !isDraftApproved && (
              <div style={{ padding: '15px', background: '#fff', borderRadius: '8px', border: '1px dashed #8b4513', marginBottom: '15px' }}>
                <strong>智能体草案：</strong>{agentDraft}
              </div>
            )}
            {isDraftApproved ? (
              <div style={{ textAlign: 'center', color: '#5a7d5a', fontWeight: 'bold' }}>✅ 已签字生效，阅后即焚。</div>
            ) : (
              <div style={{ textAlign: 'center' }}>
                <button onClick={handleTeacherSign} style={{ padding: '10px 24px', borderRadius: '30px', border: 'none', background: '#8b4513', color: '#fff', fontSize: '16px', cursor: 'pointer', fontFamily: 'serif' }}>✍️ 审核签字，发送给张三</button>
              </div>
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
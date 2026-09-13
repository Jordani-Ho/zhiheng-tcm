import { useEffect, useState, useRef } from 'react'

interface HuangliData { date: string; lunar: string; solar_term: string; solar_term_tip: string; health_trend: string; homework: string; }
interface RoleData { role_type: string; name: string; task: string; detail: string; }
interface Transcription { id: number; patient_name: string; content: string; data_type: string; }
interface Draft { id: number; transcript_id: number; patient_name: string; content: string; signed: boolean; doctor?: string; }
interface Patient { name: string; teacher_name: string; guardian_name: string; relation: string; }
interface PatientRecord { id: number; patient_name: string; ai_draft: string; final_plan: string; doctor: string; }
interface PatientProfile { patient_name: string; gender: string; birth_date: string; birth_time: string; location: string; bazi?: string; wuxing?: string; }

export default function App() {
  const [huangli, setHuangli] = useState<HuangliData | null>(null)
  const [currentRole, setCurrentRole] = useState('患者')
  const [roleData, setRoleData] = useState<RoleData | null>(null)
  const [inputText, setInputText] = useState('')
  const [transcriptions, setTranscriptions] = useState<Transcription[]>([])
  const [drafts, setDrafts] = useState<Draft[]>([])
  const [patientRecords, setPatientRecords] = useState<PatientRecord[]>([])
  const [finalPlans, setFinalPlans] = useState<{ [key: number]: string }>({})
  const [points, setPoints] = useState<{ patient_points: number; teacher_points: number } | null>(null)
  const [patients, setPatients] = useState<Patient[]>([])
  const [selectedPatient, setSelectedPatient] = useState('张三')
  const [uploading, setUploading] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [showHistory, setShowHistory] = useState(false)
  const [profile, setProfile] = useState<PatientProfile | null>(null)
  const [editingProfile, setEditingProfile] = useState(false)
  
  const [showAddFamily, setShowAddFamily] = useState(false)
  const [newFamilyName, setNewFamilyName] = useState('')
  const [newRelation, setNewRelation] = useState('')
  const [newGender, setNewGender] = useState('')
  const [newBirthYear, setNewBirthYear] = useState('')
  const [newBirthMonth, setNewBirthMonth] = useState('')
  const [newBirthDay, setNewBirthDay] = useState('')
  const [newBirthTime, setNewBirthTime] = useState('')
  const [newLocation, setNewLocation] = useState('')
  const [guardianLocation, setGuardianLocation] = useState('')
  const [guardianGender, setGuardianGender] = useState('')

  const [editingRecordId, setEditingRecordId] = useState<number | null>(null)
  const [editingRecordContent, setEditingRecordContent] = useState('')

  const currentYear = new Date().getFullYear()
  const yearOptions = Array.from({ length: currentYear - 1920 + 1 }, (_, i) => currentYear - i)
  const monthOptions = Array.from({ length: 12 }, (_, i) => i + 1)
  const getDayOptions = () => {
    const y = parseInt(newBirthYear) || currentYear
    const m = parseInt(newBirthMonth) || 1
    const days = new Date(y, m, 0).getDate()
    return Array.from({ length: days }, (_, i) => i + 1)
  }

  useEffect(() => {
    fetch('/api/huangli').then(r => r.json()).then(d => setHuangli(d)).catch(() => setHuangli(null))
    fetchPatients('张三')
    fetch('/api/patient-profile?patient_name=张三')
      .then(r => r.json())
      .then(d => {
        setGuardianLocation(d.location || '')
        setGuardianGender(d.gender || '')
      })
      .catch(() => {})
  }, [])

  const fetchPatients = (guardian: string) => {
    fetch(`/api/patients?guardian_name=${guardian}`).then(r => r.json()).then(d => setPatients(d)).catch(() => setPatients([]))
  }

  const fetchRoleData = () => {
    fetch(`/api/role-data?role=${currentRole}&patient_name=${selectedPatient}`).then(r => r.json()).then(d => setRoleData(d)).catch(() => setRoleData(null))
  }

  const fetchTranscriptions = () => {
    fetch(`/api/transcriptions?patient_name=${selectedPatient}`).then(r => r.json()).then(d => setTranscriptions(d)).catch(() => setTranscriptions([]))
  }

  const fetchDrafts = () => {
    fetch('/api/drafts').then(r => r.json()).then(d => setDrafts(d)).catch(() => setDrafts([]))
  }

  const fetchPatientRecords = () => {
    fetch(`/api/patient-records?patient_name=${selectedPatient}`).then(r => r.json()).then(d => setPatientRecords(d)).catch(() => setPatientRecords([]))
  }

  const fetchPoints = () => {
    fetch(`/api/points?patient_name=${selectedPatient}`).then(r => r.json()).then(d => setPoints(d)).catch(() => setPoints(null))
  }

  const fetchProfile = () => {
    fetch(`/api/patient-profile?patient_name=${selectedPatient}`).then(r => r.json()).then(d => setProfile(d)).catch(() => setProfile(null))
  }

  useEffect(() => {
    fetchRoleData()
    fetchTranscriptions()
    fetchDrafts()
    fetchPatientRecords()
    fetchPoints()
    fetchProfile()
    setShowHistory(false)
  }, [currentRole, selectedPatient])

  const handleCheckIn = () => { 
    fetch(`/api/check-in?patient_name=${selectedPatient}`, { method: 'POST' }).then(() => {
      fetchRoleData()
      fetchPoints()
    })
  }
  
  const handleApprove = () => { fetch(`/api/approve?patient_name=${selectedPatient}`, { method: 'POST' }).then(() => fetchRoleData()) }
  
  const handleTranscribe = () => {
    if (!inputText.trim()) return
    fetch('/api/transcribe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ patient_name: selectedPatient, content: inputText, data_type: 'text' })
    }).then(() => { setInputText(''); fetchTranscriptions() })
  }

  const handleImageUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    const formData = new FormData()
    formData.append('file', file)
    fetch(`/api/upload?patient_name=${selectedPatient}`, { method: 'POST', body: formData })
      .then(r => r.json())
      .then(() => {
        setUploading(false)
        fetchTranscriptions()
        if (fileInputRef.current) fileInputRef.current.value = ''
      })
      .catch(() => {
        setUploading(false)
        alert("图片上传失败，请重试")
      })
  }

  const handleGenerateDraft = (transcriptId: number) => {
    fetch(`/api/generate-draft?transcript_id=${transcriptId}`, { method: 'POST' })
      .then(() => {
        fetchDrafts()
        fetchTranscriptions() // 刷新陈述列表，已处理的会自动消失
      })
  }

  const handleEditDraft = (draftId: number, newContent: string) => {
    fetch(`/api/drafts/${draftId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: newContent })
    }).then(() => fetchDrafts())
  }

  const handleSignDraft = (draftId: number) => {
    const plan = finalPlans[draftId]?.trim()
    if (!plan) {
      alert("请先填写给患者的最终辨证施治方案！")
      return
    }
    fetch(`/api/drafts/${draftId}/sign`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ final_plan: plan })
    }).then(() => {
      fetchDrafts();
      fetchPatientRecords();
      fetchPoints();
      setFinalPlans(prev => ({ ...prev, [draftId]: '' }));
    })
  }

  const handleSaveProfile = () => {
    if (!profile) return
    fetch('/api/patient-profile', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(profile)
    }).then(() => {
      setEditingProfile(false)
      fetchProfile()
      alert("档案已保存！")
    })
  }

  const handleRelationChange = (value: string) => {
    setNewRelation(value)
    if (['父亲', '儿子'].includes(value)) {
      setNewGender('男')
    } else if (['母亲', '女儿'].includes(value)) {
      setNewGender('女')
    } else if (value === '配偶') {
      if (guardianGender === '男') {
        setNewGender('女')
      } else if (guardianGender === '女') {
        setNewGender('男')
      } else {
        setNewGender('')
      }
    } else {
      setNewGender('')
    }
  }

  const handleToggleAddFamily = () => {
    if (!showAddFamily) {
      setNewLocation(guardianLocation)
    }
    setShowAddFamily(!showAddFamily)
  }

  const handleAddFamily = () => {
    if (!newFamilyName.trim() || !newRelation.trim() || !newGender || !newBirthYear || !newBirthMonth || !newBirthDay) {
      alert("请至少填写姓名、关系、性别和完整的出生年月日！")
      return
    }
    const mm = String(newBirthMonth).padStart(2, '0')
    const dd = String(newBirthDay).padStart(2, '0')
    const birthDate = `${newBirthYear}-${mm}-${dd}`
    
    fetch('/api/patients/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ 
        name: newFamilyName, 
        guardian_name: '张三',
        relation: newRelation,
        gender: newGender,
        birth_date: birthDate,
        birth_time: newBirthTime,
        location: newLocation
      })
    }).then(() => {
      setNewFamilyName('')
      setNewRelation('')
      setNewGender('')
      setNewBirthYear('')
      setNewBirthMonth('')
      setNewBirthDay('')
      setNewBirthTime('')
      setNewLocation('')
      setShowAddFamily(false)
      fetchPatients('张三')
      alert("亲友档案添加成功！")
    })
  }

  const handleSaveRecord = (recordId: number) => {
    if (!editingRecordContent.trim()) {
      alert("病历内容不能为空！")
      return
    }
    fetch(`/api/patient-records/${recordId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ patient_name: selectedPatient, content: editingRecordContent })
    })
      .then(r => r.json())
      .then(d => {
        if (d.error) {
          alert(d.error)
        } else {
          setEditingRecordId(null)
          fetchPatientRecords()
        }
      })
  }

  const boxStyle = { background: '#fdfcf0', border: '1px solid #d4c8a8', borderRadius: '12px', padding: '24px', marginBottom: '20px', boxShadow: '0 4px 12px rgba(0,0,0,0.06)' }
  const roleBtnStyle = (role: string) => ({ padding: '8px 16px', margin: '5px', borderRadius: '20px', border: '1px solid #8b4513', cursor: 'pointer', fontFamily: 'serif', fontSize: '14px', backgroundColor: currentRole === role ? '#8b4513' : '#fdfcf0', color: currentRole === role ? '#fff' : '#8b4513', transition: 'all 0.2s' })
  const patientBtnStyle = (name: string) => ({ padding: '6px 14px', margin: '4px', borderRadius: '15px', border: '1px solid #5a7d5a', cursor: 'pointer', fontFamily: 'serif', fontSize: '13px', backgroundColor: selectedPatient === name ? '#5a7d5a' : '#f7fcf9', color: selectedPatient === name ? '#fff' : '#5a7d5a', transition: 'all 0.2s' })
  const inputStyle = { width: '100%', padding: '8px', borderRadius: '6px', border: '1px solid #d4c8a8', fontFamily: 'serif', marginBottom: '8px', boxSizing: 'border-box' as const }
  const dateSelectStyle = { padding: '8px', borderRadius: '6px', border: '1px solid #d4c8a8', fontFamily: 'serif', marginRight: '6px', marginBottom: '8px' }

  return (
    <div style={{ minHeight: '100vh', background: '#f5f1e6', padding: '40px 20px', fontFamily: 'serif' }}>
      <div style={{ maxWidth: '600px', margin: '0 auto' }}>
        <h1 style={{ textAlign: 'center', color: '#8b4513', borderBottom: '2px solid #d4c8a8', paddingBottom: '15px', marginBottom: '30px', fontSize: '28px', letterSpacing: '2px' }}>知衡 · 中医治未病社区</h1>

        {huangli && (
          <div style={boxStyle}>
            <div style={{ textAlign: 'center', fontSize: '18px', color: '#333', marginBottom: '5px' }}>
              <span style={{ fontWeight: 'bold' }}>{huangli.date}</span> · {huangli.lunar}
            </div>
            {huangli.solar_term_tip && huangli.solar_term_tip !== '无' && (
              <div style={{ textAlign: 'center', color: '#8b4513', fontSize: '14px', marginBottom: '15px' }}>
                🌿 {huangli.solar_term_tip}
              </div>
            )}
            <div style={{ textAlign: 'center', color: '#5a7d5a', fontSize: '16px', marginBottom: '10px' }}>
              🌿 {huangli.solar_term}：{huangli.health_trend}
            </div>
            <div style={{ textAlign: 'center', background: '#fff8e7', padding: '15px', borderRadius: '8px', color: '#8b4513' }}>
              📝 今日作业：{huangli.homework}
            </div>
          </div>
        )}

        {(currentRole === '患者' || currentRole === '患者智能体') && (
          <div style={{ ...boxStyle, background: '#f0f7f5' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
              <div style={{ fontSize: '18px', color: '#5a7d5a', fontWeight: 'bold' }}>🏠 我的家庭（{patients.length}人）</div>
              <button 
                onClick={handleToggleAddFamily} 
                style={{ padding: '4px 12px', borderRadius: '15px', border: '1px solid #5a7d5a', background: 'transparent', color: '#5a7d5a', cursor: 'pointer', fontSize: '12px' }}
              >
                {showAddFamily ? '取消' : '+ 添加亲友'}
              </button>
            </div>
            
            <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'center' }}>
              {patients.map(p => (
                <button key={p.name} style={patientBtnStyle(p.name)} onClick={() => setSelectedPatient(p.name)}>
                  {p.relation === '本人' ? `👤 ${p.name}` : `👨‍👩‍👧 ${p.name}（${p.relation}）`}
                </button>
              ))}
            </div>
            <div style={{ textAlign: 'center', fontSize: '12px', color: '#999', marginTop: '10px' }}>
              点击头像，帮家人打卡、看健康档案、代述问诊
            </div>

            {showAddFamily && (
              <div style={{ marginTop: '15px', borderTop: '1px dashed #b8d8c0', paddingTop: '15px' }}>
                <div style={{ fontSize: '14px', color: '#5a7d5a', fontWeight: 'bold', marginBottom: '10px' }}>📝 亲友基础信息</div>
                <input value={newFamilyName} onChange={(e) => setNewFamilyName(e.target.value)} placeholder="姓名（必填）" style={inputStyle} />
                
                <select value={newRelation} onChange={(e) => handleRelationChange(e.target.value)} style={inputStyle}>
                  <option value="">与您的关系（必填）</option>
                  <option value="父亲">父亲</option>
                  <option value="母亲">母亲</option>
                  <option value="儿子">儿子</option>
                  <option value="女儿">女儿</option>
                  <option value="配偶">配偶</option>
                  <option value="其他">其他</option>
                </select>
                
                <select value={newGender} onChange={(e) => setNewGender(e.target.value)} style={inputStyle}>
                  <option value="">性别（必填，选关系后自动联动）</option>
                  <option value="男">男</option>
                  <option value="女">女</option>
                </select>
                
                <label style={{ fontSize: '12px', color: '#888' }}>出生日期（按 年-月-日 顺序选择）</label>
                <div style={{ display: 'flex', flexWrap: 'wrap', marginBottom: '8px' }}>
                  <select value={newBirthYear} onChange={(e) => setNewBirthYear(e.target.value)} style={dateSelectStyle}>
                    <option value="">年</option>
                    {yearOptions.map(y => <option key={y} value={y}>{y}</option>)}
                  </select>
                  <select value={newBirthMonth} onChange={(e) => setNewBirthMonth(e.target.value)} style={dateSelectStyle}>
                    <option value="">月</option>
                    {monthOptions.map(m => <option key={m} value={m}>{m}</option>)}
                  </select>
                  <select value={newBirthDay} onChange={(e) => setNewBirthDay(e.target.value)} style={dateSelectStyle}>
                    <option value="">日</option>
                    {getDayOptions().map(d => <option key={d} value={d}>{d}</option>)}
                  </select>
                </div>
                
                <label style={{ fontSize: '12px', color: '#888' }}>出生时间（选填，精确到小时即可）</label>
                <input type="time" step="3600" value={newBirthTime} onChange={(e) => setNewBirthTime(e.target.value)} style={inputStyle} />
                
                <label style={{ fontSize: '12px', color: '#888' }}>现居住地（默认继承您的居住地，可修改）</label>
                <input value={newLocation} onChange={(e) => setNewLocation(e.target.value)} placeholder="例如：广东省广州市" style={inputStyle} />
                
                <div style={{ textAlign: 'right', marginTop: '10px' }}>
                  <button onClick={handleAddFamily} style={{ padding: '6px 20px', borderRadius: '20px', border: 'none', background: '#5a7d5a', color: '#fff', cursor: 'pointer' }}>确认添加亲友</button>
                </div>
              </div>
            )}
          </div>
        )}

        {(currentRole === '患者' || currentRole === '患者智能体') && profile && (
          <div style={{ ...boxStyle, background: '#fffaf0' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '15px' }}>
              <div style={{ fontSize: '18px', color: '#8b4513', fontWeight: 'bold' }}>📋 {selectedPatient} 的基础档案</div>
              <button 
                onClick={() => setEditingProfile(!editingProfile)}
                style={{ padding: '4px 12px', borderRadius: '15px', border: '1px solid #8b4513', background: 'transparent', color: '#8b4513', cursor: 'pointer', fontSize: '12px' }}
              >
                {editingProfile ? '取消' : '编辑/补充'}
              </button>
            </div>
            
            {editingProfile ? (
              <div>
                <label style={{ fontSize: '13px', color: '#666' }}>性别</label>
                <select value={profile.gender} onChange={e => setProfile({...profile, gender: e.target.value})} style={inputStyle}>
                  <option value="">请选择</option>
                  <option value="男">男</option>
                  <option value="女">女</option>
                </select>
                <label style={{ fontSize: '13px', color: '#666' }}>出生日期（不能选未来）</label>
                <input type="date" max={todayStr} value={profile.birth_date} onChange={e => setProfile({...profile, birth_date: e.target.value})} style={inputStyle} />
                <label style={{ fontSize: '13px', color: '#666' }}>出生时间（选填，精确到小时即可）</label>
                <input type="time" step="3600" value={profile.birth_time} onChange={e => setProfile({...profile, birth_time: e.target.value})} style={inputStyle} />
                <label style={{ fontSize: '13px', color: '#666' }}>现居住地</label>
                <input type="text" value={profile.location} onChange={e => setProfile({...profile, location: e.target.value})} placeholder="例如：广东省广州市" style={inputStyle} />
                <div style={{ textAlign: 'right' }}>
                  <button onClick={handleSaveProfile} style={{ padding: '6px 20px', borderRadius: '20px', border: 'none', background: '#8b4513', color: '#fff', cursor: 'pointer' }}>保存档案</button>
                </div>
              </div>
            ) : (
              <div style={{ fontSize: '14px', color: '#333', lineHeight: '2' }}>
                <div>性别：{profile.gender || '未填写'}</div>
                <div>出生日期：{profile.birth_date || '未填写'}</div>
                <div>出生时间：{profile.birth_time || '未填写（后续可由老师或智能体推断）'}</div>
                <div>现居住地：{profile.location || '未填写'}</div>
              </div>
            )}
          </div>
        )}

        <div style={boxStyle}>
          <div style={{ textAlign: 'center', marginBottom: '15px', color: '#8b4513', fontWeight: 'bold' }}>🧑‍⚕️ 角色切换</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'center' }}>
            {['李老师', '李老师智能体', '患者', '患者智能体'].map((role) => (
              <button key={role} style={roleBtnStyle(role)} onClick={() => setCurrentRole(role)}>{role}</button>
            ))}
          </div>
        </div>

        {points && (
          <div style={{ ...boxStyle, display: 'flex', justifyContent: 'space-around', textAlign: 'center', background: '#fffdf5' }}>
            <div>
              <div style={{ fontSize: '12px', color: '#999' }}>{selectedPatient} 积分</div>
              <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#8b4513' }}>{points.patient_points}</div>
            </div>
            <div>
              <div style={{ fontSize: '12px', color: '#999' }}>李老师 积分</div>
              <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#5a7d5a' }}>{points.teacher_points}</div>
            </div>
          </div>
        )}

        <div style={{ ...boxStyle, background: currentRole.includes('老师') ? '#e8f0e8' : '#fdfcf0' }}>
          <div style={{ textAlign: 'center', fontSize: '18px', color: '#8b4513', marginBottom: '10px' }}>{roleData ? `📋 ${roleData.name} 的任务` : '加载中...'}</div>
          <div style={{ textAlign: 'center', color: '#555', lineHeight: '1.8' }}>{roleData ? roleData.detail : '正在获取数据...'}</div>
          {currentRole === '患者' && roleData?.detail.includes('请记得') && (
            <div style={{ textAlign: 'center', marginTop: '20px' }}><button onClick={handleCheckIn} style={{ padding: '10px 24px', borderRadius: '30px', border: 'none', background: '#8b4513', color: '#fff', fontSize: '16px', cursor: 'pointer' }}>立即打卡（+10积分）</button></div>
          )}
          {currentRole === '李老师' && roleData?.task === '待审核' && roleData?.detail.includes('已打卡') && (
            <div style={{ textAlign: 'center', marginTop: '20px' }}><button onClick={handleApprove} style={{ padding: '10px 24px', borderRadius: '30px', border: 'none', background: '#5a7d5a', color: '#fff', fontSize: '16px', cursor: 'pointer' }}>签字确认</button></div>
          )}
        </div>

        {(currentRole === '李老师' || currentRole === '李老师智能体') && (
          <div style={{ ...boxStyle, background: '#fff9f0' }}>
            <div 
              style={{ textAlign: 'center', fontSize: '18px', color: '#8b4513', fontWeight: 'bold', cursor: 'pointer', display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '5px' }}
              onClick={() => setShowHistory(!showHistory)}
            >
              📂 {selectedPatient} 的历史病历 {showHistory ? '▲' : '▼'}
            </div>
            {showHistory && (
              <div style={{ marginTop: '15px' }}>
                {patientRecords.length === 0 ? (
                  <div style={{ textAlign: 'center', color: '#999' }}>暂无历史病历记录</div>
                ) : (
                  patientRecords.map(r => (
                    <div key={r.id} style={{ padding: '12px', border: '1px dashed #d4c8a8', borderRadius: '8px', marginBottom: '15px', background: '#fdfcf0' }}>
                      <div style={{ color: '#5a7d5a', fontSize: '12px', marginBottom: '8px', fontWeight: 'bold' }}>✅ 由 {r.doctor} 签字确认</div>
                      <div style={{ fontSize: '13px', color: '#999', marginBottom: '3px' }}>【智能体原始草案】</div>
                      <div style={{ whiteSpace: 'pre-wrap', fontSize: '13px', color: '#666', background: '#f5f5f5', padding: '8px', borderRadius: '6px', marginBottom: '8px' }}>{r.ai_draft}</div>
                      <div style={{ fontSize: '13px', color: '#8b4513', marginBottom: '3px' }}>【老师最终决策】</div>
                      <div style={{ whiteSpace: 'pre-wrap', fontSize: '14px', color: '#333', background: '#fff8e7', padding: '8px', borderRadius: '6px' }}>{r.final_plan}</div>
                    </div>
                  ))
                )}
              </div>
            )}
          </div>
        )}

        {(currentRole === '李老师' || currentRole === '李老师智能体') && profile && (
          <div style={{ ...boxStyle, background: '#fffaf0' }}>
            <div style={{ fontSize: '18px', color: '#8b4513', fontWeight: 'bold', marginBottom: '15px' }}>📋 {selectedPatient} 的基础档案（供辨证参考）</div>
            <div style={{ fontSize: '14px', color: '#333', lineHeight: '2' }}>
              <div>性别：{profile.gender || '未填写'}</div>
              <div>出生日期：{profile.birth_date || '未填写'}</div>
              <div>出生时间：{profile.birth_time || '未填写（时辰未知，按子时推算）'}</div>
              <div>现居住地：{profile.location || '未填写'}</div>
              <div style={{ marginTop: '8px', paddingTop: '8px', borderTop: '1px dashed #d4c8a8', color: '#8b4513', fontWeight: 'bold' }}>
                八字：{profile.bazi || '缺少出生日期，无法推算'}
              </div>
              {profile.wuxing && (
                <div style={{ color: '#5a7d5a', fontWeight: 'bold' }}>
                  五行体质参考：{profile.wuxing}
                </div>
              )}
            </div>
          </div>
        )}

        {(currentRole === '患者' || currentRole === '患者智能体') && (
          <div style={boxStyle}>
            <div style={{ textAlign: 'center', fontSize: '18px', color: '#8b4513', marginBottom: '15px' }}>🗣️ 患者智能体（仅转述，不推理）</div>
            <textarea value={inputText} onChange={(e) => setInputText(e.target.value)} placeholder="在此输入您的感受、症状或语音识别后的文字..." style={{ width: '100%', height: '80px', padding: '10px', borderRadius: '8px', border: '1px solid #d4c8a8', fontFamily: 'serif', marginBottom: '15px', boxSizing: 'border-box' }} />
            <div style={{ display: 'flex', justifyContent: 'center', gap: '10px' }}>
              <button onClick={handleTranscribe} style={{ padding: '10px 24px', borderRadius: '30px', border: 'none', background: '#8b4513', color: '#fff', fontSize: '16px', cursor: 'pointer' }}>发送文字转述</button>
              <button onClick={() => fileInputRef.current?.click()} style={{ padding: '10px 24px', borderRadius: '30px', border: '1px solid #8b4513', background: '#fdfcf0', color: '#8b4513', fontSize: '16px', cursor: 'pointer' }} disabled={uploading}>
                {uploading ? '上传中...' : '📷 上传图片'}
              </button>
              <input type="file" ref={fileInputRef} onChange={handleImageUpload} accept="image/*" style={{ display: 'none' }} />
            </div>
          </div>
        )}

        {currentRole === '李老师' && (
          <div style={boxStyle}>
            <div style={{ textAlign: 'center', fontSize: '18px', color: '#5a7d5a', marginBottom: '15px' }}>📋 待处理陈述（{selectedPatient}）</div>
            {transcriptions.length === 0 ? (
              <div style={{ textAlign: 'center', color: '#999' }}>暂无待处理陈述，请等待患者发送</div>
            ) : (
              <ul style={{ paddingLeft: '20px', color: '#333' }}>
                {transcriptions.map(t => (
                  <li key={t.id} style={{ marginBottom: '10px' }}>
                    <span style={{ color: '#8b4513', fontWeight: 'bold' }}>[{t.data_type}]</span>
                    {t.data_type === 'image' ? (
                      <img src={t.content} alt="患者上传图片" style={{ maxWidth: '150px', borderRadius: '8px', marginLeft: '5px', display: 'block', marginTop: '5px' }} />
                    ) : (
                      <span style={{ marginLeft: '5px' }}>{t.content}</span>
                    )}
                    <button onClick={() => handleGenerateDraft(t.id)} style={{ marginLeft: '10px', padding: '2px 8px', fontSize: '12px', borderRadius: '10px', border: '1px solid #5a7d5a', background: 'transparent', color: '#5a7d5a', cursor: 'pointer' }}>生成病历草案</button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {(currentRole === '李老师' || currentRole === '李老师智能体') && (
          <div style={{ ...boxStyle, background: '#fcfdfa' }}>
            <div style={{ textAlign: 'center', fontSize: '18px', color: '#8b4513', marginBottom: '15px' }}>📄 病历草案（待处理）</div>
            {drafts.length === 0 ? (
              <div style={{ textAlign: 'center', color: '#999' }}>暂无待处理病历</div>
            ) : (
              drafts.map(d => (
                <div key={d.id} style={{ padding: '15px', border: '1px solid #e0e0e0', borderRadius: '8px', marginBottom: '15px', background: '#fff' }}>
                  <div style={{ color: '#8b4513', fontWeight: 'bold', marginBottom: '5px' }}>患者：{d.patient_name} 的病历</div>
                  <textarea value={d.content} onChange={(e) => { const newDrafts = drafts.map(item => item.id === d.id ? { ...item, content: e.target.value } : item); setDrafts(newDrafts); }} style={{ width: '100%', height: '120px', padding: '10px', borderRadius: '8px', border: '1px solid #d4c8a8', fontFamily: 'serif', fontSize: '14px', marginBottom: '10px', boxSizing: 'border-box', whiteSpace: 'pre-wrap' }} />
                  <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '15px' }}>
                    <button onClick={() => handleEditDraft(d.id, d.content)} style={{ padding: '6px 16px', borderRadius: '20px', border: '1px solid #8b4513', background: 'transparent', color: '#8b4513', cursor: 'pointer' }}>保存病历修改</button>
                  </div>
                  <div style={{ borderTop: '1px dashed #d4c8a8', paddingTop: '15px' }}>
                    <div style={{ color: '#5a7d5a', fontWeight: 'bold', marginBottom: '8px' }}>📝 给 {d.patient_name} 的最终辨证施治方案（同时自动作为患者作业）</div>
                    <textarea value={finalPlans[d.id] || ''} onChange={(e) => setFinalPlans({ ...finalPlans, [d.id]: e.target.value })} placeholder="请在此写下最终结论、医嘱或调理方案（如：抓药xxx，三碗水煲成一碗，饭后服）..." style={{ width: '100%', height: '80px', padding: '10px', borderRadius: '8px', border: '1px solid #b8d8c0', background: '#f7fcf9', fontFamily: 'serif', fontSize: '14px', marginBottom: '10px', boxSizing: 'border-box' }} />
                    <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                      <button onClick={() => handleSignDraft(d.id)} style={{ padding: '8px 20px', borderRadius: '20px', border: 'none', background: '#5a7d5a', color: '#fff', cursor: 'pointer', fontWeight: 'bold' }}>签字归档（自动布置作业，支付50积分）</button>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        )}

        {(currentRole === '患者' || currentRole === '患者智能体') && (
          <div style={{ ...boxStyle, background: '#f7fcf9' }}>
            <div style={{ textAlign: 'center', fontSize: '18px', color: '#5a7d5a', marginBottom: '10px' }}>📂 {selectedPatient}的健康档案（数据主权归患者所有）</div>
            <div style={{ textAlign: 'center', fontSize: '12px', color: '#999', marginBottom: '15px', fontStyle: 'italic' }}>
              最新病历在下一次就诊前可修改，之后将永久锁定。
            </div>
            {patientRecords.length === 0 ? (
              <div style={{ textAlign: 'center', color: '#999' }}>暂无历史病历，等待老师签字归档。</div>
            ) : (
              patientRecords.map((r, index) => {
                const isLatest = index === 0;
                const isEditing = editingRecordId === r.id;
                return (
                  <div key={r.id} style={{ padding: '15px', border: '1px solid #b8d8c0', borderRadius: '8px', marginBottom: '10px', background: '#fff' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '5px' }}>
                      <div style={{ color: '#5a7d5a', fontWeight: 'bold' }}>✅ {r.doctor || '李老师'}已签字病历</div>
                      {isLatest && !isEditing && (
                        <button 
                          onClick={() => { setEditingRecordId(r.id); setEditingRecordContent(r.final_plan); }}
                          style={{ padding: '2px 10px', borderRadius: '12px', border: '1px solid #8b4513', background: 'transparent', color: '#8b4513', cursor: 'pointer', fontSize: '12px' }}
                        >
                          修改
                        </button>
                      )}
                    </div>
                    {isEditing ? (
                      <div>
                        <textarea 
                          value={editingRecordContent} 
                          onChange={(e) => setEditingRecordContent(e.target.value)} 
                          style={{ width: '100%', height: '80px', padding: '8px', borderRadius: '6px', border: '1px solid #d4c8a8', fontFamily: 'serif', fontSize: '14px', marginBottom: '8px', boxSizing: 'border-box' }} 
                        />
                        <div style={{ textAlign: 'right' }}>
                          <button onClick={() => setEditingRecordId(null)} style={{ padding: '4px 12px', borderRadius: '15px', border: '1px solid #999', background: 'transparent', color: '#666', cursor: 'pointer', fontSize: '12px', marginRight: '8px' }}>取消</button>
                          <button onClick={() => handleSaveRecord(r.id)} style={{ padding: '4px 16px', borderRadius: '15px', border: 'none', background: '#5a7d5a', color: '#fff', cursor: 'pointer', fontSize: '12px' }}>保存</button>
                        </div>
                      </div>
                    ) : (
                      <div style={{ whiteSpace: 'pre-wrap', fontSize: '14px', color: '#333', lineHeight: '1.6' }}>{r.final_plan}</div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        )}

      </div>
    </div>
  )
}
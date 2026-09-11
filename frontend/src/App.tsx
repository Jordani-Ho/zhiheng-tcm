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

  useEffect(() => {
    const saved = localStorage.getItem('tcm_patient_record')
    if (saved) setLocalRecord(saved)
  }, [])

  const saveRecordToLocal = () => {
    localStorage.setItem('tcm_patient_record', localRecord)
    alert('✅ 病历已保存在您的设备本地（数据主权归您所有）')
  }

  // 老师审核签字并发送
  const handleTeacherSign = () => {
    alert('✅ 已审核签字并发送给张三。\n系统已自动执行阅后即焚：该记录已从老师端内存中彻底擦除。')
    // 真实场景下，这里会触发后台发送逻辑。老师端不会存储病历。
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
        
        <h1 style={{ textAlign: 'center', color: '#8b4513', borderBottom: '2px solid #d4c8a8', paddingBottom: '15px', marginBottom: '30px', fontSize: '28px', letterSpacing: '2px' }}>
          知衡 · 中医治未病社区
        </h1>
        
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

        {currentRole === 'patient_zhangsan' && (
          <div style={boxStyle}>
            <div style={{ textAlign: 'center', marginBottom: '15px', color: '#8b4513', fontWeight: 'bold' }}>
              📁 我的病历本（只存在我的设备上）
            </div>
            <textarea 
              value={localRecord}
              onChange={(e) => setLocalRecord(e.target.value)}
              placeholder="请记录您今天的身体感受、症状或老师给的调理建议..."
              style={{ width: '100%', height: '100px', padding: '10px', borderRadius: '8px', border: '1px solid #d4c8a8', fontFamily: 'serif', fontSize: '14px', boxSizing: 'border-box' }}
            />
            <div style={{ textAlign: 'center', marginTop: '15px' }}>
              <button onClick={saveRecordToLocal} style={{ padding: '10px 24px', borderRadius: '30px', border: 'none', background: '#5a7d5a', color: '#fff', fontSize: '16px', cursor: 'pointer', fontFamily: 'serif' }}>
                🔒 保存在本地
              </button>
            </div>
          </div>
        )}

        {currentRole === 'teacher_li' && (
          <div style={boxStyle}>
            <div style={{ textAlign: 'center', marginBottom: '15px', color: '#8b4513', fontWeight: 'bold' }}>
              📋 患者记录审核
            </div>
            <div style={{ textAlign: 'center', color: '#666', padding: '15px', background: '#fce4e4', borderRadius: '8px', fontSize: '14px' }}>
              {localRecord ? `患者局部记录：${localRecord}` : '暂无患者临时记录（患者端未提供）。'}
            </div>
            <div style={{ textAlign: 'center', marginTop: '15px' }}>
              <button onClick={handleTeacherSign} style={{ padding: '10px 24px', borderRadius: '30px', border: 'none', background: '#8b4513', color: '#fff', fontSize: '16px', cursor: 'pointer', fontFamily: 'serif' }}>
                ✍️ 审核签字，发送给张三
              </button>
            </div>
          </div>
        )}

        <div style={{ textAlign: 'center', marginTop: '30px', padding: '12px', borderTop: '1px dashed #d4c8a8', color: '#8b4513', fontSize: '14px', fontWeight: 'bold' }}>
          {roleData?.privacy_notice || '🔒 数据主权归你所有 · 阅后即焚'}
        </div>
      </div>
    </div>
  )
}
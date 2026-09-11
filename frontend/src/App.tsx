import { useEffect, useState } from 'react'

interface AgentState {
  raw_data: string
  ai_draft: string
  is_approved: boolean
  status: string
}

export default function App() {
  const [agentState, setAgentState] = useState<AgentState | null>(null)

  // 轮询获取后端状态
  const fetchState = () => {
    fetch('/api/agent/state')
      .then(r => r.json())
      .then(d => setAgentState(d))
  }

  useEffect(() => {
    fetchState()
    const interval = setInterval(fetchState, 2000)
    return () => clearInterval(interval)
  }, [])

  // 动作函数
  const handlePatientReport = () => {
    fetch('/api/agent/patient/report', { method: 'POST' }).then(fetchState)
  }
  const handleTeacherGenerate = () => {
    fetch('/api/agent/teacher/generate_draft', { method: 'POST' }).then(fetchState)
  }
  const handleTeacherApprove = () => {
    fetch('/api/agent/teacher/approve', { method: 'POST' }).then(fetchState)
  }

  const boxStyle = {
    background: '#fdfcf0',
    border: '1px solid #d4c8a8',
    borderRadius: '12px',
    padding: '20px',
    marginBottom: '15px',
    boxShadow: '0 4px 12px rgba(0,0,0,0.06)'
  }

  return (
    <div style={{ minHeight: '100vh', background: '#f5f1e6', padding: '30px 20px', fontFamily: 'serif' }}>
      <div style={{ maxWidth: '600px', margin: '0 auto' }}>
        
        <h1 style={{ textAlign: 'center', color: '#8b4513', borderBottom: '2px solid #d4c8a8', paddingBottom: '10px', fontSize: '24px' }}>
          知衡 · 智能体协作台
        </h1>

        {/* 当前状态 */}
        <div style={boxStyle}>
          <div style={{ color: '#8b4513', fontWeight: 'bold', marginBottom: '10px' }}>
            📡 当前流转状态：<span style={{ color: '#5a7d5a' }}>{agentState?.status || '加载中...'}</span>
          </div>
        </div>

        {/* 患者智能体 */}
        <div style={boxStyle}>
          <div style={{ color: '#8b4513', fontWeight: 'bold', marginBottom: '10px' }}>🧑‍🦱 患者智能体（采集上报）</div>
          <div style={{ color: '#555', fontSize: '14px', marginBottom: '10px' }}>
            采集数据：{agentState?.raw_data || '暂无'}
          </div>
          <button 
            onClick={handlePatientReport}
            style={{ padding: '8px 16px', borderRadius: '20px', border: '1px solid #8b4513', background: '#8b4513', color: '#fff', cursor: 'pointer' }}
          >
            模拟患者打卡上报
          </button>
        </div>

        {/* 老师智能体 */}
        <div style={{ ...boxStyle, opacity: agentState?.status.includes('待老师审核') || agentState?.is_approved ? 1 : 0.5 }}>
          <div style={{ color: '#8b4513', fontWeight: 'bold', marginBottom: '10px' }}>🤖 老师智能体（生成草案）</div>
          <div style={{ color: '#555', fontSize: '14px', marginBottom: '10px' }}>
            草案内容：{agentState?.ai_draft || '暂无'}
          </div>
          <button 
            onClick={handleTeacherGenerate}
            disabled={!agentState?.status.includes('已上报')}
            style={{ padding: '8px 16px', borderRadius: '20px', border: '1px solid #8b4513', background: '#fdfcf0', color: '#8b4513', cursor: 'pointer' }}
          >
            生成草案
          </button>
        </div>

        {/* 老师真人签字 */}
        <div style={{ ...boxStyle, background: agentState?.is_approved ? '#e8f0e8' : '#fdfcf0' }}>
          <div style={{ color: '#8b4513', fontWeight: 'bold', marginBottom: '10px' }}>👨‍⚕️ 老师（真人审核签字）</div>
          <div style={{ color: '#555', fontSize: '14px', marginBottom: '10px' }}>
            签字状态：{agentState?.is_approved ? '✅ 已签字生效' : '⏳ 未签字'}
          </div>
          <button 
            onClick={handleTeacherApprove}
            disabled={!agentState?.status.includes('待老师审核')}
            style={{ padding: '8px 16px', borderRadius: '20px', border: 'none', background: '#8b4513', color: '#fff', cursor: 'pointer' }}
          >
            审核并签字
          </button>
        </div>

        <div style={{ textAlign: 'center', marginTop: '20px', padding: '10px', borderTop: '1px dashed #d4c8a8', color: '#8b4513', fontSize: '13px', fontWeight: 'bold' }}>
          🔒 数据主权归你所有 · 阅后即焚
        </div>
      </div>
    </div>
  )
}
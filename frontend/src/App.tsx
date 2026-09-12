import { useEffect, useState } from 'react'

interface RecordState {
  content: string
  is_burned: boolean
  message: string
}

export default function App() {
  const [record, setRecord] = useState<RecordState | null>(null)
  const [inputVal, setInputVal] = useState('')

  const fetchRecord = () => {
    fetch('/api/record/view')
      .then(r => r.json())
      .then(d => setRecord(d))
  }

  useEffect(() => {
    fetchRecord()
  }, [])

  const handleSave = () => {
    if (!inputVal.trim()) return alert('请输入病历内容')
    fetch('/api/record/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: inputVal })
    }).then(r => r.json()).then(d => setRecord(d))
  }

  const handleBurn = () => {
    fetch('/api/record/burn', { method: 'POST' })
      .then(r => r.json())
      .then(d => setRecord(d))
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
          知衡 · 数据主权演示台
        </h1>

        {/* 患者端病历录入 */}
        <div style={boxStyle}>
          <div style={{ color: '#8b4513', fontWeight: 'bold', marginBottom: '10px' }}>🧑‍🦱 患者端（病历录入）</div>
          <textarea 
            value={inputVal}
            onChange={(e) => setInputVal(e.target.value)}
            placeholder="例如：今日舌苔偏白，脉细，畏寒..."
            style={{ width: '100%', height: '80px', padding: '10px', boxSizing: 'border-box', borderRadius: '8px', border: '1px solid #d4c8a8', fontFamily: 'serif', marginBottom: '10px' }}
          />
          <button 
            onClick={handleSave}
            style={{ padding: '8px 16px', borderRadius: '20px', border: 'none', background: '#8b4513', color: '#fff', cursor: 'pointer' }}
          >
            提交病历（阅后即焚）
          </button>
        </div>

        {/* 老师端查看与焚毁 */}
        <div style={{ ...boxStyle, background: record?.is_burned ? '#f2f2f2' : '#e8f0e8' }}>
          <div style={{ color: '#8b4513', fontWeight: 'bold', marginBottom: '10px' }}>👨‍⚕️ 老师端（阅后即焚）</div>
          
          {record?.is_burned ? (
            <div style={{ color: '#999', fontStyle: 'italic', padding: '10px', border: '1px dashed #ccc', borderRadius: '8px' }}>
              🔥 该病历已焚毁，老师端无法再查看任何数据
            </div>
          ) : (
            <div style={{ color: '#333', padding: '10px', background: '#fff', borderRadius: '8px', minHeight: '40px', marginBottom: '10px' }}>
              当前病历：{record?.content || '暂无病历'}
            </div>
          )}

          <button 
            onClick={handleBurn}
            disabled={!record?.content || record?.is_burned}
            style={{ padding: '8px 16px', borderRadius: '20px', border: '1px solid #8b4513', background: '#fdfcf0', color: '#8b4513', cursor: record?.content && !record?.is_burned ? 'pointer' : 'not-allowed', opacity: record?.content && !record?.is_burned ? 1 : 0.5 }}
          >
            一键阅后即焚
          </button>
          {record?.message && <div style={{ marginTop: '10px', fontSize: '13px', color: '#5a7d5a' }}>{record.message}</div>}
        </div>

        <div style={{ textAlign: 'center', marginTop: '20px', padding: '10px', borderTop: '1px dashed #d4c8a8', color: '#8b4513', fontSize: '13px', fontWeight: 'bold' }}>
          🔒 数据主权归患者 · 老师端阅后即焚
        </div>
      </div>
    </div>
  )
}
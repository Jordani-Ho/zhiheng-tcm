import { useEffect, useState } from 'react'

interface HuangliData {
  date: string
  lunar: string
  solar_term: string
  health_trend: string
  homework: string
}

export default function App() {
  const [data, setData] = useState<HuangliData | null>(null)

  useEffect(() => {
    fetch('/api/huangli')
      .then(r => r.json())
      .then(d => setData(d))
      .catch(() => setData(null))
  }, [])

  const boxStyle = {
    background: '#fdfcf0',
    border: '1px solid #d4c8a8',
    borderRadius: '8px',
    padding: '20px',
    marginBottom: '15px',
    boxShadow: '0 2px 4px rgba(0,0,0,0.05)'
  }

  return (
    <div style={{ minHeight: '100vh', background: '#f5f1e6', padding: '20px', fontFamily: 'serif' }}>
      <div style={{ maxWidth: '500px', margin: '0 auto' }}>
        <h1 style={{ textAlign: 'center', color: '#8b4513', borderBottom: '2px solid #8b4513', paddingBottom: '10px' }}>
          知衡 · 中医治未病社区
        </h1>
        
        {!data ? (
          <div style={{ textAlign: 'center', padding: '50px', color: '#666' }}>加载中...</div>
        ) : (
          <>
            <div style={boxStyle}>
              <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#333' }}>{data.date}</div>
              <div style={{ color: '#666', marginTop: '5px' }}>{data.lunar}</div>
            </div>

            <div style={boxStyle}>
              <div style={{ fontSize: '18px', color: '#8b4513', fontWeight: 'bold' }}>🌿 节气提示 · {data.solar_term}</div>
              <div style={{ marginTop: '10px', lineHeight: '1.6' }}>{data.health_trend}</div>
            </div>

            <div style={boxStyle}>
              <div style={{ fontSize: '18px', color: '#8b4513', fontWeight: 'bold' }}>📝 今日作业</div>
              <div style={{ marginTop: '10px', lineHeight: '1.6', padding: '10px', background: '#fff8e7', borderRadius: '4px' }}>
                {data.homework}
              </div>
            </div>
            
            <div style={{ textAlign: 'center', color: '#999', fontSize: '12px', marginTop: '20px' }}>
              数据主权归你所有 · 阅后即焚
            </div>
          </>
        )}
      </div>
    </div>
  )
}
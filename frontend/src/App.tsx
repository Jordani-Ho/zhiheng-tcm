import { useEffect, useState } from 'react'

export default function App() {
  const [status, setStatus] = useState('检查中...')

  useEffect(() => {
    fetch('/api/health')
      .then(r => r.json())
      .then(d => setStatus(`后端已连接：${d.service}`))
      .catch(() => setStatus('对接失败，请检查后端'))
  }, [])

  return (
    <div style={{ padding: 40, fontFamily: 'sans-serif' }}>
      <h1>知衡 · 中医治未病社区</h1>
      <p>状态：{status}</p>
    </div>
  )
}

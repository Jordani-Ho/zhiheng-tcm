import { Component, StrictMode } from 'react'
import type { ErrorInfo, ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

/**
 * 【Epic 4 / 批 1 止血】極薄錯誤邊界（唯一職責：把「整站白屏」降級為「局部錯誤提示」）。
 *
 * 背景：flag on 時師門上下文探測未完成前，首屏讀接口會拿到 400 `lineage_required`
 * （響應體 `{detail:{error,msg,...}}`，而 `r.json()` **成功**）→ 錯誤體被當數據 setState
 * → 渲染期拋異常。本倉此前**沒有任何** ErrorBoundary，React 在渲染期遇到未捕獲異常
 * 會卸載整棵樹 = 白屏。
 *
 * 紀律（與本倉既有風格一致）：
 *   · 只兜「渲染期異常」，不改任何業務邏輯、不重試任何請求（重試屬批 2「就緒門」的職責）；
 *   · 文案一律繁體古字（Epic 1 §13.4 / 決策 11），視覺沿用 serif + 主色 #8b4513；
 *   · 詳情只顯示 `Error.message` 的**字符串**，不直接渲染異常對象（否則會二次拋錯）。
 */
class AppErrorBoundary extends Component<{ children: ReactNode }, { message: string }> {
  state = { message: '' }

  static getDerivedStateFromError(error: unknown) {
    return { message: error instanceof Error ? error.message : '未知錯誤' }
  }

  componentDidCatch(error: unknown, info: ErrorInfo) {
    // 只留痕、不做任何恢復動作：控制台裡的原始堆疊是排查白屏的第一手證據。
    console.error('【知衡】介面渲染異常（已由 ErrorBoundary 兜住，未白屏）', error, info)
  }

  render() {
    if (!this.state.message) return this.props.children
    return (
      <div style={{
        maxWidth: 520, margin: '80px auto', padding: '24px', border: '1px solid #d4c8a8',
        borderRadius: '10px', background: '#fdfcf0', color: '#8b4513', fontFamily: 'serif',
        textAlign: 'center', lineHeight: 1.9
      }}>
        <div style={{ fontSize: '20px', fontWeight: 'bold', marginBottom: '10px' }}>🏮 此處暫未能顯示</div>
        <div style={{ fontSize: '14px' }}>介面出了點狀況，其餘功能不受影響。請重新載入後再試。</div>
        <div style={{ fontSize: '12px', color: '#a08a6a', marginTop: '10px', wordBreak: 'break-all' }}>{this.state.message}</div>
        <button
          onClick={() => window.location.reload()}
          style={{
            marginTop: '16px', padding: '8px 20px', borderRadius: '6px', border: 'none',
            background: '#8b4513', color: '#fdfcf0', fontFamily: 'serif', fontSize: '14px', cursor: 'pointer'
          }}
        >重新載入</button>
      </div>
    )
  }
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AppErrorBoundary>
      <App />
    </AppErrorBoundary>
  </StrictMode>,
)

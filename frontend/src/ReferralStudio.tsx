/**
 * C 板塊「引薦鏈（引薦管理）」老師端寫側頁面
 *
 * 對齊：docs/phase3-governance-design.md §3（引薦鏈）+ §10.1（前端影響）
 *   §3.2  老師引薦老師：referral_reason 必填，不得自引薦
 *   §3.4  引薦人主動撤回 = 無影響
 *   §10.1 老師端：引薦列表、發起引薦、撤回背書
 *
 * 後端契約（本檔只讀不改，接口一字不動）：
 *   GET  /api/referral/chain/{agent_id}?direction=both  → {as_referrer:[...], as_referee:[...]}
 *   POST /api/referral/teacher    body {referrer_id, referee_id, referral_reason}  → {referral_id}
 *   POST /api/referral/{id}/revoke body {revoke_reason?}  → {revoked, referral_id}
 *   錯誤體：{detail:{error, msg}}（讀 res.detail.error / .msg）
 *   flag off → 404 referral_disabled；其他 4xx/5xx 依錯誤碼
 *
 * 掛載點：老師端「管理」頁籤（同 TemplateStudio）。
 * flag off → 整卡不渲染（探測 = 調 GET chain 拿 404 判斷）。
 *
 * 樣式：沿用存量內聯 style + serif 字體 + 主色 #8b4513。
 */
import { useEffect, useState } from 'react'
import type { CSSProperties } from 'react'

// ---------------------------------------------------------------------------
// API 調用包裝（照 TemplateStudio.callTemplateApi 同款）
// ---------------------------------------------------------------------------
type ApiFailure = { status: number; code: string; msg: string }
type ApiResult<T> = { ok: true; data: T } | { ok: false; failure: ApiFailure }

async function callReferralApi<T>(path: string, init?: RequestInit): Promise<ApiResult<T>> {
  try {
    const res = await fetch(path, init)
    let body: any = null
    try { body = await res.json() } catch { body = null }
    if (!res.ok) {
      const detail = (body && body.detail) || {}
      return {
        ok: false,
        failure: {
          status: res.status,
          code: String(detail.error || 'http_error'),
          msg: String(detail.msg || '請求失敗，請稍後再試'),
        },
      }
    }
    return { ok: true, data: body as T }
  } catch {
    return {
      ok: false,
      failure: { status: 0, code: 'network_error', msg: '網絡異常，請確認後端服務是否在運行' },
    }
  }
}

// ---------------------------------------------------------------------------
// 樣式常數（內聯，不引狀態庫）
// ---------------------------------------------------------------------------
const RS_PRIMARY = '#8b4513'
const RS_BORDER = '#d4c8a8'

const RS_CARD: CSSProperties = {
  background: '#fdfcf0', border: `1px solid ${RS_BORDER}`, borderRadius: '12px',
  padding: '16px', marginBottom: '16px', boxShadow: '0 4px 12px rgba(0,0,0,0.06)',
}
const RS_TITLE: CSSProperties = {
  fontFamily: 'serif', fontSize: '16px', fontWeight: 'bold', color: RS_PRIMARY,
  marginBottom: '12px',
}
const RS_SECTION: CSSProperties = {
  fontFamily: 'serif', fontSize: '14px', fontWeight: 'bold', color: RS_PRIMARY,
  marginTop: '14px', marginBottom: '8px', paddingBottom: '4px',
  borderBottom: `1px dashed ${RS_BORDER}`,
}
const RS_ROW: CSSProperties = {
  display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap',
  padding: '6px 0', borderBottom: '1px dashed #ece3cd',
}
const RS_HINT: CSSProperties = { fontSize: '12px', color: '#8a7a5c' }
const RS_BTN = (disabled: boolean): CSSProperties => ({
  padding: '6px 12px', borderRadius: '6px', border: `1px solid ${RS_PRIMARY}`,
  cursor: disabled ? 'not-allowed' : 'pointer', fontFamily: 'serif', fontSize: '13px',
  backgroundColor: disabled ? '#e8e0c8' : RS_PRIMARY, color: disabled ? '#8a7a5c' : '#fff',
})
const RS_TINY_BTN: CSSProperties = {
  padding: '4px 8px', borderRadius: '4px', border: `1px solid ${RS_PRIMARY}`,
  cursor: 'pointer', fontFamily: 'serif', fontSize: '12px',
  backgroundColor: '#fff', color: RS_PRIMARY,
}
const RS_INPUT: CSSProperties = {
  padding: '6px 10px', borderRadius: '6px', border: `1px solid ${RS_BORDER}`,
  fontFamily: 'serif', fontSize: '13px', width: '100%', boxSizing: 'border-box',
}
const RS_ERROR: CSSProperties = {
  color: '#b03030', fontSize: '13px', marginTop: '8px',
  fontFamily: 'serif', whiteSpace: 'pre-wrap',
}

// ---------------------------------------------------------------------------
// 類型
// ---------------------------------------------------------------------------
type ReferralRow = {
  referral_id: string
  referrer_id: string
  referrer_type: string
  referee_id: string
  referee_type: string
  lineage_id: string | null
  referral_reason: string | null
  created_at: string
  revoked_at: string | null
  revoke_reason: string | null
}
type ChainResponse = { as_referrer?: ReferralRow[]; as_referee?: ReferralRow[] }

// ---------------------------------------------------------------------------
// 主組件
// ---------------------------------------------------------------------------
export function ReferralStudio({ teacherId }: { teacherId: string }) {
  const [flagEnabled, setFlagEnabled] = useState<boolean | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [asReferrer, setAsReferrer] = useState<ReferralRow[]>([])
  const [asReferee, setAsReferee] = useState<ReferralRow[]>([])

  const [refereeId, setRefereeId] = useState('')
  const [reason, setReason] = useState('')
  const [formMsg, setFormMsg] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      const r = await callReferralApi<ChainResponse>(
        `/api/referral/chain/${encodeURIComponent(teacherId)}?direction=both`
      )
      if (cancelled) return
      if (!r.ok) {
        if (r.failure.status === 404 && r.failure.code === 'referral_disabled') {
          setFlagEnabled(false)
        } else {
          setFlagEnabled(true)
          setError(r.failure.msg)
        }
        setLoading(false)
        return
      }
      setFlagEnabled(true)
      setAsReferrer(r.data.as_referrer || [])
      setAsReferee(r.data.as_referee || [])
      setLoading(false)
    }
    load()
    return () => { cancelled = true }
  }, [teacherId])

  async function refresh() {
    const r = await callReferralApi<ChainResponse>(
      `/api/referral/chain/${encodeURIComponent(teacherId)}?direction=both`
    )
    if (r.ok) {
      setAsReferrer(r.data.as_referrer || [])
      setAsReferee(r.data.as_referee || [])
    }
  }

  async function handleCreate() {
    setFormMsg(null)
    if (!refereeId.trim()) { setFormMsg('被引薦人不可為空'); return }
    if (!reason.trim()) { setFormMsg('引薦理由不可為空'); return }
    setBusy(true)
    const r = await callReferralApi<{ referral_id: string }>(
      '/api/referral/teacher',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          referrer_id: teacherId,
          referee_id: refereeId.trim(),
          referral_reason: reason.trim(),
        }),
      }
    )
    setBusy(false)
    if (!r.ok) { setFormMsg(r.failure.msg); return }
    setRefereeId('')
    setReason('')
    setFormMsg('引薦已記錄')
    await refresh()
  }

  async function handleRevoke(referralId: string) {
    setBusy(true)
    const r = await callReferralApi<{ revoked: boolean }>(
      `/api/referral/${encodeURIComponent(referralId)}/revoke`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ revoke_reason: '' }),
      }
    )
    setBusy(false)
    if (!r.ok) { setError(r.failure.msg); return }
    await refresh()
  }

  if (flagEnabled === false) return null

  if (loading) {
    return (
      <div style={RS_CARD}>
        <div style={RS_TITLE}>🔗 引薦管理</div>
        <div style={RS_HINT}>載入中…</div>
      </div>
    )
  }

  return (
    <div style={RS_CARD}>
      <div style={RS_TITLE}>🔗 引薦管理</div>
      {error && <div style={RS_ERROR}>{error}</div>}

      <div style={RS_SECTION}>我引薦的（{asReferrer.length}）</div>
      {asReferrer.length === 0 && <div style={RS_HINT}>尚無引薦記錄</div>}
      {asReferrer.map(row => (
        <div key={row.referral_id} style={RS_ROW}>
          <span style={{ fontFamily: 'serif', fontWeight: 'bold' }}>{row.referee_id}</span>
          <span style={RS_HINT}>{row.referee_type}</span>
          <span style={{ ...RS_HINT, flex: '1 1 120px' }}>
            {row.referral_reason || '（無理由）'}
          </span>
          {row.revoked_at
            ? <span style={RS_HINT}>已撤回</span>
            : <button style={RS_TINY_BTN} disabled={busy}
                onClick={() => handleRevoke(row.referral_id)}>撤回</button>
          }
        </div>
      ))}

      <div style={RS_SECTION}>引薦我的（{asReferee.length}）</div>
      {asReferee.length === 0 && <div style={RS_HINT}>尚無引薦記錄</div>}
      {asReferee.map(row => (
        <div key={row.referral_id} style={RS_ROW}>
          <span style={{ fontFamily: 'serif', fontWeight: 'bold' }}>{row.referrer_id}</span>
          <span style={RS_HINT}>{row.referrer_type}</span>
          <span style={{ ...RS_HINT, flex: '1 1 120px' }}>
            {row.referral_reason || '（無理由）'}
          </span>
          {row.revoked_at && <span style={RS_HINT}>已撤回</span>}
        </div>
      ))}

      <div style={RS_SECTION}>發起新引薦</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        <input
          style={RS_INPUT}
          placeholder="被引薦老師姓名（如：王老師）"
          value={refereeId}
          onChange={e => setRefereeId(e.target.value)}
          disabled={busy}
        />
        <input
          style={RS_INPUT}
          placeholder="引薦理由（一句話，如：此人跟我學過三年）"
          value={reason}
          onChange={e => setReason(e.target.value)}
          disabled={busy}
        />
        <div>
          <button style={RS_BTN(busy)} disabled={busy} onClick={handleCreate}>
            {busy ? '處理中…' : '發起引薦'}
          </button>
        </div>
        {formMsg && <div style={RS_HINT}>{formMsg}</div>}
      </div>
    </div>
  )
}
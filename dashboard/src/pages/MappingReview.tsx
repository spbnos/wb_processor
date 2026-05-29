import { useState, useCallback, useMemo } from 'react'
import {
  CheckCircle, XCircle, ChevronDown, AlertCircle,
  RefreshCw, AlertTriangle, Play, FileText, Loader
} from 'lucide-react'
import { useApi } from '../hooks/useApi'
import { api } from '../api/client'
import ConfidenceBar from '../components/ConfidenceBar'
import Badge from '../components/Badge'
import Spinner from '../components/Spinner'
import { fmt } from '../utils/format'
import type { ReviewItem } from '../types'

const TARGET_FIELDS = [
  'sku','barcode','name','brand','category','date','quantity','price',
  'cost_price','revenue','commission','logistics','net_profit',
  'warehouse','region','campaign_id','ad_spend','impressions',
  'clicks','ctr','cpc','reserved','in_transit','ignore',
]

function levelBadge(level: string) {
  if (level === 'needs_review') return <Badge label="NEEDS REVIEW" variant="warn" />
  if (level === 'low_conf')     return <Badge label="LOW CONF"     variant="error" />
  return <Badge label={level.toUpperCase()} variant="dim" />
}

interface CardProps {
  item: ReviewItem
  onApprove: (id: string, field?: string) => void
  onReject:  (id: string, field: string)  => void
  loading: boolean
}

function ReviewCard({ item, onApprove, onReject, loading }: CardProps) {
  const [customField, setCustomField] = useState(item.suggested_field ?? '')
  const [showCustom, setShowCustom]   = useState(false)

  return (
    <div style={{
      background: 'var(--bg-panel)',
      border: `1px solid ${item.confidence_level === 'low_conf' ? 'rgba(239,68,68,0.25)' : 'var(--border-base)'}`,
      borderRadius: 'var(--radius)', padding: '16px 18px',
      animation: 'slide-in 0.2s ease',
    }}>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', marginBottom:12 }}>
        <div>
          <div style={{ fontFamily:'var(--font-mono)', fontSize:14, fontWeight:600, color:'var(--text-white)' }}>
            {item.source_column}
          </div>
          <div style={{ fontFamily:'var(--font-mono)', fontSize:9, color:'var(--text-dim)', marginTop:2 }}>
            {fmt.date ? fmt.date(item.created_at) : item.created_at.slice(0,10)}
          </div>
        </div>
        {levelBadge(item.confidence_level)}
      </div>

      <div style={{
        background:'var(--bg-raised)', border:'1px solid var(--border-dim)',
        borderRadius:'var(--radius-sm)', padding:'10px 12px', marginBottom:10,
      }}>
        <div style={{ display:'flex', justifyContent:'space-between', marginBottom:6 }}>
          <span style={{ fontFamily:'var(--font-mono)', fontSize:9, color:'var(--text-dim)' }}>ПРЕДЛОЖЕНИЕ</span>
          <span style={{ fontFamily:'var(--font-mono)', fontSize:9, color:'var(--text-dim)' }}>{item.match_method}</span>
        </div>
        <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:8 }}>
          <code style={{ fontFamily:'var(--font-mono)', fontSize:13, color:'var(--amber)', fontWeight:600 }}>
            {item.suggested_field ?? '—'}
          </code>
          <span style={{ color:'var(--text-dim)', fontSize:10 }}>({item.suggested_type})</span>
        </div>
        <ConfidenceBar score={item.confidence_score} level={item.confidence_level} />
        {item.runner_up_field && (
          <div style={{ marginTop:6, fontFamily:'var(--font-mono)', fontSize:9, color:'var(--text-dim)' }}>
            Alt: <code style={{ color:'var(--text-muted)' }}>{item.runner_up_field}</code> ({(item.runner_up_score * 100).toFixed(0)}%)
          </div>
        )}
      </div>

      {item.sample_values.length > 0 && (
        <div style={{ marginBottom:10 }}>
          <div style={{ fontFamily:'var(--font-mono)', fontSize:9, color:'var(--text-dim)', marginBottom:4 }}>ДАННЫЕ</div>
          <div style={{ display:'flex', gap:4, flexWrap:'wrap' }}>
            {item.sample_values.map((v, i) => (
              <code key={i} style={{
                fontFamily:'var(--font-mono)', fontSize:10,
                background:'var(--bg-raised)', border:'1px solid var(--border-dim)',
                padding:'1px 6px', borderRadius:3, color:'var(--text-base)',
              }}>{String(v)}</code>
            ))}
          </div>
        </div>
      )}

      {showCustom && (
        <div style={{ marginBottom:10 }}>
          <div style={{ fontFamily:'var(--font-mono)', fontSize:9, color:'var(--text-dim)', marginBottom:4 }}>ВЫБРАТЬ ПОЛЕ</div>
          <div style={{ display:'flex', gap:4, flexWrap:'wrap' }}>
            {TARGET_FIELDS.map(f => (
              <button key={f} onClick={() => setCustomField(f)} style={{
                padding:'2px 8px', borderRadius:3, cursor:'pointer',
                background: customField === f ? 'var(--amber-glow)' : 'var(--bg-raised)',
                border: `1px solid ${customField === f ? 'var(--amber)' : 'var(--border-dim)'}`,
                color: customField === f ? 'var(--amber)' : 'var(--text-muted)',
                fontFamily:'var(--font-mono)', fontSize:9, transition:'all 0.1s',
              }}>{f}</button>
            ))}
          </div>
        </div>
      )}

      <div style={{ display:'flex', gap:6 }}>
        <button onClick={() => onApprove(item.id, item.suggested_field ?? undefined)}
          disabled={loading} style={{
            flex:1, display:'flex', alignItems:'center', justifyContent:'center', gap:5,
            padding:'7px', borderRadius:'var(--radius-sm)',
            background:'var(--green-dim)', border:'1px solid var(--green)',
            color:'var(--green)', cursor: loading ? 'not-allowed' : 'pointer',
            fontFamily:'var(--font-mono)', fontSize:10, fontWeight:500,
            opacity: loading ? 0.5 : 1, transition:'all 0.15s',
          }}>
          {loading ? <Loader size={11} style={{animation:'spin 1s linear infinite'}}/> : <CheckCircle size={11}/>}
          ОДОБРИТЬ
        </button>
        <button onClick={() => setShowCustom(s => !s)} style={{
          padding:'7px 10px', borderRadius:'var(--radius-sm)', cursor:'pointer',
          background:'var(--bg-raised)', border:'1px solid var(--border-base)',
          color:'var(--text-muted)', fontFamily:'var(--font-mono)', fontSize:10,
        }}>
          <ChevronDown size={11} style={{ transform: showCustom ? 'rotate(180deg)' : 'none', transition:'0.2s' }}/>
        </button>
        {showCustom && customField && customField !== item.suggested_field && (
          <button onClick={() => onReject(item.id, customField)} disabled={loading} style={{
            flex:1, display:'flex', alignItems:'center', justifyContent:'center', gap:5,
            padding:'7px', borderRadius:'var(--radius-sm)',
            background:'var(--red-dim)', border:'1px solid var(--red)',
            color:'var(--red)', cursor: loading ? 'not-allowed' : 'pointer',
            fontFamily:'var(--font-mono)', fontSize:10, fontWeight:500,
            opacity: loading ? 0.5 : 1, transition:'all 0.15s',
          }}>
            <XCircle size={11}/> → {customField}
          </button>
        )}
      </div>
    </div>
  )
}

// Группа items одного файла
interface GroupProps {
  filename: string
  structHash: string
  items: ReviewItem[]
  resolvedIds: Set<string>
  applyingHash: string | null
  onApprove: (id: string, field?: string) => void
  onReject:  (id: string, field: string) => void
  onApply:   (hash: string) => void
  resolvingId: string | null
}

function FileGroup({ filename, structHash, items, resolvedIds, applyingHash, onApprove, onReject, onApply, resolvingId }: GroupProps) {
  const pending   = items.filter(i => !resolvedIds.has(i.id))
  const resolved  = items.filter(i => resolvedIds.has(i.id))
  const total     = items.length
  const doneCount = resolved.length
  const allDone   = doneCount === total
  const isApplying = applyingHash === structHash
  const progress  = total > 0 ? Math.round((doneCount / total) * 100) : 0

  return (
    <div style={{
      background:'var(--bg-panel)',
      border:`1px solid ${allDone ? 'rgba(34,197,94,0.3)' : 'var(--border-base)'}`,
      borderRadius:'var(--radius-lg)', marginBottom:20, overflow:'hidden',
    }}>
      {/* Group header */}
      <div style={{
        padding:'14px 18px', display:'flex', alignItems:'center', gap:12,
        borderBottom:'1px solid var(--border-dim)',
        background: allDone ? 'rgba(34,197,94,0.04)' : 'var(--bg-raised)',
      }}>
        <FileText size={14} color="var(--text-dim)"/>
        <div style={{ flex:1 }}>
          <div style={{ fontFamily:'var(--font-display)', fontSize:13, fontWeight:700, color:'var(--text-white)' }}>
            {filename}
          </div>
          <div style={{ fontFamily:'var(--font-mono)', fontSize:9, color:'var(--text-dim)', marginTop:2 }}>
            {structHash.slice(0,16)}… · {total} колонок требуют внимания
          </div>
        </div>

        {/* Progress */}
        <div style={{ textAlign:'right', minWidth:80 }}>
          <div style={{ fontFamily:'var(--font-mono)', fontSize:11, color: allDone ? 'var(--green)' : 'var(--amber)', marginBottom:4 }}>
            {doneCount}/{total}
          </div>
          <div style={{ width:80, height:4, background:'var(--bg-base)', borderRadius:2, overflow:'hidden' }}>
            <div style={{
              width:`${progress}%`, height:'100%', borderRadius:2,
              background: allDone ? 'var(--green)' : 'var(--amber)',
              transition:'width 0.4s ease',
            }}/>
          </div>
        </div>

        {/* Apply button */}
        <button
          onClick={() => onApply(structHash)}
          disabled={doneCount === 0 || isApplying}
          style={{
            display:'flex', alignItems:'center', gap:6,
            padding:'7px 14px', borderRadius:'var(--radius-sm)',
            background: allDone ? 'var(--green-dim)' : doneCount > 0 ? 'var(--amber-glow)' : 'var(--bg-raised)',
            border: `1px solid ${allDone ? 'var(--green)' : doneCount > 0 ? 'var(--amber)' : 'var(--border-dim)'}`,
            color: allDone ? 'var(--green)' : doneCount > 0 ? 'var(--amber)' : 'var(--text-dim)',
            fontFamily:'var(--font-mono)', fontSize:10, fontWeight:600,
            cursor: doneCount === 0 || isApplying ? 'not-allowed' : 'pointer',
            opacity: doneCount === 0 ? 0.4 : 1, transition:'all 0.15s',
            letterSpacing:'0.05em',
          }}
        >
          {isApplying
            ? <><Loader size={11} style={{animation:'spin 1s linear infinite'}}/> ПРИМЕНЯЮ…</>
            : <><Play size={11}/> ПРИМЕНИТЬ {doneCount > 0 ? `(${doneCount})` : ''}</>
          }
        </button>
      </div>

      {/* Items grid */}
      {pending.length > 0 && (
        <div style={{ padding:'14px 18px', display:'grid', gridTemplateColumns:'repeat(auto-fill, minmax(380px,1fr))', gap:10 }}>
          {pending.map(item => (
            <ReviewCard key={item.id} item={item}
              onApprove={onApprove} onReject={onReject}
              loading={resolvingId === item.id}
            />
          ))}
        </div>
      )}

      {allDone && doneCount > 0 && !isApplying && (
        <div style={{
          padding:'12px 18px',
          fontFamily:'var(--font-mono)', fontSize:11, color:'var(--green)',
          display:'flex', alignItems:'center', gap:8,
        }}>
          <CheckCircle size={13}/> Все решения приняты — нажми ПРИМЕНИТЬ чтобы загрузить в систему
        </div>
      )}
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────

export default function MappingReview() {
  const { data, loading, error, refetch } = useApi(api.reviewItems, [], 5_000)
  const [resolvingId, setResolvingId]   = useState<string | null>(null)
  const [applyingHash, setApplyingHash] = useState<string | null>(null)
  const [resolvedIds, setResolvedIds]   = useState<Set<string>>(new Set())
  const [applyResults, setApplyResults] = useState<Record<string, string>>({})

  // Группируем по struct_hash
  const groups = useMemo(() => {
    const all = (data ?? []).filter(i => i.status === 'pending')
    const map = new Map<string, { filename: string; items: ReviewItem[] }>()
    for (const item of all) {
      if (!map.has(item.struct_hash)) {
        map.set(item.struct_hash, { filename: item.filename, items: [] })
      }
      map.get(item.struct_hash)!.items.push(item)
    }
    return Array.from(map.entries()).map(([hash, g]) => ({ hash, ...g }))
  }, [data])

  const handleApprove = useCallback(async (id: string, field?: string) => {
    setResolvingId(id)
    try {
      await api.approve(id, field)
      setResolvedIds(s => new Set([...s, id]))
      refetch()
    } catch (e) { console.error('Approve failed:', e) }
    finally { setResolvingId(null) }
  }, [refetch])

  const handleReject = useCallback(async (id: string, field: string) => {
    setResolvingId(id)
    try {
      await api.reject(id, field)
      setResolvedIds(s => new Set([...s, id]))
      refetch()
    } catch (e) { console.error('Reject failed:', e) }
    finally { setResolvingId(null) }
  }, [refetch])

  const handleApply = useCallback(async (hash: string) => {
    setApplyingHash(hash)
    try {
      const result = await api.applyReviews(hash)
      setApplyResults(r => ({ ...r, [hash]: result.message }))
      refetch()
    } catch (e) {
      setApplyResults(r => ({ ...r, [hash]: `Ошибка: ${e}` }))
    } finally {
      setApplyingHash(null)
    }
  }, [refetch])

  const totalPending = groups.reduce((n, g) => {
    const pending = g.items.filter(i => !resolvedIds.has(i.id)).length
    return n + pending
  }, 0)

  return (
    <div style={{ padding:28 }}>
      {/* Header */}
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:24 }}>
        <div>
          <h1 style={{ fontFamily:'var(--font-display)', fontSize:22, fontWeight:800, color:'var(--text-white)', margin:0 }}>
            Mapping Review
          </h1>
          <div style={{ fontFamily:'var(--font-mono)', fontSize:10, color:'var(--text-dim)', marginTop:4 }}>
            Решения SmartMapper · авто-обновление каждые 5с · после одобрения нажми ПРИМЕНИТЬ
          </div>
        </div>
        <div style={{ display:'flex', alignItems:'center', gap:12 }}>
          {totalPending > 0 && (
            <div style={{ fontFamily:'var(--font-mono)', fontSize:12, color:'var(--amber)', display:'flex', alignItems:'center', gap:6 }}>
              <AlertCircle size={14}/> {totalPending} ожидают
            </div>
          )}
          <button onClick={refetch} disabled={loading} style={{
            padding:'6px 10px', borderRadius:'var(--radius-sm)', cursor:'pointer',
            background:'var(--bg-raised)', border:'1px solid var(--border-base)',
            color:'var(--text-muted)', display:'flex', alignItems:'center', gap:5,
            fontFamily:'var(--font-mono)', fontSize:10,
            opacity: loading ? 0.5 : 1,
          }}>
            <RefreshCw size={11} style={{ animation: loading ? 'spin 1s linear infinite' : 'none' }}/>
            ОБНОВИТЬ
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div style={{
          display:'flex', alignItems:'center', gap:10, padding:'12px 16px', marginBottom:16,
          background:'rgba(239,68,68,0.08)', border:'1px solid rgba(239,68,68,0.3)',
          borderRadius:'var(--radius)', fontFamily:'var(--font-mono)', fontSize:11,
        }}>
          <AlertTriangle size={13} color="var(--red)"/>
          <span style={{ color:'var(--red)' }}>Ошибка: {error}</span>
          <button onClick={refetch} style={{
            marginLeft:'auto', padding:'3px 8px',
            background:'transparent', border:'1px solid var(--red)',
            borderRadius:3, color:'var(--red)',
            fontFamily:'var(--font-mono)', fontSize:9, cursor:'pointer',
          }}>RETRY</button>
        </div>
      )}

      {/* Apply results */}
      {Object.entries(applyResults).map(([hash, msg]) => (
        <div key={hash} style={{
          padding:'10px 14px', marginBottom:10,
          background:'rgba(34,197,94,0.07)', border:'1px solid rgba(34,197,94,0.25)',
          borderRadius:'var(--radius)', fontFamily:'var(--font-mono)', fontSize:11, color:'var(--green)',
          display:'flex', alignItems:'center', gap:8,
        }}>
          <CheckCircle size={13}/> {msg}
        </div>
      ))}

      {/* Content */}
      {loading && !data ? (
        <div style={{ display:'flex', justifyContent:'center', padding:60 }}>
          <Spinner size={32}/>
        </div>
      ) : !error && groups.length === 0 ? (
        <div style={{
          textAlign:'center', padding:'60px 20px',
          background:'var(--bg-panel)', border:'1px solid var(--border-dim)',
          borderRadius:'var(--radius-lg)',
        }}>
          <CheckCircle size={40} color="var(--green)" style={{ margin:'0 auto 16px' }}/>
          <div style={{ fontFamily:'var(--font-display)', fontSize:18, fontWeight:700, color:'var(--text-white)' }}>
            Всё обработано
          </div>
          <div style={{ fontFamily:'var(--font-mono)', fontSize:11, color:'var(--text-dim)', marginTop:8 }}>
            SmartMapper справился с маппингом самостоятельно
          </div>
        </div>
      ) : (
        groups.map(g => (
          <FileGroup
            key={g.hash}
            filename={g.filename}
            structHash={g.hash}
            items={g.items}
            resolvedIds={resolvedIds}
            applyingHash={applyingHash}
            onApprove={handleApprove}
            onReject={handleReject}
            onApply={handleApply}
            resolvingId={resolvingId}
          />
        ))
      )}
    </div>
  )
}

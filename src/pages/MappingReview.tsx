import { useState } from 'react'
import { CheckCircle, XCircle, ChevronDown, AlertCircle } from 'lucide-react'
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
  if (level === 'low_conf')     return <Badge label="LOW CONF" variant="error" />
  return <Badge label={level.toUpperCase()} variant="dim" />
}

interface ItemCardProps {
  item: ReviewItem
  onApprove: (id: string, field?: string) => void
  onReject:  (id: string, field: string)  => void
  loading: boolean
}

function ReviewCard({ item, onApprove, onReject, loading }: ItemCardProps) {
  const [customField, setCustomField] = useState(item.suggested_field ?? '')
  const [showCustom, setShowCustom]   = useState(false)

  return (
    <div style={{
      background: 'var(--bg-panel)',
      border: `1px solid ${item.confidence_level === 'low_conf' ? 'rgba(239,68,68,0.3)' : 'var(--border-base)'}`,
      borderRadius: 'var(--radius)',
      padding: '18px 20px',
      animation: 'slide-in 0.25s ease',
    }}>
      {/* Header */}
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', marginBottom:14 }}>
        <div>
          <div style={{
            fontFamily:'var(--font-display)', fontSize:15,
            fontWeight:700, color:'var(--text-white)',
          }}>
            {item.source_column}
          </div>
          <div style={{ fontFamily:'var(--font-mono)', fontSize:9, color:'var(--text-dim)', marginTop:3 }}>
            {item.filename} · {fmt.date(item.created_at)}
          </div>
        </div>
        {levelBadge(item.confidence_level)}
      </div>

      {/* Suggestion */}
      <div style={{
        background:'var(--bg-raised)', border:'1px solid var(--border-dim)',
        borderRadius:'var(--radius-sm)', padding:'10px 14px', marginBottom:12,
      }}>
        <div style={{ display:'flex', justifyContent:'space-between', marginBottom:8 }}>
          <div style={{ fontFamily:'var(--font-mono)', fontSize:10, color:'var(--text-dim)' }}>
            ПРЕДЛОЖЕНИЕ СИСТЕМЫ
          </div>
          <div style={{ fontFamily:'var(--font-mono)', fontSize:10, color:'var(--text-muted)' }}>
            via {item.match_method}
          </div>
        </div>
        <div style={{ display:'flex', alignItems:'center', gap:12, marginBottom:10 }}>
          <code style={{
            fontFamily:'var(--font-mono)', fontSize:13,
            color:'var(--amber)', fontWeight:500,
          }}>
            {item.suggested_field ?? '—'}
          </code>
          <span style={{ color:'var(--text-dim)', fontSize:11 }}>({item.suggested_type})</span>
        </div>
        <ConfidenceBar score={item.confidence_score} level={item.confidence_level} />
        {item.runner_up_field && (
          <div style={{ marginTop:8, fontFamily:'var(--font-mono)', fontSize:10, color:'var(--text-dim)' }}>
            Альтернатива: <code style={{ color:'var(--text-muted)' }}>{item.runner_up_field}</code>
            &nbsp;({fmt.conf(item.runner_up_score)})
          </div>
        )}
      </div>

      {/* Sample values */}
      {item.sample_values.length > 0 && (
        <div style={{ marginBottom:12 }}>
          <div style={{ fontFamily:'var(--font-mono)', fontSize:9, color:'var(--text-dim)', marginBottom:6, letterSpacing:'0.1em' }}>
            ПРИМЕР ДАННЫХ
          </div>
          <div style={{ display:'flex', gap:6, flexWrap:'wrap' }}>
            {item.sample_values.map((v, i) => (
              <code key={i} style={{
                fontFamily:'var(--font-mono)', fontSize:11,
                background:'var(--bg-raised)', border:'1px solid var(--border-dim)',
                padding:'2px 8px', borderRadius:3, color:'var(--text-base)',
              }}>
                {String(v)}
              </code>
            ))}
          </div>
        </div>
      )}

      {/* Custom field selector */}
      {showCustom && (
        <div style={{ marginBottom:12 }}>
          <div style={{ fontFamily:'var(--font-mono)', fontSize:9, color:'var(--text-dim)', marginBottom:6 }}>
            ВЫБРАТЬ ДРУГОЕ ПОЛЕ
          </div>
          <div style={{ display:'flex', gap:6, flexWrap:'wrap' }}>
            {TARGET_FIELDS.map(f => (
              <button key={f} onClick={() => setCustomField(f)} style={{
                padding:'3px 10px', borderRadius:3,
                background: customField === f ? 'var(--amber-glow)' : 'var(--bg-raised)',
                border: `1px solid ${customField === f ? 'var(--amber)' : 'var(--border-dim)'}`,
                color: customField === f ? 'var(--amber)' : 'var(--text-muted)',
                fontFamily:'var(--font-mono)', fontSize:10, cursor:'pointer',
                transition:'all 0.1s',
              }}>
                {f}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Actions */}
      <div style={{ display:'flex', gap:8, marginTop:4 }}>
        <button
          onClick={() => onApprove(item.id, item.suggested_field ?? undefined)}
          disabled={loading}
          style={{
            flex:1, display:'flex', alignItems:'center', justifyContent:'center', gap:6,
            padding:'8px', borderRadius:'var(--radius-sm)',
            background:'var(--green-dim)', border:'1px solid var(--green)',
            color:'var(--green)', cursor:'pointer',
            fontFamily:'var(--font-mono)', fontSize:11, fontWeight:500,
            transition:'all 0.15s',
          }}
        >
          <CheckCircle size={13}/> ОДОБРИТЬ
        </button>

        <button
          onClick={() => setShowCustom(s => !s)}
          style={{
            padding:'8px 12px', borderRadius:'var(--radius-sm)',
            background:'var(--bg-raised)', border:'1px solid var(--border-base)',
            color:'var(--text-muted)', cursor:'pointer',
            fontFamily:'var(--font-mono)', fontSize:11,
            transition:'all 0.15s',
          }}
        >
          <ChevronDown size={13} style={{ transform: showCustom ? 'rotate(180deg)' : 'none', transition:'0.2s' }} />
        </button>

        {showCustom && customField !== item.suggested_field && (
          <button
            onClick={() => onReject(item.id, customField)}
            disabled={loading}
            style={{
              flex:1, display:'flex', alignItems:'center', justifyContent:'center', gap:6,
              padding:'8px', borderRadius:'var(--radius-sm)',
              background:'var(--red-dim)', border:'1px solid var(--red)',
              color:'var(--red)', cursor:'pointer',
              fontFamily:'var(--font-mono)', fontSize:11,
              transition:'all 0.15s',
            }}
          >
            <XCircle size={13}/> ИСПРАВИТЬ → {customField}
          </button>
        )}
      </div>
    </div>
  )
}

export default function MappingReview() {
  const { data, loading, refetch } = useApi(api.reviewItems, [])
  const [resolving, setResolving] = useState<string | null>(null)
  const [resolved, setResolved]   = useState<Set<string>>(new Set())

  const pending = (data ?? []).filter(i => i.status === 'pending' && !resolved.has(i.id))

  async function handleApprove(id: string, field?: string) {
    setResolving(id)
    try {
      await api.approve(id, field)
      setResolved(s => new Set([...s, id]))
    } finally { setResolving(null) }
  }

  async function handleReject(id: string, field: string) {
    setResolving(id)
    try {
      await api.reject(id, field)
      setResolved(s => new Set([...s, id]))
    } finally { setResolving(null) }
  }

  return (
    <div style={{ padding:28 }}>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:24 }}>
        <div>
          <h1 style={{
            fontFamily:'var(--font-display)', fontSize:22,
            fontWeight:800, color:'var(--text-white)',
          }}>
            Mapping Review
          </h1>
          <div style={{ fontFamily:'var(--font-mono)', fontSize:10, color:'var(--text-dim)', marginTop:4 }}>
            Решения SmartMapper требующие подтверждения
          </div>
        </div>
        {pending.length > 0 && (
          <div style={{
            fontFamily:'var(--font-mono)', fontSize:12, color:'var(--amber)',
            display:'flex', alignItems:'center', gap:8,
          }}>
            <AlertCircle size={16} />
            {pending.length} ожидают
          </div>
        )}
      </div>

      {loading ? (
        <div style={{ display:'flex', justifyContent:'center', padding:60 }}>
          <Spinner size={32} />
        </div>
      ) : pending.length === 0 ? (
        <div style={{
          textAlign:'center', padding:'60px 20px',
          background:'var(--bg-panel)', border:'1px solid var(--border-dim)',
          borderRadius:'var(--radius-lg)',
        }}>
          <CheckCircle size={40} color="var(--green)" style={{ margin:'0 auto 16px' }} />
          <div style={{ fontFamily:'var(--font-display)', fontSize:18, fontWeight:700, color:'var(--text-white)' }}>
            Всё обработано
          </div>
          <div style={{ fontFamily:'var(--font-mono)', fontSize:11, color:'var(--text-dim)', marginTop:8 }}>
            SmartMapper справился с маппингом самостоятельно
          </div>
        </div>
      ) : (
        <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill, minmax(440px, 1fr))', gap:14 }}>
          {pending.map(item => (
            <ReviewCard
              key={item.id}
              item={item}
              onApprove={handleApprove}
              onReject={handleReject}
              loading={resolving === item.id}
            />
          ))}
        </div>
      )}
    </div>
  )
}

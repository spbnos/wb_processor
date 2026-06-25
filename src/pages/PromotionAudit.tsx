/**
 * PromotionAudit.tsx — Аудит рекламных кампаний WB (live API)
 * Источник: api/routes/promotion_audit.py → integrations/wb_api/promotion_audit_service.py
 * Read-only аудит: список РК, статистика по товарам, конверсии, категории WB.
 */
import { useState } from 'react'
import {
  Megaphone, DollarSign, MousePointerClick, Eye, ShoppingCart,
  RefreshCw, AlertTriangle, ChevronDown, ChevronUp, Layers, Wallet,
} from 'lucide-react'
import { useApi } from '../hooks/useApi'
import { api } from '../api/client'
import Spinner from '../components/Spinner'

// ── helpers (идентичны WBCommissions.tsx) ───────────────────────────────────
function rub(n: number | null | undefined) {
  if (!n && n !== 0) return '—'
  return `${new Intl.NumberFormat('ru-RU').format(Math.round(n as number))} ₽`
}
function pct(n: number | null | undefined, d = 1) {
  if (n === null || n === undefined || isNaN(n as number)) return '—'
  return `${(n as number).toFixed(d)}%`
}
function num(n: number | null | undefined) {
  if (!n && n !== 0) return '—'
  return new Intl.NumberFormat('ru-RU').format(Math.round(n as number))
}

function SectionTitle({ title }: { title: string }) {
  return <div style={{ fontFamily:'var(--font-mono)', fontSize:9, color:'var(--text-dim)',
    letterSpacing:'0.12em', marginBottom:10, textTransform:'uppercase' }}>{title}</div>
}
function KPI({ label, value, sub, accent, warn, icon }: any) {
  return (
    <div style={{
      background:'var(--bg-panel)', borderRadius:'var(--radius)', padding:'13px 15px',
      border:`1px solid ${warn?'rgba(239,68,68,.3)':accent?'rgba(245,158,11,.3)':'var(--border-dim)'}`,
    }}>
      <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:5}}>
        <span style={{fontFamily:'var(--font-mono)',fontSize:8,color:'var(--text-dim)',letterSpacing:'0.1em'}}>{label}</span>
        <span style={{color:'var(--text-dim)',opacity:.5}}>{icon}</span>
      </div>
      <div style={{fontFamily:'var(--font-display)',fontSize:19,fontWeight:800,
        color:warn?'var(--red)':accent?'var(--amber)':'var(--text-white)',lineHeight:1.1}}>{value}</div>
      {sub && <div style={{fontFamily:'var(--font-mono)',fontSize:9,color:'var(--text-dim)',marginTop:3}}>{sub}</div>}
    </div>
  )
}

function StatusBadge({ label, statusCode }: { label: string; statusCode: number }) {
  const isActive = statusCode === 9
  const isPaused = statusCode === 11
  const color = isActive ? 'var(--green)' : isPaused ? 'var(--amber)' : 'var(--text-dim)'
  const bg = isActive ? 'rgba(16,185,129,.12)' : isPaused ? 'rgba(245,158,11,.12)' : 'rgba(255,255,255,.04)'
  return (
    <span style={{ padding:'2px 8px', borderRadius:4, fontFamily:'var(--font-mono)',
      fontSize:9, fontWeight:600, color, background:bg }}>{label}</span>
  )
}

type CampaignRow = {
  advert_id: number; name: string; type_label: string; status_code: number; status_label: string
  payment_type: string; daily_budget: number; start_time: string
  subjects: { subjectId: number; subjectName: string }[]
  nm_ids: number[]
  views: number; clicks: number; ctr: number; cpc: number; cr: number
  atbs: number; orders: number; shks: number; sum_spent: number; sum_price: number
  products: { date: string; nmId: number; name: string; views: number; clicks: number
              orders: number; shks: number; sum: number; sum_price: number }[]
  stats_warning: string
}

function CampaignCard({ c }: { c: CampaignRow }) {
  const [expanded, setExpanded] = useState(false)
  const roi = c.sum_spent > 0 ? ((c.sum_price - c.sum_spent) / c.sum_spent) * 100 : null

  return (
    <div style={{ background:'var(--bg-panel)', border:'1px solid var(--border-dim)',
      borderRadius:'var(--radius)', marginBottom:8, overflow:'hidden' }}>
      <div
        onClick={() => setExpanded(e => !e)}
        style={{ display:'flex', alignItems:'center', gap:12, padding:'10px 14px', cursor:'pointer' }}
      >
        {expanded ? <ChevronUp size={13} color="var(--text-dim)"/> : <ChevronDown size={13} color="var(--text-dim)"/>}
        <div style={{ flex:1, minWidth:0 }}>
          <div style={{ display:'flex', alignItems:'center', gap:8 }}>
            <span style={{ fontFamily:'var(--font-mono)', fontSize:11, color:'var(--text-white)', fontWeight:600 }}>
              {c.name}
            </span>
            <StatusBadge label={c.status_label} statusCode={c.status_code} />
            <span style={{ fontFamily:'var(--font-mono)', fontSize:8, color:'var(--text-dim)' }}>{c.type_label}</span>
          </div>
          <div style={{ fontFamily:'var(--font-mono)', fontSize:8, color:'var(--text-dim)', marginTop:2 }}>
            ID {c.advert_id} · {c.subjects.map(s => s.subjectName).filter(Boolean).join(', ') || 'без категории'}
            {c.start_time ? ` · старт ${c.start_time.slice(0,10)}` : ''}
          </div>
        </div>
        <div style={{ display:'flex', gap:18, fontFamily:'var(--font-mono)', fontSize:10 }}>
          <div style={{ textAlign:'right' }}>
            <div style={{ color:'var(--text-dim)', fontSize:8 }}>Показы</div>
            <div style={{ color:'var(--text-white)' }}>{num(c.views)}</div>
          </div>
          <div style={{ textAlign:'right' }}>
            <div style={{ color:'var(--text-dim)', fontSize:8 }}>CTR</div>
            <div style={{ color:'var(--text-white)' }}>{pct(c.ctr)}</div>
          </div>
          <div style={{ textAlign:'right' }}>
            <div style={{ color:'var(--text-dim)', fontSize:8 }}>CR</div>
            <div style={{ color:'var(--text-white)' }}>{pct(c.cr)}</div>
          </div>
          <div style={{ textAlign:'right' }}>
            <div style={{ color:'var(--text-dim)', fontSize:8 }}>Расход</div>
            <div style={{ color:'var(--amber)' }}>{rub(c.sum_spent)}</div>
          </div>
          <div style={{ textAlign:'right', minWidth:60 }}>
            <div style={{ color:'var(--text-dim)', fontSize:8 }}>ROI</div>
            <div style={{ color: roi === null ? 'var(--text-dim)' : roi >= 0 ? 'var(--green)' : 'var(--red)' }}>
              {roi === null ? '—' : pct(roi)}
            </div>
          </div>
        </div>
      </div>

      {c.stats_warning && (
        <div style={{ margin:'0 14px 10px', padding:'8px 10px', borderRadius:4,
          background:'rgba(245,158,11,.08)', border:'1px solid rgba(245,158,11,.25)',
          display:'flex', gap:8, alignItems:'flex-start' }}>
          <AlertTriangle size={12} color="var(--amber)" style={{ flexShrink:0, marginTop:1 }}/>
          <span style={{ fontFamily:'var(--font-mono)', fontSize:9, color:'var(--amber)' }}>{c.stats_warning}</span>
        </div>
      )}

      {expanded && (
        <div style={{ padding:'0 14px 14px' }}>
          <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:8, marginBottom:12 }}>
            <KPI label="БЮДЖЕТ/ДЕНЬ" value={rub(c.daily_budget)} icon={<Wallet size={11}/>} />
            <KPI label="КЛИКИ" value={num(c.clicks)} icon={<MousePointerClick size={11}/>} />
            <KPI label="ДОБ. В КОРЗИНУ" value={num(c.atbs)} icon={<ShoppingCart size={11}/>} />
            <KPI label="ЗАКАЗЫ / ШТ." value={`${num(c.orders)} / ${num(c.shks)}`} icon={<ShoppingCart size={11}/>} />
          </div>

          {c.products.length === 0 ? (
            <div style={{ fontFamily:'var(--font-mono)', fontSize:10, color:'var(--text-dim)', padding:'8px 0' }}>
              Нет детальной статистики по товарам за выбранный период.
            </div>
          ) : (
            <>
              <SectionTitle title={`Статистика по товарам (${c.products.length} записей)`} />
              <div style={{ overflowX:'auto' }}>
                <table style={{ width:'100%', borderCollapse:'collapse' }}>
                  <thead>
                    <tr style={{ borderBottom:'1px solid var(--border-dim)' }}>
                      {['Дата','nmId','Товар','Показы','Клики','Заказы','Шт.','Расход','Сумма продаж'].map(h => (
                        <th key={h} style={{ textAlign:'left', padding:'4px 8px', fontFamily:'var(--font-mono)',
                          fontSize:8, color:'var(--text-dim)', letterSpacing:'0.06em' }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {c.products.slice(0, 100).map((p, i) => (
                      <tr key={i} style={{ borderBottom:'1px solid var(--border-dim)' }}>
                        <td style={cellStyle}>{p.date}</td>
                        <td style={cellStyle}>{p.nmId}</td>
                        <td style={{ ...cellStyle, maxWidth:200, overflow:'hidden', textOverflow:'ellipsis' }}>{p.name || '—'}</td>
                        <td style={cellStyle}>{num(p.views)}</td>
                        <td style={cellStyle}>{num(p.clicks)}</td>
                        <td style={cellStyle}>{num(p.orders)}</td>
                        <td style={cellStyle}>{num(p.shks)}</td>
                        <td style={{ ...cellStyle, color:'var(--amber)' }}>{rub(p.sum)}</td>
                        <td style={{ ...cellStyle, color:'var(--green)' }}>{rub(p.sum_price)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}

const cellStyle: React.CSSProperties = {
  padding:'4px 8px', fontFamily:'var(--font-mono)', fontSize:9, color:'var(--text-base)',
}

export default function PromotionAudit() {
  const today = new Date()
  const weekAgo = new Date(today.getTime() - 7 * 86400_000)
  const [dateFrom, setDateFrom] = useState(weekAgo.toISOString().slice(0, 10))
  const [dateTo, setDateTo] = useState(today.toISOString().slice(0, 10))

  const params = `date_from=${dateFrom}&date_to=${dateTo}`
  const { data, loading, error, refetch } = useApi(() => api.promotionAuditRun(params), [params])
  const report = data as any

  const campaigns: CampaignRow[] = report?.campaigns ?? []
  const totalViews = campaigns.reduce((s, c) => s + (c.views || 0), 0)
  const totalClicks = campaigns.reduce((s, c) => s + (c.clicks || 0), 0)
  const totalSpent = campaigns.reduce((s, c) => s + (c.sum_spent || 0), 0)
  const totalOrders = campaigns.reduce((s, c) => s + (c.orders || 0), 0)
  const avgCtr = totalViews > 0 ? (totalClicks / totalViews) * 100 : 0
  const activeCampaigns = campaigns.filter(c => c.status_code === 9).length

  return (
    <div style={{ padding:'20px 24px' }}>
      <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:16 }}>
        <div style={{ display:'flex', alignItems:'center', gap:10 }}>
          <Megaphone size={18} color="var(--amber)" />
          <h1 style={{ fontFamily:'var(--font-display)', fontSize:16, fontWeight:700, color:'var(--text-white)', margin:0 }}>
            Аудит рекламных кампаний
          </h1>
        </div>
        <div style={{ display:'flex', alignItems:'center', gap:8 }}>
          <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)}
            style={inputStyle} />
          <span style={{ color:'var(--text-dim)', fontSize:10 }}>—</span>
          <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)}
            style={inputStyle} />
          <button onClick={refetch} style={{
            display:'flex', alignItems:'center', gap:6, padding:'6px 12px',
            background:'var(--bg-panel)', border:'1px solid var(--border-dim)',
            borderRadius:'var(--radius)', color:'var(--text-base)', fontFamily:'var(--font-mono)',
            fontSize:10, cursor:'pointer',
          }}>
            <RefreshCw size={11} className={loading ? 'spin' : ''} /> Обновить
          </button>
        </div>
      </div>

      {loading && !report && (
        <div style={{ display:'flex', justifyContent:'center', padding:40 }}><Spinner /></div>
      )}

      {error && (
        <div style={{ padding:'12px 16px', borderRadius:'var(--radius)', background:'rgba(239,68,68,.08)',
          border:'1px solid rgba(239,68,68,.25)', color:'var(--red)', fontFamily:'var(--font-mono)',
          fontSize:11, marginBottom:16 }}>
          {String(error)}
        </div>
      )}

      {report?.errors?.length > 0 && (
        <div style={{ marginBottom:16 }}>
          {report.errors.map((e: string, i: number) => (
            <div key={i} style={{ padding:'8px 12px', borderRadius:4, background:'rgba(245,158,11,.07)',
              border:'1px solid rgba(245,158,11,.2)', marginBottom:6, display:'flex', gap:8,
              fontFamily:'var(--font-mono)', fontSize:10, color:'var(--amber)' }}>
              <AlertTriangle size={12} style={{ flexShrink:0, marginTop:1 }} /> {e}
            </div>
          ))}
        </div>
      )}

      {report && (
        <>
          <div style={{ display:'grid', gridTemplateColumns:'repeat(6,1fr)', gap:8, marginBottom:16 }}>
            <KPI label="АКТИВНЫХ РК" value={num(activeCampaigns)} sub={`из ${campaigns.length} всего`} icon={<Layers size={12}/>} />
            <KPI label="ПОКАЗЫ" value={num(totalViews)} icon={<Eye size={12}/>} />
            <KPI label="КЛИКИ" value={num(totalClicks)} sub={`CTR ${pct(avgCtr)}`} icon={<MousePointerClick size={12}/>} />
            <KPI label="ЗАКАЗЫ" value={num(totalOrders)} icon={<ShoppingCart size={12}/>} />
            <KPI label="РАСХОД ЗА ПЕРИОД" value={rub(totalSpent)} accent icon={<DollarSign size={12}/>} />
            <KPI label="БАЛАНС КАБИНЕТА" value={rub(report.balance?.balance)}
              sub={report.balance?.bonus ? `+ ${rub(report.balance.bonus)} бонусов` : undefined}
              icon={<Wallet size={12}/>} />
          </div>

          <SectionTitle title={`Кампании (${campaigns.length})`} />
          {campaigns.length === 0 ? (
            <div style={{ fontFamily:'var(--font-mono)', fontSize:11, color:'var(--text-dim)', padding:'20px 0' }}>
              Кампании не найдены за выбранный период, либо WB API ключ не настроен (см. ошибки выше).
            </div>
          ) : (
            campaigns.map(c => <CampaignCard key={c.advert_id} c={c} />)
          )}

          {report.categories?.length > 0 && (
            <div style={{ marginTop:20 }}>
              <SectionTitle title={`Категории WB, доступные для РК (${report.categories.length})`} />
              <div style={{ display:'flex', flexWrap:'wrap', gap:6 }}>
                {report.categories.slice(0, 60).map((cat: any) => (
                  <span key={cat.id} style={{
                    padding:'4px 10px', borderRadius:4, background:'var(--bg-panel)',
                    border:'1px solid var(--border-dim)', fontFamily:'var(--font-mono)',
                    fontSize:9, color:'var(--text-base)',
                  }}>
                    {cat.name} <span style={{ color:'var(--text-dim)' }}>({num(cat.count)})</span>
                  </span>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}

const inputStyle: React.CSSProperties = {
  padding:'6px 10px', background:'var(--bg-panel)', border:'1px solid var(--border-dim)',
  borderRadius:'var(--radius)', color:'var(--text-base)', fontFamily:'var(--font-mono)', fontSize:10,
}

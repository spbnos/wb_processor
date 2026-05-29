import { useState, useMemo } from 'react'
import {
  TrendingUp, Package, DollarSign, BarChart2,
  AlertTriangle, RefreshCw, Truck, ShoppingBag, RotateCcw
} from 'lucide-react'
import { useApi } from '../hooks/useApi'
import { api } from '../api/client'
import { fmt } from '../utils/format'
import Spinner from '../components/Spinner'
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, PieChart, Pie, Cell, Legend,
} from 'recharts'

// ── Colors ──────────────────────────────────────────────────────────
const C = {
  amber:  '#f59e0b',
  green:  '#10b981',
  blue:   '#3b82f6',
  red:    '#ef4444',
  purple: '#8b5cf6',
  teal:   '#14b8a6',
}
const PIE_COLORS = [C.amber, C.green, C.blue, C.red, C.purple, C.teal]

const TT_STYLE = {
  backgroundColor: 'var(--bg-raised)',
  border: '1px solid var(--border-base)',
  borderRadius: 6,
  fontFamily: 'var(--font-mono)',
  fontSize: 11,
  color: 'var(--text-base)',
}

// ── KPI card ────────────────────────────────────────────────────────
function KPI({ label, value, sub, accent = false, icon }: {
  label: string; value: string; sub?: string; accent?: boolean; icon?: React.ReactNode
}) {
  return (
    <div style={{
      background: 'var(--bg-panel)',
      border: `1px solid ${accent ? 'rgba(245,158,11,0.3)' : 'var(--border-dim)'}`,
      borderRadius: 'var(--radius)',
      padding: '16px 18px',
      display: 'flex', flexDirection: 'column', gap: 6,
      minWidth: 0,
    }}>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center' }}>
        <div style={{ fontFamily:'var(--font-mono)', fontSize:9, color:'var(--text-dim)', letterSpacing:'0.1em' }}>
          {label}
        </div>
        {icon && <div style={{ color:'var(--text-dim)', opacity:.6 }}>{icon}</div>}
      </div>
      <div style={{
        fontFamily: 'var(--font-display)', fontSize: 22, fontWeight: 800,
        color: accent ? 'var(--amber)' : 'var(--text-white)',
        lineHeight: 1.1,
      }}>{value}</div>
      {sub && (
        <div style={{ fontFamily:'var(--font-mono)', fontSize:9, color:'var(--text-dim)' }}>{sub}</div>
      )}
    </div>
  )
}

// ── Section header ───────────────────────────────────────────────────
function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 24 }}>
      <div style={{
        fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-dim)',
        letterSpacing: '0.12em', marginBottom: 10, textTransform: 'uppercase',
      }}>{title}</div>
      {children}
    </div>
  )
}

// ── Tab ──────────────────────────────────────────────────────────────
function Tab({ label, active, onClick, count }: {
  label: string; active: boolean; onClick: () => void; count?: number
}) {
  return (
    <button onClick={onClick} style={{
      padding: '6px 14px', borderRadius: 'var(--radius-sm)',
      background: active ? 'var(--bg-active)' : 'transparent',
      border: `1px solid ${active ? 'var(--border-lit)' : 'transparent'}`,
      color: active ? 'var(--amber)' : 'var(--text-muted)',
      fontFamily: 'var(--font-mono)', fontSize: 10, cursor: 'pointer',
      display: 'flex', alignItems: 'center', gap: 6,
      transition: 'all 0.15s',
    }}>
      {label}
      {count !== undefined && count > 0 && (
        <span style={{
          background: active ? 'var(--amber)' : 'var(--bg-raised)',
          color: active ? '#000' : 'var(--text-dim)',
          borderRadius: 8, padding: '1px 5px', fontSize: 8, fontWeight: 700,
        }}>{count}</span>
      )}
    </button>
  )
}

// ── No data placeholder ──────────────────────────────────────────────
function NoData({ message = 'Нет данных за период' }: { message?: string }) {
  return (
    <div style={{
      padding: '40px 20px', textAlign: 'center',
      background: 'var(--bg-panel)', border: '1px solid var(--border-dim)',
      borderRadius: 'var(--radius)', marginTop: 8,
    }}>
      <BarChart2 size={28} color="var(--text-dim)" style={{ margin: '0 auto 12px' }} />
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-dim)' }}>
        {message}
      </div>
    </div>
  )
}

// ── Main ─────────────────────────────────────────────────────────────
type TabId = 'sales' | 'finance' | 'stocks' | 'ads' | 'returns' | 'supply'

export default function Analytics() {
  const today      = new Date().toISOString().slice(0, 10)
  const monthAgo   = new Date(Date.now() - 30 * 86400_000).toISOString().slice(0, 10)

  const [tab,      setTab]      = useState<TabId>('sales')
  const [dateFrom, setDateFrom] = useState(monthAgo)
  const [dateTo,   setDateTo]   = useState(today)
  const [groupBy,  setGroupBy]  = useState<'sku' | 'brand' | 'category' | 'date'>('brand')

  const params = (extra: Record<string, string> = {}) =>
    new URLSearchParams({ date_from: dateFrom, date_to: dateTo, ...extra }).toString()

  const { data: summary,  loading: sumLoading,     refetch: refetchSummary }
    = useApi(() => api.analyticsQuery('summary',     params()), [dateFrom, dateTo], 30_000)
  const { data: sales,    loading: salesLoading,   refetch: refetchSales }
    = useApi(() => api.analyticsQuery('sales',       params({ group_by: groupBy })), [dateFrom, dateTo, groupBy])
  const { data: finance,  loading: finLoading }
    = useApi(() => api.analyticsQuery('finance',     params()), [dateFrom, dateTo])
  const { data: stocks,   loading: stLoading }
    = useApi(() => api.analyticsQuery('stocks',      ''),       [])
  const { data: ads,      loading: adsLoading }
    = useApi(() => api.analyticsQuery('ads',         params()), [dateFrom, dateTo])
  const { data: returns,  loading: retLoading }
    = useApi(() => api.analyticsQuery('returns',     params()), [dateFrom, dateTo])
  const { data: supplyRaw }
    = useApi(() => api.analyticsQuery('supply-risk', 'max_days=30'), [])

  const supply = supplyRaw as { critical?: number; warning?: number; total?: number; items?: any[] } | null

  // Derived data
  const sum = summary as Record<string, any> | null
  const salesList  = (sales  as any[]) ?? []
  const finList    = (finance as any[]) ?? []
  const stocksList = (stocks  as any[]) ?? []
  const adsList    = (ads     as any[]) ?? []
  const retList    = (returns as any[]) ?? []

  // Chart data for sales tab
  const salesChartData = useMemo(() => {
    return salesList.slice(0, 12).map(r => ({
      name:    String(r.brand || r.category || r.sku_id || r.sale_date || '').slice(0, 16),
      revenue: Math.round(r.revenue ?? 0),
      profit:  Math.round(r.net_profit ?? 0),
      qty:     r.quantity ?? 0,
    }))
  }, [salesList])

  // Brand breakdown for pie
  const brandPie = useMemo(() => {
    if (!sum?.top_brands) return []
    return (sum.top_brands as any[]).slice(0, 6).map(b => ({
      name: b.brand, value: Math.round(b.revenue)
    }))
  }, [sum])

  // Finance chart
  const finChartData = useMemo(() => {
    return finList.slice(-12).map(r => ({
      name:    String(r.report_number || r.period_start || '').slice(0, 10),
      payable: Math.round(r.total_payable ?? 0),
      sales:   Math.round(r.sales_amount ?? 0),
      logistics: Math.round(r.logistics_cost ?? 0),
    }))
  }, [finList])

  // Total ad spend
  const totalAdSpend = useMemo(() =>
    adsList.reduce((s: number, r: any) => s + (r.amount ?? 0), 0)
  , [adsList])

  const isLoading = sumLoading && !sum

  return (
    <div style={{ padding: 28, minHeight: '100vh' }}>
      {/* ── Header ── */}
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', marginBottom:24 }}>
        <div>
          <h1 style={{ fontFamily:'var(--font-display)', fontSize:22, fontWeight:800, color:'var(--text-white)', margin:0 }}>
            Аналитика продаж
          </h1>
          <div style={{ fontFamily:'var(--font-mono)', fontSize:10, color:'var(--text-dim)', marginTop:4 }}>
            Wildberries · все домены · обновление каждые 30с
          </div>
        </div>

        {/* Date range + refresh */}
        <div style={{ display:'flex', alignItems:'center', gap:8 }}>
          <div style={{ fontFamily:'var(--font-mono)', fontSize:10, color:'var(--text-dim)' }}>с</div>
          <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)}
            style={{
              background:'var(--bg-raised)', border:'1px solid var(--border-base)',
              borderRadius:4, color:'var(--text-base)', fontFamily:'var(--font-mono)',
              fontSize:10, padding:'4px 8px', cursor:'pointer',
            }}
          />
          <div style={{ fontFamily:'var(--font-mono)', fontSize:10, color:'var(--text-dim)' }}>по</div>
          <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)}
            style={{
              background:'var(--bg-raised)', border:'1px solid var(--border-base)',
              borderRadius:4, color:'var(--text-base)', fontFamily:'var(--font-mono)',
              fontSize:10, padding:'4px 8px', cursor:'pointer',
            }}
          />
          <button onClick={refetchSummary} style={{
            padding:'5px 10px', borderRadius:'var(--radius-sm)',
            background:'var(--bg-raised)', border:'1px solid var(--border-base)',
            color:'var(--text-muted)', cursor:'pointer',
            display:'flex', alignItems:'center', gap:5,
            fontFamily:'var(--font-mono)', fontSize:9,
          }}>
            <RefreshCw size={10} style={{ animation: sumLoading ? 'spin 1s linear infinite' : 'none' }}/>
            ОБНОВИТЬ
          </button>
        </div>
      </div>

      {isLoading ? (
        <div style={{ display:'flex', justifyContent:'center', padding: 80 }}>
          <Spinner size={36}/>
        </div>
      ) : (
        <>
          {/* ── KPI row ── */}
          <Section title="Ключевые показатели за период">
            <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill, minmax(170px,1fr))', gap:10 }}>
              <KPI
                label="ВЫРУЧКА (к перечислению)"
                value={sum ? fmt.rub(sum.total_revenue ?? 0) : '—'}
                sub={`${fmt.num(sum?.sales_count ?? 0)} единиц`}
                icon={<DollarSign size={13}/>}
              />
              <KPI
                label="ЧИСТАЯ ПРИБЫЛЬ"
                value={sum ? fmt.rub(sum.net_profit ?? 0) : '—'}
                sub={`Маржа ${fmt.num(sum?.avg_margin_pct ?? 0)}%`}
                accent={(sum?.net_profit ?? 0) > 0}
                icon={<TrendingUp size={13}/>}
              />
              <KPI
                label="КОМИССИЯ WB"
                value={sum ? fmt.rub(sum.total_commission ?? 0) : '—'}
                sub="вознаграждение + ВВ"
                icon={<BarChart2 size={13}/>}
              />
              <KPI
                label="ЛОГИСТИКА"
                value={sum ? fmt.rub(sum.total_logistics ?? 0) : '—'}
                sub="доставка покупателям"
                icon={<Truck size={13}/>}
              />
              <KPI
                label="ХРАНЕНИЕ"
                value={sum ? fmt.rub(sum.total_storage ?? 0) : '—'}
                sub="склад WB"
                icon={<Package size={13}/>}
              />
              <KPI
                label="ШТРАФЫ"
                value={sum ? fmt.rub(sum.total_penalties ?? 0) : '—'}
                accent={(sum?.total_penalties ?? 0) > 0}
                icon={<AlertTriangle size={13}/>}
              />
              <KPI
                label="ВОЗВРАТЫ"
                value={fmt.num(sum?.returns_count ?? 0)}
                sub="единиц"
                icon={<RotateCcw size={13}/>}
              />
              <KPI
                label="УНИКАЛЬНЫХ SKU"
                value={fmt.num(sum?.unique_skus ?? 0)}
                icon={<ShoppingBag size={13}/>}
              />
            </div>
          </Section>

          {/* ── No-data warning ── */}
          {!sumLoading && (sum?.total_revenue ?? 0) === 0 && (sum?.unique_skus ?? 0) === 0 && (
            <div style={{
              padding:'12px 16px', marginBottom:20,
              background:'rgba(245,158,11,0.08)', border:'1px solid rgba(245,158,11,0.3)',
              borderRadius:'var(--radius)', fontFamily:'var(--font-mono)', fontSize:11,
              display:'flex', alignItems:'center', gap:10,
            }}>
              <AlertTriangle size={13} color="var(--amber)"/>
              <span style={{ color:'var(--amber)' }}>
                Нет данных за период. Запусти обработку файлов на Command Center → ЗАПУСТИТЬ.
              </span>
            </div>
          )}

          {/* ── Tabs ── */}
          <div style={{ display:'flex', gap:6, marginBottom:18, flexWrap:'wrap' }}>
            <Tab label="Продажи"    active={tab==='sales'}   onClick={() => setTab('sales')}
              count={salesList.length} />
            <Tab label="Финансы"    active={tab==='finance'} onClick={() => setTab('finance')}
              count={finList.length} />
            <Tab label="Остатки"    active={tab==='stocks'}  onClick={() => setTab('stocks')}
              count={stocksList.length} />
            <Tab label="Реклама"    active={tab==='ads'}     onClick={() => setTab('ads')}
              count={adsList.length} />
            <Tab label="Возвраты"   active={tab==='returns'} onClick={() => setTab('returns')}
              count={retList.length} />
            <Tab label="Риск стокаута" active={tab==='supply'} onClick={() => setTab('supply')}
              count={supply?.critical ?? 0} />
          </div>

          {/* ══════════════════ SALES TAB ══════════════════ */}
          {tab === 'sales' && (
            <div>
              {/* Group by selector */}
              <div style={{ display:'flex', gap:6, marginBottom:14, alignItems:'center' }}>
                <span style={{ fontFamily:'var(--font-mono)', fontSize:9, color:'var(--text-dim)' }}>ГРУППИРОВКА:</span>
                {(['brand','category','sku','date'] as const).map(g => (
                  <button key={g} onClick={() => setGroupBy(g)} style={{
                    padding:'3px 10px', borderRadius:3, cursor:'pointer',
                    background: groupBy===g ? 'var(--amber-glow)' : 'var(--bg-raised)',
                    border: `1px solid ${groupBy===g ? 'var(--amber)' : 'var(--border-dim)'}`,
                    color: groupBy===g ? 'var(--amber)' : 'var(--text-muted)',
                    fontFamily:'var(--font-mono)', fontSize:9,
                  }}>
                    {{ brand:'Бренд', category:'Категория', sku:'SKU', date:'Дата' }[g]}
                  </button>
                ))}
              </div>

              {salesLoading && <Spinner size={24}/>}
              {!salesLoading && salesList.length === 0 && <NoData/>}
              {salesChartData.length > 0 && (
                <div style={{ display:'grid', gridTemplateColumns:'1fr 280px', gap:14, marginBottom:14 }}>
                  {/* Bar chart */}
                  <div style={{
                    background:'var(--bg-panel)', border:'1px solid var(--border-dim)',
                    borderRadius:'var(--radius)', padding:'16px',
                  }}>
                    <div style={{ fontFamily:'var(--font-mono)', fontSize:9, color:'var(--text-dim)', marginBottom:12, letterSpacing:'0.1em' }}>
                      ВЫРУЧКА И ПРИБЫЛЬ
                    </div>
                    <ResponsiveContainer width="100%" height={220}>
                      <BarChart data={salesChartData} barCategoryGap="30%">
                        <CartesianGrid strokeDasharray="3 3" stroke="var(--border-dim)"/>
                        <XAxis dataKey="name" tick={{ fontFamily:'var(--font-mono)', fontSize:9, fill:'var(--text-dim)' }}
                          interval={0} angle={-25} textAnchor="end" height={45}/>
                        <YAxis tick={{ fontFamily:'var(--font-mono)', fontSize:9, fill:'var(--text-dim)' }}
                          tickFormatter={v => fmt.rub(v)}/>
                        <Tooltip contentStyle={TT_STYLE} formatter={(v: number) => fmt.rub(v)}/>
                        <Bar dataKey="revenue" name="Выручка" fill={C.amber} radius={[3,3,0,0]}/>
                        <Bar dataKey="profit"  name="Прибыль" fill={C.green} radius={[3,3,0,0]}/>
                      </BarChart>
                    </ResponsiveContainer>
                  </div>

                  {/* Pie chart */}
                  {brandPie.length > 0 && (
                    <div style={{
                      background:'var(--bg-panel)', border:'1px solid var(--border-dim)',
                      borderRadius:'var(--radius)', padding:'16px',
                    }}>
                      <div style={{ fontFamily:'var(--font-mono)', fontSize:9, color:'var(--text-dim)', marginBottom:12, letterSpacing:'0.1em' }}>
                        ДОЛЯ БРЕНДОВ
                      </div>
                      <ResponsiveContainer width="100%" height={180}>
                        <PieChart>
                          <Pie data={brandPie} cx="50%" cy="50%" innerRadius={45} outerRadius={70}
                            dataKey="value" nameKey="name" paddingAngle={3}>
                            {brandPie.map((_, i) => (
                              <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]}/>
                            ))}
                          </Pie>
                          <Tooltip contentStyle={TT_STYLE} formatter={(v: number) => fmt.rub(v)}/>
                          <Legend iconSize={8} wrapperStyle={{ fontFamily:'var(--font-mono)', fontSize:9 }}/>
                        </PieChart>
                      </ResponsiveContainer>
                    </div>
                  )}
                </div>
              )}

              {/* Table */}
              {salesList.length > 0 && (
                <div style={{
                  background:'var(--bg-panel)', border:'1px solid var(--border-dim)',
                  borderRadius:'var(--radius)', overflow:'hidden',
                }}>
                  <div style={{ overflowX:'auto' }}>
                    <table style={{ width:'100%', borderCollapse:'collapse' }}>
                      <thead>
                        <tr style={{ background:'var(--bg-raised)' }}>
                          {['Бренд','Категория','SKU','Кол-во','Выручка','Комиссия','Логистика','Прибыль'].map(h => (
                            <th key={h} style={{
                              padding:'8px 12px', textAlign:'left',
                              fontFamily:'var(--font-mono)', fontSize:8,
                              color:'var(--text-dim)', letterSpacing:'0.1em',
                              borderBottom:'1px solid var(--border-dim)', fontWeight:400,
                            }}>{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {salesList.slice(0, 30).map((r: any, i: number) => (
                          <tr key={i} style={{
                            borderBottom:'1px solid var(--border-dim)',
                            background: i%2===0 ? 'transparent' : 'rgba(255,255,255,0.01)',
                          }}>
                            <td style={{ padding:'7px 12px', fontFamily:'var(--font-mono)', fontSize:10, color:'var(--amber)' }}>{r.brand || '—'}</td>
                            <td style={{ padding:'7px 12px', fontFamily:'var(--font-mono)', fontSize:10, color:'var(--text-muted)' }}>{r.category || '—'}</td>
                            <td style={{ padding:'7px 12px', fontFamily:'var(--font-mono)', fontSize:9,  color:'var(--text-dim)' }}>{r.sku_id || '—'}</td>
                            <td style={{ padding:'7px 12px', fontFamily:'var(--font-mono)', fontSize:10, color:'var(--text-base)', textAlign:'right' }}>{fmt.num(r.quantity ?? 0)}</td>
                            <td style={{ padding:'7px 12px', fontFamily:'var(--font-mono)', fontSize:10, color:'var(--text-white)', textAlign:'right' }}>{fmt.rub(r.revenue ?? 0)}</td>
                            <td style={{ padding:'7px 12px', fontFamily:'var(--font-mono)', fontSize:10, color:'var(--text-muted)', textAlign:'right' }}>{fmt.rub(r.commission ?? 0)}</td>
                            <td style={{ padding:'7px 12px', fontFamily:'var(--font-mono)', fontSize:10, color:'var(--text-muted)', textAlign:'right' }}>{fmt.rub(r.logistics ?? 0)}</td>
                            <td style={{ padding:'7px 12px', fontFamily:'var(--font-mono)', fontSize:10, textAlign:'right',
                              color: (r.net_profit ?? 0) >= 0 ? 'var(--green)' : 'var(--red)' }}>
                              {fmt.rub(r.net_profit ?? 0)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ══════════════════ FINANCE TAB ══════════════════ */}
          {tab === 'finance' && (
            <div>
              {finLoading && <Spinner size={24}/>}
              {!finLoading && finList.length === 0 && <NoData message="Нет данных из еженедельных отчётов. Добавь файл 'Еженедельный отчёт...' в incoming/"/>}
              {finChartData.length > 0 && (
                <div style={{
                  background:'var(--bg-panel)', border:'1px solid var(--border-dim)',
                  borderRadius:'var(--radius)', padding:'16px', marginBottom:14,
                }}>
                  <div style={{ fontFamily:'var(--font-mono)', fontSize:9, color:'var(--text-dim)', marginBottom:12 }}>
                    ДИНАМИКА ВЫПЛАТ ПО НЕДЕЛЯМ
                  </div>
                  <ResponsiveContainer width="100%" height={200}>
                    <LineChart data={finChartData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--border-dim)"/>
                      <XAxis dataKey="name" tick={{ fontFamily:'var(--font-mono)', fontSize:9, fill:'var(--text-dim)' }}/>
                      <YAxis tick={{ fontFamily:'var(--font-mono)', fontSize:9, fill:'var(--text-dim)' }}
                        tickFormatter={v => fmt.rub(v)}/>
                      <Tooltip contentStyle={TT_STYLE} formatter={(v: number) => fmt.rub(v)}/>
                      <Line type="monotone" dataKey="payable" name="К оплате" stroke={C.green} strokeWidth={2} dot={false}/>
                      <Line type="monotone" dataKey="logistics" name="Логистика" stroke={C.amber} strokeWidth={1.5} dot={false}/>
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}
              {finList.length > 0 && (
                <div style={{ background:'var(--bg-panel)', border:'1px solid var(--border-dim)', borderRadius:'var(--radius)', overflow:'hidden' }}>
                  <table style={{ width:'100%', borderCollapse:'collapse' }}>
                    <thead>
                      <tr style={{ background:'var(--bg-raised)' }}>
                        {['№ отчёта','Период','Продажи','К оплате','Логистика','Хранение','Штрафы'].map(h => (
                          <th key={h} style={{ padding:'8px 12px', textAlign:'left', fontFamily:'var(--font-mono)', fontSize:8, color:'var(--text-dim)', letterSpacing:'0.1em', borderBottom:'1px solid var(--border-dim)', fontWeight:400 }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {finList.slice(0,20).map((r: any, i: number) => (
                        <tr key={i} style={{ borderBottom:'1px solid var(--border-dim)' }}>
                          <td style={{ padding:'7px 12px', fontFamily:'var(--font-mono)', fontSize:10, color:'var(--amber)' }}>{r.report_number}</td>
                          <td style={{ padding:'7px 12px', fontFamily:'var(--font-mono)', fontSize:9,  color:'var(--text-dim)' }}>{r.period_start} — {r.period_end}</td>
                          <td style={{ padding:'7px 12px', fontFamily:'var(--font-mono)', fontSize:10, color:'var(--text-white)', textAlign:'right' }}>{fmt.rub(r.sales_amount)}</td>
                          <td style={{ padding:'7px 12px', fontFamily:'var(--font-mono)', fontSize:10, color:'var(--green)', textAlign:'right' }}>{fmt.rub(r.total_payable)}</td>
                          <td style={{ padding:'7px 12px', fontFamily:'var(--font-mono)', fontSize:10, color:'var(--text-muted)', textAlign:'right' }}>{fmt.rub(r.logistics_cost)}</td>
                          <td style={{ padding:'7px 12px', fontFamily:'var(--font-mono)', fontSize:10, color:'var(--text-muted)', textAlign:'right' }}>{fmt.rub(r.storage_cost)}</td>
                          <td style={{ padding:'7px 12px', fontFamily:'var(--font-mono)', fontSize:10, textAlign:'right', color:(r.total_penalties??0)>0?'var(--red)':'var(--text-dim)' }}>{fmt.rub(r.total_penalties)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {/* ══════════════════ STOCKS TAB ══════════════════ */}
          {tab === 'stocks' && (
            <div>
              {stLoading && <Spinner size={24}/>}
              {!stLoading && stocksList.length === 0 && <NoData message="Нет данных по остаткам. Добавь файл 'Актуальные_остатки...' в incoming/"/>}
              {stocksList.length > 0 && (
                <div style={{ background:'var(--bg-panel)', border:'1px solid var(--border-dim)', borderRadius:'var(--radius)', overflow:'hidden' }}>
                  <div style={{ overflowX:'auto' }}>
                    <table style={{ width:'100%', borderCollapse:'collapse' }}>
                      <thead>
                        <tr style={{ background:'var(--bg-raised)' }}>
                          {['Бренд','Категория','Артикул','Склад','Кол-во','Всего WB'].map(h => (
                            <th key={h} style={{ padding:'8px 12px', textAlign:'left', fontFamily:'var(--font-mono)', fontSize:8, color:'var(--text-dim)', letterSpacing:'0.1em', borderBottom:'1px solid var(--border-dim)', fontWeight:400 }}>{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {stocksList.slice(0,40).map((r: any, i: number) => (
                          <tr key={i} style={{ borderBottom:'1px solid var(--border-dim)', background: i%2===0 ? 'transparent':'rgba(255,255,255,0.01)' }}>
                            <td style={{ padding:'6px 12px', fontFamily:'var(--font-mono)', fontSize:10, color:'var(--amber)' }}>{r.brand||'—'}</td>
                            <td style={{ padding:'6px 12px', fontFamily:'var(--font-mono)', fontSize:10, color:'var(--text-muted)' }}>{r.category||'—'}</td>
                            <td style={{ padding:'6px 12px', fontFamily:'var(--font-mono)', fontSize:9,  color:'var(--text-dim)' }}>{r.seller_article||r.sku_id||'—'}</td>
                            <td style={{ padding:'6px 12px', fontFamily:'var(--font-mono)', fontSize:10, color:'var(--text-base)' }}>{r.warehouse_name||'—'}</td>
                            <td style={{ padding:'6px 12px', fontFamily:'var(--font-mono)', fontSize:10, color:'var(--text-white)', textAlign:'right' }}>{fmt.num(r.quantity??0)}</td>
                            <td style={{ padding:'6px 12px', fontFamily:'var(--font-mono)', fontSize:10, color:'var(--text-muted)', textAlign:'right' }}>{fmt.num(r.total_stock??0)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ══════════════════ ADS TAB ══════════════════ */}
          {tab === 'ads' && (
            <div>
              {adsLoading && <Spinner size={24}/>}
              {!adsLoading && adsList.length === 0 && <NoData message="Нет данных по рекламе. Добавь файл 'История-затрат...' в incoming/"/>}
              {adsList.length > 0 && (
                <>
                  <div style={{ display:'flex', gap:10, marginBottom:14 }}>
                    <KPI label="ВСЕГО ПОТРАЧЕНО" value={fmt.rub(totalAdSpend)}
                      accent={totalAdSpend > 0} icon={<TrendingUp size={13}/>}/>
                    <KPI label="КАМПАНИЙ" value={fmt.num(new Set(adsList.map((r:any)=>r.campaign_id)).size)}
                      icon={<BarChart2 size={13}/>}/>
                  </div>
                  <div style={{ background:'var(--bg-panel)', border:'1px solid var(--border-dim)', borderRadius:'var(--radius)', overflow:'hidden' }}>
                    <table style={{ width:'100%', borderCollapse:'collapse' }}>
                      <thead>
                        <tr style={{ background:'var(--bg-raised)' }}>
                          {['ID кампании','Название','Раздел','Дата','Сумма'].map(h => (
                            <th key={h} style={{ padding:'8px 12px', textAlign:'left', fontFamily:'var(--font-mono)', fontSize:8, color:'var(--text-dim)', letterSpacing:'0.1em', borderBottom:'1px solid var(--border-dim)', fontWeight:400 }}>{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {adsList.slice(0,30).map((r: any, i: number) => (
                          <tr key={i} style={{ borderBottom:'1px solid var(--border-dim)' }}>
                            <td style={{ padding:'7px 12px', fontFamily:'var(--font-mono)', fontSize:9, color:'var(--text-dim)' }}>{r.campaign_id}</td>
                            <td style={{ padding:'7px 12px', fontFamily:'var(--font-mono)', fontSize:10, color:'var(--amber)' }}>{r.campaign_name||'—'}</td>
                            <td style={{ padding:'7px 12px', fontFamily:'var(--font-mono)', fontSize:9, color:'var(--text-muted)' }}>{r.section||'—'}</td>
                            <td style={{ padding:'7px 12px', fontFamily:'var(--font-mono)', fontSize:9, color:'var(--text-dim)' }}>{r.charge_date}</td>
                            <td style={{ padding:'7px 12px', fontFamily:'var(--font-mono)', fontSize:10, color:'var(--text-white)', textAlign:'right' }}>{fmt.rub(r.amount??0)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
            </div>
          )}

          {/* ══════════════════ RETURNS TAB ══════════════════ */}
          {tab === 'returns' && (
            <div>
              {retLoading && <Spinner size={24}/>}
              {!retLoading && retList.length === 0 && <NoData message="Нет данных по возвратам. Добавь файл 'Возвраты за...' в incoming/"/>}
              {retList.length > 0 && (
                <div style={{ background:'var(--bg-panel)', border:'1px solid var(--border-dim)', borderRadius:'var(--radius)', overflow:'hidden' }}>
                  <table style={{ width:'100%', borderCollapse:'collapse' }}>
                    <thead>
                      <tr style={{ background:'var(--bg-raised)' }}>
                        {['Бренд','Категория','SKU','Статус','Дата заказа','Причина'].map(h => (
                          <th key={h} style={{ padding:'8px 12px', textAlign:'left', fontFamily:'var(--font-mono)', fontSize:8, color:'var(--text-dim)', letterSpacing:'0.1em', borderBottom:'1px solid var(--border-dim)', fontWeight:400 }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {retList.slice(0,30).map((r: any, i: number) => (
                        <tr key={i} style={{ borderBottom:'1px solid var(--border-dim)' }}>
                          <td style={{ padding:'7px 12px', fontFamily:'var(--font-mono)', fontSize:10, color:'var(--amber)' }}>{r.brand||'—'}</td>
                          <td style={{ padding:'7px 12px', fontFamily:'var(--font-mono)', fontSize:10, color:'var(--text-muted)' }}>{r.category||'—'}</td>
                          <td style={{ padding:'7px 12px', fontFamily:'var(--font-mono)', fontSize:9, color:'var(--text-dim)' }}>{r.sku_id||'—'}</td>
                          <td style={{ padding:'7px 12px', fontFamily:'var(--font-mono)', fontSize:10, color:'var(--text-base)' }}>{r.status||'—'}</td>
                          <td style={{ padding:'7px 12px', fontFamily:'var(--font-mono)', fontSize:9, color:'var(--text-dim)' }}>{r.order_date||'—'}</td>
                          <td style={{ padding:'7px 12px', fontFamily:'var(--font-mono)', fontSize:10, color:'var(--text-muted)' }}>{r.return_reason||'—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {/* ══════════════════ SUPPLY RISK TAB ══════════════════ */}
          {tab === 'supply' && (
            <div>
              {supply && (
                <div style={{ display:'flex', gap:10, marginBottom:14 }}>
                  <KPI label="КРИТИЧЕСКИЙ РИСК" value={fmt.num(supply.critical??0)}
                    accent={(supply.critical??0)>0} icon={<AlertTriangle size={13}/>}/>
                  <KPI label="ПРЕДУПРЕЖДЕНИЕ"   value={fmt.num(supply.warning??0)}
                    icon={<Package size={13}/>}/>
                  <KPI label="ВСЕГО ТОВАРОВ"    value={fmt.num(supply.total??0)}
                    icon={<ShoppingBag size={13}/>}/>
                </div>
              )}
              {(!supply || !supply.items?.length) && <NoData message="Нет данных по поставкам. Добавь файл 'recommendations...' в incoming/"/>}
              {(supply?.items?.length ?? 0) > 0 && (
                <div style={{ background:'var(--bg-panel)', border:'1px solid var(--border-dim)', borderRadius:'var(--radius)', overflow:'hidden' }}>
                  <table style={{ width:'100%', borderCollapse:'collapse' }}>
                    <thead>
                      <tr style={{ background:'var(--bg-raised)' }}>
                        {['Артикул','Регион','Остаток (дн)','Заказов/день','Потери 28д','Рекоменд. отгрузка','Риск'].map(h => (
                          <th key={h} style={{ padding:'8px 12px', textAlign:'left', fontFamily:'var(--font-mono)', fontSize:8, color:'var(--text-dim)', letterSpacing:'0.1em', borderBottom:'1px solid var(--border-dim)', fontWeight:400 }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {(supply?.items ?? []).slice(0,30).map((r: any, i: number) => (
                        <tr key={i} style={{ borderBottom:'1px solid var(--border-dim)' }}>
                          <td style={{ padding:'7px 12px', fontFamily:'var(--font-mono)', fontSize:10, color:'var(--amber)' }}>{r.seller_article||r.sku_id||'—'}</td>
                          <td style={{ padding:'7px 12px', fontFamily:'var(--font-mono)', fontSize:10, color:'var(--text-muted)' }}>{r.region||'—'}</td>
                          <td style={{ padding:'7px 12px', fontFamily:'var(--font-mono)', fontSize:10, textAlign:'right',
                            color: r.days_of_stock<=7 ? 'var(--red)' : r.days_of_stock<=14 ? 'var(--amber)' : 'var(--green)' }}>
                            {r.days_of_stock}
                          </td>
                          <td style={{ padding:'7px 12px', fontFamily:'var(--font-mono)', fontSize:10, color:'var(--text-base)', textAlign:'right' }}>{r.avg_orders_per_day}</td>
                          <td style={{ padding:'7px 12px', fontFamily:'var(--font-mono)', fontSize:10, textAlign:'right',
                            color: (r.revenue_loss_28d??0)>0 ? 'var(--red)' : 'var(--text-dim)' }}>
                            {(r.revenue_loss_28d??0)>0 ? fmt.rub(r.revenue_loss_28d) : '—'}
                          </td>
                          <td style={{ padding:'7px 12px', fontFamily:'var(--font-mono)', fontSize:10, color:'var(--text-white)', textAlign:'right' }}>{fmt.num(r.rec_supply_28d??0)}</td>
                          <td style={{ padding:'7px 12px' }}>
                            <span style={{
                              padding:'2px 8px', borderRadius:3,
                              background: r.risk==='critical' ? 'rgba(239,68,68,0.15)' : r.risk==='warning' ? 'rgba(245,158,11,0.15)' : 'rgba(16,185,129,0.15)',
                              color: r.risk==='critical' ? 'var(--red)' : r.risk==='warning' ? 'var(--amber)' : 'var(--green)',
                              fontFamily:'var(--font-mono)', fontSize:8, fontWeight:600, letterSpacing:'0.1em',
                            }}>
                              {r.risk?.toUpperCase()}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}

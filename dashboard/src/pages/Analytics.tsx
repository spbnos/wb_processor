import { useState, useMemo, useCallback } from 'react'
import {
  TrendingUp, Package, DollarSign, BarChart2,
  AlertTriangle, RefreshCw, Truck, ShoppingBag,
  RotateCcw, Megaphone, Calculator, Info,
} from 'lucide-react'
import { useApi } from '../hooks/useApi'
import { api } from '../api/client'
import { fmt } from '../utils/format'
import Spinner from '../components/Spinner'
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis,
  CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend,
} from 'recharts'

// ── Design tokens ────────────────────────────────────────────────────
const C = {
  amber: '#f59e0b', green: '#10b981', blue: '#3b82f6',
  red: '#ef4444', purple: '#8b5cf6', teal: '#14b8a6',
  orange: '#f97316', cyan: '#06b6d4',
}
const PIE_COLORS = [C.amber, C.green, C.blue, C.red, C.purple, C.teal, C.orange, C.cyan]
const TT = {
  backgroundColor: 'var(--bg-raised)', border: '1px solid var(--border-base)',
  borderRadius: 6, fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-base)',
}

// ── Helpers ──────────────────────────────────────────────────────────
type TabId = 'sales' | 'finance' | 'stocks' | 'ads' | 'returns' | 'supply' | 'unit'

function rub(n: number) {
  return fmt.rub ? fmt.rub(n) : `${new Intl.NumberFormat('ru-RU').format(Math.round(n))} ₽`
}

// ── Sub-components ───────────────────────────────────────────────────
function KPI({ label, value, sub, accent = false, warn = false, icon, tip }: {
  label: string; value: string; sub?: string
  accent?: boolean; warn?: boolean; icon?: React.ReactNode; tip?: string
}) {
  const color = warn ? 'var(--red)' : accent ? 'var(--amber)' : 'var(--text-white)'
  return (
    <div style={{
      background: 'var(--bg-panel)',
      border: `1px solid ${warn ? 'rgba(239,68,68,0.3)' : accent ? 'rgba(245,158,11,0.3)' : 'var(--border-dim)'}`,
      borderRadius: 'var(--radius)', padding: '14px 16px', minWidth: 0,
    }}>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:6 }}>
        <span style={{ fontFamily:'var(--font-mono)', fontSize:8, color:'var(--text-dim)', letterSpacing:'0.1em' }}>{label}</span>
        <span style={{ color:'var(--text-dim)', opacity:.5 }}>{icon}</span>
      </div>
      <div style={{ fontFamily:'var(--font-display)', fontSize:20, fontWeight:800, color, lineHeight:1.1 }}>{value}</div>
      {sub && <div style={{ fontFamily:'var(--font-mono)', fontSize:9, color:'var(--text-dim)', marginTop:3 }}>{sub}</div>}
    </div>
  )
}

function Tab({ label, active, onClick, count }: {
  label: string; active: boolean; onClick: () => void; count?: number
}) {
  return (
    <button onClick={onClick} style={{
      padding:'6px 13px', borderRadius:'var(--radius-sm)', cursor:'pointer',
      background: active ? 'var(--bg-active)' : 'transparent',
      border: `1px solid ${active ? 'var(--border-lit)' : 'transparent'}`,
      color: active ? 'var(--amber)' : 'var(--text-muted)',
      fontFamily:'var(--font-mono)', fontSize:10, display:'flex', alignItems:'center', gap:5,
      transition:'all 0.15s',
    }}>
      {label}
      {count !== undefined && count > 0 && (
        <span style={{
          background: active ? 'var(--amber)' : 'rgba(255,255,255,0.1)',
          color: active ? '#000' : 'var(--text-dim)',
          borderRadius:8, padding:'1px 5px', fontSize:8, fontWeight:700,
        }}>{count}</span>
      )}
    </button>
  )
}

function NoData({ msg = 'Нет данных за период', hint }: { msg?: string; hint?: string }) {
  return (
    <div style={{
      padding:'40px 20px', textAlign:'center',
      background:'var(--bg-panel)', border:'1px solid var(--border-dim)',
      borderRadius:'var(--radius)', marginTop:8,
    }}>
      <BarChart2 size={28} color="var(--text-dim)" style={{ margin:'0 auto 12px' }}/>
      <div style={{ fontFamily:'var(--font-mono)', fontSize:11, color:'var(--text-dim)' }}>{msg}</div>
      {hint && <div style={{ fontFamily:'var(--font-mono)', fontSize:9, color:'var(--text-dim)', marginTop:6, opacity:.6 }}>{hint}</div>}
    </div>
  )
}

function SectionTitle({ title }: { title: string }) {
  return (
    <div style={{ fontFamily:'var(--font-mono)', fontSize:9, color:'var(--text-dim)', letterSpacing:'0.12em', marginBottom:10, textTransform:'uppercase' }}>
      {title}
    </div>
  )
}

function TableWrap({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ background:'var(--bg-panel)', border:'1px solid var(--border-dim)', borderRadius:'var(--radius)', overflow:'hidden' }}>
      <div style={{ overflowX:'auto' }}>{children}</div>
    </div>
  )
}

function Th({ children, right }: { children: React.ReactNode; right?: boolean }) {
  return (
    <th style={{
      padding:'8px 12px', textAlign: right ? 'right' : 'left',
      fontFamily:'var(--font-mono)', fontSize:8, color:'var(--text-dim)',
      letterSpacing:'0.1em', borderBottom:'1px solid var(--border-dim)', fontWeight:400,
    }}>{children}</th>
  )
}

function Td({ children, color, right, mono = true }: {
  children: React.ReactNode; color?: string; right?: boolean; mono?: boolean
}) {
  return (
    <td style={{
      padding:'7px 12px', textAlign: right ? 'right' : 'left',
      fontFamily: mono ? 'var(--font-mono)' : 'inherit', fontSize:10,
      color: color || 'var(--text-muted)',
    }}>{children}</td>
  )
}

function RiskBadge({ risk }: { risk: string }) {
  const conf: Record<string,[string,string]> = {
    critical: ['rgba(239,68,68,0.15)','var(--red)'],
    warning:  ['rgba(245,158,11,0.15)','var(--amber)'],
    ok:       ['rgba(16,185,129,0.15)','var(--green)'],
  }
  const [bg,col] = conf[risk] || conf.ok
  return (
    <span style={{ padding:'2px 7px', borderRadius:3, background:bg, color:col,
      fontFamily:'var(--font-mono)', fontSize:8, fontWeight:600, letterSpacing:'0.1em' }}>
      {risk?.toUpperCase()}
    </span>
  )
}

// ── Main page ────────────────────────────────────────────────────────
export default function Analytics() {
  const today    = new Date().toISOString().slice(0,10)
  const monthAgo = new Date(Date.now()-30*86400_000).toISOString().slice(0,10)

  const [tab,      setTab]      = useState<TabId>('sales')
  const [dateFrom, setDateFrom] = useState(monthAgo)
  const [dateTo,   setDateTo]   = useState(today)
  const [groupBy,  setGroupBy]  = useState<'brand'|'category'|'sku'|'date'>('brand')

  const p = useCallback((extra: Record<string,string> = {}) =>
    new URLSearchParams({ date_from: dateFrom, date_to: dateTo, ...extra }).toString(),
    [dateFrom, dateTo]
  )

  const { data: sumRaw,  loading: sumL, refetch: refetchSum }
    = useApi(() => api.analyticsQuery('summary',     p()),      [dateFrom,dateTo], 30_000)
  const { data: salesRaw,loading: salesL }
    = useApi(() => api.analyticsQuery('sales',       p({group_by:groupBy})), [dateFrom,dateTo,groupBy])
  const { data: finRaw,  loading: finL }
    = useApi(() => api.analyticsQuery('finance',     p()),      [dateFrom,dateTo])
  const { data: stSumRaw, loading: stL }
    = useApi(() => api.analyticsQuery('stocks/summary',''),     [])
  const { data: adsRaw,  loading: adsL }
    = useApi(() => api.analyticsQuery('ads',         p()),      [dateFrom,dateTo])
  const { data: retRaw,  loading: retL }
    = useApi(() => api.analyticsQuery('returns',     p()),      [dateFrom,dateTo])
  const { data: supplyRaw }
    = useApi(() => api.analyticsQuery('supply-risk', 'max_days=30'), [])
  const { data: unitRaw, loading: unitL }
    = useApi(() => api.analyticsQuery('unit-economics', p()),   [dateFrom,dateTo])

  const sum    = sumRaw   as Record<string,any> | null
  const sales  = (salesRaw  as any[]) ?? []
  const fin    = (finRaw    as any[]) ?? []
  const stSum  = stSumRaw  as Record<string,any> | null
  const ads    = adsRaw   as Record<string,any> | null
  const ret    = retRaw   as Record<string,any> | null
  const supply = supplyRaw as Record<string,any> | null
  const units  = (unitRaw as any[]) ?? []

  // Data period from actual data (not filter)
  const dataPeriod = sum
    ? `${sum.period_from || '—'} → ${sum.period_to || '—'}`
    : '—'

  // Charts
  const salesChart = useMemo(() =>
    sales.slice(0,10).map((r:any) => ({
      name:    String(r.brand||r.category||r.sku_id||r.sale_date||'').slice(0,14),
      revenue: Math.round(r.revenue??0),
      profit:  Math.round(r.net_profit??0),
      cost:    Math.round(r.cost??0),
    })), [sales])

  const brandPie = useMemo(() =>
    ((sum?.top_brands as any[])||[]).slice(0,8).map((b:any)=>({
      name: b.brand, value: Math.round(b.revenue)
    })), [sum])

  const finChart = useMemo(() =>
    fin.slice(-16).map((r:any)=>({
      name:     String(r.report_number||r.period_start||'').slice(0,8),
      payable:  Math.round(r.total_payable??0),
      sales:    Math.round(r.sales_amount??0),
      logistics:Math.round(r.logistics_cost??0),
      storage:  Math.round(r.storage_cost??0),
    })), [fin])

  return (
    <div style={{ padding:28, minHeight:'100vh' }}>
      {/* ── Header ── */}
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', marginBottom:20 }}>
        <div>
          <h1 style={{ fontFamily:'var(--font-display)', fontSize:22, fontWeight:800, color:'var(--text-white)', margin:0 }}>
            Аналитика продаж
          </h1>
          <div style={{ fontFamily:'var(--font-mono)', fontSize:9, color:'var(--text-dim)', marginTop:3 }}>
            WB · данные в системе: <span style={{ color:'var(--amber)' }}>{dataPeriod}</span>
            {' · '}обновление каждые 30с
          </div>
        </div>

        {/* Date range */}
        <div style={{ display:'flex', alignItems:'center', gap:8 }}>
          <span style={{ fontFamily:'var(--font-mono)', fontSize:10, color:'var(--text-dim)' }}>с</span>
          <input type="date" value={dateFrom} onChange={e=>setDateFrom(e.target.value)} style={{
            background:'var(--bg-raised)', border:'1px solid var(--border-base)',
            borderRadius:4, color:'var(--text-base)', fontFamily:'var(--font-mono)',
            fontSize:10, padding:'4px 8px', cursor:'pointer',
          }}/>
          <span style={{ fontFamily:'var(--font-mono)', fontSize:10, color:'var(--text-dim)' }}>по</span>
          <input type="date" value={dateTo} onChange={e=>setDateTo(e.target.value)} style={{
            background:'var(--bg-raised)', border:'1px solid var(--border-base)',
            borderRadius:4, color:'var(--text-base)', fontFamily:'var(--font-mono)',
            fontSize:10, padding:'4px 8px', cursor:'pointer',
          }}/>
          <button onClick={refetchSum} style={{
            padding:'5px 9px', borderRadius:'var(--radius-sm)', cursor:'pointer',
            background:'var(--bg-raised)', border:'1px solid var(--border-base)',
            color:'var(--text-muted)', display:'flex', alignItems:'center', gap:4,
            fontFamily:'var(--font-mono)', fontSize:9,
          }}>
            <RefreshCw size={10} style={{ animation: sumL ? 'spin 1s linear infinite' : 'none' }}/>
            ОБНОВИТЬ
          </button>
        </div>
      </div>

      {/* ── KPI row ── */}
      <div style={{ marginBottom:16 }}>
        <SectionTitle title="Ключевые показатели"/>
        <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill,minmax(155px,1fr))', gap:8 }}>
          <KPI label="ВЫРУЧКА (к перечислению)" value={sum ? rub(sum.total_revenue??0) : '—'}
            sub={`${fmt.num(sum?.sales_count??0)} единиц`} icon={<DollarSign size={12}/>}/>
          <KPI label="ЧИСТАЯ ПРИБЫЛЬ (без себест.)" value={sum ? rub(sum.net_profit??0) : '—'}
            sub={`Маржа ${sum?.avg_margin_pct??0}%`} accent={(sum?.net_profit??0)>0}
            warn={(sum?.net_profit??0)<0} icon={<TrendingUp size={12}/>}/>
          {(sum?.total_cost??0)>0 && (
            <KPI label="ПРИБЫЛЬ (с себест.)" value={sum ? rub(sum.unit_net_profit??0) : '—'}
              sub={`${sum?.unit_margin_pct??0}% юнит-маржа`} accent={(sum?.unit_net_profit??0)>0}
              warn={(sum?.unit_net_profit??0)<0} icon={<Calculator size={12}/>}/>
          )}
          <KPI label="КОМИССИЯ WB" value={sum ? rub(sum.total_commission??0) : '—'}
            sub="вознаграждение + ВВ" icon={<BarChart2 size={12}/>}/>
          <KPI label="ЛОГИСТИКА" value={sum ? rub(sum.total_logistics??0) : '—'}
            sub="доставка покупателям" icon={<Truck size={12}/>}/>
          <KPI label="ХРАНЕНИЕ" value={sum ? rub(sum.total_storage??0) : '—'}
            sub="склад WB" icon={<Package size={12}/>}/>
          <KPI label="ШТРАФЫ / УДЕРЖАНИЯ" value={sum ? rub(sum.total_penalties??0) : '—'}
            warn={(sum?.total_penalties??0)>0} icon={<AlertTriangle size={12}/>}/>
          <KPI label="ВОЗВРАТЫ (ед.)" value={fmt.num(sum?.returns_count??0)}
            icon={<RotateCcw size={12}/>}/>
          <KPI label="УНИКАЛЬНЫХ SKU" value={fmt.num(sum?.unique_skus??0)}
            icon={<ShoppingBag size={12}/>}/>
        </div>
      </div>

      {/* ── No data warning ── */}
      {!sumL && (sum?.total_revenue??0)===0 && (sum?.unique_skus??0)===0 && (
        <div style={{
          padding:'12px 16px', marginBottom:16,
          background:'rgba(245,158,11,0.07)', border:'1px solid rgba(245,158,11,0.3)',
          borderRadius:'var(--radius)', fontFamily:'var(--font-mono)', fontSize:11,
          display:'flex', alignItems:'center', gap:10,
        }}>
          <AlertTriangle size={13} color="var(--amber)"/>
          <span style={{ color:'var(--amber)' }}>
            Нет данных за период {dateFrom} → {dateTo}.
            Данные в системе: <strong>{dataPeriod}</strong>.
            Измени период или нажми ЗАПУСТИТЬ на Command Center.
          </span>
        </div>
      )}

      {/* ── Tabs ── */}
      <div style={{ display:'flex', gap:5, marginBottom:16, flexWrap:'wrap' }}>
        <Tab label="Продажи"      active={tab==='sales'}   onClick={()=>setTab('sales')}   count={sales.length}/>
        <Tab label="Финансы"      active={tab==='finance'} onClick={()=>setTab('finance')} count={fin.length}/>
        <Tab label="Остатки"      active={tab==='stocks'}  onClick={()=>setTab('stocks')}/>
        <Tab label="Реклама"      active={tab==='ads'}     onClick={()=>setTab('ads')}     count={ads?.campaigns_count??0}/>
        <Tab label="Возвраты"     active={tab==='returns'} onClick={()=>setTab('returns')} count={ret?.total_returns??0}/>
        <Tab label="Риск стокаута" active={tab==='supply'}  onClick={()=>setTab('supply')}  count={supply?.critical??0}/>
        <Tab label="Юнит-экономика" active={tab==='unit'}  onClick={()=>setTab('unit')}    count={units.filter((r:any)=>r.unit_margin<0).length}/>
      </div>

      {/* ══ SALES ══════════════════════════════════════════════════════ */}
      {tab==='sales' && (
        <div>
          {/* Group by */}
          <div style={{ display:'flex', gap:6, marginBottom:12, alignItems:'center' }}>
            <span style={{ fontFamily:'var(--font-mono)', fontSize:9, color:'var(--text-dim)' }}>ГРУППИРОВКА:</span>
            {(['brand','category','sku','date'] as const).map(g=>(
              <button key={g} onClick={()=>setGroupBy(g)} style={{
                padding:'3px 9px', borderRadius:3, cursor:'pointer',
                background: groupBy===g ? 'var(--amber-glow)' : 'var(--bg-raised)',
                border:`1px solid ${groupBy===g?'var(--amber)':'var(--border-dim)'}`,
                color: groupBy===g ? 'var(--amber)' : 'var(--text-muted)',
                fontFamily:'var(--font-mono)', fontSize:9,
              }}>
                {{brand:'Бренд',category:'Категория',sku:'SKU',date:'Дата'}[g]}
              </button>
            ))}
          </div>

          {salesL && <Spinner size={24}/>}
          {!salesL && sales.length===0 && <NoData hint="Добавь ежедневные отчёты в incoming/ и нажми ЗАПУСТИТЬ"/>}

          {salesChart.length>0 && (
            <div style={{ display:'grid', gridTemplateColumns:'1fr 260px', gap:12, marginBottom:12 }}>
              <div style={{ background:'var(--bg-panel)', border:'1px solid var(--border-dim)', borderRadius:'var(--radius)', padding:'14px 16px' }}>
                <SectionTitle title="Выручка и прибыль"/>
                <ResponsiveContainer width="100%" height={210}>
                  <BarChart data={salesChart} barCategoryGap="28%">
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border-dim)"/>
                    <XAxis dataKey="name" tick={{fontFamily:'var(--font-mono)',fontSize:8,fill:'var(--text-dim)'}} interval={0} angle={-20} textAnchor="end" height={40}/>
                    <YAxis tick={{fontFamily:'var(--font-mono)',fontSize:8,fill:'var(--text-dim)'}} tickFormatter={v=>rub(v)}/>
                    <Tooltip contentStyle={TT} formatter={(v:number)=>rub(v)}/>
                    <Bar dataKey="revenue" name="Выручка" fill={C.amber} radius={[3,3,0,0]}/>
                    <Bar dataKey="profit"  name="Прибыль (без с/с)" fill={C.green} radius={[3,3,0,0]}/>
                  </BarChart>
                </ResponsiveContainer>
              </div>
              {brandPie.length>0 && (
                <div style={{ background:'var(--bg-panel)', border:'1px solid var(--border-dim)', borderRadius:'var(--radius)', padding:'14px 16px' }}>
                  <SectionTitle title="Доля брендов"/>
                  <ResponsiveContainer width="100%" height={185}>
                    <PieChart>
                      <Pie data={brandPie} cx="50%" cy="50%" innerRadius={42} outerRadius={68}
                        dataKey="value" paddingAngle={2}>
                        {brandPie.map((_,i)=><Cell key={i} fill={PIE_COLORS[i%PIE_COLORS.length]}/>)}
                      </Pie>
                      <Tooltip contentStyle={TT} formatter={(v:number)=>rub(v)}/>
                      <Legend iconSize={7} wrapperStyle={{fontFamily:'var(--font-mono)',fontSize:8}}/>
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>
          )}

          {sales.length>0 && (
            <TableWrap>
              <table style={{ width:'100%', borderCollapse:'collapse' }}>
                <thead><tr style={{ background:'var(--bg-raised)' }}>
                  <Th>Бренд</Th><Th>Категория</Th><Th>SKU</Th>
                  <Th right>Кол-во</Th><Th right>Выручка</Th>
                  <Th right>Комиссия</Th><Th right>Логистика</Th>
                  <Th right>Прибыль</Th>
                </tr></thead>
                <tbody>
                  {sales.slice(0,50).map((r:any,i:number)=>(
                    <tr key={i} style={{ borderBottom:'1px solid var(--border-dim)', background:i%2?'rgba(255,255,255,0.01)':'transparent' }}>
                      <Td color="var(--amber)">{r.brand||'—'}</Td>
                      <Td>{r.category||'—'}</Td>
                      <Td color="var(--text-dim)">{r.sku_id||'—'}</Td>
                      <Td right>{fmt.num(r.quantity??0)}</Td>
                      <Td right color="var(--text-white)">{rub(r.revenue??0)}</Td>
                      <Td right color="var(--text-dim)">{rub(r.commission??0)}</Td>
                      <Td right color="var(--text-dim)">{rub(r.logistics??0)}</Td>
                      <Td right color={(r.net_profit??0)>=0?'var(--green)':'var(--red)'}>{rub(r.net_profit??0)}</Td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
          )}
        </div>
      )}

      {/* ══ FINANCE ════════════════════════════════════════════════════ */}
      {tab==='finance' && (
        <div>
          {finL && <Spinner size={24}/>}
          {!finL && fin.length===0 && <NoData hint="Добавь 'Еженедельный отчёт...' в incoming/"/>}
          {finChart.length>0 && (
            <div style={{ background:'var(--bg-panel)', border:'1px solid var(--border-dim)', borderRadius:'var(--radius)', padding:'14px', marginBottom:12 }}>
              <SectionTitle title="Динамика выплат по неделям"/>
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={finChart}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border-dim)"/>
                  <XAxis dataKey="name" tick={{fontFamily:'var(--font-mono)',fontSize:8,fill:'var(--text-dim)'}}/>
                  <YAxis tick={{fontFamily:'var(--font-mono)',fontSize:8,fill:'var(--text-dim)'}} tickFormatter={v=>rub(v)}/>
                  <Tooltip contentStyle={TT} formatter={(v:number)=>rub(v)}/>
                  <Line type="monotone" dataKey="payable" name="К оплате" stroke={C.green} strokeWidth={2} dot={false}/>
                  <Line type="monotone" dataKey="logistics" name="Логистика" stroke={C.amber} strokeWidth={1.5} dot={false}/>
                  <Line type="monotone" dataKey="storage"   name="Хранение"  stroke={C.blue}  strokeWidth={1.5} dot={false}/>
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
          {fin.length>0 && (
            <TableWrap>
              <table style={{ width:'100%', borderCollapse:'collapse' }}>
                <thead><tr style={{ background:'var(--bg-raised)' }}>
                  <Th>№ отчёта</Th><Th>Период</Th>
                  <Th right>Продажи</Th><Th right>К оплате</Th>
                  <Th right>Логистика</Th><Th right>Хранение</Th>
                  <Th right>Приёмка</Th><Th right>Штрафы</Th>
                </tr></thead>
                <tbody>
                  {fin.slice(0,30).map((r:any,i:number)=>(
                    <tr key={i} style={{ borderBottom:'1px solid var(--border-dim)' }}>
                      <Td color="var(--amber)">{r.report_number}</Td>
                      <Td color="var(--text-dim)">{r.period_start} — {r.period_end}</Td>
                      <Td right color="var(--text-white)">{rub(r.sales_amount??0)}</Td>
                      <Td right color="var(--green)">{rub(r.total_payable??0)}</Td>
                      <Td right>{rub(r.logistics_cost??0)}</Td>
                      <Td right>{rub(r.storage_cost??0)}</Td>
                      <Td right>{rub(r.acceptance_cost??0)}</Td>
                      <Td right color={(r.total_penalties??0)>0?'var(--red)':'var(--text-dim)'}>{rub(r.total_penalties??0)}</Td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
          )}
        </div>
      )}

      {/* ══ STOCKS ════════════════════════════════════════════════════ */}
      {tab==='stocks' && (
        <div>
          {stL && <Spinner size={24}/>}
          {!stL && !stSum && <NoData hint="Добавь файл остатков 'report_YYYY_M_D.xlsx' в incoming/"/>}
          {stSum && (
            <>
              {/* Summary KPIs */}
              <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill,minmax(170px,1fr))', gap:8, marginBottom:14 }}>
                <KPI label="ВСЕГО FBO (ед.)" value={fmt.num(stSum.total_fbo_stock??0)} icon={<Package size={12}/>}/>
                <KPI label="В ПУТИ ДО ПОКУПАТЕЛЕЙ" value={fmt.num(stSum.total_in_transit??0)} accent={(stSum.total_in_transit??0)>0} icon={<Truck size={12}/>}/>
                <KPI label="ВОЗВРАТЫ В ПУТИ" value={fmt.num(stSum.total_returns_transit??0)} warn={(stSum.total_returns_transit??0)>0} icon={<RotateCcw size={12}/>}/>
                <KPI label="СТОИМОСТЬ СКЛАДА (с/с)" value={rub(stSum.total_stock_value??0)} icon={<DollarSign size={12}/>}/>
                <KPI label="УНИКАЛЬНЫХ SKU" value={fmt.num(stSum.total_skus??0)} icon={<ShoppingBag size={12}/>}/>
              </div>

              <TableWrap>
                <table style={{ width:'100%', borderCollapse:'collapse' }}>
                  <thead><tr style={{ background:'var(--bg-raised)' }}>
                    <Th>Бренд</Th><Th>Категория</Th><Th>Артикул</Th><Th>Товар</Th>
                    <Th right>FBO (ед.)</Th><Th right>В пути</Th><Th right>Возвраты</Th><Th right>С/С ₽</Th>
                  </tr></thead>
                  <tbody>
                    {(stSum.items as any[]).slice(0,60).map((r:any,i:number)=>(
                      <tr key={i} style={{ borderBottom:'1px solid var(--border-dim)', background:i%2?'rgba(255,255,255,0.01)':'transparent' }}>
                        <Td color="var(--amber)">{r.brand||'—'}</Td>
                        <Td>{r.category||'—'}</Td>
                        <Td color="var(--text-dim)">{r.seller_article||r.sku_id||'—'}</Td>
                        <Td color="var(--text-muted)" mono={false}>{(r.product_name||'').slice(0,30)}</Td>
                        <Td right color="var(--text-white)">{fmt.num(r.total_fbo??0)}</Td>
                        <Td right color={(r.in_transit_to_customer??0)>0?'var(--amber)':'var(--text-dim)'}>{fmt.num(r.in_transit_to_customer??0)}</Td>
                        <Td right color={(r.in_transit_returns??0)>0?'var(--red)':'var(--text-dim)'}>{fmt.num(r.in_transit_returns??0)}</Td>
                        <Td right color="var(--text-dim)">{(r.cost_price??0)>0?rub(r.cost_price):'—'}</Td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </TableWrap>
            </>
          )}
        </div>
      )}

      {/* ══ ADS ════════════════════════════════════════════════════════ */}
      {tab==='ads' && (
        <div>
          {adsL && <Spinner size={24}/>}
          {!adsL && !ads?.total_spent && <NoData hint="Добавь 'История-затрат...' в incoming/ и нажми ЗАПУСТИТЬ"/>}
          {(ads?.total_spent??0)>0 && (
            <>
              <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill,minmax(170px,1fr))', gap:8, marginBottom:14 }}>
                <KPI label="ВСЕГО ПОТРАЧЕНО" value={rub(ads?.total_spent??0)} accent icon={<Megaphone size={12}/>}/>
                <KPI label="КАМПАНИЙ" value={fmt.num(ads?.campaigns_count??0)} icon={<BarChart2 size={12}/>}/>
              </div>

              {/* By campaign */}
              <div style={{ marginBottom:12 }}>
                <SectionTitle title="По кампаниям"/>
                <TableWrap>
                  <table style={{ width:'100%', borderCollapse:'collapse' }}>
                    <thead><tr style={{ background:'var(--bg-raised)' }}>
                      <Th>ID</Th><Th>Кампания</Th><Th>Раздел</Th>
                      <Th right>Потрачено</Th><Th>Период</Th><Th right>Записей</Th>
                    </tr></thead>
                    <tbody>
                      {(ads?.by_campaign as any[]||[]).map((r:any,i:number)=>(
                        <tr key={i} style={{ borderBottom:'1px solid var(--border-dim)' }}>
                          <Td color="var(--text-dim)">{r.campaign_id}</Td>
                          <Td color="var(--amber)">{r.campaign_name||'—'}</Td>
                          <Td>{r.section||'—'}</Td>
                          <Td right color="var(--text-white)">{rub(r.total_spent??0)}</Td>
                          <Td color="var(--text-dim)">{r.first_date} – {r.last_date}</Td>
                          <Td right>{r.records}</Td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </TableWrap>
              </div>

              {/* Raw records */}
              <SectionTitle title="Детали списаний"/>
              <TableWrap>
                <table style={{ width:'100%', borderCollapse:'collapse' }}>
                  <thead><tr style={{ background:'var(--bg-raised)' }}>
                    <Th>Дата</Th><Th>Кампания</Th><Th>Раздел</Th><Th right>Сумма</Th>
                  </tr></thead>
                  <tbody>
                    {(ads?.records as any[]||[]).slice(0,50).map((r:any,i:number)=>(
                      <tr key={i} style={{ borderBottom:'1px solid var(--border-dim)' }}>
                        <Td color="var(--text-dim)">{r.charge_date}</Td>
                        <Td color="var(--amber)">{r.campaign_name||r.campaign_id||'—'}</Td>
                        <Td>{r.section||'—'}</Td>
                        <Td right color="var(--text-white)">{rub(r.amount??0)}</Td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </TableWrap>
            </>
          )}
        </div>
      )}

      {/* ══ RETURNS ════════════════════════════════════════════════════ */}
      {tab==='returns' && (
        <div>
          {retL && <Spinner size={24}/>}
          {!retL && !ret?.total_returns && <NoData hint="Добавь 'Возвраты за...' в incoming/"/>}
          {(ret?.total_returns??0)>0 && (
            <>
              <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:12, marginBottom:14 }}>
                {/* By reason */}
                <div style={{ background:'var(--bg-panel)', border:'1px solid var(--border-dim)', borderRadius:'var(--radius)', padding:'14px' }}>
                  <SectionTitle title="По причине"/>
                  {(ret?.by_reason as any[]||[]).map((r:any,i:number)=>(
                    <div key={i} style={{ display:'flex', justifyContent:'space-between', padding:'4px 0',
                      borderBottom:'1px solid var(--border-dim)', fontFamily:'var(--font-mono)', fontSize:10 }}>
                      <span style={{ color:'var(--text-muted)' }}>{r.reason}</span>
                      <span style={{ color:'var(--amber)', fontWeight:600 }}>{r.count}</span>
                    </div>
                  ))}
                </div>
                {/* By brand */}
                <div style={{ background:'var(--bg-panel)', border:'1px solid var(--border-dim)', borderRadius:'var(--radius)', padding:'14px' }}>
                  <SectionTitle title="По бренду"/>
                  {(ret?.by_brand as any[]||[]).map((r:any,i:number)=>(
                    <div key={i} style={{ display:'flex', justifyContent:'space-between', padding:'4px 0',
                      borderBottom:'1px solid var(--border-dim)', fontFamily:'var(--font-mono)', fontSize:10 }}>
                      <span style={{ color:'var(--amber)' }}>{r.brand}</span>
                      <span style={{ color:'var(--text-white)', fontWeight:600 }}>{r.count}</span>
                    </div>
                  ))}
                </div>
              </div>

              <TableWrap>
                <table style={{ width:'100%', borderCollapse:'collapse' }}>
                  <thead><tr style={{ background:'var(--bg-raised)' }}>
                    <Th>Бренд</Th><Th>Категория</Th><Th>SKU</Th>
                    <Th>Статус</Th><Th>Дата заказа</Th><Th>Причина</Th>
                  </tr></thead>
                  <tbody>
                    {(ret?.records as any[]||[]).slice(0,50).map((r:any,i:number)=>(
                      <tr key={i} style={{ borderBottom:'1px solid var(--border-dim)' }}>
                        <Td color="var(--amber)">{r.brand||'—'}</Td>
                        <Td>{r.category||'—'}</Td>
                        <Td color="var(--text-dim)">{r.sku_id||'—'}</Td>
                        <Td>{r.status||'—'}</Td>
                        <Td color="var(--text-dim)">{r.order_date||'—'}</Td>
                        <Td color="var(--text-muted)">{r.return_reason||'—'}</Td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </TableWrap>
            </>
          )}
        </div>
      )}

      {/* ══ SUPPLY RISK ════════════════════════════════════════════════ */}
      {tab==='supply' && (
        <div>
          {supply && (
            <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill,minmax(170px,1fr))', gap:8, marginBottom:14 }}>
              <KPI label="КРИТИЧЕСКИЙ РИСК" value={fmt.num(supply.critical??0)}
                warn={(supply.critical??0)>0} icon={<AlertTriangle size={12}/>}/>
              <KPI label="ПРЕДУПРЕЖДЕНИЕ" value={fmt.num(supply.warning??0)}
                accent={(supply.warning??0)>0} icon={<Package size={12}/>}/>
              <KPI label="ВСЕГО В МОНИТОРИНГЕ" value={fmt.num(supply.total??0)} icon={<ShoppingBag size={12}/>}/>
            </div>
          )}
          {!supply?.items?.length && <NoData hint="Добавь 'recommendations*.xlsx' в incoming/"/>}
          {(supply?.items?.length??0)>0 && (
            <TableWrap>
              <table style={{ width:'100%', borderCollapse:'collapse' }}>
                <thead><tr style={{ background:'var(--bg-raised)' }}>
                  <Th>Артикул</Th><Th>Товар</Th><Th>Регион</Th>
                  <Th right>Остаток (дн.)</Th><Th right>Заказов/день</Th>
                  <Th right>Потери 28д</Th><Th right>Рек. отгрузка</Th><Th>Риск</Th>
                </tr></thead>
                <tbody>
                  {(supply?.items as any[]).slice(0,60).map((r:any,i:number)=>(
                    <tr key={i} style={{ borderBottom:'1px solid var(--border-dim)' }}>
                      <Td color="var(--amber)">{r.seller_article||r.sku_id||'—'}</Td>
                      <Td color="var(--text-muted)" mono={false}>{(r.product_name||'').slice(0,24)}</Td>
                      <Td>{r.region||'—'}</Td>
                      <Td right color={r.days_of_stock<=7?'var(--red)':r.days_of_stock<=14?'var(--amber)':'var(--green)'}>
                        {r.days_of_stock}
                      </Td>
                      <Td right>{r.avg_orders_per_day}</Td>
                      <Td right color={(r.revenue_loss_28d??0)>0?'var(--red)':'var(--text-dim)'}>
                        {(r.revenue_loss_28d??0)>0?rub(r.revenue_loss_28d):'—'}
                      </Td>
                      <Td right>{fmt.num(r.rec_supply_28d??0)}</Td>
                      <Td><RiskBadge risk={r.risk}/></Td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
          )}
        </div>
      )}

      {/* ══ UNIT ECONOMICS ═════════════════════════════════════════════ */}
      {tab==='unit' && (
        <div>
          {unitL && <Spinner size={24}/>}
          {!unitL && units.length===0 && (
            <NoData
              msg="Нет данных для юнит-экономики"
              hint="Нужны: ежедневный отчёт + файл 'Актуальные_остатки_fixed.xlsx' (себестоимость)"
            />
          )}
          {units.length>0 && (
            <>
              {/* Summary */}
              <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill,minmax(170px,1fr))', gap:8, marginBottom:14 }}>
                {(() => {
                  const loss = units.filter((r:any)=>r.unit_margin<0)
                  const profitable = units.filter((r:any)=>r.unit_margin>0)
                  const totalMargin = units.reduce((s:number,r:any)=>s+(r.unit_margin||0),0)
                  return (
                    <>
                      <KPI label="ПРИБЫЛЬНЫХ SKU" value={fmt.num(profitable.length)}
                        accent icon={<TrendingUp size={12}/>}/>
                      <KPI label="УБЫТОЧНЫХ SKU" value={fmt.num(loss.length)}
                        warn={(loss.length)>0} icon={<AlertTriangle size={12}/>}/>
                      <KPI label="СУММАРНАЯ ЮНИТ-МАРЖА" value={rub(totalMargin)}
                        accent={totalMargin>0} warn={totalMargin<0} icon={<Calculator size={12}/>}/>
                    </>
                  )
                })()}
              </div>

              <div style={{
                padding:'10px 14px', marginBottom:12, borderRadius:'var(--radius)',
                background:'rgba(59,130,246,0.07)', border:'1px solid rgba(59,130,246,0.25)',
                fontFamily:'var(--font-mono)', fontSize:10, color:'var(--text-dim)',
                display:'flex', gap:8, alignItems:'center',
              }}>
                <Info size={12} color="var(--blue)"/>
                Юнит-маржа = Выручка − Комиссия WB − Логистика − Хранение − Себестоимость.
                Себестоимость из файла «Актуальные_остатки_fixed.xlsx» (поле «Цена закупочная»).
              </div>

              <TableWrap>
                <table style={{ width:'100%', borderCollapse:'collapse' }}>
                  <thead><tr style={{ background:'var(--bg-raised)' }}>
                    <Th>Бренд</Th><Th>Категория</Th><Th>SKU</Th>
                    <Th right>Кол-во</Th><Th right>Выручка</Th>
                    <Th right>С/С (ед.)</Th><Th right>Комис.</Th><Th right>Логист.</Th>
                    <Th right>Юнит-маржа</Th><Th right>Маржа %</Th>
                  </tr></thead>
                  <tbody>
                    {units.slice(0,60).map((r:any,i:number)=>(
                      <tr key={i} style={{ borderBottom:'1px solid var(--border-dim)', background:i%2?'rgba(255,255,255,0.01)':'transparent' }}>
                        <Td color="var(--amber)">{r.brand||'—'}</Td>
                        <Td>{r.category||'—'}</Td>
                        <Td color="var(--text-dim)">{r.seller_article||r.sku_id||'—'}</Td>
                        <Td right>{fmt.num(r.quantity??0)}</Td>
                        <Td right color="var(--text-white)">{rub(r.revenue??0)}</Td>
                        <Td right color={(r.cost_price??0)>0?'var(--text-muted)':'var(--text-dim)'}>
                          {(r.cost_price??0)>0?rub(r.cost_price):'нет'}
                        </Td>
                        <Td right color="var(--text-dim)">{rub(r.commission??0)}</Td>
                        <Td right color="var(--text-dim)">{rub(r.logistics??0)}</Td>
                        <Td right color={(r.unit_margin??0)>=0?'var(--green)':'var(--red)'}>
                          {rub(r.unit_margin??0)}
                        </Td>
                        <Td right color={(r.margin_pct??0)>=0?'var(--green)':'var(--red)'}>
                          {(r.margin_pct??0).toFixed(1)}%
                        </Td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </TableWrap>
            </>
          )}
        </div>
      )}
    </div>
  )
}

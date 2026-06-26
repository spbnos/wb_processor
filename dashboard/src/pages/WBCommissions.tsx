/**
 * WBCommissions.tsx — Вкладка «Удержания WB»
 * Три секции:
 *  1. Текущие удержания из фактических данных
 *  2. Таблица комиссий WB по предметам (7413 строк, поиск)
 *  3. Калькулятор юнит-экономики
 */
import { useState, useMemo, useCallback } from 'react'
import {
  DollarSign, Calculator, Search, TrendingDown,
  RefreshCw, ChevronDown, ChevronUp, Info, AlertTriangle,
  CheckCircle, BarChart2,
} from 'lucide-react'
import { useApi } from '../hooks/useApi'
import { api } from '../api/client'
import { fmt } from '../utils/format'
import Spinner from '../components/Spinner'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, PieChart, Pie, Cell,
} from 'recharts'

// ── helpers ────────────────────────────────────────────────────────────────
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

type TabId = 'deductions' | 'rates' | 'calculator'

const C = ['#f59e0b','#ef4444','#3b82f6','#10b981','#8b5cf6']
const TT = { backgroundColor:'var(--bg-raised)', border:'1px solid var(--border-base)',
             borderRadius:6, fontFamily:'var(--font-mono)', fontSize:11, color:'var(--text-base)' }

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

// ── Calculator component ───────────────────────────────────────────────────
function UnitCalculator() {
  const [form, setForm] = useState({
    subject:'', price:'1000', cost_price:'300', volume_l:'0.5',
    weight_kg:'0.3', scheme:'fbo', warehouse:'_default',
    buyout_pct:'85', localization_pct:'75', drr_pct:'5', custom_kvv_pct:'0',
  })
  const [result, setResult] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [subjects, setSubjects] = useState<{value:string;label:string}[]>([])
  const [subjectSearch, setSubjectSearch] = useState('')

  const { data: ratesData } = useApi(() => api.commissionsQuery('calculator'), [], 300_000)
  const defaults = ratesData as any

  const filteredSubjects = useMemo(() => {
    if (!subjectSearch || subjectSearch.length < 2) return []
    const q = subjectSearch.toLowerCase()
    // Fetch from rates
    return []
  }, [subjectSearch])

  const set = (k: string, v: string) => setForm(f => ({...f, [k]: v}))

  const compute = async () => {
    setLoading(true)
    try {
      const body = {
        subject:         form.subject,
        price:           parseFloat(form.price)||0,
        cost_price:      parseFloat(form.cost_price)||0,
        volume_l:        parseFloat(form.volume_l)||0.5,
        weight_kg:       parseFloat(form.weight_kg)||0.3,
        scheme:          form.scheme,
        warehouse:       form.warehouse,
        buyout_pct:      parseFloat(form.buyout_pct)||85,
        localization_pct:parseFloat(form.localization_pct)||75,
        drr_pct:         parseFloat(form.drr_pct)||0,
        custom_kvv_pct:  parseFloat(form.custom_kvv_pct)||0,
        category:        '',
      }
      const r = await api.commissionsCompute(body)
      setResult(r)
    } catch(e) { console.error(e) }
    finally { setLoading(false) }
  }

  const inp = (label: string, key: string, placeholder='', hint='') => (
    <div>
      <div style={{fontFamily:'var(--font-mono)',fontSize:8,color:'var(--text-dim)',marginBottom:4,letterSpacing:'0.08em'}}>{label}</div>
      <input value={form[key as keyof typeof form]} onChange={e=>set(key,e.target.value)}
        placeholder={placeholder}
        style={{width:'100%',padding:'7px 10px',boxSizing:'border-box',
          background:'var(--bg-raised)',border:'1px solid var(--border-base)',
          borderRadius:'var(--radius-sm)',color:'var(--text-base)',
          fontFamily:'var(--font-mono)',fontSize:11}}
      />
      {hint && <div style={{fontFamily:'var(--font-mono)',fontSize:8,color:'var(--text-dim)',marginTop:2,opacity:.7}}>{hint}</div>}
    </div>
  )

  const sel = (label: string, key: string, options: {v:string;l:string}[]) => (
    <div>
      <div style={{fontFamily:'var(--font-mono)',fontSize:8,color:'var(--text-dim)',marginBottom:4,letterSpacing:'0.08em'}}>{label}</div>
      <select value={form[key as keyof typeof form]} onChange={e=>set(key,e.target.value)}
        style={{width:'100%',padding:'7px 10px',background:'var(--bg-raised)',
          border:'1px solid var(--border-base)',borderRadius:'var(--radius-sm)',
          color:'var(--text-base)',fontFamily:'var(--font-mono)',fontSize:11,cursor:'pointer'}}>
        {options.map(o=><option key={o.v} value={o.v}>{o.l}</option>)}
      </select>
    </div>
  )

  const ue = result?.unit_economics
  const margin_color = ue?.is_profitable ? 'var(--green)' : 'var(--red)'

  return (
    <div style={{display:'grid',gridTemplateColumns:'340px 1fr',gap:16}}>
      {/* Input panel */}
      <div style={{background:'var(--bg-panel)',border:'1px solid var(--border-dim)',
        borderRadius:'var(--radius)',padding:'18px'}}>
        <SectionTitle title="Параметры товара"/>
        <div style={{display:'flex',flexDirection:'column',gap:10}}>
          {inp('Предмет WB (для авто-комиссии)','subject','Например: Серьги','Оставь пустым для ручной ставки')}
          {inp('Розничная цена, ₽','price','1000')}
          {inp('Себестоимость, ₽','cost_price','300')}
          {inp('Объём упаковки, л','volume_l','0.5','Влияет на тариф логистики')}
          <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:8}}>
            {sel('Схема работы','scheme',[{v:'fbo',l:'FBO (склад WB)'},{v:'fbs',l:'FBS (склад продавца)'}])}
            {sel('Склад FBO','warehouse',[
              {v:'_default',l:'Средний тариф'},
              {v:'Коледино',l:'Коледино'},
              {v:'Казань',l:'Казань'},
              {v:'Краснодар',l:'Краснодар'},
              {v:'Тула',l:'Тула'},
            ])}
          </div>
          <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:8}}>
            {inp('% выкупа','buyout_pct','85','Влияет на лог./продажу')}
            {inp('% локализации','localization_pct','75','Доля заказов с ближн. склада')}
          </div>
          <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:8}}>
            {inp('ДРР, %','drr_pct','0','Доля рекл. расходов от выручки')}
            {inp('ВВ% вручную (0=авто)','custom_kvv_pct','0')}
          </div>

          <button onClick={compute} disabled={loading} style={{
            padding:'10px',borderRadius:'var(--radius-sm)',cursor:'pointer',
            background:loading?'var(--bg-raised)':'var(--amber-glow)',
            border:`1px solid ${loading?'var(--border-dim)':'var(--amber)'}`,
            color:loading?'var(--text-dim)':'var(--amber)',
            fontFamily:'var(--font-mono)',fontSize:11,fontWeight:600,
            display:'flex',alignItems:'center',justifyContent:'center',gap:8,
            transition:'all .15s',
          }}>
            {loading ? <><RefreshCw size={12} style={{animation:'spin 1s linear infinite'}}/> РАСЧЁТ…</> : <><Calculator size={12}/> РАССЧИТАТЬ</>}
          </button>
        </div>
      </div>

      {/* Result panel */}
      <div>
        {!result && !loading && (
          <div style={{
            padding:'50px 20px',textAlign:'center',
            background:'var(--bg-panel)',border:'1px solid var(--border-dim)',
            borderRadius:'var(--radius)',height:'100%',display:'flex',
            flexDirection:'column',alignItems:'center',justifyContent:'center',gap:12,
          }}>
            <Calculator size={36} color="var(--text-dim)"/>
            <div style={{fontFamily:'var(--font-mono)',fontSize:11,color:'var(--text-dim)'}}>
              Заполни параметры и нажми РАССЧИТАТЬ
            </div>
            <div style={{fontFamily:'var(--font-mono)',fontSize:9,color:'var(--text-dim)',opacity:.6,maxWidth:260,textAlign:'center'}}>
              {(defaults?.has_commission_table)
                ? `✅ Таблица комиссий загружена: ${num(defaults?.subjects_count)} предметов`
                : '⚠ Загрузи commission.xlsx для автоопределения ВВ%'}
            </div>
          </div>
        )}

        {result && (
          <div style={{display:'flex',flexDirection:'column',gap:10}}>
            {/* Main KPIs */}
            <div style={{display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:8}}>
              <KPI label="ВЫРУЧКА ПРОДАВЦА" value={rub(result.commission?.wb_payment)}
                icon={<DollarSign size={11}/>}/>
              <KPI label="МАРЖА ВАЛОВАЯ" value={rub(ue?.gross_margin)}
                sub={pct(ue?.gross_margin_pct)} accent={ue?.gross_margin>0}
                warn={ue?.gross_margin<=0} icon={<TrendingDown size={11}/>}/>
              <KPI label="МАРЖА ЧИСТАЯ (с/с)" value={rub(ue?.net_margin)}
                sub={pct(ue?.net_margin_pct)} accent={ue?.is_profitable}
                warn={!ue?.is_profitable} icon={<BarChart2 size={11}/>}/>
              <KPI label="ROI" value={pct(ue?.roi_pct)}
                accent={ue?.roi_pct>0} warn={ue?.roi_pct<=0} icon={<TrendingDown size={11}/>}/>
            </div>

            {/* Breakdown table */}
            <div style={{background:'var(--bg-panel)',border:'1px solid var(--border-dim)',
              borderRadius:'var(--radius)',padding:'14px 16px'}}>
              <SectionTitle title="Разбивка затрат"/>
              {(result.cost_breakdown||[]).map((row:any,i:number)=>{
                const isTotal = row.item==='ИТОГО МАРЖА'
                return (
                  <div key={i} style={{
                    display:'flex',justifyContent:'space-between',alignItems:'center',
                    padding:'6px 0',
                    borderBottom: isTotal ? 'none' : '1px solid var(--border-dim)',
                    borderTop: isTotal ? '2px solid var(--border-base)' : 'none',
                    marginTop: isTotal ? 4 : 0,
                  }}>
                    <span style={{fontFamily:'var(--font-mono)',fontSize:10,
                      color:isTotal?'var(--text-white)':'var(--text-muted)',
                      fontWeight:isTotal?700:400}}>{row.item}</span>
                    <span style={{fontFamily:'var(--font-mono)',fontSize:11,fontWeight:600,
                      color:isTotal?(row.amount>=0?'var(--green)':'var(--red)'):
                           (row.amount<0?'var(--text-dim)':'var(--text-white)')}}>
                      {row.amount>0?'+':''}{rub(row.amount)}
                    </span>
                  </div>
                )
              })}
            </div>

            {/* Key params */}
            <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:8}}>
              <div style={{background:'var(--bg-panel)',border:'1px solid var(--border-dim)',
                borderRadius:'var(--radius)',padding:'12px 14px'}}>
                <SectionTitle title="Комиссия WB"/>
                <div style={{fontFamily:'var(--font-mono)',fontSize:12,color:'var(--amber)',fontWeight:700}}>
                  {pct(result.commission?.kvv_pct)}
                  <span style={{fontFamily:'var(--font-mono)',fontSize:8,color:'var(--text-dim)',marginLeft:6,fontWeight:400}}>
                    ({result.commission?.source === 'wb_table' ? '📋 из таблицы' : result.commission?.source === 'manual' ? '✏️ вручную' : '⚠ по умолчанию'})
                  </span>
                </div>
                <div style={{fontFamily:'var(--font-mono)',fontSize:9,color:'var(--text-dim)',marginTop:4}}>
                  Сумма: {rub(result.commission?.amount)}
                </div>
              </div>
              <div style={{background:'var(--bg-panel)',border:'1px solid var(--border-dim)',
                borderRadius:'var(--radius)',padding:'12px 14px'}}>
                <SectionTitle title="Логистика (на продажу)"/>
                <div style={{fontFamily:'var(--font-mono)',fontSize:12,color:'var(--text-white)',fontWeight:700}}>
                  {rub(result.logistics?.per_sale)}
                </div>
                <div style={{fontFamily:'var(--font-mono)',fontSize:9,color:'var(--text-dim)',marginTop:4}}>
                  Базовая: {rub(result.logistics?.base)} · коэфф. лок.: ×{result.logistics?.localization_coeff}
                  · возвраты: {pct(result.logistics?.return_rate_pct,0)}
                </div>
              </div>
            </div>

            {/* Breakeven */}
            <div style={{
              padding:'10px 14px',borderRadius:'var(--radius)',
              background:'rgba(59,130,246,.06)',border:'1px solid rgba(59,130,246,.2)',
              fontFamily:'var(--font-mono)',fontSize:10,color:'var(--text-dim)',
            }}>
              <span style={{color:'var(--blue)',fontWeight:600}}>Безубыточная цена:</span>
              {' '}без с/с: <strong style={{color:'var(--text-base)'}}>{rub(ue?.breakeven_no_cost)}</strong>
              {' '}· с с/с: <strong style={{color:'var(--text-base)'}}>{rub(ue?.breakeven_with_cost)}</strong>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Main page ──────────────────────────────────────────────────────────────
export default function WBCommissions() {
  const [tab, setTab] = useState<TabId>('deductions')
  const [rateSearch, setRateSearch] = useState('')
  const [rateCategory, setRateCategory] = useState('')
  const [showSchemes, setShowSchemes] = useState(false)

  const { data: deductRaw, loading: dedL, refetch: refetchDed }
    = useApi(() => api.commissionsQuery('deductions'), [], 60_000)
  const { data: ratesRaw, loading: ratesL }
    = useApi(() => api.commissionsQuery(`rates${rateCategory?`?category=${encodeURIComponent(rateCategory)}&limit=300`:'?limit=200'}`), [rateCategory])
  const { data: catsRaw }
    = useApi(() => api.commissionsQuery('categories'), [], 300_000)

  const deductions = deductRaw as any
  const ratesData  = ratesRaw  as any
  const cats       = (catsRaw  as any[]) ?? []

  const filteredRates = useMemo(() => {
    const items = ratesData?.items ?? []
    if (!rateSearch) return items
    const q = rateSearch.toLowerCase()
    return items.filter((r:any) =>
      (r.subject||'').toLowerCase().includes(q) ||
      (r.category||'').toLowerCase().includes(q)
    )
  }, [ratesData, rateSearch])

  const dedBreakdown = deductions?.deduction_breakdown ?? []
  const pieData = dedBreakdown.filter((r:any) => r.amount > 0).map((r:any) => ({
    name: r.type.slice(0,20), value: r.amount
  }))

  const Tab = ({ id, label, count }: { id: TabId; label: string; count?: number }) => (
    <button onClick={() => setTab(id)} style={{
      padding:'6px 13px', borderRadius:'var(--radius-sm)', cursor:'pointer',
      background: tab===id ? 'var(--bg-active)' : 'transparent',
      border: `1px solid ${tab===id ? 'var(--border-lit)' : 'transparent'}`,
      color: tab===id ? 'var(--amber)' : 'var(--text-muted)',
      fontFamily:'var(--font-mono)', fontSize:10, display:'flex', alignItems:'center', gap:5,
    }}>
      {label}
      {count !== undefined && (
        <span style={{
          background: tab===id ? 'var(--amber)' : 'rgba(255,255,255,.08)',
          color: tab===id ? '#000' : 'var(--text-dim)',
          borderRadius:8, padding:'1px 5px', fontSize:8, fontWeight:700,
        }}>{new Intl.NumberFormat('ru-RU').format(count)}</span>
      )}
    </button>
  )

  return (
    <div style={{ padding:28, minHeight:'100vh' }}>
      {/* Header */}
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', marginBottom:20 }}>
        <div>
          <h1 style={{ fontFamily:'var(--font-display)', fontSize:22, fontWeight:800, color:'var(--text-white)', margin:0 }}>
            Удержания WB
          </h1>
          <div style={{ fontFamily:'var(--font-mono)', fontSize:9, color:'var(--text-dim)', marginTop:3 }}>
            Комиссии · Логистика · Штрафы · Калькулятор юнит-экономики
          </div>
        </div>
        <button onClick={refetchDed} style={{
          padding:'6px 10px', borderRadius:'var(--radius-sm)', cursor:'pointer',
          background:'var(--bg-raised)', border:'1px solid var(--border-base)',
          color:'var(--text-muted)', display:'flex', alignItems:'center', gap:4,
          fontFamily:'var(--font-mono)', fontSize:10,
        }}>
          <RefreshCw size={10} style={{animation:dedL?'spin 1s linear infinite':'none'}}/>
          ОБНОВИТЬ
        </button>
      </div>

      {/* Tabs */}
      <div style={{ display:'flex', gap:5, marginBottom:16 }}>
        <Tab id="deductions" label="Удержания факт"/>
        <Tab id="rates"      label="Ставки WB" count={ratesData?.meta?.subjects}/>
        <Tab id="calculator" label="Калькулятор юнитки"/>
      </div>

      {/* ══ DEDUCTIONS ══════════════════════════════════════════════════ */}
      {tab==='deductions' && (
        <div>
          {dedL && !deductions && <div style={{display:'flex',justifyContent:'center',padding:60}}><Spinner size={32}/></div>}
          {!dedL && !deductions?.summary?.total_revenue && (
            <div style={{
              padding:'30px 20px', textAlign:'center',
              background:'var(--bg-panel)', border:'1px solid var(--border-dim)',
              borderRadius:'var(--radius)',
            }}>
              <AlertTriangle size={28} color="var(--amber)" style={{margin:'0 auto 12px'}}/>
              <div style={{fontFamily:'var(--font-mono)',fontSize:11,color:'var(--text-dim)'}}>
                Нет данных. Загрузи ежедневные отчёты и еженедельные отчёты WB.
              </div>
            </div>
          )}
          {deductions?.summary?.total_revenue > 0 && (<>
            {/* KPI row */}
            <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fill,minmax(155px,1fr))',gap:8,marginBottom:16}}>
              <KPI label="ВЫРУЧКА К ПЕРЕЧИСЛЕНИЮ" value={rub(deductions.summary.total_revenue)} icon={<DollarSign size={11}/>}/>
              <KPI label="КОМИССИЯ WB (ВВ)" value={rub(deductions.summary.total_commission_wb)} warn accent={false} icon={<TrendingDown size={11}/>}/>
              <KPI label="ЛОГИСТИКА WB" value={rub(deductions.summary.total_logistics)} warn icon={<TrendingDown size={11}/>}/>
              <KPI label="ХРАНЕНИЕ" value={rub(deductions.summary.total_storage)} icon={<TrendingDown size={11}/>}/>
              <KPI label="ШТРАФЫ" value={rub(deductions.summary.total_penalties)} warn={(deductions.summary.total_penalties||0)>0} icon={<AlertTriangle size={11}/>}/>
              <KPI label="ИТОГО УДЕРЖАНО" value={rub(deductions.summary.total_deductions)}
                sub={`${pct(deductions.summary.effective_deduction_pct)} от выручки`} warn icon={<TrendingDown size={11}/>}/>
              <KPI label="СРЕДНИЙ ВВ% ФАКТ" value={pct(deductions.summary.avg_kvv_pct)} icon={<BarChart2 size={11}/>}/>
              <KPI label="ИТОГО ЧИСТЫМИ" value={rub(deductions.summary.net_to_seller)} accent icon={<CheckCircle size={11}/>}/>
            </div>

            {/* Charts */}
            <div style={{display:'grid',gridTemplateColumns:'1fr 260px',gap:12,marginBottom:16}}>
              <div style={{background:'var(--bg-panel)',border:'1px solid var(--border-dim)',borderRadius:'var(--radius)',padding:'14px'}}>
                <SectionTitle title="Структура удержаний"/>
                <ResponsiveContainer width="100%" height={180}>
                  <BarChart data={dedBreakdown.filter((r:any)=>r.amount>0)} layout="vertical">
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border-dim)" horizontal={false}/>
                    <XAxis type="number" tick={{fontFamily:'var(--font-mono)',fontSize:8,fill:'var(--text-dim)'}} tickFormatter={v=>rub(v)}/>
                    <YAxis type="category" dataKey="type" tick={{fontFamily:'var(--font-mono)',fontSize:8,fill:'var(--text-dim)'}} width={160}/>
                    <Tooltip contentStyle={TT} formatter={(v:number)=>rub(v)}/>
                    <Bar dataKey="amount" fill="#ef4444" radius={[0,3,3,0]}/>
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <div style={{background:'var(--bg-panel)',border:'1px solid var(--border-dim)',borderRadius:'var(--radius)',padding:'14px'}}>
                <SectionTitle title="Доля удержаний"/>
                <ResponsiveContainer width="100%" height={180}>
                  <PieChart>
                    <Pie data={pieData} cx="50%" cy="50%" innerRadius={40} outerRadius={65}
                      dataKey="value" nameKey="name" paddingAngle={2}>
                      {pieData.map((_:any,i:number)=><Cell key={i} fill={C[i%C.length]}/>)}
                    </Pie>
                    <Tooltip contentStyle={TT} formatter={(v:number)=>rub(v)}/>
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Weekly additional */}
            {deductions.weekly_additional?.total_payable > 0 && (
              <div style={{
                padding:'12px 16px',marginBottom:14,
                background:'rgba(59,130,246,.06)',border:'1px solid rgba(59,130,246,.2)',
                borderRadius:'var(--radius)',fontFamily:'var(--font-mono)',fontSize:10,
                display:'flex',gap:16,flexWrap:'wrap',
              }}>
                <span style={{color:'var(--blue)',fontWeight:600}}>Из еженедельных отчётов:</span>
                <span>Приёмка: <strong>{rub(deductions.weekly_additional.acceptance_cost)}</strong></span>
                <span>Программа лояльности: <strong>{rub(deductions.weekly_additional.loyalty_program)}</strong></span>
                <span>Прочие: <strong>{rub(deductions.weekly_additional.other)}</strong></span>
                <span>К оплате итого: <strong style={{color:'var(--green)'}}>{rub(deductions.weekly_additional.total_payable)}</strong></span>
              </div>
            )}

            {/* Top by deductions */}
            <SectionTitle title="Топ SKU по удержаниям"/>
            <div style={{background:'var(--bg-panel)',border:'1px solid var(--border-dim)',borderRadius:'var(--radius)',overflow:'hidden'}}>
              <table style={{width:'100%',borderCollapse:'collapse'}}>
                <thead><tr style={{background:'var(--bg-raised)'}}>
                  {['SKU','Бренд','Категория','Комиссия','Логистика','Хранение','Штрафы','Итого','% удерж.'].map(h=>(
                    <th key={h} style={{padding:'7px 10px',textAlign:h!=='SKU'&&h!=='Бренд'&&h!=='Категория'?'right':'left',
                      fontFamily:'var(--font-mono)',fontSize:8,color:'var(--text-dim)',letterSpacing:'0.08em',
                      borderBottom:'1px solid var(--border-dim)',fontWeight:400,whiteSpace:'nowrap'}}>{h}</th>
                  ))}
                </tr></thead>
                <tbody>
                  {(deductions.top_by_deductions||[]).slice(0,30).map((r:any,i:number)=>(
                    <tr key={i} style={{borderBottom:'1px solid var(--border-dim)',
                      background:i%2?'rgba(255,255,255,.01)':'transparent'}}>
                      <td style={{padding:'6px 10px',fontFamily:'var(--font-mono)',fontSize:9,color:'var(--text-dim)'}}>{r.sku_id}</td>
                      <td style={{padding:'6px 10px',fontFamily:'var(--font-mono)',fontSize:10,color:'var(--amber)'}}>{r.brand||'—'}</td>
                      <td style={{padding:'6px 10px',fontFamily:'var(--font-mono)',fontSize:10,color:'var(--text-muted)'}}>{(r.category||'—').slice(0,20)}</td>
                      <td style={{padding:'6px 10px',fontFamily:'var(--font-mono)',fontSize:10,color:'var(--text-dim)',textAlign:'right'}}>{rub(r.commission)}</td>
                      <td style={{padding:'6px 10px',fontFamily:'var(--font-mono)',fontSize:10,color:'var(--text-dim)',textAlign:'right'}}>{rub(r.logistics)}</td>
                      <td style={{padding:'6px 10px',fontFamily:'var(--font-mono)',fontSize:10,color:'var(--text-dim)',textAlign:'right'}}>{rub(r.storage)}</td>
                      <td style={{padding:'6px 10px',fontFamily:'var(--font-mono)',fontSize:10,
                        color:(r.penalties||0)>0?'var(--red)':'var(--text-dim)',textAlign:'right'}}>{rub(r.penalties)}</td>
                      <td style={{padding:'6px 10px',fontFamily:'var(--font-mono)',fontSize:10,color:'var(--red)',textAlign:'right',fontWeight:600}}>{rub(r.total_deductions)}</td>
                      <td style={{padding:'6px 10px',fontFamily:'var(--font-mono)',fontSize:10,color:'var(--text-muted)',textAlign:'right'}}>{pct(r.deduction_rate_pct)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>)}
        </div>
      )}

      {/* ══ RATES ═══════════════════════════════════════════════════════ */}
      {tab==='rates' && (
        <div>
          {!ratesData?.total && !ratesL && (
            <div style={{
              padding:'30px 20px',textAlign:'center',
              background:'var(--bg-panel)',border:'1px solid var(--border-dim)',borderRadius:'var(--radius)',
            }}>
              <AlertTriangle size={28} color="var(--amber)" style={{margin:'0 auto 12px'}}/>
              <div style={{fontFamily:'var(--font-mono)',fontSize:11,color:'var(--text-dim)'}}>
                Таблица комиссий не загружена.<br/>
                Добавь <strong>commission.xlsx</strong> в incoming/ и нажми ЗАПУСТИТЬ на Command Center.
              </div>
            </div>
          )}
          {ratesData?.total > 0 && (<>
            {/* Filters */}
            <div style={{display:'flex',gap:8,marginBottom:12,flexWrap:'wrap'}}>
              <div style={{position:'relative',flex:'1 1 200px'}}>
                <Search size={11} style={{position:'absolute',left:9,top:'50%',transform:'translateY(-50%)',color:'var(--text-dim)'}}/>
                <input value={rateSearch} onChange={e=>setRateSearch(e.target.value)}
                  placeholder="Поиск предмета..."
                  style={{width:'100%',padding:'6px 10px 6px 28px',boxSizing:'border-box',
                    background:'var(--bg-raised)',border:'1px solid var(--border-base)',
                    borderRadius:'var(--radius-sm)',color:'var(--text-base)',
                    fontFamily:'var(--font-mono)',fontSize:10}}
                />
              </div>
              <select value={rateCategory} onChange={e=>setRateCategory(e.target.value)} style={{
                padding:'6px 10px',background:'var(--bg-raised)',border:'1px solid var(--border-base)',
                borderRadius:'var(--radius-sm)',color:'var(--text-base)',
                fontFamily:'var(--font-mono)',fontSize:10,cursor:'pointer',
              }}>
                <option value="">Все категории ({cats.length})</option>
                {cats.map((c:any)=>(
                  <option key={c.category} value={c.category}>
                    {c.category} — FBO {c.fbo_min?.toFixed(1)}%–{c.fbo_max?.toFixed(1)}% ({c.subjects_count} предметов)
                  </option>
                ))}
              </select>
              <button onClick={()=>setShowSchemes(s=>!s)} style={{
                padding:'6px 10px',background:'var(--bg-raised)',border:'1px solid var(--border-base)',
                borderRadius:'var(--radius-sm)',color:'var(--text-muted)',cursor:'pointer',
                fontFamily:'var(--font-mono)',fontSize:10,display:'flex',alignItems:'center',gap:5,
              }}>
                {showSchemes ? <ChevronUp size={10}/> : <ChevronDown size={10}/>} Все схемы
              </button>
            </div>

            <div style={{fontFamily:'var(--font-mono)',fontSize:9,color:'var(--text-dim)',marginBottom:8}}>
              Показано: {filteredRates.length} из {ratesData.total} предметов
            </div>

            <div style={{background:'var(--bg-panel)',border:'1px solid var(--border-dim)',borderRadius:'var(--radius)',overflow:'hidden'}}>
              <table style={{width:'100%',borderCollapse:'collapse'}}>
                <thead><tr style={{background:'var(--bg-raised)'}}>
                  <th style={thStyle}>Категория</th>
                  <th style={thStyle}>Предмет</th>
                  <th style={{...thStyle,textAlign:'right',color:'var(--amber)'}}>FBO %</th>
                  <th style={{...thStyle,textAlign:'right'}}>FBS (склад WB) %</th>
                  {showSchemes && (<>
                    <th style={{...thStyle,textAlign:'right'}}>FBS самост. %</th>
                    <th style={{...thStyle,textAlign:'right'}}>FBS экспресс %</th>
                    <th style={{...thStyle,textAlign:'right'}}>Самовывоз %</th>
                    <th style={{...thStyle,textAlign:'right'}}>Бронир. %</th>
                  </>)}
                </tr></thead>
                <tbody>
                  {filteredRates.slice(0,300).map((r:any,i:number)=>(
                    <tr key={i} style={{borderBottom:'1px solid var(--border-dim)',
                      background:i%2?'rgba(255,255,255,.01)':'transparent'}}>
                      <td style={{padding:'5px 10px',fontFamily:'var(--font-mono)',fontSize:9,color:'var(--text-dim)'}}>{r.category||'—'}</td>
                      <td style={{padding:'5px 10px',fontFamily:'var(--font-mono)',fontSize:10,color:'var(--text-base)'}}>{r.subject}</td>
                      <td style={{padding:'5px 10px',fontFamily:'var(--font-mono)',fontSize:11,color:'var(--amber)',textAlign:'right',fontWeight:600}}>
                        {r.fbo_pct?.toFixed(1)}%
                      </td>
                      <td style={{padding:'5px 10px',fontFamily:'var(--font-mono)',fontSize:10,color:'var(--text-muted)',textAlign:'right'}}>
                        {r.fbs_wb_pct?.toFixed(1)}%
                      </td>
                      {showSchemes && (<>
                        <td style={{padding:'5px 10px',fontFamily:'var(--font-mono)',fontSize:10,color:'var(--text-dim)',textAlign:'right'}}>{r.fbs_dbs_pct?.toFixed(1)}%</td>
                        <td style={{padding:'5px 10px',fontFamily:'var(--font-mono)',fontSize:10,color:'var(--text-dim)',textAlign:'right'}}>{r.fbs_express_pct?.toFixed(1)}%</td>
                        <td style={{padding:'5px 10px',fontFamily:'var(--font-mono)',fontSize:10,color:'var(--text-dim)',textAlign:'right'}}>{r.fbs_pickup_pct?.toFixed(1)}%</td>
                        <td style={{padding:'5px 10px',fontFamily:'var(--font-mono)',fontSize:10,color:'var(--text-dim)',textAlign:'right'}}>{r.booking_pct?.toFixed(1)}%</td>
                      </>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>)}
        </div>
      )}

      {/* ══ CALCULATOR ══════════════════════════════════════════════════ */}
      {tab==='calculator' && <UnitCalculator/>}
    </div>
  )
}

const thStyle: React.CSSProperties = {
  padding:'7px 10px', textAlign:'left',
  fontFamily:'var(--font-mono)', fontSize:8, color:'var(--text-dim)',
  letterSpacing:'0.08em', borderBottom:'1px solid var(--border-dim)',
  fontWeight:400, whiteSpace:'nowrap',
}

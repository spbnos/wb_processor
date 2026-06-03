/**
 * ProductMatrix.tsx — Матрица товаров
 * Единая карточка каждого SKU: себестоимость, габариты, комиссии WB,
 * расчётная логистика, FBO/FBS остатки, юнит-маржа, риск стокаута.
 */
import { useState, useMemo, useCallback } from 'react'
import {
  Package, DollarSign, TrendingUp, AlertTriangle,
  Truck, RefreshCw, Download, Search, Edit3,
  CheckCircle, XCircle, Info, BarChart2, ShoppingBag,
} from 'lucide-react'
import { useApi } from '../hooks/useApi'
import { api } from '../api/client'
import { fmt } from '../utils/format'
import Spinner from '../components/Spinner'

// ── helpers ────────────────────────────────────────────────────────────────
function rub(n: number) {
  if (!n || isNaN(n)) return '—'
  return `${new Intl.NumberFormat('ru-RU').format(Math.round(n))} ₽`
}
function pct(n: number, decimals = 1) {
  if (!n && n !== 0) return '—'
  return `${n.toFixed(decimals)}%`
}
function num(n: number) {
  if (!n && n !== 0) return '—'
  return new Intl.NumberFormat('ru-RU').format(Math.round(n))
}

type SortKey = 'revenue'|'margin'|'stock'|'days_of_stock'|'name'

function RiskPill({ risk }: { risk: string }) {
  const map: Record<string,[string,string]> = {
    critical: ['rgba(239,68,68,.15)','var(--red)'],
    warning:  ['rgba(245,158,11,.15)','var(--amber)'],
    ok:       ['rgba(16,185,129,.15)','var(--green)'],
    unknown:  ['rgba(255,255,255,.05)','var(--text-dim)'],
  }
  const [bg,col] = map[risk]||map.unknown
  return (
    <span style={{padding:'1px 6px',borderRadius:3,background:bg,color:col,
      fontFamily:'var(--font-mono)',fontSize:8,fontWeight:600,letterSpacing:'0.08em',whiteSpace:'nowrap'}}>
      {risk==='critical'?'КРИТИЧНО':risk==='warning'?'НИЗКИЙ':risk==='ok'?'OK':'—'}
    </span>
  )
}

function MarginBar({ pct: p }: { pct: number }) {
  const clamp = Math.max(-100, Math.min(100, p))
  const pos = clamp >= 0
  return (
    <div style={{display:'flex',alignItems:'center',gap:6}}>
      <div style={{width:50,height:5,background:'var(--bg-raised)',borderRadius:3,overflow:'hidden',flexShrink:0}}>
        {pos ? (
          <div style={{width:`${clamp}%`,height:'100%',background:'var(--green)',borderRadius:3}}/>
        ) : (
          <div style={{width:`${Math.abs(clamp)}%`,height:'100%',background:'var(--red)',borderRadius:3,marginLeft:`${100-Math.abs(clamp)}%`}}/>
        )}
      </div>
      <span style={{fontFamily:'var(--font-mono)',fontSize:9,color:pos?'var(--green)':'var(--red)',whiteSpace:'nowrap'}}>
        {pct(p)}
      </span>
    </div>
  )
}

// Inline cost editor
function CostEditor({ sku, current, onSave }: { sku:string; current:number; onSave:(v:number)=>void }) {
  const [editing, setEditing] = useState(false)
  const [val, setVal] = useState(String(current||''))
  const [saving, setSaving] = useState(false)

  const save = async () => {
    const n = parseFloat(val.replace(',','.'))
    if (isNaN(n) || n <= 0) return
    setSaving(true)
    try {
      await api.updateCost(sku, n)
      onSave(n)
      setEditing(false)
    } catch(e) { console.error(e) }
    finally { setSaving(false) }
  }

  if (!editing) return (
    <div style={{display:'flex',alignItems:'center',gap:4,cursor:'pointer'}} onClick={()=>setEditing(true)}>
      <span style={{fontFamily:'var(--font-mono)',fontSize:10,
        color:current>0?'var(--text-white)':'var(--text-dim)'}}>
        {current>0?rub(current):'нет'}
      </span>
      <Edit3 size={9} color="var(--text-dim)" style={{opacity:.5}}/>
    </div>
  )

  return (
    <div style={{display:'flex',alignItems:'center',gap:4}}>
      <input value={val} onChange={e=>setVal(e.target.value)} onKeyDown={e=>e.key==='Enter'&&save()}
        autoFocus
        style={{width:70,padding:'2px 5px',fontFamily:'var(--font-mono)',fontSize:10,
          background:'var(--bg-raised)',border:'1px solid var(--amber)',
          borderRadius:3,color:'var(--text-white)'}}
      />
      <button onClick={save} disabled={saving} style={{
        padding:'2px 4px',background:'transparent',border:'none',cursor:'pointer',
        color:'var(--green)',opacity:saving?.5:1}}>
        <CheckCircle size={11}/>
      </button>
      <button onClick={()=>setEditing(false)} style={{
        padding:'2px 4px',background:'transparent',border:'none',cursor:'pointer',color:'var(--red)'}}>
        <XCircle size={11}/>
      </button>
    </div>
  )
}

// ── Main page ──────────────────────────────────────────────────────────────
export default function ProductMatrix() {
  const [search,   setSearch]   = useState('')
  const [brand,    setBrand]    = useState('')
  const [category, setCategory] = useState('')
  const [sortBy,   setSortBy]   = useState<SortKey>('revenue')
  const [riskFilter, setRiskFilter] = useState('')
  const [hasCost,  setHasCost]  = useState<boolean|null>(null)
  const [expanded, setExpanded] = useState<string|null>(null)
  const [costsCache, setCostsCache] = useState<Record<string,number>>({})
  const [activeTab, setActiveTab] = useState<'overview'|'economics'|'stocks'|'supply'>('overview')

  // Build params
  const params = useMemo(() => {
    const p: Record<string,string> = { sort_by: sortBy, limit: '500' }
    if (brand)    p.brand    = brand
    if (category) p.category = category
    if (riskFilter) p.risk   = riskFilter
    if (hasCost !== null) p.has_cost = String(hasCost)
    return new URLSearchParams(p).toString()
  }, [brand, category, sortBy, riskFilter, hasCost])

  const { data: rawData, loading, refetch }
    = useApi(() => api.productsMatrix(params), [params], 60_000)
  const { data: categories } = useApi(() => api.productsCategories(), [], 300_000)
  const { data: brands }     = useApi(() => api.productsBrands(), [], 300_000)

  const matrix = rawData as { total:number; items:any[]; stats:Record<string,any> } | null
  const items  = matrix?.items ?? []
  const stats  = matrix?.stats ?? {}

  // Client-side search
  const filtered = useMemo(() => {
    if (!search) return items
    const q = search.toLowerCase()
    return items.filter(r =>
      (r.sku_id||'').toLowerCase().includes(q) ||
      (r.seller_article||'').toLowerCase().includes(q) ||
      (r.product_name||'').toLowerCase().includes(q) ||
      (r.brand||'').toLowerCase().includes(q) ||
      (r.barcode||'').includes(q)
    )
  }, [items, search])

  const handleCostSave = useCallback((sku: string, cost: number) => {
    setCostsCache(c => ({ ...c, [sku]: cost }))
    setTimeout(refetch, 500)
  }, [refetch])

  const handleExport = useCallback(async () => {
    try {
      const res = await fetch('/api/products/export', {
        headers: { 'X-API-Key': (window as any).__API_KEY__ ?? 'dev-key-change-in-prod' }
      })
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = 'product_matrix.csv'; a.click()
      URL.revokeObjectURL(url)
    } catch(e) { console.error(e) }
  }, [])

  return (
    <div style={{ padding:28, minHeight:'100vh' }}>
      {/* ── Header ── */}
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', marginBottom:20 }}>
        <div>
          <h1 style={{ fontFamily:'var(--font-display)', fontSize:22, fontWeight:800, color:'var(--text-white)', margin:0 }}>
            Матрица товаров
          </h1>
          <div style={{ fontFamily:'var(--font-mono)', fontSize:9, color:'var(--text-dim)', marginTop:3 }}>
            Единый реестр SKU · себестоимость · комиссии WB · юнит-экономика · FBO/FBS
          </div>
        </div>
        <div style={{ display:'flex', gap:8 }}>
          <button onClick={handleExport} style={{
            padding:'6px 12px', borderRadius:'var(--radius-sm)', cursor:'pointer',
            background:'var(--bg-raised)', border:'1px solid var(--border-base)',
            color:'var(--text-muted)', display:'flex', alignItems:'center', gap:5,
            fontFamily:'var(--font-mono)', fontSize:10,
          }}>
            <Download size={11}/> CSV
          </button>
          <button onClick={refetch} style={{
            padding:'6px 10px', borderRadius:'var(--radius-sm)', cursor:'pointer',
            background:'var(--bg-raised)', border:'1px solid var(--border-base)',
            color:'var(--text-muted)', display:'flex', alignItems:'center', gap:4,
            fontFamily:'var(--font-mono)', fontSize:10,
          }}>
            <RefreshCw size={10} style={{ animation: loading ? 'spin 1s linear infinite' : 'none' }}/>
          </button>
        </div>
      </div>

      {/* ── KPI summary ── */}
      <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill,minmax(145px,1fr))', gap:8, marginBottom:16 }}>
        {[
          { label:'ВСЕГО SKU', value:num(matrix?.total||0), icon:<ShoppingBag size={11}/> },
          { label:'С СЕБЕСТОИМОСТЬЮ', value:num(stats.with_cost||0), accent:true, icon:<DollarSign size={11}/> },
          { label:'FBO ОСТАТОК (ед.)', value:num(stats.total_fbo||0), icon:<Package size={11}/> },
          { label:'В ПУТИ', value:num(stats.total_in_transit||0), icon:<Truck size={11}/> },
          { label:'КРИТИЧЕСКИЙ РИСК', value:num(stats.critical_risk||0), warn:(stats.critical_risk||0)>0, icon:<AlertTriangle size={11}/> },
          { label:'НИЗКИЙ ОСТАТОК', value:num(stats.warning_risk||0), icon:<AlertTriangle size={11}/> },
        ].map(({ label, value, icon, accent, warn }: any) => (
          <div key={label} style={{
            background:'var(--bg-panel)',
            border:`1px solid ${warn?'rgba(239,68,68,.3)':accent?'rgba(245,158,11,.3)':'var(--border-dim)'}`,
            borderRadius:'var(--radius)', padding:'12px 14px',
          }}>
            <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:5 }}>
              <span style={{ fontFamily:'var(--font-mono)', fontSize:8, color:'var(--text-dim)', letterSpacing:'0.1em' }}>{label}</span>
              <span style={{ color:'var(--text-dim)', opacity:.5 }}>{icon}</span>
            </div>
            <div style={{ fontFamily:'var(--font-display)', fontSize:18, fontWeight:800,
              color:warn?'var(--red)':accent?'var(--amber)':'var(--text-white)' }}>{value}</div>
          </div>
        ))}
      </div>

      {/* ── Filters ── */}
      <div style={{ display:'flex', gap:8, flexWrap:'wrap', marginBottom:14, alignItems:'center' }}>
        {/* Search */}
        <div style={{ position:'relative', flex:'1 1 200px' }}>
          <Search size={11} style={{ position:'absolute', left:9, top:'50%', transform:'translateY(-50%)', color:'var(--text-dim)' }}/>
          <input value={search} onChange={e=>setSearch(e.target.value)}
            placeholder="Поиск: SKU, артикул, название..."
            style={{
              width:'100%', padding:'6px 10px 6px 28px', boxSizing:'border-box',
              background:'var(--bg-raised)', border:'1px solid var(--border-base)',
              borderRadius:'var(--radius-sm)', color:'var(--text-base)',
              fontFamily:'var(--font-mono)', fontSize:10,
            }}
          />
        </div>

        {/* Brand filter */}
        <select value={brand} onChange={e=>setBrand(e.target.value)} style={{
          padding:'6px 10px', background:'var(--bg-raised)', border:'1px solid var(--border-base)',
          borderRadius:'var(--radius-sm)', color:'var(--text-base)',
          fontFamily:'var(--font-mono)', fontSize:10, cursor:'pointer',
        }}>
          <option value="">Все бренды</option>
          {(brands as any[]||[]).map((b:any)=>(
            <option key={b.brand} value={b.brand}>{b.brand} ({b.skus})</option>
          ))}
        </select>

        {/* Category filter */}
        <select value={category} onChange={e=>setCategory(e.target.value)} style={{
          padding:'6px 10px', background:'var(--bg-raised)', border:'1px solid var(--border-base)',
          borderRadius:'var(--radius-sm)', color:'var(--text-base)',
          fontFamily:'var(--font-mono)', fontSize:10, cursor:'pointer',
        }}>
          <option value="">Все категории</option>
          {(categories as any[]||[]).map((c:any)=>(
            <option key={c.category} value={c.category}>{c.category} (ВВ {c.kvv_fbo_pct}%)</option>
          ))}
        </select>

        {/* Risk filter */}
        <select value={riskFilter} onChange={e=>setRiskFilter(e.target.value)} style={{
          padding:'6px 10px', background:'var(--bg-raised)', border:'1px solid var(--border-base)',
          borderRadius:'var(--radius-sm)', color:'var(--text-base)',
          fontFamily:'var(--font-mono)', fontSize:10, cursor:'pointer',
        }}>
          <option value="">Все риски</option>
          <option value="critical">Критический</option>
          <option value="warning">Низкий</option>
          <option value="ok">Нормальный</option>
        </select>

        {/* Cost filter */}
        <select value={hasCost===null?'':String(hasCost)}
          onChange={e=>setHasCost(e.target.value===''?null:e.target.value==='true')} style={{
          padding:'6px 10px', background:'var(--bg-raised)', border:'1px solid var(--border-base)',
          borderRadius:'var(--radius-sm)', color:'var(--text-base)',
          fontFamily:'var(--font-mono)', fontSize:10, cursor:'pointer',
        }}>
          <option value="">С/С: все</option>
          <option value="true">Есть себестоимость</option>
          <option value="false">Без себестоимости</option>
        </select>

        {/* Sort */}
        <select value={sortBy} onChange={e=>setSortBy(e.target.value as SortKey)} style={{
          padding:'6px 10px', background:'var(--bg-raised)', border:'1px solid var(--border-base)',
          borderRadius:'var(--radius-sm)', color:'var(--text-base)',
          fontFamily:'var(--font-mono)', fontSize:10, cursor:'pointer',
        }}>
          <option value="revenue">↓ Выручка</option>
          <option value="margin">↓ Маржа</option>
          <option value="stock">↓ Остаток</option>
          <option value="days_of_stock">↑ Дней остатка</option>
          <option value="name">А-Я название</option>
        </select>
      </div>

      {/* ── View tabs ── */}
      <div style={{ display:'flex', gap:5, marginBottom:12 }}>
        {([
          ['overview',   'Обзор'],
          ['economics',  'Юнит-экономика'],
          ['stocks',     'Остатки FBO/FBS'],
          ['supply',     'Поставки'],
        ] as [string,string][]).map(([id,label])=>(
          <button key={id} onClick={()=>setActiveTab(id as any)} style={{
            padding:'5px 12px', borderRadius:'var(--radius-sm)', cursor:'pointer',
            background: activeTab===id ? 'var(--bg-active)' : 'transparent',
            border: `1px solid ${activeTab===id ? 'var(--border-lit)' : 'transparent'}`,
            color: activeTab===id ? 'var(--amber)' : 'var(--text-muted)',
            fontFamily:'var(--font-mono)', fontSize:10, transition:'all .15s',
          }}>{label}</button>
        ))}
        <span style={{ fontFamily:'var(--font-mono)', fontSize:9, color:'var(--text-dim)', alignSelf:'center', marginLeft:8 }}>
          {filtered.length} из {matrix?.total||0}
        </span>
      </div>

      {loading && !matrix && (
        <div style={{ display:'flex', justifyContent:'center', padding:60 }}><Spinner size={32}/></div>
      )}

      {!loading && filtered.length === 0 && (
        <div style={{
          padding:'40px 20px', textAlign:'center',
          background:'var(--bg-panel)', border:'1px solid var(--border-dim)',
          borderRadius:'var(--radius)',
        }}>
          <BarChart2 size={28} color="var(--text-dim)" style={{ margin:'0 auto 12px' }}/>
          <div style={{ fontFamily:'var(--font-mono)', fontSize:11, color:'var(--text-dim)' }}>
            Нет товаров. Добавь «Шаблон цен» или «Актуальные_остатки» в incoming/ и нажми ЗАПУСТИТЬ.
          </div>
        </div>
      )}

      {/* ── Table ── */}
      {filtered.length > 0 && (
        <div style={{ background:'var(--bg-panel)', border:'1px solid var(--border-dim)', borderRadius:'var(--radius)', overflow:'hidden' }}>
          <div style={{ overflowX:'auto' }}>
            <table style={{ width:'100%', borderCollapse:'collapse', minWidth:900 }}>
              <thead>
                <tr style={{ background:'var(--bg-raised)' }}>
                  {activeTab === 'overview' && (<>
                    <Th w={30}/>
                    <Th>Товар</Th>
                    <Th>SKU / Артикул</Th>
                    <Th>Бренд</Th>
                    <Th>Категория</Th>
                    <Th right>Цена</Th>
                    <Th right>Скидка</Th>
                    <Th right>С/С ₽</Th>
                    <Th right>ВВ% FBO</Th>
                    <Th right>Продано ед.</Th>
                    <Th right>Выручка</Th>
                    <Th>Риск</Th>
                  </>)}
                  {activeTab === 'economics' && (<>
                    <Th>Товар / SKU</Th>
                    <Th right>Цена</Th>
                    <Th right>С/С ₽</Th>
                    <Th right>ВВ% FBO</Th>
                    <Th right>Лог. FBO ₽</Th>
                    <Th right>Маржа FBO ₽</Th>
                    <Th right>Маржа %</Th>
                    <Th right>Лог. FBS ₽</Th>
                    <Th right>Маржа FBS ₽</Th>
                    <Th right>Безубыток ₽</Th>
                    <Th right>ROI %</Th>
                  </>)}
                  {activeTab === 'stocks' && (<>
                    <Th>Товар / SKU</Th>
                    <Th right>FBO всего</Th>
                    <Th right>В пути →</Th>
                    <Th right>Возвраты ↩</Th>
                    <Th>Склады FBO</Th>
                    <Th right>Остаток (дн.)</Th>
                    <Th right>Заказов/день</Th>
                    <Th>Риск</Th>
                  </>)}
                  {activeTab === 'supply' && (<>
                    <Th>Товар / SKU</Th>
                    <Th right>Остаток (дн.)</Th>
                    <Th right>FBO ед.</Th>
                    <Th right>Потери 28д</Th>
                    <Th right>Рек. отгрузка</Th>
                    <Th right>Оборачив. (дн.)</Th>
                    <Th>Риск</Th>
                    <Th right>С/С склада ₽</Th>
                  </>)}
                </tr>
              </thead>
              <tbody>
                {filtered.slice(0,300).map((r:any, i:number) => {
                  const isOpen = expanded === r.sku_id
                  const costVal = costsCache[r.sku_id] ?? r.cost_price
                  const rowBg = i%2 ? 'rgba(255,255,255,.01)' : 'transparent'

                  return (
                    <>
                      <tr key={r.sku_id||i}
                        style={{ borderBottom:'1px solid var(--border-dim)', background:rowBg, cursor:'pointer' }}
                        onClick={()=>setExpanded(isOpen?null:r.sku_id)}>

                        {activeTab==='overview' && (<>
                          <td style={{padding:'6px 8px',textAlign:'center',color:'var(--text-dim)',fontSize:9}}>
                            {isOpen?'▼':'▶'}
                          </td>
                          <Td mono={false}><span style={{color:'var(--text-muted)',fontSize:10}}>{(r.product_name||r.category||'').slice(0,30)}</span></Td>
                          <Td color="var(--text-dim)"><div style={{fontFamily:'var(--font-mono)',fontSize:9}}>{r.sku_id||'—'}</div><div style={{fontFamily:'var(--font-mono)',fontSize:8,color:'var(--text-dim)'}}>{r.seller_article||''}</div></Td>
                          <Td color="var(--amber)">{r.brand||'—'}</Td>
                          <Td>{(r.category||'—').slice(0,22)}</Td>
                          <Td right color="var(--text-white)">{rub(r.discounted_price||r.current_price)}</Td>
                          <Td right color="var(--text-dim)">{r.current_discount_pct?pct(r.current_discount_pct):'—'}</Td>
                          <td style={{padding:'6px 10px',textAlign:'right'}} onClick={e=>e.stopPropagation()}>
                            <CostEditor sku={r.sku_id||r.seller_article} current={costVal} onSave={v=>handleCostSave(r.sku_id,v)}/>
                          </td>
                          <Td right color={r.kvv_fbo_pct?'var(--text-base)':'var(--text-dim)'}>{r.kvv_fbo_pct?pct(r.kvv_fbo_pct):'—'}</Td>
                          <Td right color="var(--text-white)">{r.units_sold?num(r.units_sold):'—'}</Td>
                          <Td right color="var(--text-white)">{r.revenue_total?rub(r.revenue_total):'—'}</Td>
                          <td style={{padding:'6px 10px'}}><RiskPill risk={r.stock_risk}/></td>
                        </>)}

                        {activeTab==='economics' && (<>
                          <Td><div style={{fontFamily:'var(--font-mono)',fontSize:9,color:'var(--amber)'}}>{r.brand||r.sku_id||'—'}</div><div style={{fontFamily:'var(--font-mono)',fontSize:8,color:'var(--text-dim)'}}>{r.sku_id||''} {r.seller_article||''}</div></Td>
                          <Td right color="var(--text-white)">{rub(r.discounted_price||r.current_price)}</Td>
                          <td style={{padding:'6px 10px',textAlign:'right'}} onClick={e=>e.stopPropagation()}>
                            <CostEditor sku={r.sku_id||r.seller_article} current={costVal} onSave={v=>handleCostSave(r.sku_id,v)}/>
                          </td>
                          <Td right>{r.kvv_fbo_pct?pct(r.kvv_fbo_pct):'—'}</Td>
                          <Td right color="var(--text-muted)">{rub(r.logistics_fbo_est)}</Td>
                          <Td right color={(r.unit_margin_fbo??0)>=0?'var(--green)':'var(--red)'}>{rub(r.unit_margin_fbo)}</Td>
                          <td style={{padding:'6px 10px'}}><MarginBar pct={r.unit_margin_pct_fbo??0}/></td>
                          <Td right color="var(--text-dim)">{rub(r.logistics_fbs_est)}</Td>
                          <Td right color={(r.unit_margin_fbs??0)>=0?'var(--green)':'var(--red)'}>{rub(r.unit_margin_fbs)}</Td>
                          <Td right color="var(--text-dim)">{r.breakeven_price_fbo?rub(r.breakeven_price_fbo):'—'}</Td>
                          <Td right color={(r.roi_pct??0)>0?'var(--green)':'var(--red)'}>{r.roi_pct?pct(r.roi_pct):'—'}</Td>
                        </>)}

                        {activeTab==='stocks' && (<>
                          <Td><div style={{fontFamily:'var(--font-mono)',fontSize:9,color:'var(--amber)'}}>{r.brand||r.sku_id}</div><div style={{fontFamily:'var(--font-mono)',fontSize:8,color:'var(--text-dim)'}}>{r.sku_id}</div></Td>
                          <Td right color="var(--text-white)">{num(r.fbo_total)}</Td>
                          <Td right color={(r.in_transit_to_customer??0)>0?'var(--amber)':'var(--text-dim)'}>{num(r.in_transit_to_customer)||'—'}</Td>
                          <Td right color={(r.in_transit_returns??0)>0?'var(--red)':'var(--text-dim)'}>{num(r.in_transit_returns)||'—'}</Td>
                          <td style={{padding:'6px 10px'}}>
                            <div style={{display:'flex',gap:3,flexWrap:'wrap'}}>
                              {Object.entries(r.fbo_by_warehouse||{}).slice(0,4).map(([wh,q]:any)=>(
                                <span key={wh} style={{
                                  padding:'1px 5px',borderRadius:3,
                                  background:'var(--bg-raised)',border:'1px solid var(--border-dim)',
                                  fontFamily:'var(--font-mono)',fontSize:7,color:'var(--text-muted)',whiteSpace:'nowrap',
                                }}>{wh.slice(0,10)}: {Math.round(q)}</span>
                              ))}
                              {Object.keys(r.fbo_by_warehouse||{}).length===0 && (
                                <span style={{fontFamily:'var(--font-mono)',fontSize:9,color:'var(--text-dim)'}}>—</span>
                              )}
                            </div>
                          </td>
                          <Td right color={r.days_of_stock<=7?'var(--red)':r.days_of_stock<=14?'var(--amber)':r.days_of_stock>0?'var(--green)':'var(--text-dim)'}>
                            {r.days_of_stock>0?r.days_of_stock:'—'}
                          </Td>
                          <Td right>{r.avg_orders_per_day>0?r.avg_orders_per_day:'—'}</Td>
                          <td style={{padding:'6px 10px'}}><RiskPill risk={r.stock_risk}/></td>
                        </>)}

                        {activeTab==='supply' && (<>
                          <Td><div style={{fontFamily:'var(--font-mono)',fontSize:9,color:'var(--amber)'}}>{r.brand||r.sku_id}</div><div style={{fontFamily:'var(--font-mono)',fontSize:8,color:'var(--text-dim)'}}>{r.seller_article||r.sku_id}</div></Td>
                          <Td right color={r.days_of_stock<=7?'var(--red)':r.days_of_stock<=14?'var(--amber)':r.days_of_stock>0?'var(--green)':'var(--text-dim)'}>
                            {r.days_of_stock>0?r.days_of_stock:'—'}
                          </Td>
                          <Td right color="var(--text-white)">{num(r.fbo_total)}</Td>
                          <Td right color={(r.rec_supply_28d??0)>0?'var(--red)':'var(--text-dim)'}>{r.revenue_loss??r.rec_supply_28d?rub(r.rec_supply_28d??0):'—'}</Td>
                          <Td right color="var(--text-white)">{r.rec_supply_28d>0?num(r.rec_supply_28d):'—'}</Td>
                          <Td right color="var(--text-muted)">{r.turnover_days>0?r.turnover_days:'—'}</Td>
                          <td style={{padding:'6px 10px'}}><RiskPill risk={r.stock_risk}/></td>
                          <Td right color={costVal>0?'var(--text-muted)':'var(--text-dim)'}>{costVal>0?rub(costVal*r.fbo_total):'—'}</Td>
                        </>)}
                      </tr>

                      {/* ── Expanded detail row ── */}
                      {isOpen && activeTab==='overview' && (
                        <tr key={`${r.sku_id}-detail`} style={{ background:'var(--bg-raised)' }}>
                          <td colSpan={12} style={{ padding:'12px 16px' }}>
                            <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill,minmax(180px,1fr))', gap:10 }}>
                              {[
                                ['Баркод', r.barcode||'—'],
                                ['Категория WB', r.category||'—'],
                                ['ВВ% FBS', pct(r.kvv_fbs_pct)],
                                ['Лог. FBO (расч.)', rub(r.logistics_fbo_est)],
                                ['Лог. FBS (расч.)', rub(r.logistics_fbs_est)],
                                ['Объём (л)', r.volume_l>0?r.volume_l.toFixed(2)+'л':'—'],
                                ['Вес', r.weight_kg>0?r.weight_kg+'кг':'—'],
                                ['Габ. (ШВД)', r.width_cm?`${r.width_cm}×${r.height_cm}×${r.length_cm}см`:'—'],
                                ['Цена фактич.', rub(r.avg_sell_price)],
                                ['Маржа FBO', `${rub(r.unit_margin_fbo)} (${pct(r.unit_margin_pct_fbo)})`],
                                ['Маржа FBS', rub(r.unit_margin_fbs)],
                                ['Безубыток FBO', rub(r.breakeven_price_fbo)],
                                ['ROI', r.roi_pct?pct(r.roi_pct):'—'],
                                ['Оборачиваемость', r.turnover_days>0?`${r.turnover_days} дн.`:'—'],
                                ['Источники данных', (r.data_sources||[]).join(', ')],
                              ].map(([k,v])=>(
                                <div key={k as string}>
                                  <div style={{fontFamily:'var(--font-mono)',fontSize:8,color:'var(--text-dim)',marginBottom:2}}>{k}</div>
                                  <div style={{fontFamily:'var(--font-mono)',fontSize:10,color:'var(--text-base)'}}>{v as string}</div>
                                </div>
                              ))}
                            </div>
                            {(r.data_sources||[]).length > 0 && (r.data_sources||[]).some((s:string)=>s==='product_catalog') ? null : (
                              <div style={{
                                marginTop:10,padding:'6px 10px',
                                background:'rgba(245,158,11,.07)',border:'1px solid rgba(245,158,11,.2)',
                                borderRadius:4,fontFamily:'var(--font-mono)',fontSize:9,color:'var(--amber)',
                                display:'flex',alignItems:'center',gap:6,
                              }}>
                                <Info size={10}/>
                                Себестоимость отсутствует в каталоге. Введи вручную (кнопка карандаша) или загрузи Актуальные_остатки_fixed.xlsx
                              </div>
                            )}
                          </td>
                        </tr>
                      )}
                    </>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Info block */}
      <div style={{
        marginTop:16, padding:'10px 14px',
        background:'rgba(59,130,246,.06)', border:'1px solid rgba(59,130,246,.2)',
        borderRadius:'var(--radius)', fontFamily:'var(--font-mono)', fontSize:9, color:'var(--text-dim)',
        lineHeight:1.7,
      }}>
        <span style={{color:'var(--blue)',fontWeight:600}}>Формула юнит-маржи FBO:</span>
        {' '}Маржа = Цена × (1 − ВВ%/100) − Логистика (расч.) − Себестоимость
        <br/>
        <span style={{color:'var(--blue)',fontWeight:600}}>Логистика WB (расч.):</span>
        {' '}по объёму упаковки согласно тарифам Оферты WB
        <br/>
        <span style={{color:'var(--blue)',fontWeight:600}}>ВВ% по категориям:</span>
        {' '}из Оферты WB 2024-2025 (обновляется вручную)
        <span style={{marginLeft:8,color:'var(--text-dim)'}}>· Себестоимость: кликни карандаш для ручного ввода</span>
      </div>
    </div>
  )
}

// ── Table primitives ─────────────────────────────────────────────────────────
function Th({ children, right, w }: { children?: React.ReactNode; right?: boolean; w?: number }) {
  return (
    <th style={{
      padding:'7px 10px', textAlign: right ? 'right' : 'left',
      fontFamily:'var(--font-mono)', fontSize:8, color:'var(--text-dim)',
      letterSpacing:'0.08em', borderBottom:'1px solid var(--border-dim)', fontWeight:400,
      whiteSpace:'nowrap', width: w,
    }}>{children}</th>
  )
}
function Td({ children, color, right, mono=true }: {
  children?: React.ReactNode; color?: string; right?: boolean; mono?: boolean
}) {
  return (
    <td style={{
      padding:'6px 10px', textAlign: right ? 'right' : 'left',
      fontFamily: mono ? 'var(--font-mono)' : 'inherit', fontSize: 10,
      color: color || 'var(--text-muted)', whiteSpace:'nowrap',
    }}>{children}</td>
  )
}

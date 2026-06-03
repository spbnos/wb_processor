import { useState } from 'react'
import { Activity, Layers, AlertTriangle, CheckCircle, Upload, RefreshCw, Play, FolderOpen } from 'lucide-react'
import { usePolling } from '../hooks/useApi'
import { api } from '../api/client'
import StatCard from '../components/StatCard'
import Badge from '../components/Badge'
import Spinner from '../components/Spinner'
import { fmt, statusColor, categoryLabel } from '../utils/format'

export default function CommandCenter() {
  const { data: stats, loading, refetch } = usePolling(api.systemStats, 8_000)
  const { data: health } = usePolling(api.health, 10_000)
  const [dragging, setDragging]   = useState(false)
  const [uploading, setUploading] = useState(false)
  const [lastTask, setLastTask]   = useState<string | null>(null)
  const [taskStatus, setTaskStatus] = useState<string | null>(null)
  const [processing, setProcessing] = useState(false)
  const [processResult, setProcessResult] = useState<{queued:number;files:string[]} | null>(null)
  const { data: incoming } = usePolling(api.listIncoming, 10_000)

  async function handleProcessAll() {
    setProcessing(true)
    setProcessResult(null)
    try {
      const r = await api.processAll()
      setProcessResult(r)
      setTimeout(refetch, 3000)
    } catch(e) { console.error(e) }
    finally { setProcessing(false) }
  }

  async function handleDrop(e: React.DragEvent) {
    e.preventDefault(); setDragging(false)
    const file = e.dataTransfer.files[0]
    if (!file) return
    setUploading(true)
    try {
      const r = await api.uploadFile(file)
      setLastTask(r.task_id)
      setTaskStatus('queued')
      // Poll task
      const poll = setInterval(async () => {
        const t = await api.taskStatus(r.task_id)
        setTaskStatus(t.status)
        if (['done','failed'].includes(t.status)) {
          clearInterval(poll); setUploading(false); refetch()
        }
      }, 1500)
    } catch { setUploading(false) }
  }

  const pending = stats?.review_queue.pending ?? 0
  const totalMappings = stats?.mappings.active ?? 0
  const queueTotal = Object.values(stats?.redis_queues ?? {}).reduce((a,b) => a+b, 0)

  return (
    <div style={{ padding: 28, animation: 'slide-in 0.3s ease' }}>
      {/* Header */}
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', marginBottom: 28 }}>
        <div>
          <h1 style={{
            fontFamily: 'var(--font-display)', fontSize: 24,
            fontWeight: 800, color: 'var(--text-white)',
            letterSpacing: '-0.5px',
          }}>
            Command Center
          </h1>
          <div style={{ fontFamily:'var(--font-mono)', fontSize:10, color:'var(--text-dim)', marginTop:4 }}>
            {new Date().toLocaleString('ru-RU')} · UPTIME {health?.uptime_seconds != null ? fmt.num(Math.floor(health.uptime_seconds)) : '—'}s
          </div>
        </div>
        <button onClick={() => refetch()} style={{
          display:'flex', alignItems:'center', gap:6,
          padding:'7px 14px', borderRadius:'var(--radius-sm)',
          background:'var(--bg-raised)', border:'1px solid var(--border-base)',
          color:'var(--text-muted)', cursor:'pointer',
          fontFamily:'var(--font-mono)', fontSize:10,
          transition:'all 0.15s',
        }}>
          <RefreshCw size={12} /> REFRESH
        </button>
      </div>

      {/* Stats grid */}
      {loading ? (
        <div style={{ display:'flex', justifyContent:'center', padding:60 }}>
          <Spinner size={32} />
        </div>
      ) : (
        <>
          <div style={{
            display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:12, marginBottom:20
          }}>
            <StatCard
              label="Активных маппингов"
              value={fmt.num(totalMappings)}
              sub={`Всего: ${fmt.num(stats?.mappings.total ?? 0)}`}
              icon={<Layers size={14}/>}
            />
            <StatCard
              label="Ожидают ревью"
              value={fmt.num(pending)}
              sub={pending > 0 ? '↑ Требует внимания' : 'Всё чисто'}
              accent={pending > 0}
              glow={pending > 0 ? 'amber' : 'none'}
              icon={<AlertTriangle size={14}/>}
            />
            <StatCard
              label="В incoming/"
              value={fmt.num(incoming?.count ?? 0)}
              sub={(incoming?.count ?? 0) > 0 ? '↑ Ожидают обработки' : 'Все обработаны'}
              accent={(incoming?.count ?? 0) > 0}
              glow={(incoming?.count ?? 0) > 0 ? 'amber' : 'none'}
              icon={<FolderOpen size={14}/>}
            />
            <StatCard
              label="Задач в очереди"
              value={fmt.num(queueTotal)}
              sub="Redis queue depth"
              glow={queueTotal > 5 ? 'amber' : 'none'}
              icon={<Activity size={14}/>}
            />
            <StatCard
              label="Система"
              value={health?.status === 'ok' ? 'ONLINE' : 'OFFLINE'}
              sub={`API · Worker · Redis`}
              glow={health?.status === 'ok' ? 'green' : 'red'}
              icon={<CheckCircle size={14}/>}
            />
          </div>

          {/* Two column layout */}
          <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:16 }}>

            {/* Drop zone */}
            <div
              onDragOver={e => { e.preventDefault(); setDragging(true) }}
              onDragLeave={() => setDragging(false)}
              onDrop={handleDrop}
              style={{
                background: dragging ? 'var(--amber-glow)' : 'var(--bg-panel)',
                border: `2px dashed ${dragging ? 'var(--amber)' : 'var(--border-base)'}`,
                borderRadius: 'var(--radius-lg)',
                padding: '32px 24px',
                textAlign: 'center',
                cursor: 'pointer',
                transition: 'all 0.2s',
                boxShadow: dragging ? 'var(--glow-amber)' : 'none',
              }}
            >
              {uploading ? (
                <div style={{ display:'flex', flexDirection:'column', alignItems:'center', gap:12 }}>
                  <Spinner size={28} />
                  <div style={{ fontFamily:'var(--font-mono)', fontSize:11, color:'var(--amber)' }}>
                    ОБРАБОТКА...
                  </div>
                  {taskStatus && (
                    <Badge
                      label={taskStatus.toUpperCase()}
                      variant={taskStatus==='done'?'ok': taskStatus==='failed'?'error':'warn'}
                    />
                  )}
                </div>
              ) : (
                <>
                  <Upload size={28} color={dragging ? 'var(--amber)' : 'var(--text-dim)'} />
                  <div style={{
                    fontFamily:'var(--font-mono)', fontSize:12,
                    color: dragging ? 'var(--amber)' : 'var(--text-muted)',
                    marginTop:12, lineHeight:1.6,
                  }}>
                    Перетащи файл сюда<br/>
                    <span style={{ fontSize:10, color:'var(--text-dim)' }}>
                      .xlsx · .xls · .csv — SmartMapper определит формат
                    </span>
                  </div>
                  {lastTask && (
                    <div style={{ marginTop:12 }}>
                      <Badge label={`TASK: ${lastTask.slice(0,8)}`} variant={taskStatus==='done'?'ok':'dim'} />
                    </div>
                  )}
                </>
              )}
            </div>

            {/* Process All incoming */}
            <div style={{
              background: 'var(--bg-panel)',
              border: `1px solid ${(incoming?.count ?? 0) > 0 ? 'rgba(245,158,11,0.3)' : 'var(--border-dim)'}`,
              borderRadius: 'var(--radius-lg)',
              padding: '20px 22px',
              display: 'flex', flexDirection: 'column', gap: 14,
            }}>
              <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center' }}>
                <div>
                  <div style={{ fontFamily:'var(--font-display)', fontSize:14, fontWeight:700, color:'var(--text-white)' }}>
                    Обработать входящие
                  </div>
                  <div style={{ fontFamily:'var(--font-mono)', fontSize:9, color:'var(--text-dim)', marginTop:3 }}>
                    CanonicalReportClassifier · {(incoming?.count ?? 0)} файлов в incoming/
                  </div>
                </div>
                <button
                  onClick={handleProcessAll}
                  disabled={processing || (incoming?.count ?? 0) === 0}
                  style={{
                    display:'flex', alignItems:'center', gap:7,
                    padding:'8px 16px', borderRadius:'var(--radius-sm)',
                    background: processing ? 'var(--bg-raised)' : (incoming?.count ?? 0) > 0 ? 'var(--amber-glow)' : 'var(--bg-raised)',
                    border: `1px solid ${processing ? 'var(--border-dim)' : (incoming?.count ?? 0) > 0 ? 'var(--amber)' : 'var(--border-dim)'}`,
                    color: processing ? 'var(--text-dim)' : (incoming?.count ?? 0) > 0 ? 'var(--amber)' : 'var(--text-dim)',
                    fontFamily:'var(--font-mono)', fontSize:11, fontWeight:600,
                    cursor: processing || (incoming?.count ?? 0) === 0 ? 'not-allowed' : 'pointer',
                    transition:'all 0.15s', letterSpacing:'0.05em',
                  }}
                >
                  {processing
                    ? <><RefreshCw size={12} style={{animation:'spin 1s linear infinite'}}/> ОБРАБОТКА…</>
                    : <><Play size={12}/> ЗАПУСТИТЬ</>
                  }
                </button>
              </div>

              {/* File list */}
              {(incoming?.files?.length ?? 0) > 0 && (
                <div style={{ maxHeight:140, overflowY:'auto' }}>
                  {(incoming?.files ?? []).slice(0, 12).map((f, i) => (
                    <div key={i} style={{
                      padding:'4px 8px', marginBottom:2,
                      background:'var(--bg-raised)', borderRadius:3,
                      fontFamily:'var(--font-mono)', fontSize:9, color:'var(--text-muted)',
                      display:'flex', justifyContent:'space-between',
                    }}>
                      <span style={{ overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap', maxWidth:'80%' }}>
                        {f.name}
                      </span>
                      <span style={{ color:'var(--text-dim)', flexShrink:0 }}>{f.size_kb}кб</span>
                    </div>
                  ))}
                  {(incoming?.files?.length ?? 0) > 12 && (
                    <div style={{ fontFamily:'var(--font-mono)', fontSize:9, color:'var(--text-dim)', padding:'4px 8px' }}>
                      …и ещё {(incoming?.files?.length ?? 0) - 12} файлов
                    </div>
                  )}
                </div>
              )}

              {/* Result */}
              {processResult && (
                <div style={{
                  padding:'8px 10px', borderRadius:4,
                  background:'rgba(34,197,94,0.08)', border:'1px solid rgba(34,197,94,0.25)',
                  fontFamily:'var(--font-mono)', fontSize:10, color:'var(--green)',
                  display:'flex', alignItems:'center', gap:6,
                }}>
                  <CheckCircle size={11}/> Запущена обработка {processResult.queued} файлов
                </div>
              )}
            </div>

            {/* Category breakdown */}
            <div style={{
              background:'var(--bg-panel)',
              border:'1px solid var(--border-dim)',
              borderRadius:'var(--radius-lg)',
              padding:'20px 24px',
            }}>
              <div style={{
                fontFamily:'var(--font-mono)', fontSize:10,
                color:'var(--text-dim)', letterSpacing:'0.1em',
                textTransform:'uppercase', marginBottom:16,
              }}>
                Маппинги по категориям
              </div>
              {Object.entries(stats?.mappings.by_category ?? {}).length === 0 ? (
                <div style={{ color:'var(--text-dim)', fontFamily:'var(--font-mono)', fontSize:11 }}>
                  Нет маппингов
                </div>
              ) : (
                Object.entries(stats?.mappings.by_category ?? {}).map(([cat, count]) => (
                  <div key={cat} style={{
                    display:'flex', justifyContent:'space-between', alignItems:'center',
                    padding:'8px 0', borderBottom:'1px solid var(--border-dim)',
                  }}>
                    <span style={{ fontFamily:'var(--font-mono)', fontSize:11, color:'var(--text-base)' }}>
                      {categoryLabel(cat)}
                    </span>
                    <span style={{
                      fontFamily:'var(--font-display)', fontSize:16, fontWeight:700,
                      color:'var(--amber)',
                    }}>
                      {count}
                    </span>
                  </div>
                ))
              )}

              {/* Queue depths */}
              <div style={{
                marginTop:16,
                fontFamily:'var(--font-mono)', fontSize:10,
                color:'var(--text-dim)', letterSpacing:'0.1em',
                textTransform:'uppercase', marginBottom:12,
              }}>
                Redis Queues
              </div>
              {Object.entries(stats?.redis_queues ?? {}).map(([q, depth]) => (
                <div key={q} style={{
                  display:'flex', justifyContent:'space-between',
                  padding:'4px 0',
                }}>
                  <span style={{ fontFamily:'var(--font-mono)', fontSize:10, color:'var(--text-muted)' }}>
                    {q.split(':').pop()}
                  </span>
                  <span style={{
                    fontFamily:'var(--font-mono)', fontSize:11,
                    color: (depth as number) > 0 ? 'var(--amber)' : 'var(--text-dim)',
                  }}>
                    {depth as number}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  )
}

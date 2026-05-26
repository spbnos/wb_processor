import { useMemo } from 'react'
import { BarChart2, TrendingUp, Package } from 'lucide-react'
import { useApi } from '../hooks/useApi'
import { api } from '../api/client'
import StatCard from '../components/StatCard'
import Spinner from '../components/Spinner'
import { fmt } from '../utils/format'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, PieChart, Pie, Cell,
} from 'recharts'

const COLORS = ['#f59e0b', '#10b981', '#3b82f6', '#ef4444', '#8b5cf6']

const ChartTooltipStyle = {
  backgroundColor: 'var(--bg-raised)',
  border: '1px solid var(--border-base)',
  borderRadius: 6,
  fontFamily: 'var(--font-mono)',
  fontSize: 11,
  color: 'var(--text-base)',
}

export default function Analytics() {
  const { data: stats, loading } = useApi(api.systemStats, [])
  const { data: mappings }       = useApi(api.mappings, [])
  const { data: reviewStats }    = useApi(api.reviewStats, [])

  const catData = useMemo(() => {
    const by = stats?.mappings.by_category ?? {}
    return Object.entries(by).map(([name, value]) => ({
      name: { wb_report: 'WB Отчёт', ad: 'Реклама', external: 'Внешний' }[name] ?? name,
      value,
    }))
  }, [stats])

  const queueData = useMemo(() => {
    const q = stats?.redis_queues ?? {}
    return Object.entries(q)
      .map(([name, value]) => ({
        name: name.split(':').pop() ?? name,
        depth: Number(value),
      }))
      .filter(d => d.name !== 'dead')
  }, [stats])

  const reviewData = useMemo(() => {
    const by = stats?.review_queue.by_status ?? {}
    return Object.entries(by).map(([name, value]) => ({ name, value }))
  }, [stats])

  const totalMappingCols = useMemo(
    () => (mappings ?? []).reduce((acc, m) => acc + m.columns, 0),
    [mappings]
  )

  return (
    <div style={{ padding: 28 }}>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 22, fontWeight: 800, color: 'var(--text-white)' }}>
          Аналитика
        </h1>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-dim)', marginTop: 4 }}>
          Статистика маппингов, очередей и review pipeline
        </div>
      </div>

      {loading ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: 60 }}>
          <Spinner size={32} />
        </div>
      ) : (
        <>
          {/* KPIs */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 24 }}>
            <StatCard
              label="Маппингов"
              value={fmt.num(stats?.mappings.active ?? 0)}
              sub={`Из ${fmt.num(stats?.mappings.total ?? 0)} всего`}
              icon={<BarChart2 size={14} />}
            />
            <StatCard
              label="Колонок замаплено"
              value={fmt.num(totalMappingCols)}
              sub="Суммарно по всем форматам"
              icon={<TrendingUp size={14} />}
            />
            <StatCard
              label="Review — всего"
              value={fmt.num(reviewStats?.total ?? 0)}
              sub={`Pending: ${fmt.num(reviewStats?.pending ?? 0)}`}
              accent={(reviewStats?.pending ?? 0) > 0}
              icon={<Package size={14} />}
            />
            <StatCard
              label="Форматов файлов"
              value={fmt.num(mappings?.length ?? 0)}
              sub="Уникальных форматов"
              glow="none"
            />
          </div>

          {/* Charts row */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>

            {/* Категории маппингов */}
            <div style={{
              background: 'var(--bg-panel)', border: '1px solid var(--border-dim)',
              borderRadius: 'var(--radius-lg)', padding: '20px 24px',
            }}>
              <div style={{
                fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-dim)',
                letterSpacing: '0.12em', textTransform: 'uppercase', marginBottom: 16,
              }}>
                Маппинги по категориям
              </div>
              {catData.length > 0 ? (
                <div style={{ display: 'flex', alignItems: 'center', gap: 24 }}>
                  <ResponsiveContainer width={160} height={160}>
                    <PieChart>
                      <Pie data={catData} cx="50%" cy="50%" innerRadius={45} outerRadius={70}
                        dataKey="value" paddingAngle={3}>
                        {catData.map((_, i) => (
                          <Cell key={i} fill={COLORS[i % COLORS.length]} />
                        ))}
                      </Pie>
                      <Tooltip contentStyle={ChartTooltipStyle} />
                    </PieChart>
                  </ResponsiveContainer>
                  <div style={{ flex: 1 }}>
                    {catData.map((d, i) => (
                      <div key={d.name} style={{
                        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                        padding: '5px 0', borderBottom: '1px solid var(--border-dim)',
                      }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <div style={{ width: 8, height: 8, borderRadius: '50%', background: COLORS[i % COLORS.length] }} />
                          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-base)' }}>
                            {d.name}
                          </span>
                        </div>
                        <span style={{ fontFamily: 'var(--font-display)', fontSize: 16, fontWeight: 700, color: 'var(--amber)' }}>
                          {d.value}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-dim)', fontFamily: 'var(--font-mono)', fontSize: 11 }}>
                  Нет данных
                </div>
              )}
            </div>

            {/* Redis queue depths */}
            <div style={{
              background: 'var(--bg-panel)', border: '1px solid var(--border-dim)',
              borderRadius: 'var(--radius-lg)', padding: '20px 24px',
            }}>
              <div style={{
                fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-dim)',
                letterSpacing: '0.12em', textTransform: 'uppercase', marginBottom: 16,
              }}>
                Redis Queue Depths
              </div>
              {queueData.length > 0 ? (
                <ResponsiveContainer width="100%" height={180}>
                  <BarChart data={queueData} barSize={28}>
                    <CartesianGrid strokeDasharray="2 4" stroke="var(--border-dim)" vertical={false} />
                    <XAxis dataKey="name" tick={{ fontFamily: 'var(--font-mono)', fontSize: 10, fill: 'var(--text-dim)' }} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fontFamily: 'var(--font-mono)', fontSize: 10, fill: 'var(--text-dim)' }} axisLine={false} tickLine={false} />
                    <Tooltip contentStyle={ChartTooltipStyle} cursor={{ fill: 'var(--bg-hover)' }} />
                    <Bar dataKey="depth" fill="var(--amber)" radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div style={{ textAlign: 'center', padding: 60, color: 'var(--text-dim)', fontFamily: 'var(--font-mono)', fontSize: 11 }}>
                  Очереди пусты
                </div>
              )}
            </div>
          </div>

          {/* Review pipeline status */}
          {reviewData.length > 0 && (
            <div style={{
              background: 'var(--bg-panel)', border: '1px solid var(--border-dim)',
              borderRadius: 'var(--radius-lg)', padding: '20px 24px',
            }}>
              <div style={{
                fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-dim)',
                letterSpacing: '0.12em', textTransform: 'uppercase', marginBottom: 16,
              }}>
                Review Pipeline по статусам
              </div>
              <div style={{ display: 'flex', gap: 16 }}>
                {reviewData.map((d, i) => {
                  const colors: Record<string, string> = {
                    pending: 'var(--amber)', approved: 'var(--green)',
                    rejected: 'var(--blue)', expired: 'var(--text-dim)',
                  }
                  const c = colors[d.name] ?? COLORS[i % COLORS.length]
                  return (
                    <div key={d.name} style={{
                      flex: 1, background: 'var(--bg-raised)', border: `1px solid var(--border-dim)`,
                      borderRadius: 'var(--radius)', padding: '14px 16px', textAlign: 'center',
                    }}>
                      <div style={{ fontFamily: 'var(--font-display)', fontSize: 28, fontWeight: 700, color: c }}>
                        {d.value}
                      </div>
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-dim)', marginTop: 4, textTransform: 'uppercase', letterSpacing: '0.1em' }}>
                        {d.name}
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}

import { useState } from 'react'
import { Brain, Zap, AlertTriangle, TrendingUp, RefreshCw } from 'lucide-react'
import { useApi, usePolling } from '../hooks/useApi'
import { api } from '../api/client'
import StatCard from '../components/StatCard'
import Badge from '../components/Badge'
import Spinner from '../components/Spinner'
import { fmt } from '../utils/format'
import type { ModelVersion } from '../types'

function ModelCard({ name }: { name: string }) {
  const { data: versions, loading } = useApi(() => api.mlVersions(name), [name])
  const active = versions?.find(v => v.status === 'active')

  return (
    <div style={{
      background: 'var(--bg-panel)',
      border: '1px solid var(--border-base)',
      borderRadius: 'var(--radius-lg)',
      padding: '20px 24px',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
        <div>
          <div style={{
            fontFamily: 'var(--font-display)', fontSize: 15, fontWeight: 700,
            color: 'var(--text-white)',
          }}>
            {name.replace('_', ' ').toUpperCase()}
          </div>
          {active && (
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-dim)', marginTop: 3 }}>
              {active.version} · {fmt.date(active.trained_at)}
            </div>
          )}
        </div>
        <Badge label={active ? 'ACTIVE' : 'NO MODEL'} variant={active ? 'ok' : 'dim'} />
      </div>

      {loading ? <Spinner size={20} /> : active ? (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 14 }}>
            {Object.entries(active.metrics).slice(0, 4).map(([k, v]) => (
              <div key={k} style={{
                background: 'var(--bg-raised)', border: '1px solid var(--border-dim)',
                borderRadius: 'var(--radius-sm)', padding: '10px 12px',
              }}>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 8, color: 'var(--text-dim)', marginBottom: 4, textTransform: 'uppercase' }}>
                  {k}
                </div>
                <div style={{ fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 700, color: 'var(--amber)' }}>
                  {typeof v === 'number' ? (v < 1 && v > 0 ? fmt.pct(v) : v.toFixed(0)) : v}
                </div>
              </div>
            ))}
          </div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-muted)' }}>
            Обучено на {fmt.num(active.training_samples)} образцах
          </div>

          {/* Version history */}
          {(versions?.length ?? 0) > 1 && (
            <div style={{ marginTop: 14 }}>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-dim)', marginBottom: 8, letterSpacing: '0.1em' }}>
                ИСТОРИЯ ВЕРСИЙ
              </div>
              {versions?.slice(0, 3).map(v => (
                <div key={v.version} style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '5px 0', borderBottom: '1px solid var(--border-dim)',
                }}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-muted)' }}>
                    {v.version}
                  </span>
                  <Badge label={v.status.toUpperCase()} variant={v.status === 'active' ? 'ok' : 'dim'} />
                </div>
              ))}
            </div>
          )}
        </>
      ) : (
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-dim)', textAlign: 'center', padding: '20px 0' }}>
          Модель ещё не обучена
        </div>
      )}
    </div>
  )
}

export default function MLInsights() {
  const { data: models, loading: modelsLoading } = useApi(api.mlModels, [])
  const { data: featStats } = useApi(api.mlFeatureStats, [])
  const [training, setTraining] = useState(false)
  const [trainResult, setTrainResult] = useState<string | null>(null)

  async function handleTrain() {
    setTraining(true); setTrainResult(null)
    try {
      const r = await api.mlTrain() as any
      const trained = (r.trained ?? []) as Array<{model: string; ok: boolean; version?: string}>
      const ok = trained.filter(t => t.ok).length
      setTrainResult(`✓ Обучено ${ok}/${trained.length} моделей`)
    } catch (e: any) {
      setTrainResult(`✗ Ошибка: ${e.message}`)
    } finally { setTraining(false) }
  }

  const salesCount = (featStats as any)?.sales_count ?? 0
  const stockCount = (featStats as any)?.stock_count ?? 0

  return (
    <div style={{ padding: 28 }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 24 }}>
        <div>
          <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 22, fontWeight: 800, color: 'var(--text-white)' }}>
            ML Insights
          </h1>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-dim)', marginTop: 4 }}>
            Аномалии · Прогнозы stockout · Model Registry
          </div>
        </div>
        <button onClick={handleTrain} disabled={training} style={{
          display: 'flex', alignItems: 'center', gap: 8,
          padding: '9px 18px', borderRadius: 'var(--radius-sm)',
          background: training ? 'var(--bg-raised)' : 'var(--amber-glow)',
          border: `1px solid ${training ? 'var(--border-base)' : 'var(--amber)'}`,
          color: training ? 'var(--text-muted)' : 'var(--amber)',
          cursor: training ? 'not-allowed' : 'pointer',
          fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 500,
          transition: 'all 0.15s',
        }}>
          {training ? <Spinner size={14} /> : <Zap size={14} />}
          {training ? 'ОБУЧЕНИЕ...' : 'ЗАПУСТИТЬ ОБУЧЕНИЕ'}
        </button>
      </div>

      {trainResult && (
        <div style={{
          padding: '10px 16px', marginBottom: 20,
          background: trainResult.startsWith('✓') ? 'var(--green-dim)' : 'var(--red-dim)',
          border: `1px solid ${trainResult.startsWith('✓') ? 'var(--green)' : 'var(--red)'}`,
          borderRadius: 'var(--radius)', fontFamily: 'var(--font-mono)', fontSize: 11,
          color: trainResult.startsWith('✓') ? 'var(--green)' : 'var(--red)',
        }}>
          {trainResult}
        </div>
      )}

      {/* Feature Store stats */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginBottom: 24 }}>
        <StatCard
          label="Sales Features"
          value={fmt.num(salesCount)}
          sub="Фич в Feature Store"
          icon={<TrendingUp size={14} />}
        />
        <StatCard
          label="Stock Features"
          value={fmt.num(stockCount)}
          sub="Фич по остаткам"
          icon={<Brain size={14} />}
        />
        <StatCard
          label="Моделей"
          value={fmt.num(models?.length ?? 0)}
          sub="В Model Registry"
          accent={true}
          icon={<Zap size={14} />}
        />
      </div>

      {/* Model cards */}
      {modelsLoading ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: 60 }}>
          <Spinner size={32} />
        </div>
      ) : (models?.length ?? 0) === 0 ? (
        <div style={{
          textAlign: 'center', padding: '60px 20px',
          background: 'var(--bg-panel)', border: '1px solid var(--border-dim)',
          borderRadius: 'var(--radius-lg)',
        }}>
          <Brain size={40} color="var(--text-dim)" style={{ margin: '0 auto 16px' }} />
          <div style={{ fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 700, color: 'var(--text-white)' }}>
            Нет обученных моделей
          </div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-dim)', marginTop: 8 }}>
            Загрузи данные → нажми «Запустить обучение»
          </div>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(380px, 1fr))', gap: 16 }}>
          {(models ?? []).map(name => <ModelCard key={name} name={name} />)}
        </div>
      )}
    </div>
  )
}

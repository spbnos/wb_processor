import { useState } from 'react'
import { Trash2, RefreshCw, GitMerge } from 'lucide-react'
import { useApi } from '../hooks/useApi'
import { api } from '../api/client'
import Badge from '../components/Badge'
import Spinner from '../components/Spinner'
import { categoryLabel, fmt } from '../utils/format'
import type { MappingItem } from '../types'

function MappingRow({ m, onDelete }: { m: MappingItem; onDelete: (id: number) => void }) {
  const [deleting, setDeleting] = useState(false)

  async function handleDelete() {
    if (!confirm(`Удалить маппинг "${m.name}"?`)) return
    setDeleting(true)
    try { await onDelete(m.id) } finally { setDeleting(false) }
  }

  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: '1fr 120px 100px 80px 80px 40px',
      alignItems: 'center', gap: 12,
      padding: '12px 16px',
      background: 'var(--bg-panel)',
      border: '1px solid var(--border-dim)',
      borderRadius: 'var(--radius)',
      transition: 'border-color 0.15s',
    }}>
      <div>
        <div style={{ fontFamily: 'var(--font-display)', fontSize: 13, fontWeight: 600, color: 'var(--text-white)' }}>
          {m.name}
        </div>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-dim)', marginTop: 2 }}>
          {m.struct_hash.slice(0, 14)}…
        </div>
      </div>

      <Badge
        label={categoryLabel(m.category)}
        variant={m.category === 'wb_report' ? 'ok' : m.category === 'ad' ? 'warn' : 'dim'}
      />

      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-muted)' }}>
        {m.subcategory ?? '—'}
      </div>

      <div style={{
        fontFamily: 'var(--font-display)', fontSize: 16, fontWeight: 700,
        color: 'var(--amber)', textAlign: 'center',
      }}>
        {m.columns}
      </div>

      <Badge label={m.active ? 'ACTIVE' : 'OFF'} variant={m.active ? 'ok' : 'dim'} />

      <button onClick={handleDelete} disabled={deleting} style={{
        background: 'transparent', border: 'none', cursor: 'pointer',
        color: 'var(--text-dim)', display: 'flex', alignItems: 'center',
        padding: 4, borderRadius: 4, transition: 'color 0.15s',
      }}>
        {deleting ? <Spinner size={12} /> : <Trash2 size={14} />}
      </button>
    </div>
  )
}

export default function Mappings() {
  const { data, loading, refetch } = useApi(api.mappings, [])
  const [deleting, setDeleting] = useState<number | null>(null)

  async function handleDelete(id: number) {
    setDeleting(id)
    try {
      await api.deleteMapping(id)
      await refetch()
    } finally { setDeleting(null) }
  }

  const mappings = data ?? []
  const active = mappings.filter(m => m.active).length

  return (
    <div style={{ padding: 28 }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 24 }}>
        <div>
          <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 22, fontWeight: 800, color: 'var(--text-white)' }}>
            Маппинги форматов
          </h1>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-dim)', marginTop: 4 }}>
            {fmt.num(active)} активных · {fmt.num(mappings.length)} всего
          </div>
        </div>
        <button onClick={() => refetch()} style={{
          display: 'flex', alignItems: 'center', gap: 6,
          padding: '7px 14px', borderRadius: 'var(--radius-sm)',
          background: 'var(--bg-raised)', border: '1px solid var(--border-base)',
          color: 'var(--text-muted)', cursor: 'pointer',
          fontFamily: 'var(--font-mono)', fontSize: 10,
        }}>
          <RefreshCw size={12} /> REFRESH
        </button>
      </div>

      {/* Table header */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '1fr 120px 100px 80px 80px 40px',
        gap: 12, padding: '8px 16px', marginBottom: 8,
        fontFamily: 'var(--font-mono)', fontSize: 9,
        color: 'var(--text-dim)', letterSpacing: '0.1em',
        textTransform: 'uppercase',
      }}>
        <span>Название / Hash</span>
        <span>Категория</span>
        <span>Подкатег.</span>
        <span style={{ textAlign: 'center' }}>Колонок</span>
        <span>Статус</span>
        <span />
      </div>

      {loading ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: 60 }}>
          <Spinner size={32} />
        </div>
      ) : mappings.length === 0 ? (
        <div style={{
          textAlign: 'center', padding: '60px 20px',
          background: 'var(--bg-panel)', border: '1px solid var(--border-dim)',
          borderRadius: 'var(--radius-lg)',
        }}>
          <GitMerge size={40} color="var(--text-dim)" style={{ margin: '0 auto 16px' }} />
          <div style={{ fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 700, color: 'var(--text-white)' }}>
            Нет маппингов
          </div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-dim)', marginTop: 8 }}>
            Загрузи файл на Command Center — SmartMapper создаст маппинг автоматически
          </div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {mappings.map(m => (
            <MappingRow key={m.id} m={m} onDelete={handleDelete} />
          ))}
        </div>
      )}
    </div>
  )
}

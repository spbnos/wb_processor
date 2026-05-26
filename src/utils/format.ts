export const fmt = {
  num:  (n: number) => new Intl.NumberFormat('ru-RU').format(n),
  pct:  (n: number) => `${(n * 100).toFixed(1)}%`,
  ms:   (ms: number) => ms < 1000 ? `${ms}ms` : `${(ms/1000).toFixed(1)}s`,
  date: (s: string) => {
    const d = new Date(s)
    if (Number.isNaN(d.getTime())) return '—'
    return d.toLocaleString('ru-RU', {
      day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
    })
  },
  conf: (score: number) => `${(score * 100).toFixed(0)}%`,
}

export function confColor(level: string): string {
  if (level === 'auto_apply')   return 'var(--green)'
  if (level === 'needs_review') return 'var(--amber)'
  if (level === 'low_conf')     return 'var(--red)'
  return 'var(--text-dim)'
}

export function statusColor(s: string): string {
  if (s === 'ok' || s === 'done')     return 'var(--green)'
  if (s === 'queued' || s === 'pending') return 'var(--amber)'
  if (s === 'error' || s === 'failed')   return 'var(--red)'
  return 'var(--text-muted)'
}

export function categoryLabel(cat: string): string {
  const m: Record<string,string> = {
    wb_report: 'WB Отчёт', ad: 'Реклама', external: 'Внешний'
  }
  return m[cat] ?? cat
}

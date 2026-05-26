interface Props {
  label: string
  variant?: 'ok' | 'warn' | 'error' | 'dim' | 'info'
}

const styles: Record<string, { bg: string; border: string; color: string }> = {
  ok:    { bg: 'var(--green-dim)',   border: 'rgba(16,185,129,0.3)',  color: 'var(--green)' },
  warn:  { bg: 'var(--yellow-dim)',  border: 'rgba(245,158,11,0.3)',  color: 'var(--amber)' },
  error: { bg: 'var(--red-dim)',     border: 'rgba(239,68,68,0.3)',   color: 'var(--red)'   },
  info:  { bg: 'var(--blue-dim)',    border: 'rgba(59,130,246,0.3)',  color: 'var(--blue)'  },
  dim:   { bg: 'var(--bg-raised)',   border: 'var(--border-dim)',     color: 'var(--text-dim)' },
}

export default function Badge({ label, variant = 'dim' }: Props) {
  const s = styles[variant] ?? styles.dim
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center',
      padding: '2px 8px', borderRadius: 3,
      background: s.bg, border: `1px solid ${s.border}`,
      color: s.color,
      fontFamily: 'var(--font-mono)', fontSize: 9,
      fontWeight: 500, letterSpacing: '0.08em',
      textTransform: 'uppercase', whiteSpace: 'nowrap',
    }}>
      {label}
    </span>
  )
}

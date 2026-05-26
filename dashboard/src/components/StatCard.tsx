import { ReactNode } from 'react'

interface Props {
  label: string
  value: string | number
  sub?: string
  accent?: boolean
  glow?: 'green' | 'amber' | 'red' | 'none'
  icon?: ReactNode
}

export default function StatCard({ label, value, sub, accent, glow = 'none', icon }: Props) {
  const glowMap = {
    green: 'var(--glow-green)',
    amber: 'var(--glow-amber)',
    red:   '0 0 20px rgba(239,68,68,0.2)',
    none:  'none',
  }
  return (
    <div style={{
      background: 'var(--bg-panel)',
      border: `1px solid ${accent ? 'var(--border-lit)' : 'var(--border-dim)'}`,
      borderRadius: 'var(--radius)',
      padding: '16px 20px',
      boxShadow: glowMap[glow],
      transition: 'all 0.2s',
    }}>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start' }}>
        <div style={{
          fontFamily: 'var(--font-mono)', fontSize: 9,
          color: 'var(--text-dim)', letterSpacing: '0.12em',
          textTransform: 'uppercase', marginBottom: 8,
        }}>
          {label}
        </div>
        {icon && <div style={{ color: 'var(--text-dim)' }}>{icon}</div>}
      </div>
      <div style={{
        fontFamily: 'var(--font-display)', fontSize: 28, fontWeight: 700,
        color: accent ? 'var(--amber)' : 'var(--text-white)',
        lineHeight: 1,
      }}>
        {value}
      </div>
      {sub && (
        <div style={{
          fontFamily: 'var(--font-mono)', fontSize: 10,
          color: 'var(--text-muted)', marginTop: 6,
        }}>
          {sub}
        </div>
      )}
    </div>
  )
}

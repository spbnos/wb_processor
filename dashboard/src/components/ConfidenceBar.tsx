interface Props { score: number; level: string; showLabel?: boolean }

function color(level: string) {
  if (level === 'auto_apply')   return 'var(--green)'
  if (level === 'needs_review') return 'var(--amber)'
  if (level === 'low_conf')     return 'var(--red)'
  return 'var(--text-dim)'
}

export default function ConfidenceBar({ score, level, showLabel = true }: Props) {
  const c = color(level)
  return (
    <div style={{ display:'flex', alignItems:'center', gap:8 }}>
      <div style={{
        flex:1, height:4,
        background: 'var(--bg-raised)',
        borderRadius: 2, overflow:'hidden',
      }}>
        <div style={{
          width: `${score * 100}%`, height: '100%',
          background: c,
          borderRadius: 2,
          transition: 'width 0.4s ease',
          boxShadow: `0 0 6px ${c}`,
        }} />
      </div>
      {showLabel && (
        <span style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 11, color: c,
          minWidth: 34, textAlign: 'right',
        }}>
          {(score * 100).toFixed(0)}%
        </span>
      )}
    </div>
  )
}

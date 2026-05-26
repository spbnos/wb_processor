interface Props { size?: number; color?: string }
export default function Spinner({ size = 20, color = 'var(--amber)' }: Props) {
  return (
    <div style={{
      width: size, height: size, borderRadius: '50%',
      border: `${Math.max(2, size / 8)}px solid var(--border-dim)`,
      borderTopColor: color,
      animation: 'spin 0.8s linear infinite',
      flexShrink: 0,
    }} />
  )
}

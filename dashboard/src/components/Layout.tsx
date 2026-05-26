import { NavLink, Outlet } from 'react-router-dom'
import { Activity, FileUp, GitBranch, Brain, BarChart2, Settings } from 'lucide-react'
import { usePolling } from '../hooks/useApi'
import { api } from '../api/client'

const NAV = [
  { to: '/',        icon: Activity,   label: 'Command Center' },
  { to: '/files',   icon: FileUp,     label: 'Files' },
  { to: '/review',  icon: GitBranch,  label: 'Review' },
  { to: '/mappings',icon: Settings,   label: 'Mappings' },
  { to: '/ml',      icon: Brain,      label: 'ML Insights' },
  { to: '/analytics',icon: BarChart2, label: 'Analytics' },
]

export default function Layout() {
  const { data: health } = usePolling(api.health, 10_000)

  return (
    <div style={{ display:'flex', height:'100vh', overflow:'hidden' }}>
      {/* Sidebar */}
      <nav style={{
        width: 220, flexShrink: 0,
        background: 'var(--bg-panel)',
        borderRight: '1px solid var(--border-dim)',
        display: 'flex', flexDirection: 'column',
        overflow: 'hidden',
      }}>
        {/* Logo */}
        <div style={{
          padding: '20px 20px 16px',
          borderBottom: '1px solid var(--border-dim)',
        }}>
          <div style={{
            fontFamily: 'var(--font-display)',
            fontSize: 18, fontWeight: 800,
            color: 'var(--text-white)',
            letterSpacing: '-0.5px',
          }}>
            WB<span style={{ color: 'var(--amber)' }}>·</span>PLATFORM
          </div>
          <div style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 10, color: 'var(--text-dim)',
            marginTop: 2, letterSpacing: '0.08em',
          }}>
            COMMAND CENTER v2.0
          </div>
        </div>

        {/* Status dot */}
        <div style={{
          padding: '10px 20px',
          borderBottom: '1px solid var(--border-dim)',
          display: 'flex', alignItems: 'center', gap: 8,
        }}>
          <div style={{
            width: 7, height: 7, borderRadius: '50%',
            background: health?.status === 'ok' ? 'var(--green)' : 'var(--red)',
            boxShadow: health?.status === 'ok' ? 'var(--glow-green)' : 'none',
            animation: 'pulse-amber 2s infinite',
          }} />
          <span style={{ fontFamily:'var(--font-mono)', fontSize:10, color:'var(--text-muted)' }}>
            {health?.status === 'ok' ? 'СИСТЕМА АКТИВНА' : 'OFFLINE'}
          </span>
        </div>

        {/* Nav links */}
        <div style={{ flex: 1, padding: '8px 12px', overflowY: 'auto' }}>
          {NAV.map(({ to, icon: Icon, label }) => (
            <NavLink key={to} to={to} end={to === '/'}
              style={({ isActive }) => ({
                display: 'flex', alignItems: 'center', gap: 10,
                padding: '8px 12px', borderRadius: 'var(--radius-sm)',
                marginBottom: 2,
                background: isActive ? 'var(--bg-active)' : 'transparent',
                border: `1px solid ${isActive ? 'var(--border-lit)' : 'transparent'}`,
                color: isActive ? 'var(--amber)' : 'var(--text-muted)',
                textDecoration: 'none', transition: 'all 0.15s',
                fontFamily: 'var(--font-mono)', fontSize: 11,
                fontWeight: isActive ? 500 : 400,
                letterSpacing: '0.06em',
              })}
            >
              <Icon size={14} />
              {label}
            </NavLink>
          ))}
        </div>

        {/* Footer */}
        <div style={{
          padding: '12px 20px',
          borderTop: '1px solid var(--border-dim)',
          fontFamily: 'var(--font-mono)', fontSize: 9,
          color: 'var(--text-dim)', lineHeight: 1.8,
        }}>
          <div>BUILD 2024.12.01</div>
          <div>ФАЗЫ 0–6 ✓</div>
        </div>
      </nav>

      {/* Main */}
      <main style={{ flex: 1, overflow: 'auto', background: 'var(--bg-base)' }}>
        <Outlet />
      </main>
    </div>
  )
}

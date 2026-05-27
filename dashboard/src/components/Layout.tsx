import { NavLink, Outlet } from 'react-router-dom'
import { Activity, FileUp, GitBranch, Brain, BarChart2, Settings, BookOpen } from 'lucide-react'
import { usePolling } from '../hooks/useApi'
import { api } from '../api/client'

export default function Layout() {
  const { data: health }    = usePolling(api.health,      10_000)
  const { data: stats }     = usePolling(api.systemStats, 8_000)
  const { data: kbStatus }  = usePolling(api.kbStatus,    30_000)

  const pendingReview = stats?.review_queue?.pending ?? 0

  const NAV = [
    { to: '/',          icon: Activity,   label: 'Command Center', badge: null },
    { to: '/files',     icon: FileUp,     label: 'Files',          badge: null },
    { to: '/review',    icon: GitBranch,  label: 'Review',         badge: pendingReview > 0 ? pendingReview : null },
    { to: '/mappings',  icon: Settings,   label: 'Mappings',       badge: null },
    { to: '/ml',        icon: Brain,      label: 'ML Insights',    badge: null },
    { to: '/analytics', icon: BarChart2,  label: 'Analytics',      badge: null },
  ]

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
          {NAV.map(({ to, icon: Icon, label, badge }) => (
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
              <span style={{ flex: 1 }}>{label}</span>
              {badge !== null && (
                <span style={{
                  background: 'var(--amber)', color: '#000',
                  borderRadius: 8, padding: '1px 6px',
                  fontSize: 9, fontWeight: 700,
                  fontFamily: 'var(--font-mono)',
                  minWidth: 16, textAlign: 'center',
                }}>
                  {badge}
                </span>
              )}
            </NavLink>
          ))}
        </div>

        {/* KB Status block */}
        <div style={{
          margin: '0 12px 8px',
          padding: '10px 12px',
          background: 'var(--bg-raised)',
          border: '1px solid var(--border-dim)',
          borderRadius: 'var(--radius-sm)',
        }}>
          <div style={{ display:'flex', alignItems:'center', gap:6, marginBottom:6 }}>
            <BookOpen size={10} color="var(--text-dim)" />
            <span style={{ fontFamily:'var(--font-mono)', fontSize:9, color:'var(--text-dim)', letterSpacing:'0.1em' }}>
              KNOWLEDGE BASE
            </span>
          </div>
          {kbStatus ? (
            <>
              <div style={{ fontFamily:'var(--font-mono)', fontSize:10, color:'var(--text-muted)', lineHeight:1.7 }}>
                <div>
                  <span style={{ color:'var(--text-dim)' }}>PDF: </span>
                  <span style={{ color: kbStatus.loaded_pdfs > 0 ? 'var(--green)' : 'var(--amber)' }}>
                    {kbStatus.loaded_pdfs}/{kbStatus.available_pdfs}
                  </span>
                  {kbStatus.loaded_pdfs === 0 && (
                    <span style={{ color:'var(--amber)', marginLeft:4 }}>⚠</span>
                  )}
                </div>
                <div>
                  <span style={{ color:'var(--text-dim)' }}>Термины: </span>
                  <span style={{ color:'var(--text-base)' }}>{kbStatus.indexed_terms}</span>
                </div>
                <div>
                  <span style={{ color:'var(--text-dim)' }}>Поля WB: </span>
                  <span style={{ color:'var(--text-base)' }}>{kbStatus.registry_fields}</span>
                </div>
              </div>
              {kbStatus.loaded_pdfs === 0 && kbStatus.available_pdfs > 0 && (
                <button
                  onClick={() => api.kbReindex().then(() => window.location.reload())}
                  style={{
                    marginTop:6, width:'100%', padding:'4px 0',
                    background:'var(--amber-glow)', border:'1px solid var(--amber)',
                    borderRadius:3, color:'var(--amber)',
                    fontFamily:'var(--font-mono)', fontSize:9, cursor:'pointer',
                    letterSpacing:'0.08em',
                  }}
                >
                  ПЕРЕИНДЕКСИРОВАТЬ
                </button>
              )}
            </>
          ) : (
            <div style={{ fontFamily:'var(--font-mono)', fontSize:9, color:'var(--text-dim)' }}>
              загрузка…
            </div>
          )}
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

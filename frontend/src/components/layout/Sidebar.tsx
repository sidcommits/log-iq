// frontend/src/components/layout/Sidebar.tsx
import { NavLink } from 'react-router-dom'
import { StatusPanel } from './StatusPanel'

const NAV_ITEMS = [
  { to: '/', label: 'Search', exact: true, icon: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <circle cx="6.5" cy="6.5" r="4.5"/><path d="M10 10l3.5 3.5"/>
    </svg>
  )},
  { to: '/anomalies', label: 'Anomalies', exact: false, icon: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M8 2L14 13H2L8 2z"/><path d="M8 7v3M8 11.5v.5" strokeLinecap="round"/>
    </svg>
  )},
  { to: '/tasks', label: 'Tasks', exact: false, icon: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <rect x="2" y="2" width="12" height="12"/><path d="M5 8l2 2 4-4" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  )},
]

const SYSTEM_ITEMS = [
  { to: '/health', label: 'Health', exact: false, icon: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M2 8h3l2-4 2 8 2-4h3" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  )},
]

const navItemStyle = (isActive: boolean): React.CSSProperties => ({
  display: 'flex',
  alignItems: 'center',
  gap: '10px',
  padding: '9px 18px',
  cursor: 'pointer',
  color: isActive ? 'var(--amber)' : 'var(--text-secondary)',
  background: isActive ? 'var(--bg-active)' : 'transparent',
  fontFamily: 'var(--font-head)',
  fontWeight: 500,
  fontSize: '14px',
  textTransform: 'uppercase' as const,
  letterSpacing: '0.1em',
  textDecoration: 'none',
  border: 'none',
  width: '100%',
  position: 'relative' as const,
  borderLeft: isActive ? '2px solid var(--amber)' : '2px solid transparent',
  transition: 'all 0.15s',
})

export function Sidebar() {
  return (
    <aside style={{
      width: '220px',
      flexShrink: 0,
      background: 'var(--bg-sidebar)',
      borderRight: '1px solid var(--border)',
      display: 'flex',
      flexDirection: 'column',
    }}>
      <div style={{ padding: '20px 18px 16px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: '9px' }}>
        <div style={{ width: '26px', height: '26px', border: '1.5px solid var(--amber)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
          <span style={{ color: 'var(--amber)', fontSize: '11px' }}>◆</span>
        </div>
        <div>
          <div style={{ fontFamily: 'var(--font-head)', fontSize: '18px', fontWeight: 700, letterSpacing: '0.12em', color: 'var(--amber)', textTransform: 'uppercase' }}>LogIQ</div>
          <div style={{ fontSize: '10px', color: 'var(--text-muted)', letterSpacing: '0.06em' }}>v1.0.0-rc1</div>
        </div>
      </div>

      <nav style={{ flex: 1, padding: '10px 0', overflowY: 'auto' }}>
        <div style={{ fontFamily: 'var(--font-head)', fontSize: '12px', fontWeight: 600, letterSpacing: '0.15em', color: 'var(--text-muted)', textTransform: 'uppercase', padding: '8px 18px 4px' }}>Intelligence</div>
        {NAV_ITEMS.map((item) => (
          <NavLink key={item.to} to={item.to} end={item.exact} style={({ isActive }) => navItemStyle(isActive)}>
            {item.icon}
            {item.label}
          </NavLink>
        ))}
        <div style={{ fontFamily: 'var(--font-head)', fontSize: '12px', fontWeight: 600, letterSpacing: '0.15em', color: 'var(--text-muted)', textTransform: 'uppercase', padding: '16px 18px 4px' }}>System</div>
        {SYSTEM_ITEMS.map((item) => (
          <NavLink key={item.to} to={item.to} end={item.exact} style={({ isActive }) => navItemStyle(isActive)}>
            {item.icon}
            {item.label}
          </NavLink>
        ))}
      </nav>

      <StatusPanel />
    </aside>
  )
}

// frontend/src/components/layout/TopBar.tsx
import { useLocation } from 'react-router-dom'
import { useEffect, useState } from 'react'

const PAGE_LABELS: Record<string, string> = {
  '/': 'SEARCH',
  '/anomalies': 'ANOMALIES',
  '/tasks': 'TASKS',
  '/health': 'HEALTH',
}

export function TopBar() {
  const location = useLocation()
  const label = PAGE_LABELS[location.pathname] ?? 'LOGIQ'
  const [time, setTime] = useState(() => new Date().toUTCString().slice(17, 25))

  useEffect(() => {
    const id = setInterval(() => setTime(new Date().toUTCString().slice(17, 25)), 1000)
    return () => clearInterval(id)
  }, [])

  return (
    <div style={{
      height: '44px',
      borderBottom: '1px solid var(--border)',
      display: 'flex',
      alignItems: 'center',
      padding: '0 20px',
      background: 'var(--bg)',
      flexShrink: 0,
    }}>
      <div style={{ fontFamily: 'var(--font-head)', fontSize: '14px', fontWeight: 600, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>
        LOGIQ / <span style={{ color: 'var(--amber)' }}>{label}</span>
      </div>
      <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '16px', fontSize: '13px', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
        <span>{time} UTC</span>
      </div>
    </div>
  )
}

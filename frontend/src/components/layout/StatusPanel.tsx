import { useHealth } from '../../hooks/useHealth'

export function StatusPanel() {
  const { data, status } = useHealth()
  const firstSource = data?.sync_sources[0]

  return (
    <div style={{ borderTop: '1px solid var(--border)', padding: '14px 18px', fontSize: '13px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '8px', fontFamily: 'var(--font-head)', fontWeight: 600, fontSize: '12px', letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>
        <span style={{
          width: '6px', height: '6px', borderRadius: '50%', flexShrink: 0,
          background: status === 'success' ? 'var(--green)' : 'var(--text-muted)',
          boxShadow: status === 'success' ? '0 0 6px var(--green)' : 'none',
        }} />
        Ingestion
      </div>

      {status !== 'success' ? (
        <div style={{ color: 'var(--text-muted)', fontSize: '12px' }}>Connecting...</div>
      ) : (
        <>
          <StatusRow label="Events" value={data.metrics.total_logs.toLocaleString()} highlight />
          <StatusRow label="Last sync" value={firstSource?.last_synced_at ? formatAgo(firstSource.last_synced_at) : '—'} />
          <StatusRow label="Mode" value={firstSource?.mode.toUpperCase() ?? '—'} />
          <StatusRow label="Lag" value={firstSource?.lag_ms != null ? `${firstSource.lag_ms}ms` : '—'} />
        </>
      )}
    </div>
  )
}

function StatusRow({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', padding: '2px 0' }}>
      <span style={{ color: 'var(--text-muted)', fontSize: '12px' }}>{label}</span>
      <span style={{ color: highlight ? 'var(--amber)' : 'var(--text-secondary)', fontSize: '12px' }}>{value}</span>
    </div>
  )
}

function formatAgo(isoString: string): string {
  const diffMs = Date.now() - new Date(isoString).getTime()
  const diffS = Math.floor(diffMs / 1000)
  if (diffS < 60) return `${diffS}s ago`
  return `${Math.floor(diffS / 60)}m ago`
}

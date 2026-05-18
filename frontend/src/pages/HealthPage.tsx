import { useHealth } from '../hooks/useHealth'
import { ErrorState } from '../components/ui/ErrorState'
import type { HealthDependency, SyncStatus } from '../api/types'

const STATUS_COLOR: Record<string, string> = {
  ok:       'var(--green)',
  degraded: 'var(--amber)',
  error:    'var(--red)',
}

export function HealthPage() {
  const { data, isLoading, isError, refetch } = useHealth()

  if (isError) return <ErrorState message="Failed to load health status" onRetry={refetch} />

  return (
    <div>
      <div style={{ fontFamily: 'var(--font-head)', fontSize: '22px', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: '4px' }}>System Health</div>
      <div style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '24px' }}>Live dependency status — polling every 5s</div>

      <SectionLabel>Dependencies</SectionLabel>
      {isLoading ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: '12px', marginBottom: '24px' }}>
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} style={{ border: '1px solid var(--border)', background: 'var(--bg-panel)', padding: '16px', height: '80px' }} />
          ))}
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: '12px', marginBottom: '24px' }}>
          {data?.dependencies?.map((dep) => <DependencyCard key={dep.name} dep={dep} />)}
        </div>
      )}

      <SectionLabel>LogIQ Metrics</SectionLabel>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px', marginBottom: '24px' }}>
        {isLoading ? (
          [1, 2, 3, 4].map((i) => <div key={i} style={{ border: '1px solid var(--border)', background: 'var(--bg-panel)', padding: '14px 16px', height: '72px' }} />)
        ) : (
          <>
            <MetricCard value={data?.metrics.total_logs.toLocaleString() ?? '—'} label="Logs Ingested" />
            <MetricCard value={String(data?.metrics.total_anomalies ?? '—')} label="Anomalies Detected" />
            <MetricCard value={String(data?.metrics.total_rcas ?? '—')} label="RCAs Generated" />
            <MetricCard value={String(data?.metrics.pending_tasks ?? '—')} label="Pending Tasks" />
          </>
        )}
      </div>

      <SectionLabel>Source Sync Status</SectionLabel>
      <table style={{ width: '100%', borderCollapse: 'collapse', border: '1px solid var(--border)' }}>
        <thead>
          <tr>
            {['Source', 'Mode', 'Last Synced', 'Lag', 'Status'].map((h) => (
              <th key={h} style={{ fontFamily: 'var(--font-head)', fontSize: '12px', fontWeight: 700, letterSpacing: '0.15em', textTransform: 'uppercase', color: 'var(--text-muted)', padding: '8px 14px', borderBottom: '1px solid var(--border)', background: 'var(--bg-sidebar)', textAlign: 'left' }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {isLoading ? (
            <tr><td colSpan={5} style={{ padding: '20px 14px', color: 'var(--text-muted)', fontSize: '13px' }}>Loading...</td></tr>
          ) : data?.sync_sources?.map((src) => (
            <SyncRow key={src.source_name} src={src} />
          ))}
        </tbody>
      </table>
    </div>
  )
}

function DependencyCard({ dep }: { dep: HealthDependency }) {
  const color = STATUS_COLOR[dep.status] ?? 'var(--text-muted)'
  return (
    <div style={{ border: '1px solid var(--border)', background: 'var(--bg-panel)', padding: '16px', position: 'relative', borderLeft: `3px solid ${color}` }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '10px' }}>
        <div style={{ fontFamily: 'var(--font-head)', fontSize: '14px', fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase' }}>{dep.name}</div>
        <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: color, boxShadow: `0 0 8px ${color}` }} />
      </div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: '20px', fontWeight: 300, marginBottom: '2px' }}>
        {dep.latency_ms != null ? `${dep.latency_ms}ms` : '—'}
      </div>
      <div style={{ fontFamily: 'var(--font-head)', fontSize: '12px', fontWeight: 600, letterSpacing: '0.12em', textTransform: 'uppercase', color }}>{dep.status}</div>
    </div>
  )
}

function MetricCard({ value, label }: { value: string; label: string }) {
  return (
    <div style={{ border: '1px solid var(--border)', background: 'var(--bg-panel)', padding: '14px 16px' }}>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: '26px', fontWeight: 400, lineHeight: 1.1, marginBottom: '4px' }}>{value}</div>
      <div style={{ fontFamily: 'var(--font-head)', fontSize: '12px', fontWeight: 600, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>{label}</div>
    </div>
  )
}

function SyncRow({ src }: { src: SyncStatus }) {
  return (
    <tr>
      <td style={{ padding: '10px 14px', borderBottom: '1px solid var(--border)', fontFamily: 'var(--font-head)', fontSize: '14px', fontWeight: 600, letterSpacing: '0.06em', color: 'var(--text-secondary)', textTransform: 'uppercase' }}>{src.source_name}</td>
      <td style={{ padding: '10px 14px', borderBottom: '1px solid var(--border)' }}>
        <span style={{ fontFamily: 'var(--font-head)', fontSize: '12px', fontWeight: 600, letterSpacing: '0.1em', textTransform: 'uppercase', padding: '2px 7px', border: '1px solid var(--border-mid)', color: 'var(--text-secondary)' }}>{src.mode}</span>
      </td>
      <td style={{ padding: '10px 14px', borderBottom: '1px solid var(--border)', fontSize: '13px', color: 'var(--text-muted)' }}>{src.last_synced_at ? new Date(src.last_synced_at).toUTCString().slice(0, 25) : '—'}</td>
      <td style={{ padding: '10px 14px', borderBottom: '1px solid var(--border)', color: src.lag_ms && src.lag_ms < 1000 ? 'var(--green)' : 'var(--text-secondary)', fontSize: '14px' }}>{src.lag_ms != null ? `${src.lag_ms}ms` : '—'}</td>
      <td style={{ padding: '10px 14px', borderBottom: '1px solid var(--border)' }}>
        <span style={{ fontFamily: 'var(--font-head)', fontSize: '12px', fontWeight: 600, letterSpacing: '0.1em', textTransform: 'uppercase', padding: '2px 8px', border: '1px solid', borderColor: src.online ? 'var(--green)' : 'var(--red)', color: src.online ? 'var(--green)' : 'var(--red)', background: src.online ? 'var(--green-dim)' : 'var(--red-dim)' }}>
          {src.online ? 'Online' : 'Offline'}
        </span>
      </td>
    </tr>
  )
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ fontFamily: 'var(--font-head)', fontSize: '13px', fontWeight: 600, letterSpacing: '0.15em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: '12px', paddingBottom: '6px', borderBottom: '1px solid var(--border)' }}>
      {children}
    </div>
  )
}

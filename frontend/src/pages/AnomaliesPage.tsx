import { useState } from 'react'
import { useAnomalies, useReviewAnomaly } from '../hooks/useAnomalies'
import { SeverityBadge } from '../components/ui/SeverityBadge'
import { ScoreBar } from '../components/ui/ScoreBar'
import { ErrorState } from '../components/ui/ErrorState'
import type { AnomalyResult } from '../api/types'

export function AnomaliesPage() {
  const [showReviewed, setShowReviewed] = useState(false)
  const { data, isLoading, isError, refetch } = useAnomalies({ reviewed: showReviewed ? undefined : false })
  const { mutate: review } = useReviewAnomaly()
  const [expandedId, setExpandedId] = useState<string | null>(null)

  if (isError) return <ErrorState message="Failed to load anomalies" onRetry={refetch} />

  return (
    <div>
      <div style={{ fontFamily: 'var(--font-head)', fontSize: '22px', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: '4px' }}>Anomaly Feed</div>
      <div style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '20px' }}>Flagged by KNN outlier detection — sorted by score</div>

      <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
        <button onClick={() => setShowReviewed(false)} style={filterTabStyle(!showReviewed)}>Unreviewed</button>
        <button onClick={() => setShowReviewed(true)} style={filterTabStyle(showReviewed)}>All</button>
      </div>

      {isLoading && <SkeletonTable />}

      {!isLoading && data && (data.anomalies?.length ?? 0) === 0 && (
        <div style={{ padding: '48px 0', textAlign: 'center', color: 'var(--text-muted)' }}>No anomalies matching current filter</div>
      )}

      {!isLoading && data && (data.anomalies?.length ?? 0) > 0 && (
        <table style={{ width: '100%', borderCollapse: 'collapse', border: '1px solid var(--border)' }}>
          <thead>
            <tr>
              {['Score', 'Service', 'Severity', 'Timestamp', 'Message', 'Status'].map((h) => (
                <th key={h} style={{ fontFamily: 'var(--font-head)', fontSize: '12px', fontWeight: 700, letterSpacing: '0.15em', textTransform: 'uppercase', color: 'var(--text-muted)', padding: '9px 14px', textAlign: 'left', borderBottom: '1px solid var(--border)', background: 'var(--bg-sidebar)', whiteSpace: 'nowrap' }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.anomalies?.map((anomaly) => (
              <AnomalyRow
                key={anomaly.id}
                anomaly={anomaly}
                expanded={expandedId === anomaly.id}
                onToggle={() => setExpandedId(expandedId === anomaly.id ? null : anomaly.id)}
                onReview={() => review(anomaly.id)}
              />
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

function AnomalyRow({ anomaly, expanded, onToggle, onReview }: { anomaly: AnomalyResult; expanded: boolean; onToggle: () => void; onReview: () => void }) {
  const { log, score, reviewed } = anomaly
  if (!log) return null
  return (
    <>
      <tr onClick={onToggle} style={{ cursor: 'pointer' }}>
        <td style={tdStyle}><ScoreBar score={score} /></td>
        <td style={tdStyle}><span style={{ fontFamily: 'var(--font-head)', fontSize: '14px', fontWeight: 600, letterSpacing: '0.06em', color: 'var(--text-secondary)', textTransform: 'uppercase' }}>{log.service}</span></td>
        <td style={tdStyle}><SeverityBadge severity={log.severity} /></td>
        <td style={{ ...tdStyle, fontSize: '13px', color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>{new Date(log.timestamp).toUTCString().slice(0, 25)}</td>
        <td style={{ ...tdStyle, maxWidth: '300px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: '14px' }}>{log.message}</td>
        <td style={tdStyle}>
          <span style={{ fontFamily: 'var(--font-head)', fontSize: '12px', fontWeight: 600, letterSpacing: '0.1em', textTransform: 'uppercase', padding: '2px 8px', border: '1px solid', borderColor: reviewed ? 'var(--green)' : 'var(--border-mid)', color: reviewed ? 'var(--green)' : 'var(--text-muted)', background: reviewed ? 'var(--green-dim)' : 'transparent' }}>
            {reviewed ? 'Reviewed' : 'Pending'}
          </span>
        </td>
      </tr>
      {expanded && (
        <tr>
          <td colSpan={6} style={{ padding: '12px 14px', borderBottom: '1px solid var(--border)', background: 'var(--bg-panel)' }}>
            <pre style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', color: 'var(--text-secondary)', overflowX: 'auto', marginBottom: '12px' }}>{JSON.stringify(log, null, 2)}</pre>
            {!reviewed && (
              <button
                onClick={(e) => { e.stopPropagation(); onReview() }}
                style={{ fontFamily: 'var(--font-head)', fontSize: '13px', fontWeight: 600, letterSpacing: '0.1em', textTransform: 'uppercase', background: 'var(--green-dim)', border: '1px solid var(--green)', color: 'var(--green)', padding: '6px 14px', cursor: 'pointer' }}
              >
                Mark as Reviewed
              </button>
            )}
          </td>
        </tr>
      )}
    </>
  )
}

const tdStyle: React.CSSProperties = { padding: '10px 14px', borderBottom: '1px solid var(--border)', verticalAlign: 'middle' }

function filterTabStyle(active: boolean): React.CSSProperties {
  return { fontFamily: 'var(--font-mono)', fontSize: '13px', padding: '6px 12px', border: '1px solid', borderColor: active ? 'var(--border-hot)' : 'var(--border)', color: active ? 'var(--amber)' : 'var(--text-secondary)', background: active ? 'var(--bg-active)' : 'var(--bg-panel)', cursor: 'pointer' }
}

function SkeletonTable() {
  return (
    <div style={{ border: '1px solid var(--border)' }}>
      {[1, 2, 3, 4].map((i) => (
        <div key={i} style={{ display: 'grid', gridTemplateColumns: '120px 120px 80px 160px 1fr 100px', gap: '12px', padding: '12px 14px', borderBottom: '1px solid var(--border)' }}>
          {[80, 90, 60, 100, 200, 70].map((w, j) => (
            <div key={j} style={{ width: `${w}px`, height: '14px', background: 'var(--text-muted)', opacity: 0.15 }} />
          ))}
        </div>
      ))}
    </div>
  )
}

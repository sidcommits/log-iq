import { useState } from 'react'
import { useSearch, useAnalyze } from '../hooks/useSearch'
import { SeverityBadge } from '../components/ui/SeverityBadge'
import { ScoreBar } from '../components/ui/ScoreBar'
import type { SearchResult, SearchFilters, RootCauseAnalysis } from '../api/types'

export function SearchPage() {
  const [query, setQuery] = useState('')
  const [filters, setFilters] = useState<SearchFilters>({})
  const { mutate: search, data, isPending } = useSearch()
  const { mutate: analyze, data: rcaData, isPending: analyzing } = useAnalyze()
  const [expandedId, setExpandedId] = useState<string | null>(null)

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (query.trim()) search({ query: query.trim(), filters })
  }

  function handleAnalyze() {
    if (!data?.results.length) return
    analyze({ log_ids: data.results.map((r) => r.log.id) })
  }

  return (
    <div>
      <div style={{ marginBottom: '20px' }}>
        <div style={{ fontFamily: 'var(--font-head)', fontSize: '12px', fontWeight: 600, letterSpacing: '0.15em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: '10px' }}>
          Semantic Log Search
        </div>
        <form role="search" onSubmit={handleSubmit} style={{ position: 'relative' }}>
          <span style={{ position: 'absolute', left: '14px', top: '50%', transform: 'translateY(-50%)', color: 'var(--amber)', fontSize: '16px', pointerEvents: 'none', zIndex: 1 }}>›_</span>
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Ask anything about your logs..."
            style={{
              width: '100%',
              background: 'var(--bg-panel)',
              border: '1px solid var(--border-mid)',
              color: 'var(--text-primary)',
              fontFamily: 'var(--font-mono)',
              fontSize: '14px',
              padding: '14px 16px 14px 42px',
              outline: 'none',
            }}
          />
        </form>
        <div style={{ display: 'flex', gap: '8px', marginTop: '10px', flexWrap: 'wrap' }}>
          <select
            style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)', color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)', fontSize: '13px', padding: '6px 10px', cursor: 'pointer', outline: 'none' }}
            onChange={(e) => setFilters((f) => ({ ...f, service: e.target.value || undefined }))}
          >
            <option value="">All services</option>
            <option value="auth-service">Auth Service</option>
            <option value="api-gateway">API Gateway</option>
            <option value="payment-svc">Payment Svc</option>
          </select>
          <select
            style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)', color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)', fontSize: '13px', padding: '6px 10px', cursor: 'pointer', outline: 'none' }}
            onChange={(e) => setFilters((f) => ({ ...f, environment: e.target.value || undefined }))}
          >
            <option value="">All environments</option>
            <option value="production">production</option>
            <option value="staging">staging</option>
            <option value="development">development</option>
          </select>
        </div>
      </div>

      {isPending && <SkeletonResults />}

      {!isPending && data && (
        <>
          <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', margin: '20px 0 12px', paddingBottom: '8px', borderBottom: '1px solid var(--border)' }}>
            <div style={{ fontFamily: 'var(--font-head)', fontSize: '13px', fontWeight: 600, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>
              {data.total === 0 ? 'No results' : <>Showing <span style={{ color: 'var(--amber)' }}>{data.total}</span> results in <span style={{ color: 'var(--amber)' }}>{data.query_time_ms}ms</span></>}
            </div>
            {data.results.length > 0 && (
              <button
                onClick={handleAnalyze}
                disabled={analyzing}
                style={{ fontFamily: 'var(--font-head)', fontSize: '13px', fontWeight: 600, letterSpacing: '0.12em', textTransform: 'uppercase', background: 'var(--bg-active)', border: '1px solid var(--border-hot)', color: 'var(--amber)', padding: '6px 14px', cursor: 'pointer' }}
              >
                {analyzing ? 'Analyzing...' : '◈ Analyze These Results'}
              </button>
            )}
          </div>

          {data.results.map((result) => (
            <ResultRow
              key={result.log.id}
              result={result}
              expanded={expandedId === result.log.id}
              onToggle={() => setExpandedId(expandedId === result.log.id ? null : result.log.id)}
            />
          ))}

          {rcaData && <RcaPanel rca={rcaData.rca} />}
        </>
      )}
    </div>
  )
}

function ResultRow({ result, expanded, onToggle }: { result: SearchResult; expanded: boolean; onToggle: () => void }) {
  const { log, score } = result
  return (
    <div
      onClick={onToggle}
      style={{ border: '1px solid var(--border)', background: 'var(--bg-panel)', marginBottom: '6px', cursor: 'pointer' }}
    >
      <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr auto', alignItems: 'center', gap: '12px', padding: '10px 14px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <SeverityBadge severity={log.severity} />
          <span style={{ fontFamily: 'var(--font-head)', fontSize: '14px', fontWeight: 600, letterSpacing: '0.06em', color: 'var(--text-secondary)', textTransform: 'uppercase', whiteSpace: 'nowrap' }}>{log.service}</span>
        </div>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: '14px', color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{log.message}</div>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '4px', flexShrink: 0 }}>
          <div style={{ fontSize: '12px', color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>{new Date(log.timestamp).toUTCString().slice(17, 25)} UTC</div>
          <ScoreBar score={score} />
        </div>
      </div>
      {expanded && (
        <div style={{ padding: '0 14px 14px', borderTop: '1px solid var(--border)' }}>
          <pre style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', color: 'var(--text-secondary)', overflowX: 'auto', marginTop: '12px' }}>
            {JSON.stringify(log, null, 2)}
          </pre>
        </div>
      )}
    </div>
  )
}

function RcaPanel({ rca }: { rca: RootCauseAnalysis }) {
  return (
    <div style={{ border: '1px solid var(--border-hot)', background: 'var(--bg-panel)', padding: '20px', marginTop: '20px' }}>
      <div style={{ fontFamily: 'var(--font-head)', fontSize: '13px', fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--amber)', marginBottom: '12px' }}>Root Cause Analysis</div>
      <div style={{ marginBottom: '12px' }}>
        <div style={{ fontSize: '12px', color: 'var(--text-muted)', fontFamily: 'var(--font-head)', letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: '4px' }}>Summary</div>
        <div style={{ color: 'var(--text-primary)' }}>{rca.summary}</div>
      </div>
      <div style={{ marginBottom: '12px' }}>
        <div style={{ fontSize: '12px', color: 'var(--text-muted)', fontFamily: 'var(--font-head)', letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: '4px' }}>Root Cause</div>
        <div style={{ color: 'var(--text-primary)' }}>{rca.root_cause}</div>
      </div>
      <div>
        <div style={{ fontSize: '12px', color: 'var(--text-muted)', fontFamily: 'var(--font-head)', letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: '8px' }}>Suggested Fixes</div>
        {rca.suggested_fixes.map((fix, i) => (
          <div key={i} style={{ display: 'flex', gap: '8px', marginBottom: '6px' }}>
            <span style={{ color: 'var(--amber)', flexShrink: 0 }}>›</span>
            <span style={{ color: 'var(--text-secondary)' }}>{fix}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function SkeletonResults() {
  return (
    <div>
      {[1, 2, 3].map((i) => (
        <div key={i} style={{ border: '1px solid var(--border)', background: 'var(--bg-panel)', marginBottom: '6px', padding: '10px 14px', display: 'flex', gap: '12px', alignItems: 'center' }}>
          <div style={{ width: '60px', height: '22px', background: 'var(--text-muted)', opacity: 0.2 }} />
          <div style={{ flex: 1, height: '14px', background: 'var(--text-muted)', opacity: 0.15 }} />
          <div style={{ width: '80px', height: '14px', background: 'var(--text-muted)', opacity: 0.1 }} />
        </div>
      ))}
    </div>
  )
}

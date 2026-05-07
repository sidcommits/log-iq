interface ErrorStateProps {
  message: string
  onRetry?: () => void
}

export function ErrorState({ message, onRetry }: ErrorStateProps) {
  return (
    <div style={{ padding: '48px 24px', textAlign: 'center' }}>
      <div style={{
        fontFamily: 'var(--font-head)',
        fontSize: '11px',
        letterSpacing: '0.15em',
        textTransform: 'uppercase',
        color: 'var(--red)',
        marginBottom: '12px',
      }}>
        Error
      </div>
      <div style={{ color: 'var(--text-secondary)', marginBottom: '20px' }}>{message}</div>
      {onRetry && (
        <button
          onClick={onRetry}
          style={{
            fontFamily: 'var(--font-head)',
            fontSize: '13px',
            fontWeight: 600,
            letterSpacing: '0.1em',
            textTransform: 'uppercase',
            background: 'var(--red-dim)',
            border: '1px solid var(--red)',
            color: 'var(--red)',
            padding: '8px 18px',
            cursor: 'pointer',
          }}
        >
          Retry
        </button>
      )}
    </div>
  )
}

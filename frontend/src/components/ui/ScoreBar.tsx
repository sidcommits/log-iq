interface ScoreBarProps {
  score: number // 0–1
}

function getColor(score: number): string {
  if (score >= 0.8) return 'var(--red)'
  if (score >= 0.6) return 'var(--amber)'
  return 'var(--blue)'
}

export function ScoreBar({ score }: ScoreBarProps) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
      <div style={{ width: '80px', height: '4px', background: 'rgba(255,255,255,0.06)', position: 'relative' }}>
        <div
          data-testid="score-fill"
          style={{ height: '100%', width: `${score * 100}%`, background: getColor(score) }}
        />
      </div>
      <span style={{ fontSize: '13px', fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
        {score.toFixed(2)}
      </span>
    </div>
  )
}

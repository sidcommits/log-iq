import { SEVERITY_COLORS, type Severity } from '../../lib/constants'

export function SeverityBadge({ severity }: { severity: Severity }) {
  const c = SEVERITY_COLORS[severity] ?? SEVERITY_COLORS.UNKNOWN
  return (
    <span
      style={{
        fontFamily: 'var(--font-head)',
        fontSize: '12px',
        fontWeight: 700,
        letterSpacing: '0.1em',
        padding: '2px 7px',
        background: c.bg,
        border: `1px solid ${c.border}`,
        color: c.text,
      }}
    >
      {severity}
    </span>
  )
}

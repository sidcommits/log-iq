// frontend/src/lib/constants.ts
export const POLL_INTERVAL_MS = 5_000

export const SEVERITY_COLORS = {
  ERROR: {
    bg: 'var(--red-dim)',
    border: 'var(--red)',
    text: 'var(--red)',
  },
  WARN: {
    bg: 'var(--amber-badge)',
    border: 'var(--amber)',
    text: 'var(--amber)',
  },
  INFO: {
    bg: 'var(--blue-dim)',
    border: 'var(--blue)',
    text: 'var(--blue)',
  },
  DEBUG: {
    bg: '#1a1a1a',
    border: '#333',
    text: '#666',
  },
  TRACE: {
    bg: '#1a1a1a',
    border: '#333',
    text: '#555',
  },
  UNKNOWN: {
    bg: '#1a1a1a',
    border: '#333',
    text: '#555',
  },
} as const

export type Severity = keyof typeof SEVERITY_COLORS

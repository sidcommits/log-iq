import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders } from '../test-utils'
import { HealthPage } from './HealthPage'
import * as healthApi from '../api/health'

vi.mock('../api/health')

const mockHealthOk = {
  status: 'ok' as const,
  dependencies: [
    { name: 'PostgreSQL', status: 'ok' as const, latency_ms: 2 },
    { name: 'Qdrant',     status: 'ok' as const, latency_ms: 8 },
    { name: 'Claude',     status: 'degraded' as const, latency_ms: 1240 },
  ],
  sync_sources: [
    { source_name: 'loki-prod', mode: 'stream' as const, last_synced_at: new Date().toISOString(), lag_ms: 140, online: true },
  ],
  metrics: { total_logs: 1247391, total_anomalies: 12, total_rcas: 47, pending_tasks: 5 },
}

describe('HealthPage', () => {
  beforeEach(() => vi.clearAllMocks())

  it('renders page title', () => {
    vi.mocked(healthApi.getHealth).mockResolvedValue(mockHealthOk)
    renderWithProviders(<HealthPage />)
    expect(screen.getByText('System Health')).toBeInTheDocument()
  })

  it('renders dependency cards', async () => {
    vi.mocked(healthApi.getHealth).mockResolvedValue(mockHealthOk)
    renderWithProviders(<HealthPage />)
    await waitFor(() => expect(screen.getByText('PostgreSQL')).toBeInTheDocument())
    expect(screen.getByText('Qdrant')).toBeInTheDocument()
    expect(screen.getByText('Claude')).toBeInTheDocument()
  })

  it('shows latency for healthy dependency', async () => {
    vi.mocked(healthApi.getHealth).mockResolvedValue(mockHealthOk)
    renderWithProviders(<HealthPage />)
    await waitFor(() => screen.getByText('PostgreSQL'))
    expect(screen.getByText('2ms')).toBeInTheDocument()
  })

  it('shows metrics totals', async () => {
    vi.mocked(healthApi.getHealth).mockResolvedValue(mockHealthOk)
    renderWithProviders(<HealthPage />)
    await waitFor(() => screen.getByText('1,247,391'))
    expect(screen.getByText('12')).toBeInTheDocument()
  })
})

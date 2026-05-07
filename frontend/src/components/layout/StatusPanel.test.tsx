import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClientProvider } from '@tanstack/react-query'
import { createTestQueryClient } from '../../lib/queryClient'
import { StatusPanel } from './StatusPanel'
import * as healthApi from '../../api/health'

vi.mock('../../api/health')

describe('StatusPanel', () => {
  beforeEach(() => vi.clearAllMocks())

  it('displays total logs from health response', async () => {
    vi.mocked(healthApi.getHealth).mockResolvedValue({
      status: 'ok',
      dependencies: [],
      sync_sources: [{ source_name: 'loki-prod', mode: 'stream', last_synced_at: new Date().toISOString(), lag_ms: 140, online: true }],
      metrics: { total_logs: 1247391, total_anomalies: 12, total_rcas: 47, pending_tasks: 5 },
    })
    render(
      <QueryClientProvider client={createTestQueryClient()}>
        <StatusPanel />
      </QueryClientProvider>
    )
    await waitFor(() => expect(screen.getByText('1,247,391')).toBeInTheDocument())
  })

  it('shows loading state initially', () => {
    vi.mocked(healthApi.getHealth).mockReturnValue(new Promise(() => {}))
    render(
      <QueryClientProvider client={createTestQueryClient()}>
        <StatusPanel />
      </QueryClientProvider>
    )
    expect(screen.getByText(/connecting/i)).toBeInTheDocument()
  })
})

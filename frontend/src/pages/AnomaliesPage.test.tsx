import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders } from '../test-utils'
import { AnomaliesPage } from './AnomaliesPage'
import * as anomaliesApi from '../api/anomalies'
import type { LogEvent } from '../api/types'

vi.mock('../api/anomalies')

const mockLog: LogEvent = {
  id: 'log-1', timestamp: '2026-05-07T14:31:58Z', severity: 'ERROR',
  service: 'payment-svc', environment: 'production', trace_id: null,
  span_id: null, message: 'Stripe webhook signature mismatch', metadata: {}, raw: '', source: 'loki',
}

describe('AnomaliesPage', () => {
  beforeEach(() => vi.clearAllMocks())

  it('renders page title', () => {
    vi.mocked(anomaliesApi.getAnomalies).mockResolvedValue({ anomalies: [], total: 0 })
    renderWithProviders(<AnomaliesPage />)
    expect(screen.getByText('Anomaly Feed')).toBeInTheDocument()
  })

  it('renders anomaly rows with service and message', async () => {
    vi.mocked(anomaliesApi.getAnomalies).mockResolvedValue({
      anomalies: [{ id: 'a-1', log_id: 'log-1', score: 0.92, nearest_neighbours: [], reviewed: false, created_at: '2026-05-07T14:31:58Z', log: mockLog }],
      total: 1,
    })
    renderWithProviders(<AnomaliesPage />)
    await waitFor(() => expect(screen.getByText('Stripe webhook signature mismatch')).toBeInTheDocument())
    expect(screen.getByText('payment-svc')).toBeInTheDocument()
  })

  it('calls reviewAnomaly when Mark as Reviewed clicked', async () => {
    vi.mocked(anomaliesApi.getAnomalies).mockResolvedValue({
      anomalies: [{ id: 'a-1', log_id: 'log-1', score: 0.92, nearest_neighbours: [], reviewed: false, created_at: '2026-05-07T14:31:58Z', log: mockLog }],
      total: 1,
    })
    vi.mocked(anomaliesApi.reviewAnomaly).mockResolvedValue(undefined)
    renderWithProviders(<AnomaliesPage />)
    await waitFor(() => screen.getByText('Stripe webhook signature mismatch'))
    fireEvent.click(screen.getByText('Stripe webhook signature mismatch'))
    await waitFor(() => fireEvent.click(screen.getByText(/mark as reviewed/i)))
    expect(anomaliesApi.reviewAnomaly).toHaveBeenCalledWith('a-1')
  })

  it('shows empty state when no anomalies', async () => {
    vi.mocked(anomaliesApi.getAnomalies).mockResolvedValue({ anomalies: [], total: 0 })
    renderWithProviders(<AnomaliesPage />)
    await waitFor(() => expect(screen.getByText(/no anomalies/i)).toBeInTheDocument())
  })
})

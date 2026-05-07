import { describe, it, expect, vi, beforeEach } from 'vitest'
import { getAnomalies, reviewAnomaly } from './anomalies'
import * as client from './client'

vi.mock('./client')

describe('anomalies API', () => {
  beforeEach(() => vi.clearAllMocks())

  it('getAnomalies calls GET /api/anomalies', async () => {
    vi.mocked(client.apiFetch).mockResolvedValue({ anomalies: [], total: 0 })
    await getAnomalies({})
    expect(client.apiFetch).toHaveBeenCalledWith('/api/anomalies?')
  })

  it('getAnomalies appends query params', async () => {
    vi.mocked(client.apiFetch).mockResolvedValue({ anomalies: [], total: 0 })
    await getAnomalies({ reviewed: false, service: 'auth' })
    expect(client.apiFetch).toHaveBeenCalledWith(
      expect.stringContaining('reviewed=false')
    )
  })

  it('reviewAnomaly calls POST /api/anomalies/:id/review', async () => {
    vi.mocked(client.apiFetch).mockResolvedValue({})
    await reviewAnomaly('abc-123')
    expect(client.apiFetch).toHaveBeenCalledWith('/api/anomalies/abc-123/review', { method: 'POST' })
  })
})

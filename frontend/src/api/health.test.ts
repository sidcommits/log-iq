import { describe, it, expect, vi, beforeEach } from 'vitest'
import { getHealth } from './health'
import * as client from './client'

vi.mock('./client')

describe('health API', () => {
  beforeEach(() => vi.clearAllMocks())

  it('getHealth calls GET /api/health', async () => {
    vi.mocked(client.apiFetch).mockResolvedValue({ status: 'ok', dependencies: [], sync_sources: [], metrics: {} })
    await getHealth()
    expect(client.apiFetch).toHaveBeenCalledWith('/api/health')
  })
})

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { postSearch, postAnalyze } from './search'
import * as client from './client'

vi.mock('./client')

describe('search API', () => {
  beforeEach(() => vi.clearAllMocks())

  it('postSearch calls POST /api/search with body', async () => {
    vi.mocked(client.apiFetch).mockResolvedValue({ results: [], total: 0, query_time_ms: 10 })
    const req = { query: 'database timeout', filters: { service: 'auth' } }
    await postSearch(req)
    expect(client.apiFetch).toHaveBeenCalledWith('/api/search', {
      method: 'POST',
      body: JSON.stringify(req),
    })
  })

  it('postAnalyze calls POST /api/analyze', async () => {
    vi.mocked(client.apiFetch).mockResolvedValue({ rca: {}, tasks: [] })
    await postAnalyze({ log_ids: ['a', 'b'] })
    expect(client.apiFetch).toHaveBeenCalledWith('/api/analyze', {
      method: 'POST',
      body: JSON.stringify({ log_ids: ['a', 'b'] }),
    })
  })
})

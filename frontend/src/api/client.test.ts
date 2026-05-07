import { describe, it, expect, vi, beforeEach } from 'vitest'
import { apiFetch } from './client'

describe('apiFetch', () => {
  beforeEach(() => { vi.restoreAllMocks() })

  it('returns parsed JSON on 2xx response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ data: 'ok' }),
    }))
    const result = await apiFetch<{ data: string }>('/api/test')
    expect(result).toEqual({ data: 'ok' })
  })

  it('throws with server error message on non-2xx', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: () => Promise.resolve({ error: 'Internal server error' }),
    }))
    await expect(apiFetch('/api/test')).rejects.toThrow('Internal server error')
  })

  it('throws HTTP status when body has no error field', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      json: () => Promise.reject(new Error('not json')),
    }))
    await expect(apiFetch('/api/test')).rejects.toThrow('HTTP 503')
  })

  it('sends Content-Type header', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({}),
    })
    vi.stubGlobal('fetch', mockFetch)
    await apiFetch('/api/test')
    expect(mockFetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        headers: expect.objectContaining({ 'Content-Type': 'application/json' }),
      })
    )
  })
})

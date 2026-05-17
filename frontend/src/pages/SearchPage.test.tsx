import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders } from '../test-utils'
import { SearchPage } from './SearchPage'
import * as searchApi from '../api/search'
import type { LogEvent } from '../api/types'

vi.mock('../api/search')

const mockLog: LogEvent = {
  id: '1', timestamp: '2026-05-07T14:31:58Z', severity: 'ERROR',
  service: 'auth-service', environment: 'production', trace_id: null,
  span_id: null, message: 'Connection pool exhausted', metadata: {}, raw: '', source: 'loki',
}

describe('SearchPage', () => {
  beforeEach(() => vi.clearAllMocks())

  it('renders search input with placeholder', () => {
    renderWithProviders(<SearchPage />)
    expect(screen.getByPlaceholderText(/ask anything about your logs/i)).toBeInTheDocument()
  })

  it('shows results after search submission', async () => {
    vi.mocked(searchApi.postSearch).mockResolvedValue({
      results: [{ log: mockLog, score: 0.94 }],
      total: 1,
      query_time_ms: 120,
    })
    renderWithProviders(<SearchPage />)
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'database timeout' } })
    fireEvent.submit(screen.getByRole('search'))
    await waitFor(() => expect(screen.getByText('Connection pool exhausted')).toBeInTheDocument())
    expect(screen.getByText('auth-service')).toBeInTheDocument()
  })

  it('shows empty state when results are empty', async () => {
    vi.mocked(searchApi.postSearch).mockResolvedValue({ results: [], total: 0, query_time_ms: 50 })
    renderWithProviders(<SearchPage />)
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'nothing here' } })
    fireEvent.submit(screen.getByRole('search'))
    await waitFor(() => expect(screen.getByText(/no results/i)).toBeInTheDocument())
  })

  it('shows result count and query time after search', async () => {
    vi.mocked(searchApi.postSearch).mockResolvedValue({
      results: [{ log: mockLog, score: 0.94 }],
      total: 1,
      query_time_ms: 312,
    })
    renderWithProviders(<SearchPage />)
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'test' } })
    fireEvent.submit(screen.getByRole('search'))
    await waitFor(() => expect(screen.getByText(/312ms/)).toBeInTheDocument())
  })
})

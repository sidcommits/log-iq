// frontend/src/components/layout/Sidebar.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { QueryClientProvider } from '@tanstack/react-query'
import { createTestQueryClient } from '../../lib/queryClient'
import * as healthApi from '../../api/health'

vi.mock('../../api/health')

describe('Sidebar', () => {
  function renderSidebar(initialPath = '/') {
    vi.mocked(healthApi.getHealth).mockResolvedValue({
      status: 'ok', dependencies: [], sync_sources: [],
      metrics: { total_logs: 1000, total_anomalies: 3, total_rcas: 5, pending_tasks: 2 }
    })
    return render(
      <QueryClientProvider client={createTestQueryClient()}>
        <MemoryRouter initialEntries={[initialPath]}>
          <Sidebar />
        </MemoryRouter>
      </QueryClientProvider>
    )
  }

  it('renders LogIQ logo', () => {
    renderSidebar()
    expect(screen.getByText('LogIQ')).toBeInTheDocument()
  })

  it('renders all nav items', () => {
    renderSidebar()
    expect(screen.getByText('Search')).toBeInTheDocument()
    expect(screen.getByText('Anomalies')).toBeInTheDocument()
    expect(screen.getByText('Tasks')).toBeInTheDocument()
    expect(screen.getByText('Health')).toBeInTheDocument()
  })
})

import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders } from '../test-utils'
import { TasksPage } from './TasksPage'
import * as tasksApi from '../api/tasks'
import type { ActionableTask } from '../api/types'

vi.mock('../api/tasks')

const mockTask: ActionableTask = {
  id: 'task-1', rca_id: 'rca-1', log_id: 'log-1',
  type: 'config_change', priority: 'critical',
  description: 'Increase PostgreSQL connection pool size from 50 to 200',
  target_service: 'auth-service', estimated_effort: '15 min',
  status: 'pending', created_at: '2026-05-07T14:32:01Z',
}

describe('TasksPage', () => {
  beforeEach(() => vi.clearAllMocks())

  it('renders page title', () => {
    vi.mocked(tasksApi.getTasks).mockResolvedValue({ tasks: [], total: 0 })
    renderWithProviders(<TasksPage />)
    expect(screen.getByText('Task Queue')).toBeInTheDocument()
  })

  it('renders task description', async () => {
    vi.mocked(tasksApi.getTasks).mockResolvedValue({ tasks: [mockTask], total: 1 })
    renderWithProviders(<TasksPage />)
    await waitFor(() => expect(screen.getByText('Increase PostgreSQL connection pool size from 50 to 200')).toBeInTheDocument())
  })

  it('calls approveTask when Approve button clicked', async () => {
    vi.mocked(tasksApi.getTasks).mockResolvedValue({ tasks: [mockTask], total: 1 })
    vi.mocked(tasksApi.approveTask).mockResolvedValue(undefined)
    renderWithProviders(<TasksPage />)
    await waitFor(() => screen.getByText('Increase PostgreSQL connection pool size from 50 to 200'))
    fireEvent.click(screen.getByText(/approve/i))
    await waitFor(() => expect(tasksApi.approveTask).toHaveBeenCalledWith('task-1', expect.anything()))
  })

  it('calls dismissTask when Dismiss button clicked', async () => {
    vi.mocked(tasksApi.getTasks).mockResolvedValue({ tasks: [mockTask], total: 1 })
    vi.mocked(tasksApi.dismissTask).mockResolvedValue(undefined)
    renderWithProviders(<TasksPage />)
    await waitFor(() => screen.getByText('Increase PostgreSQL connection pool size from 50 to 200'))
    fireEvent.click(screen.getByTitle(/dismiss/i))
    await waitFor(() => expect(tasksApi.dismissTask).toHaveBeenCalledWith('task-1', expect.anything()))
  })

  it('shows empty state when no tasks', async () => {
    vi.mocked(tasksApi.getTasks).mockResolvedValue({ tasks: [], total: 0 })
    renderWithProviders(<TasksPage />)
    await waitFor(() => expect(screen.getByText(/no pending tasks/i)).toBeInTheDocument())
  })
})

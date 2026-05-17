import { describe, it, expect, vi, beforeEach } from 'vitest'
import { getTasks, approveTask, dismissTask } from './tasks'
import * as client from './client'

vi.mock('./client')

describe('tasks API', () => {
  beforeEach(() => vi.clearAllMocks())

  it('getTasks calls GET /api/tasks', async () => {
    vi.mocked(client.apiFetch).mockResolvedValue({ tasks: [], total: 0 })
    await getTasks({})
    expect(client.apiFetch).toHaveBeenCalledWith('/api/tasks?')
  })

  it('approveTask calls POST /api/tasks/:id/approve', async () => {
    vi.mocked(client.apiFetch).mockResolvedValue({})
    await approveTask('task-1')
    expect(client.apiFetch).toHaveBeenCalledWith('/api/tasks/task-1/approve', { method: 'POST' })
  })

  it('dismissTask calls POST /api/tasks/:id/dismiss', async () => {
    vi.mocked(client.apiFetch).mockResolvedValue({})
    await dismissTask('task-1')
    expect(client.apiFetch).toHaveBeenCalledWith('/api/tasks/task-1/dismiss', { method: 'POST' })
  })
})

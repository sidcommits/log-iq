import { apiFetch } from './client'
import type { TasksResponse, TaskStatus } from './types'

export interface TaskFilters {
  status?: TaskStatus
  service?: string
  priority?: string
}

export function getTasks(filters: TaskFilters): Promise<TasksResponse> {
  const params = new URLSearchParams()
  if (filters.status) params.set('status', filters.status)
  if (filters.service) params.set('service', filters.service)
  if (filters.priority) params.set('priority', filters.priority)
  return apiFetch(`/api/tasks?${params.toString()}`)
}

export function approveTask(id: string): Promise<void> {
  return apiFetch(`/api/tasks/${id}/approve`, { method: 'POST' })
}

export function dismissTask(id: string): Promise<void> {
  return apiFetch(`/api/tasks/${id}/dismiss`, { method: 'POST' })
}

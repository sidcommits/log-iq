import { apiFetch } from './client'
import type { HealthResponse } from './types'

export function getHealth(): Promise<HealthResponse> {
  return apiFetch('/api/health')
}

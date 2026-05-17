import { apiFetch } from './client'
import type { AnomaliesResponse } from './types'

export interface AnomalyFilters {
  reviewed?: boolean
  service?: string
  severity?: string
  min_score?: number
}

export function getAnomalies(filters: AnomalyFilters): Promise<AnomaliesResponse> {
  const params = new URLSearchParams()
  if (filters.reviewed !== undefined) params.set('reviewed', String(filters.reviewed))
  if (filters.service) params.set('service', filters.service)
  if (filters.severity) params.set('severity', filters.severity)
  if (filters.min_score !== undefined) params.set('min_score', String(filters.min_score))
  return apiFetch(`/api/anomalies?${params.toString()}`)
}

export function reviewAnomaly(id: string): Promise<void> {
  return apiFetch(`/api/anomalies/${id}/review`, { method: 'POST' })
}

import { apiFetch } from './client'
import type { SearchRequest, SearchResponse, AnalyzeRequest, AnalyzeResponse } from './types'

export function postSearch(req: SearchRequest): Promise<SearchResponse> {
  return apiFetch('/api/search', { method: 'POST', body: JSON.stringify(req) })
}

export function postAnalyze(req: AnalyzeRequest): Promise<AnalyzeResponse> {
  return apiFetch('/api/analyze', { method: 'POST', body: JSON.stringify(req) })
}

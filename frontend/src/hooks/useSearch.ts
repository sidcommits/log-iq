import { useMutation } from '@tanstack/react-query'
import { postSearch, postAnalyze } from '../api/search'
import type { SearchRequest, AnalyzeRequest } from '../api/types'

export function useSearch() {
  return useMutation({
    mutationFn: (req: SearchRequest) => postSearch(req),
  })
}

export function useAnalyze() {
  return useMutation({
    mutationFn: (req: AnalyzeRequest) => postAnalyze(req),
  })
}

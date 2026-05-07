import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getAnomalies, reviewAnomaly } from '../api/anomalies'
import type { AnomalyFilters } from '../api/anomalies'

export function useAnomalies(filters: AnomalyFilters = {}) {
  return useQuery({
    queryKey: ['anomalies', filters],
    queryFn: () => getAnomalies(filters),
  })
}

export function useReviewAnomaly() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => reviewAnomaly(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['anomalies'] }),
  })
}

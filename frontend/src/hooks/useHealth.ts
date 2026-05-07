import { useQuery } from '@tanstack/react-query'
import { getHealth } from '../api/health'
import { POLL_INTERVAL_MS } from '../lib/constants'

export function useHealth() {
  return useQuery({
    queryKey: ['health'],
    queryFn: getHealth,
    refetchInterval: POLL_INTERVAL_MS,
  })
}

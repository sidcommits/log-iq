import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getTasks, approveTask, dismissTask } from '../api/tasks'
import type { TaskFilters } from '../api/tasks'
import type { TasksResponse } from '../api/types'
import { toast } from 'sonner'

export function useTasks(filters: TaskFilters = {}) {
  return useQuery({
    queryKey: ['tasks', filters],
    queryFn: () => getTasks(filters),
  })
}

export function useApproveTask(filters: TaskFilters = {}) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: approveTask,
    onMutate: async (taskId: string) => {
      await queryClient.cancelQueries({ queryKey: ['tasks', filters] })
      const previous = queryClient.getQueryData<TasksResponse>(['tasks', filters])
      queryClient.setQueryData<TasksResponse>(['tasks', filters], (old) =>
        old ? { ...old, tasks: old.tasks.filter((t) => t.id !== taskId) } : old
      )
      return { previous }
    },
    onError: (_err, _id, context) => {
      queryClient.setQueryData(['tasks', filters], context?.previous)
      toast.error('Failed to approve task')
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] })
      toast.success('Task approved')
    },
  })
}

export function useDismissTask(filters: TaskFilters = {}) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: dismissTask,
    onMutate: async (taskId: string) => {
      await queryClient.cancelQueries({ queryKey: ['tasks', filters] })
      const previous = queryClient.getQueryData<TasksResponse>(['tasks', filters])
      queryClient.setQueryData<TasksResponse>(['tasks', filters], (old) =>
        old ? { ...old, tasks: old.tasks.filter((t) => t.id !== taskId) } : old
      )
      return { previous }
    },
    onError: (_err, _id, context) => {
      queryClient.setQueryData(['tasks', filters], context?.previous)
      toast.error('Failed to dismiss task')
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] })
      toast.success('Task dismissed')
    },
  })
}

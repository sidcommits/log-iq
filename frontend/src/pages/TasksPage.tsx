import { useState } from 'react'
import { useTasks, useApproveTask, useDismissTask } from '../hooks/useTasks'
import { approveTask, dismissTask } from '../api/tasks'
import { ErrorState } from '../components/ui/ErrorState'
import type { ActionableTask, TaskStatus } from '../api/types'

const STATUS_TABS: { label: string; value: TaskStatus }[] = [
  { label: 'Pending', value: 'pending' },
  { label: 'In Progress', value: 'in_progress' },
  { label: 'Resolved', value: 'resolved' },
  { label: 'Dismissed', value: 'dismissed' },
]

const PRIORITY_COLORS: Record<string, { bg: string; border: string; text: string }> = {
  critical: { bg: 'var(--red-dim)',    border: 'var(--red)',         text: 'var(--red)' },
  high:     { bg: 'var(--amber-badge)', border: 'var(--amber)',      text: 'var(--amber)' },
  medium:   { bg: 'var(--blue-dim)',   border: 'var(--blue)',        text: 'var(--blue)' },
  low:      { bg: 'transparent',       border: 'var(--border-mid)',  text: 'var(--text-muted)' },
}

export function TasksPage() {
  const [activeStatus, setActiveStatus] = useState<TaskStatus>('pending')
  const filters = { status: activeStatus }
  const { data, isLoading, isError, refetch } = useTasks(filters)
  useApproveTask(filters)
  useDismissTask(filters)

  if (isError) return <ErrorState message="Failed to load tasks" onRetry={refetch} />

  return (
    <div>
      <div style={{ fontFamily: 'var(--font-head)', fontSize: '22px', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: '4px' }}>Task Queue</div>
      <div style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '20px' }}>Actionable items from RCA — requires human approval</div>

      <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
        {STATUS_TABS.map((tab) => (
          <button
            key={tab.value}
            onClick={() => setActiveStatus(tab.value)}
            style={{ fontFamily: 'var(--font-mono)', fontSize: '13px', padding: '6px 12px', border: '1px solid', borderColor: activeStatus === tab.value ? 'var(--border-hot)' : 'var(--border)', color: activeStatus === tab.value ? 'var(--amber)' : 'var(--text-secondary)', background: activeStatus === tab.value ? 'var(--bg-active)' : 'var(--bg-panel)', cursor: 'pointer' }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {isLoading && <SkeletonCards />}

      {!isLoading && data?.total === 0 && (
        <div style={{ padding: '48px 0', textAlign: 'center', color: 'var(--text-muted)' }}>No {activeStatus.replace('_', ' ')} tasks</div>
      )}

      {!isLoading && data?.tasks.map((task) => (
        <TaskCard key={task.id} task={task} onApprove={() => { approveTask(task.id); refetch() }} onDismiss={() => { dismissTask(task.id); refetch() }} />
      ))}
    </div>
  )
}

function TaskCard({ task, onApprove, onDismiss }: { task: ActionableTask; onApprove: () => void; onDismiss: () => void }) {
  const pc = PRIORITY_COLORS[task.priority] ?? PRIORITY_COLORS.low
  return (
    <div style={{ border: '1px solid var(--border)', background: 'var(--bg-panel)', padding: '14px 16px', marginBottom: '8px', display: 'grid', gridTemplateColumns: 'auto 1fr auto', gap: '14px', alignItems: 'start' }}>
      <span style={{ fontFamily: 'var(--font-head)', fontSize: '12px', fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', padding: '3px 8px', border: '1px solid', borderColor: pc.border, color: pc.text, background: pc.bg, whiteSpace: 'nowrap', marginTop: '2px' }}>
        {task.priority}
      </span>
      <div>
        <div style={{ fontFamily: 'var(--font-head)', fontSize: '12px', fontWeight: 600, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: '4px' }}>{task.type.replace('_', ' ')}</div>
        <div style={{ fontSize: '15px', color: 'var(--text-primary)', marginBottom: '6px', lineHeight: 1.4 }}>{task.description}</div>
        <div style={{ fontSize: '13px', color: 'var(--text-muted)', display: 'flex', gap: '14px' }}>
          <span>Service: <strong style={{ color: 'var(--text-secondary)' }}>{task.target_service}</strong></span>
          <span>Effort: <strong style={{ color: 'var(--text-secondary)' }}>{task.estimated_effort}</strong></span>
        </div>
      </div>
      {task.status === 'pending' && (
        <div style={{ display: 'flex', gap: '6px', flexShrink: 0 }}>
          <button onClick={onApprove} style={{ fontFamily: 'var(--font-head)', fontSize: '13px', fontWeight: 600, letterSpacing: '0.1em', textTransform: 'uppercase', padding: '6px 14px', border: '1px solid var(--green)', color: 'var(--green)', background: 'var(--green-dim)', cursor: 'pointer' }}>
            ✓ Approve
          </button>
          <button title="Dismiss task" onClick={onDismiss} style={{ fontFamily: 'var(--font-head)', fontSize: '13px', fontWeight: 600, letterSpacing: '0.1em', textTransform: 'uppercase', padding: '6px 10px', border: '1px solid var(--border)', color: 'var(--text-muted)', background: 'transparent', cursor: 'pointer' }}>
            ✕
          </button>
        </div>
      )}
    </div>
  )
}

function SkeletonCards() {
  return (
    <div>
      {[1, 2, 3].map((i) => (
        <div key={i} style={{ border: '1px solid var(--border)', background: 'var(--bg-panel)', padding: '14px 16px', marginBottom: '8px', display: 'flex', gap: '14px' }}>
          <div style={{ width: '70px', height: '24px', background: 'var(--text-muted)', opacity: 0.2 }} />
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <div style={{ width: '30%', height: '12px', background: 'var(--text-muted)', opacity: 0.15 }} />
            <div style={{ width: '80%', height: '15px', background: 'var(--text-muted)', opacity: 0.15 }} />
          </div>
        </div>
      ))}
    </div>
  )
}

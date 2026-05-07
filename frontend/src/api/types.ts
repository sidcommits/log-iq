export type Severity = 'ERROR' | 'WARN' | 'INFO' | 'DEBUG' | 'TRACE' | 'UNKNOWN'

export interface LogEvent {
  id: string
  timestamp: string
  severity: Severity
  service: string
  environment: string
  trace_id: string | null
  span_id: string | null
  message: string
  metadata: Record<string, unknown>
  raw: string
  source: string
}

export interface SearchResult {
  log: LogEvent
  score: number
}

export interface SearchResponse {
  results: SearchResult[]
  total: number
  query_time_ms: number
}

export interface SearchFilters {
  service?: string
  severity?: Severity[]
  environment?: string
  start_time?: string
  end_time?: string
}

export interface SearchRequest {
  query: string
  filters?: SearchFilters
  limit?: number
}

export interface RootCauseAnalysis {
  id: string
  log_ids: string[]
  summary: string
  root_cause: string
  suggested_fixes: string[]
  confidence: number
  created_at: string
}

export interface AnalyzeRequest {
  log_ids: string[]
}

export interface AnalyzeResponse {
  rca: RootCauseAnalysis
  tasks: ActionableTask[]
}

export interface AnomalyResult {
  id: string
  log_id: string
  score: number
  nearest_neighbours: LogEvent[]
  reviewed: boolean
  created_at: string
  log: LogEvent
}

export interface AnomaliesResponse {
  anomalies: AnomalyResult[]
  total: number
}

export type TaskStatus = 'pending' | 'approved' | 'in_progress' | 'resolved' | 'dismissed'
export type TaskPriority = 'critical' | 'high' | 'medium' | 'low'
export type TaskType = 'config_change' | 'investigation' | 'deploy' | 'code_fix' | 'alert'

export interface ActionableTask {
  id: string
  rca_id: string
  log_id: string
  type: TaskType
  priority: TaskPriority
  description: string
  target_service: string
  estimated_effort: string
  status: TaskStatus
  created_at: string
}

export interface TasksResponse {
  tasks: ActionableTask[]
  total: number
}

export interface HealthDependency {
  name: string
  status: 'ok' | 'degraded' | 'error'
  latency_ms: number | null
}

export interface SyncStatus {
  source_name: string
  mode: 'poll' | 'stream'
  last_synced_at: string | null
  lag_ms: number | null
  online: boolean
}

export interface HealthMetrics {
  total_logs: number
  total_anomalies: number
  total_rcas: number
  pending_tasks: number
}

export interface HealthResponse {
  status: 'ok' | 'degraded' | 'error'
  dependencies: HealthDependency[]
  sync_sources: SyncStatus[]
  metrics: HealthMetrics
}

import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'sonner'
import { queryClient } from './lib/queryClient'
import { AppShell } from './components/layout/AppShell'
import { SearchPage } from './pages/SearchPage'
import { AnomaliesPage } from './pages/AnomaliesPage'
import { TasksPage } from './pages/TasksPage'
import { HealthPage } from './pages/HealthPage'
import { ErrorBoundary } from './components/ui/ErrorBoundary'

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AppShell>
          <Routes>
            <Route path="/"          element={<ErrorBoundary><SearchPage /></ErrorBoundary>} />
            <Route path="/anomalies" element={<ErrorBoundary><AnomaliesPage /></ErrorBoundary>} />
            <Route path="/tasks"     element={<ErrorBoundary><TasksPage /></ErrorBoundary>} />
            <Route path="/health"    element={<ErrorBoundary><HealthPage /></ErrorBoundary>} />
            <Route path="*"          element={<Navigate to="/" replace />} />
          </Routes>
        </AppShell>
      </BrowserRouter>
      <Toaster theme="dark" position="bottom-right" richColors />
    </QueryClientProvider>
  )
}

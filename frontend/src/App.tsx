import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'sonner'
import { queryClient } from './lib/queryClient'
import { AppShell } from './components/layout/AppShell'
import { SearchPage } from './pages/SearchPage'
import { AnomaliesPage } from './pages/AnomaliesPage'
import { TasksPage } from './pages/TasksPage'
import { HealthPage } from './pages/HealthPage'

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AppShell>
          <Routes>
            <Route path="/"          element={<SearchPage />} />
            <Route path="/anomalies" element={<AnomaliesPage />} />
            <Route path="/tasks"     element={<TasksPage />} />
            <Route path="/health"    element={<HealthPage />} />
            <Route path="*"          element={<Navigate to="/" replace />} />
          </Routes>
        </AppShell>
      </BrowserRouter>
      <Toaster theme="dark" position="bottom-right" richColors />
    </QueryClientProvider>
  )
}

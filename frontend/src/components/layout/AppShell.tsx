// frontend/src/components/layout/AppShell.tsx
import { Sidebar } from './Sidebar'
import { TopBar } from './TopBar'

interface AppShellProps { children: React.ReactNode }

export function AppShell({ children }: AppShellProps) {
  return (
    <div style={{ display: 'flex', height: '100vh', position: 'relative', zIndex: 1 }}>
      <Sidebar />
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <TopBar />
        <div style={{ flex: 1, overflowY: 'auto', padding: '24px' }}>
          {children}
        </div>
      </div>
    </div>
  )
}

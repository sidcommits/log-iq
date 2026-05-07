// frontend/src/components/layout/TopBar.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { TopBar } from './TopBar'

describe('TopBar', () => {
  it('renders LOGIQ breadcrumb prefix', () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route path="*" element={<TopBar />} />
        </Routes>
      </MemoryRouter>
    )
    expect(screen.getByText(/LOGIQ/)).toBeInTheDocument()
  })
})

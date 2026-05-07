import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { SeverityBadge } from './SeverityBadge'

describe('SeverityBadge', () => {
  it('renders the severity label', () => {
    render(<SeverityBadge severity="ERROR" />)
    expect(screen.getByText('ERROR')).toBeInTheDocument()
  })

  it('renders WARN severity', () => {
    render(<SeverityBadge severity="WARN" />)
    expect(screen.getByText('WARN')).toBeInTheDocument()
  })

  it('renders INFO severity', () => {
    render(<SeverityBadge severity="INFO" />)
    expect(screen.getByText('INFO')).toBeInTheDocument()
  })
})

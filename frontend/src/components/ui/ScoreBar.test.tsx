import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { ScoreBar } from './ScoreBar'

describe('ScoreBar', () => {
  it('displays the score value', () => {
    render(<ScoreBar score={0.87} />)
    expect(screen.getByText('0.87')).toBeInTheDocument()
  })

  it('fill width reflects score percentage', () => {
    const { container } = render(<ScoreBar score={0.6} />)
    const fill = container.querySelector('[data-testid="score-fill"]')
    expect(fill).toHaveStyle({ width: '60%' })
  })
})

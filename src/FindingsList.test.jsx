import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import FindingsList from './FindingsList'

afterEach(cleanup)

describe('FindingsList', () => {
  it('shows an empty state when there are no findings', () => {
    render(<FindingsList title="Bugs" items={[]} />)
    expect(screen.getByText('No issues found.')).toBeTruthy()
    expect(screen.getByText('(0)')).toBeTruthy()
  })

  it('renders severity, line number and description for each finding', () => {
    const items = [
      { line: 3, severity: 'high', description: 'Hardcoded credential' },
      { line: 7, severity: 'low', description: 'Debug print' },
    ]
    render(<FindingsList title="Security" items={items} />)
    expect(screen.getByText('(2)')).toBeTruthy()
    expect(screen.getByText('high')).toBeTruthy()
    expect(screen.getByText('L7')).toBeTruthy()
    expect(screen.getByText(/Hardcoded credential/)).toBeTruthy()
  })

  it('does not crash on an unknown severity', () => {
    render(<FindingsList title="Quality" items={[{ line: 1, severity: 'weird', description: 'x' }]} />)
    expect(screen.getByText('weird')).toBeTruthy()
  })
})

import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useDebouncedValue } from './useDebouncedValue'

describe('useDebouncedValue', () => {
  afterEach(() => vi.useRealTimers())

  it('waits for the delay and cancels stale updates', () => {
    vi.useFakeTimers()
    const { result, rerender } = renderHook(
      ({ value }) => useDebouncedValue(value, 250),
      { initialProps: { value: 'initial' } },
    )

    rerender({ value: 'stale' })
    act(() => vi.advanceTimersByTime(150))
    rerender({ value: 'final' })
    act(() => vi.advanceTimersByTime(249))
    expect(result.current).toBe('initial')

    act(() => vi.advanceTimersByTime(1))
    expect(result.current).toBe('final')
  })
})

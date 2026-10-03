import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

// Explicit cleanup is required when constrained hosts reuse one worker.
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

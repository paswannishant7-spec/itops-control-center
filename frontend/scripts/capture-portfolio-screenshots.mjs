import { spawnSync } from 'node:child_process'
import path from 'node:path'

const cli = path.resolve('node_modules', '@playwright', 'test', 'cli.js')
const result = spawnSync(
  process.execPath,
  [cli, 'test', 'e2e/portfolio-screenshots.spec.ts', '--project=chromium'],
  {
    stdio: 'inherit',
    env: { ...process.env, CAPTURE_PORTFOLIO: '1' },
  },
)

process.exit(result.status ?? 1)

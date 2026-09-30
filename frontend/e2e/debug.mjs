// The debug overlay (?debug=1): team lines, targets, pressers and the ball carrier's options
// drawn over a live match, and still there while paused.
// Usage: node e2e/debug.mjs <url> <dir>
import { chromium } from 'playwright'
import { target } from './target.mjs'

const base = await target(process.argv[2])
const out = process.argv[3] ?? '/tmp'
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
const errors = []
page.on('pageerror', (e) => errors.push(e.message))
const shot = (name) => page.screenshot({ path: `${out}/${name}.png` })

// /start shows the start page even when the server still has a career open (from an
// earlier script, say), where / would show that career's dashboard.
await page.goto(new URL('/start', base).href)
await page.getByText('New career').waitFor()
await page.getByPlaceholder('Your name').fill('Debug')
// The club tile is a button; the saved-careers list may show the same name as text.
await page.getByRole('button', { name: /^Arsenal Squad/ }).click()
await page.getByRole('button', { name: 'Start career' }).click()
await page.getByRole('button', { name: 'Continue' }).click()
await page.getByText('Your starting XI').waitFor({ timeout: 60000 })
await page.getByRole('button', { name: 'Watch match' }).click()
await page.getByRole('button', { name: 'Play' }).waitFor({ timeout: 30000 })

// The overlay is only offered with ?debug=1.
if (await page.getByRole('checkbox', { name: /Debug overlay/ }).count()) throw new Error('offered without ?debug=1')
await page.goto(`${page.url()}?debug=1`)
await page.getByRole('button', { name: 'Play' }).waitFor({ timeout: 30000 })
await page.getByRole('checkbox', { name: /Debug overlay/ }).check()
await page.getByRole('button', { name: 'Play' }).click()
await page.waitForTimeout(6000)
await shot('20-debug-playing')
await page.getByRole('button', { name: 'Pause' }).click()
await page.waitForTimeout(4000) // updates keep arriving while paused
await shot('21-debug-paused')
console.log(errors.length ? `ERRORS:\n${errors.join('\n')}` : 'no browser errors')
await browser.close()

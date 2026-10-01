// Sims a new career to the end of its season from the browser and checks what follows: the
// results first, then a separate season summary leading with the club's finish. Takes several
// minutes (a whole season of the user's matches), so it isn't part of `just e2e`.
// Usage: node e2e/season.mjs <url> <dir>
import { chromium } from 'playwright'
import { target } from './target.mjs'

const base = await target(process.argv[2])
const out = process.argv[3] ?? '/tmp'
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
const errors = []
page.on('pageerror', (e) => errors.push(e.message))
const expected = (m) => m.text().includes('409') && m.location().url.endsWith('/api/career')
page.on('console', (m) => m.type() === 'error' && !expected(m) && errors.push(m.text()))
const shot = (name) => page.screenshot({ path: `${out}/${name}.png` })

await page.goto(new URL('/start', base).href)
await page.getByText('New career').waitFor()
await page.getByPlaceholder('Your name').fill('Season')
await page.getByRole('button', { name: /^Arsenal Squad/ }).click()
await page.getByRole('button', { name: 'Start career' }).click()
await page.getByText('Dashboard', { exact: true }).first().waitFor()

await page.getByRole('button', { name: 'Sim to…' }).click()
await page.getByRole('menuitem', { name: 'End of season' }).click()
await page.getByRole('progressbar', { name: 'Simulation progress' }).waitFor({ timeout: 10000 })
const finished = page.getByRole('dialog', { name: 'Simulation finished' })
await finished.waitFor({ timeout: 30 * 60 * 1000 })
await shot('season-1-results')
const results = await finished.innerText()
console.log(`results: ${results.split('\n').slice(0, 4).join(' | ')} …`)
if (!/The season is over/.test(results)) errors.push('the sim did not stop at the season end')

await finished.getByRole('button', { name: 'Season summary' }).click()
// The results window closes first (a short fade), then the season summary opens on its own.
await finished.waitFor({ state: 'hidden', timeout: 3000 })
const summary = page.getByRole('dialog', { name: 'Season summary' })
await summary.waitFor({ timeout: 5000 })
await page.waitForTimeout(400) // let it finish fading in for the screenshot
if (await finished.isVisible()) errors.push('the results window is open again over the summary')
await shot('season-2-summary')
const text = await summary.innerText()
console.log(`summary: ${text.split('\n').slice(0, 6).join(' | ')} …`)
if (!/^\d+(st|nd|rd|th) in the /m.test(text)) errors.push('no finishing position in the summary')
await summary.getByRole('button', { name: 'OK' }).click()
await page.waitForTimeout(500)
if (await summary.isVisible()) errors.push('the season summary did not close')
console.log(errors.length ? `ERRORS:\n${errors.join('\n')}` : 'no browser errors')
await browser.close()

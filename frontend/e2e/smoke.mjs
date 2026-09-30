// Drives the running app through a career start, a match and the main screens, saving
// screenshots. Usage: node e2e/smoke.mjs <base url> <screenshot dir>
import { chromium } from 'playwright'
import { target } from './target.mjs'

const base = await target(process.argv[2])
const out = process.argv[3] ?? '/tmp'
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1400, height: 900 } })
const errors = []
page.on('pageerror', (e) => errors.push(e.message))
page.on('console', (m) => m.type() === 'error' && errors.push(m.text()))

const shot = async (name) => page.screenshot({ path: `${out}/${name}.png`, fullPage: true })

// /start shows the start page even when the server still has a career open (from an
// earlier script, say), where / would show that career's dashboard.
await page.goto(new URL('/start', base).href)
await page.getByText('New career').waitFor()
await page.getByPlaceholder('Your name').fill('Alex')
// The club tile is a button; the saved-careers list may show the same name as text.
await page.getByRole('button', { name: /^Arsenal Squad/ }).click()
await shot('01-start')
await page.getByRole('button', { name: 'Start career' }).click()
await page.getByText('Dashboard', { exact: true }).first().waitFor()
await shot('02-dashboard')
await page.getByRole('button', { name: 'Continue' }).click()
await page.getByText('Your starting XI').waitFor({ timeout: 60000 })
await shot('03-matchday')
await page.getByRole('button', { name: 'Instant result' }).click()
await page.getByText('Statistics').waitFor({ timeout: 60000 })
await shot('04-report')
for (const [label, name] of [['Squad', '05-squad'], ['Tactics', '06-tactics'], ['League', '07-league'], ['Fixtures', '08-fixtures']]) {
  await page.getByRole('navigation').getByText(label, { exact: true }).click()
  await page.waitForTimeout(1200)
  await shot(name)
}
await page.getByRole('navigation').getByText('Squad', { exact: true }).click()
await page.waitForTimeout(800)
await page.locator('tbody tr').first().click()
await page.getByText('Best roles').waitFor()
await shot('09-player')

// Another club: League -> club page -> one of their players.
await page.getByRole('navigation').getByText('League', { exact: true }).click()
await page.getByRole('link', { name: 'Chelsea', exact: true }).click()
await page.getByText('Transfer budget').waitFor()
await page.getByRole('heading', { name: 'Squad' }).waitFor()
await shot('10-club')
await page.locator('tbody tr').last().click()
await page.getByText('Best roles').waitFor()
await shot('11-club-player')
console.log(errors.length ? `ERRORS:\n${errors.join('\n')}` : 'no browser errors')
await browser.close()

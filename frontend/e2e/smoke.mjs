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
// A fresh server has no career yet: its start page asking for one gets a 409, as intended.
const expected = (m) => m.text().includes('409') && m.location().url.endsWith('/api/career')
page.on('console', (m) => m.type() === 'error' && !expected(m) && errors.push(m.text()))

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
// Passing the 1st of a month brings the players' development news (P13): close it first.
const monthNews = page.getByRole('dialog', { name: 'News' })
await monthNews.waitFor({ timeout: 3000 }).catch(() => {})
if (await monthNews.isVisible()) {
  console.log(`news: ${(await monthNews.innerText()).split('\n').slice(1, 3).join(' | ')}`)
  await monthNews.getByRole('button', { name: 'OK' }).click()
  await monthNews.waitFor({ state: 'hidden' })
}
await page.getByRole('button', { name: 'Instant result' }).click()
await page.getByText('Statistics').waitFor({ timeout: 60000 })
await shot('04-report')
for (const [label, name] of [['Squad', '05-squad'], ['Tactics', '06-tactics'], ['League', '07-league'], ['Fixtures', '08-fixtures'], ['Cups', '08b-cups']]) {
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
await page.getByText('Budget', { exact: true }).waitFor()
await page.getByRole('heading', { name: 'Squad' }).waitFor()
await shot('10-club')
await page.locator('tbody tr').last().click()
await page.getByText('Best roles').waitFor()
await shot('11-club-player')

// Sim to date: a week on, the user's matches on the way played instantly, then a summary.
const header = page.locator('.mantine-AppShell-header')
const before = await header.innerText()
await page.getByRole('button', { name: 'Sim to…' }).click()
await page.getByRole('menuitem', { name: 'One week' }).click()
// Attached, not visible: at 0% the bar has no width, and a cold server's first step can take a while.
await page.getByRole('progressbar', { name: 'Simulation progress' }).waitFor({ state: 'attached', timeout: 10000 })
await shot('12-sim-progress')
const finished = page.getByRole('dialog', { name: 'Simulation finished' })
await finished.waitFor({ timeout: 180000 })
await shot('13-sim-summary')
const summary = await finished.innerText()
console.log(`sim summary: ${summary.replace(/\n+/g, ' | ')}`)
// Results first; any news (cup draws, say, or at the season's end a season summary) opens in
// its own window once the results window has closed.
const next = finished.getByRole('button', { name: /^(OK|News|Season summary)$/ })
const label = await next.innerText()
await next.click()
if (label !== 'OK') {
  const news = page.getByRole('dialog', { name: /^(News|Season summary)$/ })
  await news.waitFor({ timeout: 5000 })
  await shot('14-sim-news')
  console.log(`sim news: ${(await news.innerText()).replace(/\n+/g, ' | ').slice(0, 300)}`)
  await news.getByRole('button', { name: 'OK' }).click()
  await news.waitFor({ state: 'hidden', timeout: 5000 })
}
await page.waitForTimeout(500)
const after = await header.innerText()
if (after === before) errors.push('the date in the header did not move on after the sim')
console.log(errors.length ? `ERRORS:\n${errors.join('\n')}` : 'no browser errors')
await browser.close()

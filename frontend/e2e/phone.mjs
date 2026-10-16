// The game on a phone (390×844, touch): a career start, the main screens through the menu, a
// change on the tactics pitch by tapping, then a live match on the upright pitch with a
// substitution made by tapping while paused. No screen may scroll sideways.
// Usage: node e2e/phone.mjs <url> <dir>
import { chromium, devices } from 'playwright'
import { closeNews, toMatchDay } from './flow.mjs'
import { target } from './target.mjs'

const base = await target(process.argv[2])
const out = process.argv[3] ?? '/tmp'
const browser = await chromium.launch()
const context = await browser.newContext({ ...devices['iPhone 13'], viewport: { width: 390, height: 844 } })
const page = await context.newPage()
const errors = []
page.on('pageerror', (e) => errors.push(e.message))
const expected = (m) => m.text().includes('409') && m.location().url.endsWith('/api/career')
page.on('console', (m) => m.type() === 'error' && !expected(m) && errors.push(m.text()))
const shot = (name) => page.screenshot({ path: `${out}/${name}.png` })

// Nothing wider than the screen: the page itself never scrolls sideways.
const fits = async (where) => {
  const [scroll, inner] = await page.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth])
  if (scroll > inner) errors.push(`${where}: the page is ${scroll}px wide on a ${inner}px screen`)
}
const menu = async (label) => {
  await page.getByRole('button', { name: 'Menu' }).tap()
  await page.getByRole('navigation').getByText(label, { exact: true }).tap()
  await page.waitForTimeout(1200)
  await closeNews(page)
}

await page.goto(new URL('/start', base).href)
await page.getByText('New career').waitFor()
await fits('start')
await page.getByPlaceholder('Your name').fill('Phone')
await page.getByRole('button', { name: /^Brentford Squad/ }).tap()
await page.getByRole('button', { name: 'Start career' }).tap()
await page.getByText('Dashboard', { exact: true }).first().waitFor()
await shot('p01-dashboard')
await fits('dashboard')

for (const [label, name] of [['Squad', 'p02-squad'], ['Transfers', 'p03-transfers'], ['Finances', 'p04-finances'], ['League', 'p05-league'], ['Fixtures', 'p06-fixtures']]) {
  await menu(label)
  await shot(name)
  await fits(label)
}

// Tactics: tap a bench player, then the first player on the pitch; they change places.
await menu('Tactics')
const bench = page.locator('tbody tr').first()
const benchName = (await bench.innerText()).split('\n').find((t) => /[A-Za-z]{3}/.test(t))
await bench.tap()
await page.getByText('Tap a slot or player to swap').waitFor()
await page.locator('[title*="·"]').last().tap() // the pitch's front end: an outfield player
await page.waitForTimeout(1500)
await shot('p07-tactics')
await fits('tactics')
console.log(`tactics: tapped ${benchName} onto the pitch`)

// A live match on the upright pitch.
await menu('Dashboard')
await toMatchDay(page)
await page.getByRole('button', { name: 'Watch match' }).tap()
await page.getByRole('button', { name: 'Play' }).waitFor({ timeout: 30000 })
const canvas = page.locator('canvas').first()
const box = await canvas.boundingBox()
if (!(box && box.height > box.width)) errors.push(`the pitch isn't upright on a phone: ${JSON.stringify(box)}`)
await page.getByRole('button', { name: 'Play' }).tap()
await page.waitForTimeout(5000)
await shot('p08-live')
await fits('live match')
await page.getByRole('button', { name: 'Pause' }).tap()

// A substitution by tapping while paused: it waits, with Undo, until play resumes and, paused in
// open play, until the first stoppage after (the fourth official waits for a dead ball).
await page.getByRole('tab', { name: 'Subs' }).tap()
await page.waitForTimeout(500)
// An outfield substitute (the bench's reserve keeper can be anywhere in it) for an outfield player
// (the keeper is the first of the eleven).
await page.locator('[title*="condition"]').filter({ hasNotText: '· GK' }).first().tap()
await page.locator('[title*="match rating"]').nth(1).tap()
await page.getByRole('button', { name: 'Undo' }).waitFor({ timeout: 5000 })
await shot('p09-live-sub-staged')
await page.getByRole('button', { name: 'Play' }).tap()
try {
  await page.getByRole('button', { name: 'Undo' }).waitFor({ state: 'detached', timeout: 60000 })
} catch {
  errors.push('the substitution was still waiting a minute after play resumed')
}
await shot('p10-live-sub-made')

await page.getByRole('button', { name: 'Instant result' }).tap()
await page.getByRole('button', { name: 'Match report' }).waitFor({ timeout: 60000 })
await page.getByRole('button', { name: 'Match report' }).tap()
await page.getByText('Statistics').waitFor({ timeout: 30000 })
await shot('p11-report')
await fits('match report')
console.log(errors.length ? `ERRORS:\n${errors.join('\n')}` : 'no browser errors')
await browser.close()
if (errors.length) process.exit(1)

// Starts a career, goes to match day and watches the live match: speed controls, half-time
// changes, the subs panel, a player card, then an instant finish and the report.
// Usage: node e2e/live.mjs <url> <dir>
import { chromium } from 'playwright'

const base = process.argv[2] ?? 'http://127.0.0.1:8765'
const out = process.argv[3] ?? '/tmp'
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
const errors = []
page.on('pageerror', (e) => errors.push(e.message))
page.on('console', (m) => m.type() === 'error' && errors.push(m.text()))
const shot = (name) => page.screenshot({ path: `${out}/${name}.png` })

await page.goto(base)
await page.getByText('New career').waitFor()
await page.getByPlaceholder('Your name').fill('Alex')
await page.getByText('Liverpool', { exact: true }).click()
await page.getByRole('button', { name: 'Start career' }).click()
await page.getByRole('button', { name: 'Continue' }).click()
await page.getByText('Your starting XI').waitFor({ timeout: 60000 })
await page.getByRole('button', { name: 'Watch match' }).click()
await page.getByRole('button', { name: 'Play' }).waitFor({ timeout: 30000 })
await page.waitForTimeout(1000)
await shot('10-live-kickoff')

// 1x: about 9 match seconds per real second.
await page.getByRole('button', { name: 'Play' }).click()
await page.waitForTimeout(5000)
const clockAt1x = await page.getByLabel('Match clock').innerText()
console.log(`clock after 5 s at 1x: ${clockAt1x}`)
await shot('11-live-1x')

await page.getByText('8×').click()
await page.getByRole('button', { name: 'Start second half' }).waitFor({ timeout: 90000 })
await shot('12-live-half-time')

await page.getByRole('tab', { name: 'Tactics' }).click()
await page.getByRole('combobox', { name: 'Formation' }).click()
await page.getByRole('option', { name: /4-2-3-1/ }).click()
// Hand the tactics to the assistant. The box shows the server's state, so wait for it to
// confirm rather than expecting it to flip on the click itself.
const assistant = page.getByRole('checkbox', { name: /Assistant adjusts tactics/ })
const settles = async (want) => {
  for (let i = 0; i < 30; i++) {
    if ((await assistant.isChecked()) === want) return
    await page.waitForTimeout(100)
  }
  throw new Error(`assistant toggle did not become ${want ? 'on' : 'off'}`)
}
await assistant.click()
await settles(true)
await shot('13a-live-tactics-assistant')
await assistant.click()
await settles(false)
await page.getByRole('tab', { name: 'Subs' }).click()
await page.waitForTimeout(500)
await shot('13-live-subs-at-half-time')
await page.getByRole('button', { name: 'Start second half' }).click()
await page.waitForTimeout(4000)

// Click around the middle of the pitch until a player card opens.
const canvas = page.locator('canvas')
const box = await canvas.boundingBox()
for (const [fx, fy] of [[0.5, 0.5], [0.4, 0.4], [0.6, 0.6], [0.3, 0.5], [0.7, 0.5], [0.45, 0.3], [0.55, 0.7]]) {
  await canvas.click({ position: { x: box.width * fx, y: box.height * fy } })
  if (await page.getByText(/Fitness at kick-off/).count()) break
}
await shot('14-live-player-card')

await page.getByRole('button', { name: 'Instant result' }).click()
await page.getByRole('button', { name: 'Match report' }).waitFor({ timeout: 60000 })
await shot('15-live-end')
await page.getByRole('button', { name: 'Match report' }).click()
await page.getByText('Statistics').waitFor({ timeout: 30000 })
await page.screenshot({ path: `${out}/16-live-report.png`, fullPage: true })
console.log(errors.length ? `ERRORS:\n${errors.join('\n')}` : 'no browser errors')
await browser.close()

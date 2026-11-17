// The Americas (W9a): an MLS career (Atlanta United, started through the API), its MLS roster
// page reached from the Squad page (a designation changed, the roster model tried, the
// international-slot window opened), then the College page: a conference's table and tournament,
// the RPI, the NCAA bracket and the draft pool. Then the same pages on a phone, which must not
// scroll sideways. No browser errors.
// Usage: node e2e/americas.mjs <url> <dir>
import { chromium, devices } from 'playwright'
import { closeNews } from './flow.mjs'
import { target } from './target.mjs'

const base = await target(process.argv[2])
const out = process.argv[3] ?? '/tmp'
const api = async (method, path, body) => {
  const response = await fetch(new URL(`/api${path}`, base), {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!response.ok) throw new Error(`${method} ${path}: ${response.status} ${await response.text()}`)
  return response.json()
}

// A new career at Atlanta United, in save slot 1.
const usa = (await api('GET', '/world/leagues')).find((l) => l.key === 'USA1')
const atlanta = usa?.clubs?.find((c) => c.name === 'Atlanta United')
if (!atlanta) throw new Error('Atlanta United is not in the world')
await api('POST', '/saves/1/new', { club_id: atlanta.id, manager_name: 'Americas', budget_eur: null, board_enabled: true, currency: 'USD' })
console.log(`career: Atlanta United (${atlanta.id})`)

const browser = await chromium.launch()
const errors = []
// A refused roster change answers 409, which the browser logs; the page shows the refusal.
const expected = (m) => /\b409\b/.test(m.text()) && /\/api\/(career|mls\/)/.test(m.location().url)
const watch = (page, where) => {
  page.on('pageerror', (e) => errors.push(`${where}: ${e.message}`))
  page.on('console', (m) => m.type() === 'error' && !expected(m) && errors.push(`${where}: ${m.text()}`))
}

// --- a computer ---------------------------------------------------------------------------------
const page = await browser.newPage({ viewport: { width: 1400, height: 900 } })
watch(page, 'desktop')
const shot = (name) => page.screenshot({ path: `${out}/${name}.png`, fullPage: true })
await page.goto(new URL('/squad', base).href)
await closeNews(page)
await page.getByRole('button', { name: 'MLS roster' }).click()
await page.getByText('Salary budget left').waitFor()
await shot('a01-mls-roster')

// Change a designation: the first choice the server takes. A refusal is shown under the player.
const designation = async () => {
  const selects = page.getByRole('combobox', { name: /^Designation of / })
  const count = await selects.count()
  for (let i = 0; i < count; i++) {
    const select = selects.nth(i)
    const label = await select.getAttribute('aria-label')
    const current = await select.inputValue()
    const options = await select.locator('option').evaluateAll((os) => os.map((o) => o.value))
    for (const option of options.filter((o) => o !== current)) {
      const answer = page.waitForResponse((r) => r.url().includes('/api/mls/designation'))
      await select.selectOption(option)
      const response = await answer
      if (response.ok()) {
        await page.waitForTimeout(400)
        const now = await page.getByRole('combobox', { name: label }).inputValue()
        if (now !== option) errors.push(`${label}: the page shows ${now} after ${option} was accepted`)
        return `${label}: ${current} -> ${option}`
      }
      const refusal = page.getByRole('alert').filter({ hasText: /\S/ }).first()
      await refusal.waitFor({ timeout: 3000 })
      console.log(`refused (${label} -> ${option}): ${await refusal.innerText()}`)
    }
  }
  return null
}
const changed = await designation()
if (changed) console.log(`designation: ${changed}`)
else errors.push('no designation change was accepted')
await shot('a02-mls-designation')

// The roster model: Model 2 has two DP slots, so a club with three DPs is refused.
const model = page.waitForResponse((r) => r.url().includes('/api/mls/roster-model'))
await page.getByRole('radiogroup', { name: 'Roster model' }).getByText('2: 2 DP').click()
const modelAnswer = await model
console.log(`roster model 2: ${modelAnswer.status()}${modelAnswer.ok() ? '' : ` (${(await modelAnswer.json()).detail})`}`)

// The international-slot window lists the clubs with one to spare.
await page.getByRole('button', { name: 'Buy a slot' }).click()
await page.getByRole('dialog', { name: 'Buy an international slot' }).getByText(/costs/).waitFor()
await page.screenshot({ path: `${out}/a03-mls-slot.png` })
await page.keyboard.press('Escape')

// The College page, from the menu.
await page.getByRole('navigation').getByText('College', { exact: true }).click()
await page.getByText('College soccer', { exact: true }).waitFor()
await page.getByText('Conference games only').waitFor()
await shot('a04-college-table')
await page.getByRole('radiogroup', { name: 'Table or tournament' }).getByText('Tournament').click()
await page.waitForTimeout(800)
await shot('a05-college-tournament')
await page.getByRole('radiogroup', { name: 'College view' }).getByText('RPI').click()
await page.waitForTimeout(800)
await page.getByRole('radiogroup', { name: 'College view' }).getByText('NCAA').click()
await page.getByText('NCAA Tournament').first().waitFor()
await page.waitForTimeout(500)
await shot('a06-college-ncaa')
await page.getByRole('radiogroup', { name: 'College view' }).getByText('Draft pool').click()
await page.waitForTimeout(800)
await shot('a07-college-draft')

// --- a phone ------------------------------------------------------------------------------------
const phoneContext = await browser.newContext({ ...devices['iPhone 13'], viewport: { width: 375, height: 812 } })
const phone = await phoneContext.newPage()
watch(phone, 'phone')
const fits = async (where) => {
  const [scroll, inner] = await phone.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth])
  if (scroll > inner) errors.push(`phone ${where}: the page is ${scroll}px wide on a ${inner}px screen`)
}
const more = async (label) => {
  await phone.getByRole('navigation', { name: 'Main' }).getByRole('button', { name: 'More', exact: true }).tap()
  await phone.getByRole('dialog').getByRole('button', { name: label, exact: true }).tap()
  await phone.waitForTimeout(1200)
}
await phone.goto(new URL('/', base).href)
await phone.getByText('Next match', { exact: true }).first().waitFor()
await closeNews(phone)
await more('MLS roster')
await phone.getByText('Salary budget left').waitFor()
await phone.screenshot({ path: `${out}/a08-phone-mls.png`, fullPage: true })
await fits('MLS roster')
await more('College')
await phone.getByText('Conference games only').waitFor()
await phone.screenshot({ path: `${out}/a09-phone-college.png`, fullPage: true })
await fits('College')
await phone.getByRole('radiogroup', { name: 'College view' }).getByText('NCAA').tap()
await phone.getByText('NCAA Tournament').first().waitFor()
await phone.waitForTimeout(500)
await phone.screenshot({ path: `${out}/a10-phone-ncaa.png`, fullPage: true })
await fits('NCAA')

console.log(errors.length ? `ERRORS:\n${errors.join('\n')}` : 'no browser errors')
await browser.close()
if (errors.length) process.exit(1)

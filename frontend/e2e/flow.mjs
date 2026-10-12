// Steps the e2e scripts share.

// Continue until the next match day, then open the match day page. Continue stays on the page
// it was pressed on (the header button turns into "Match day"), and it also stops early for
// news, such as a bid for one of the user's players: those windows are closed and logged.
export async function toMatchDay(page) {
  const header = page.locator('.mantine-AppShell-header')
  const matchDay = header.getByRole('button', { name: 'Match day' })
  for (let presses = 0; presses < 8 && !(await matchDay.isVisible()); presses++) {
    await closeDialogs(page)
    const before = await header.innerText()
    await header.getByRole('button', { name: 'Continue' }).click()
    // Done when the header changes (a new date or the Match day button) or a window opens.
    for (let waited = 0; waited < 60000; waited += 250) {
      if ((await header.innerText()) !== before || (await page.getByRole('dialog').count())) break
      await page.waitForTimeout(250)
    }
  }
  await closeDialogs(page)
  await matchDay.click()
  await page.getByText('Your starting XI').waitFor({ timeout: 30000 })
  await closeNews(page)
}

// Any windows a Continue left open (news, a bid, a season summary): logged, then closed.
async function closeDialogs(page) {
  await page.waitForTimeout(500)
  for (let i = 0; i < 5; i++) {
    const dialog = page.getByRole('dialog').first()
    if (!(await dialog.count()) || !(await dialog.isVisible())) return
    console.log(`window: ${(await dialog.innerText()).split('\n').slice(0, 3).join(' | ')}`)
    const button = dialog.getByRole('button', { name: /^(OK|Close|Later|Not now)$/ }).first()
    if (await button.count()) await button.click()
    else await page.keyboard.press('Escape')
    await page.waitForTimeout(300)
  }
}

// Passing the 1st of a month brings the players' development news (P13): close it first.
export async function closeNews(page) {
  const monthNews = page.getByRole('dialog', { name: 'News' })
  await monthNews.waitFor({ timeout: 3000 }).catch(() => {})
  if (await monthNews.isVisible()) {
    console.log(`news: ${(await monthNews.innerText()).split('\n').slice(1, 3).join(' | ')}`)
    await monthNews.getByRole('button', { name: 'OK' }).click()
    await monthNews.waitFor({ state: 'hidden' })
  }
}

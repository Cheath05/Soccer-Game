import { Text, Tooltip, UnstyledButton } from '@mantine/core'
import { useDisclosure } from '@mantine/hooks'
import { useState } from 'react'

import { useHealth } from '../api/hooks'
import { useDevice } from '../lib/device'
import WhatsNew from './WhatsNew'

const UNKNOWN = 'unknown'

// A date as written in the ISO string, in the committer's own time zone: "6 Oct".
function dayMonth(iso: string): string {
  const day = new Date(`${iso.slice(0, 10)}T12:00:00`)
  return Number.isNaN(day.getTime()) ? iso : day.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
}

// An instant in the viewer's time zone: "6 Oct 2026, 16:05".
function dateTime(iso: string): string {
  const instant = new Date(iso)
  return Number.isNaN(instant.getTime()) ? iso : instant.toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' })
}

async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    // fall through to the textarea route
  }
  // The clipboard API needs a secure page (https or localhost); over plain http, select and copy.
  const box = document.createElement('textarea')
  box.value = text
  box.setAttribute('readonly', '')
  box.style.position = 'fixed'
  box.style.opacity = '0'
  document.body.appendChild(box)
  box.select()
  try {
    return document.execCommand('copy')
  } catch {
    return false
  } finally {
    document.body.removeChild(box)
  }
}

// A version number as shown ("v1.12"), or the commit where there isn't one (a server that
// predates version numbers, or a copy without git).
function shown(version: string, commit: string): string {
  return version !== UNKNOWN ? `v${version}` : commit
}

// Which build this is, for saying "I'm on v1.12". It shows the server's version number and the
// date of its commit; if the page was built from another commit (the server was updated but the
// frontend wasn't rebuilt, or the other way round) it shows both versions, in orange. Click it for
// what changed in each version and help on the game (WhatsNew); the window also has the button
// that copies a line to paste into a bug report.
export default function VersionTag({ truncate = false }: { truncate?: boolean }) {
  const health = useHealth()
  const { touch } = useDevice()
  const [copied, setCopied] = useState(false)
  const [opened, { open, close }] = useDisclosure(false)

  if (health.isPending) return null
  const data = health.data
  const server = data?.commit ?? UNKNOWN
  const page = __BUILD_COMMIT__
  // A server that predates version numbers still sends `version`, but it is the package's own.
  const serverVersion = data?.package_version !== undefined ? data.version : UNKNOWN
  const pageVersion = __BUILD_VERSION__
  const mismatch = server !== UNKNOWN && page !== UNKNOWN && server !== page
  const branch = data?.branch ?? UNKNOWN
  const dirty = data?.dirty ? '+' : ''
  const date = data?.commit_date && data.commit_date !== UNKNOWN ? data.commit_date : null
  const serverName = shown(serverVersion, server)
  const pageName = shown(pageVersion, page)

  let label: string
  if (!data) label = `page ${pageName} · server unreachable`
  else if (mismatch) label = `server ${serverName}${dirty} · page ${pageName}`
  else if (server === UNKNOWN && serverVersion === UNKNOWN) label = 'version unknown'
  else label = `${serverName}${dirty}${date ? ` · ${dayMonth(date)}` : ''}`

  // What the window opens with: where the player is.
  let heading: string
  if (!data) heading = `This page is ${pageName}. The server can't be reached.`
  else if (serverName === UNKNOWN) heading = "This server doesn't say which version it is."
  else heading = `You're on ${serverName}${dirty}${date ? ` · ${dayMonth(date)}` : ''}`

  const summary = mismatch
    ? `footsim server ${serverName}${dirty} (${server}) / page ${pageName} (${page}) (${branch}) built ${__BUILD_TIME__}`
    : `footsim ${serverName === UNKNOWN ? pageName : serverName}${dirty} (${server === UNKNOWN ? page : server}, ${branch}) built ${__BUILD_TIME__}`

  const copy = () => {
    void copyText(summary).then((ok) => {
      if (!ok) return
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })
  }

  const facts = (
    <>
      <div>Version: {serverName}{dirty && ' (tracked files changed since)'}</div>
      <div>Branch: {branch}</div>
      <div>Commit: {server}</div>
      {date && <div>Committed: {dateTime(date)}</div>}
      <div>Page built at {pageName} ({page}): {dateTime(__BUILD_TIME__)}</div>
      {mismatch && <div>The page and the server are on different commits: rebuild the page, or restart the server.</div>}
    </>
  )

  return (
    <>
      <Tooltip
        label={
          <div>
            {facts}
            <div>Click for what&apos;s new and help.</div>
          </div>
        }
        multiline
        maw={300}
        withArrow
        openDelay={300}
        disabled={touch} // no hovering on a touch screen: the window has the same details
      >
        {/* On a touch screen the line of small text is padded out (without moving anything) to be easier to hit. */}
        <UnstyledButton
          onClick={open}
          display="block"
          maw="100%"
          py={touch ? 8 : 0}
          my={touch ? -8 : 0}
          aria-label={`What's new and help. ${label}`}
          aria-haspopup="dialog"
        >
          <Text component="span" display="block" size="xs" c={mismatch || !data ? 'orange' : 'dimmed'} truncate={truncate}>
            {label}
          </Text>
        </UnstyledButton>
      </Tooltip>
      <WhatsNew
        opened={opened}
        onClose={close}
        heading={heading}
        version={data && serverVersion !== UNKNOWN ? serverVersion : null}
        details={facts}
        mismatch={mismatch}
        copy={copy}
        copied={copied}
      />
    </>
  )
}

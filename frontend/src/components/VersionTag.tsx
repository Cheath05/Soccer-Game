import { Text, Tooltip, UnstyledButton } from '@mantine/core'
import { useState } from 'react'

import { useHealth } from '../api/hooks'

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

// Which build this is, for saying "I'm on 70b9171". It shows the server's commit; if the page
// was built from another commit (the server was updated but the frontend wasn't rebuilt, or the
// other way round) it shows both, in orange. Click to copy a line to paste into a bug report.
export default function VersionTag({ truncate = false }: { truncate?: boolean }) {
  const health = useHealth()
  const [copied, setCopied] = useState(false)

  if (health.isPending) return null
  const data = health.data
  const server = data?.commit ?? UNKNOWN
  const page = __BUILD_COMMIT__
  const mismatch = server !== UNKNOWN && page !== UNKNOWN && server !== page
  const branch = data?.branch ?? UNKNOWN
  const dirty = data?.dirty ? '+' : ''
  const date = data?.commit_date && data.commit_date !== UNKNOWN ? data.commit_date : null

  let label: string
  if (!data) label = `page ${page} · server unreachable`
  else if (mismatch) label = `server ${server}${dirty} · page ${page}`
  else if (server === UNKNOWN) label = 'version unknown'
  else label = `v${server}${dirty}${date ? ` · ${dayMonth(date)}` : ''}`

  const summary = mismatch
    ? `footsim server ${server}${dirty} / page ${page} (${branch}) built ${__BUILD_TIME__}`
    : `footsim ${server === UNKNOWN ? page : server}${dirty} (${branch}) built ${__BUILD_TIME__}`

  const copy = () => {
    void copyText(summary).then((ok) => {
      if (!ok) return
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })
  }

  const details = (
    <div>
      <div>Branch: {branch}</div>
      <div>Commit: {server}{dirty && ' (tracked files changed since)'}</div>
      {date && <div>Committed: {dateTime(date)}</div>}
      <div>Page built from {page}: {dateTime(__BUILD_TIME__)}</div>
      {mismatch && <div>The page and the server are on different commits: rebuild the page, or restart the server.</div>}
      <div>Click to copy.</div>
    </div>
  )

  return (
    <Tooltip label={details} multiline maw={300} withArrow openDelay={300}>
      <UnstyledButton onClick={copy} display="block" maw="100%" aria-label="Copy the version">
        <Text component="span" display="block" size="xs" c={mismatch || !data ? 'orange' : 'dimmed'} truncate={truncate}>
          {copied ? 'Copied' : label}
        </Text>
      </UnstyledButton>
    </Tooltip>
  )
}

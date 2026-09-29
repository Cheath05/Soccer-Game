import { Link } from '@tanstack/react-router'

import type { ClubRef } from '../api/types'

/** A club's name that opens its page. The click stays on the link, so it also works inside
 * table rows that open something else. */
export default function ClubLink({ club, bold }: { club: ClubRef; bold?: boolean }) {
  return (
    <Link
      to="/clubs/$clubId"
      params={{ clubId: String(club.id) }}
      onClick={(e) => e.stopPropagation()}
      style={{ color: 'inherit', fontWeight: bold ? 700 : undefined, textDecoration: 'none' }}
      onMouseEnter={(e) => (e.currentTarget.style.textDecoration = 'underline')}
      onMouseLeave={(e) => (e.currentTarget.style.textDecoration = 'none')}
    >
      {club.name}
    </Link>
  )
}

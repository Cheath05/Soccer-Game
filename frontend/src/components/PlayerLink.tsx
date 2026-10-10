import { Link } from '@tanstack/react-router'

/** A player's name that opens his page. The click stays on the link, so it also works inside rows that open something else. */
export default function PlayerLink({ player, label }: { player: { id: number; name: string }; label?: string }) {
  return (
    <Link
      to="/players/$playerId"
      params={{ playerId: String(player.id) }}
      onClick={(e) => e.stopPropagation()}
      style={{ color: 'inherit', textDecoration: 'none' }}
      onMouseEnter={(e) => (e.currentTarget.style.textDecoration = 'underline')}
      onMouseLeave={(e) => (e.currentTarget.style.textDecoration = 'none')}
    >
      {label ?? player.name}
    </Link>
  )
}

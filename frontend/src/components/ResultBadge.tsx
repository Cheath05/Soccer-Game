import { Badge } from '@mantine/core'

import type { Fixture } from '../api/types'

export default function ResultBadge({ fixture, clubId }: { fixture: Fixture; clubId: number }) {
  if (fixture.status !== 'played' || fixture.home_goals === null || fixture.away_goals === null) return null
  const home = fixture.home.id === clubId
  let mine = home ? fixture.home_goals : fixture.away_goals
  let theirs = home ? fixture.away_goals : fixture.home_goals
  if (mine === theirs && fixture.home_pens !== null && fixture.away_pens !== null) {
    mine = home ? fixture.home_pens : fixture.away_pens
    theirs = home ? fixture.away_pens : fixture.home_pens
  }
  const result = mine > theirs ? 'W' : mine < theirs ? 'L' : 'D'
  const color = result === 'W' ? 'green' : result === 'L' ? 'red' : 'gray'
  return (
    <Badge color={color} w={28} px={0}>
      {result}
    </Badge>
  )
}

import { useMemo, useState } from 'react'

import type { Career, CupRound, EuropeLeaguePhase } from '../../api/types'
import { useDevice } from '../../lib/device'
import { BracketDesktop, BracketPhone, PathLine } from './Bracket'
import { buildBracket, userPath } from './bracketModel'

/** The knockout rounds as a bracket (Bracket.tsx): the play-off feeding the round of 16, then the
 * two halves of the draw meeting in the final, with your club's path marked. Before a round is
 * drawn its slots read "1st in the league phase", "Winner of 16th v 17th", "Winner of R16 tie 1". */
export default function Knockouts({
  rounds,
  phase,
  userId,
  career,
}: {
  rounds: CupRound[]
  phase: EuropeLeaguePhase
  userId: number | undefined
  career: Career | undefined
}) {
  const { phone } = useDevice()
  const [selected, setSelected] = useState<string | null>(null)
  const model = useMemo(() => buildBracket(rounds, phase), [rounds, phase])
  const toggle = (id: string) => setSelected((cur) => (cur === id ? null : id))
  const props = { model, userId, career, selected, onSelect: toggle }
  return (
    <>
      <PathLine path={userPath(model, userId)} />
      {phone ? <BracketPhone {...props} /> : <BracketDesktop {...props} />}
    </>
  )
}

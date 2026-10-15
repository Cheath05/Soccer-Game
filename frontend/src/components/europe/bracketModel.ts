import type { ClubRef, CupRound, CupTie, EuropeLeaguePhase, Fixture } from '../../api/types'

/** The knockout bracket as data: the play-off, then the round of 16 to the final, each tie with
 * its two sides. A side is a club once it is known (the league phase is over, or the tie before
 * it is decided) and otherwise the slot it will be filled from ("1st in the league phase",
 * "Winner of 16th v 17th", "Winner of R16 tie 1"), so the bracket reads before anything is
 * drawn. It mirrors world/europe/knockout.py: the round of 16 is in bracket order, and tie n of
 * a later round is played by the winners of ties 2n-1 and 2n of the round before. */
export interface Slot {
  club: ClubRef | null
  label: string
  seed: number | null // the league-phase position, once it is known
}

export interface BNode {
  id: string
  round: number // 0 play-off, 1 round of 16, 2 quarter-finals, 3 semi-finals, 4 final
  pos: number // its place in the round, top of the bracket first
  title: string
  a: Slot
  b: Slot
  tie: CupTie | null // null: not drawn yet
}

export interface BracketModel {
  nodes: BNode[][]
  info: (CupRound | undefined)[] // the API's round: name, dates, legs, drawn
  seedsKnown: boolean
}

const BRACKET = [1, 8, 4, 5, 2, 7, 3, 6] // the round-of-16 ties by seed, as in knockout.py
export const SHORT = ['Play-off', 'R16', 'QF', 'SF', 'Final']

export function ordinal(n: number): string {
  const rest = n % 100
  if (rest >= 11 && rest <= 13) return `${n}th`
  return `${n}${({ 1: 'st', 2: 'nd', 3: 'rd' } as Record<number, string>)[n % 10] ?? 'th'}`
}

export function buildBracket(rounds: CupRound[], phase: EuropeLeaguePhase): BracketModel {
  const rank = new Map<number, number>()
  const byPos = new Map<number, ClubRef>()
  for (const row of phase.table) {
    rank.set(row.club.id, row.position)
    byPos.set(row.position, row.club)
  }
  const known = phase.final
  const clubSlot = (club: ClubRef): Slot => ({ club, label: club.name, seed: rank.get(club.id) ?? null })
  const seedSlot = (p: number): Slot => {
    const club = known ? (byPos.get(p) ?? null) : null
    return club ? clubSlot(club) : { club: null, label: `${ordinal(p)} in the league phase`, seed: null }
  }
  const winnerSlot = (from: BNode | undefined, text: string): Slot => {
    const club = from?.tie?.winner ?? null
    return club ? clubSlot(club) : { club: null, label: `Winner of ${text}`, seed: null }
  }

  const [first, last] = phase.to_playoff
  const count = Math.floor((last - first + 1) / 2)
  const nr16 = phase.to_round_of_16
  const nodes: BNode[][] = []

  // Play-off: tie j is (first + j) v (last - j), the better placed club first.
  nodes.push(
    Array.from({ length: count }, (_, j) => {
      const lo = first + j
      const hi = last - j
      const tie = rounds[0]?.ties[j] ?? null
      let a = seedSlot(lo)
      let b = seedSlot(hi)
      if (tie?.away) {
        const sides = [clubSlot(tie.home), clubSlot(tie.away)].sort((x, y) => (x.seed ?? 99) - (y.seed ?? 99))
        a = sides[0] ?? a
        b = sides[1] ?? b
      }
      return { id: `0-${j}`, round: 0, pos: j, title: `${ordinal(lo)} v ${ordinal(hi)}`, a, b, tie }
    }),
  )

  // Round of 16: seed s in bracket order meets the winner of play-off tie count - s.
  const order = nr16 === BRACKET.length ? BRACKET : Array.from({ length: nr16 }, (_, k) => k + 1)
  nodes.push(
    order.map((seed, k) => {
      const tie = rounds[1]?.ties[k] ?? null
      const feeder = nodes[0]?.[count - seed]
      let a = seedSlot(seed)
      let b = winnerSlot(feeder, feeder ? feeder.title : 'the play-off')
      if (tie?.away) {
        const sides = [clubSlot(tie.home), clubSlot(tie.away)].sort((x, y) => (x.seed ?? 99) - (y.seed ?? 99))
        a = sides[0] ?? a
        b = sides[1] ?? b
      }
      return { id: `1-${k}`, round: 1, pos: k, title: `Tie ${k + 1}`, a, b, tie }
    }),
  )

  // Quarter-finals, semi-finals, final: tie n from ties 2n-1 and 2n before it.
  for (let r = 2; r <= 4; r++) {
    const before = nodes[r - 1] ?? []
    nodes.push(
      Array.from({ length: Math.floor(before.length / 2) }, (_, n) => {
        const up = before[2 * n]
        const down = before[2 * n + 1]
        const tie = rounds[r]?.ties[n] ?? null
        let a = winnerSlot(up, `${SHORT[r - 1]} tie ${2 * n + 1}`)
        let b = winnerSlot(down, `${SHORT[r - 1]} tie ${2 * n + 2}`)
        if (tie?.away) {
          const upper = up?.tie?.winner?.id
          const sides = tie.home.id === upper ? [tie.home, tie.away] : [tie.away, tie.home]
          a = clubSlot(sides[0] ?? tie.home)
          b = clubSlot(sides[1] ?? tie.away)
        }
        return { id: `${r}-${n}`, round: r, pos: n, title: r === 4 ? 'Final' : `Tie ${n + 1}`, a, b, tie }
      }),
    )
  }
  return { nodes, info: rounds, seedsKnown: known }
}

const goalsOf = (f: Fixture, clubId: number) => (f.home.id === clubId ? f.home_goals : f.away_goals)

export function aggregate(tie: CupTie | null, club: ClubRef | null): number | null {
  if (!tie || !club) return null
  const played = tie.fixtures.filter((f) => f.status === 'played')
  return played.length ? played.reduce((sum, f) => sum + (goalsOf(f, club.id) ?? 0), 0) : null
}

/** The node a winner of this one goes on to play in. */
function nextNode(model: BracketModel, node: BNode): BNode | undefined {
  if (node.round === 0) return model.nodes[1]?.[r16Of(model, node)]
  return model.nodes[node.round + 1]?.[Math.floor(node.pos / 2)]
}

function order(model: BracketModel): number[] {
  const n = model.nodes[1]?.length ?? 0
  return n === BRACKET.length ? BRACKET : Array.from({ length: n }, (_, k) => k + 1)
}

/** The R16 tie a play-off tie feeds, by index. */
export function r16Of(model: BracketModel, node: BNode): number {
  const count = model.nodes[0]?.length ?? 0
  const seed = count - node.pos
  return order(model).indexOf(seed)
}

/** What the winner of a tie goes on to: "Winner plays 1st (R16 tie 1)". */
export function feedsText(model: BracketModel, node: BNode): string | null {
  if (node.round === 4) return null
  if (node.round === 0) {
    const k = r16Of(model, node)
    const slot = model.nodes[1]?.[k]?.a
    if (!slot) return null
    return `Winner plays ${slot.club ? slot.club.name : ordinal(count0Seed(model, node))} in R16 tie ${k + 1}`
  }
  const sibling = model.nodes[node.round]?.[node.pos ^ 1]
  const next = model.info[node.round + 1]?.name ?? 'the next round'
  const who = sibling?.tie?.winner ? sibling.tie.winner.name : `the winner of ${SHORT[node.round]} tie ${(node.pos ^ 1) + 1}`
  return `Winner plays ${who} in the ${next.toLowerCase()}`
}

function count0Seed(model: BracketModel, node: BNode): number {
  return (model.nodes[0]?.length ?? 0) - node.pos
}

/** Your club's route: each tie it has played or is in, then the one it goes to if it won. */
export function userPath(model: BracketModel, userId: number | undefined): string[] {
  if (userId === undefined) return []
  const mine: BNode[] = []
  for (const round of model.nodes) for (const n of round) if (n.a.club?.id === userId || n.b.club?.id === userId) mine.push(n)
  if (!mine.length) return []
  const line = (n: BNode): string => {
    const me = n.a.club?.id === userId ? n.a : n.b
    const them = me === n.a ? n.b : n.a
    const own = aggregate(n.tie, me.club)
    const other = aggregate(n.tie, them.club)
    const score = own !== null && other !== null ? ` ${own}–${other}` : ''
    const result = n.tie?.winner ? (n.tie.winner.id === userId ? ', won' : ', out') : ''
    return `${SHORT[n.round]}: v ${them.label}${score}${result}`
  }
  const out = mine.map(line)
  const lastNode = mine[mine.length - 1]
  if (lastNode && lastNode.tie?.winner?.id === userId && lastNode.round < 4) {
    const next = nextNode(model, lastNode)
    if (next) {
      const them = next.a.club?.id === userId ? next.b : next.a
      if (!mine.includes(next)) out.push(`${SHORT[next.round]}: v ${them.label}`)
    }
  }
  return out
}


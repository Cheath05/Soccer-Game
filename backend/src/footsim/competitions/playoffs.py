"""Play-off brackets: who meets whom in each round, and who hosts."""

from dataclasses import dataclass

from footsim.defs.competitions import EntrantRef, PlayoffDef, PlayoffRoundDef


@dataclass(frozen=True)
class Entrant:
    club_id: int
    rank: int  # final league position, used for seeding and hosting


@dataclass(frozen=True)
class Tie:
    tie_id: str
    round_index: int
    a: Entrant  # higher league rank (smaller number)
    b: Entrant


@dataclass(frozen=True)
class Leg:
    home: int
    away: int
    leg: int | None
    neutral: bool


def _resolve(ref: EntrantRef, ranks: dict[int, int], winners: dict[str, Entrant]) -> Entrant:
    if ref.rank is not None:
        return Entrant(ranks[ref.rank], ref.rank)
    candidates = [winners[t] for t in ref.winner_of]
    if ref.pick == "highest_ranked":
        return min(candidates, key=lambda e: e.rank)
    if ref.pick == "lowest_ranked":
        return max(candidates, key=lambda e: e.rank)
    return candidates[0]


def round_ties(
    playoff: PlayoffDef, round_index: int, ranks: dict[int, int], winners: dict[str, Entrant]
) -> list[Tie]:
    """Ties for a round. ``ranks`` maps league position -> club; ``winners`` maps earlier
    tie ids -> winning entrant."""
    ties = []
    for tie in playoff.rounds[round_index].ties:
        a = _resolve(tie.a, ranks, winners)
        b = _resolve(tie.b, ranks, winners)
        if b.rank < a.rank:
            a, b = b, a
        ties.append(Tie(tie.id, round_index, a, b))
    return ties


def legs_for(tie: Tie, rnd: PlayoffRoundDef) -> list[Leg]:
    if rnd.host == "neutral":
        return [Leg(tie.a.club_id, tie.b.club_id, None, neutral=True)]
    host, visitor = (tie.a, tie.b) if rnd.host == "higher_ranked" else (tie.b, tie.a)
    if rnd.legs == 1:
        return [Leg(host.club_id, visitor.club_id, None, neutral=False)]
    # Two legs: ``host`` plays the second leg at home.
    return [
        Leg(visitor.club_id, host.club_id, 1, neutral=False),
        Leg(host.club_id, visitor.club_id, 2, neutral=False),
    ]

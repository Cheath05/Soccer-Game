"""Play-off brackets: who meets whom in each round, and who hosts."""

from dataclasses import dataclass

from footsim.defs.competitions import EntrantRef, PlayoffDef, PlayoffRoundDef


@dataclass(frozen=True)
class Entrant:
    club_id: int
    rank: int  # position in the seeding table (the league's, or a phase's), for seeding and hosting


@dataclass(frozen=True)
class Seeds:
    """Who holds each place of the table a play-off seeds from: by league rank, and by rank
    within each conference or zone (ranked by the same table, so a group's order is the
    league's)."""

    ranks: dict[int, int]  # league position -> club
    groups: dict[str, dict[int, int]]  # group -> rank within it -> club

    @property
    def rank_of(self) -> dict[int, int]:
        return {club: rank for rank, club in self.ranks.items()}

    @classmethod
    def of(cls, order: list[int], groups: dict[str, set[int]] | None = None) -> "Seeds":
        """From a table's clubs in order, and each group's members."""
        ranks = {k: club for k, club in enumerate(order, start=1)}
        by_group = {g: {k: club for k, club in enumerate(
            [c for c in order if c in members], start=1)}
            for g, members in (groups or {}).items()}
        return cls(ranks, by_group)


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


def _resolve(ref: EntrantRef, seeds: Seeds, winners: dict[str, Entrant]) -> Entrant:
    if ref.rank is not None:
        club = seeds.groups[ref.group][ref.rank] if ref.group else seeds.ranks[ref.rank]
        return Entrant(club, seeds.rank_of[club])
    candidates = sorted((winners[t] for t in ref.winner_of), key=lambda e: e.rank)
    pick = {"highest_ranked": 0, "second_highest": 1, "second_lowest": -2,
            "lowest_ranked": -1, "only": 0}[ref.pick]
    return candidates[pick]


def round_ties(
    playoff: PlayoffDef, round_index: int, ranks: dict[int, int] | Seeds,
    winners: dict[str, Entrant]
) -> list[Tie]:
    """Ties for a round. ``ranks`` maps league position -> club (or is the full Seeds, with
    the groups' ranks); ``winners`` maps earlier tie ids -> winning entrant."""
    seeds = ranks if isinstance(ranks, Seeds) else Seeds(ranks, {})
    ties = []
    for tie in playoff.rounds[round_index].ties:
        a = _resolve(tie.a, seeds, winners)
        b = _resolve(tie.b, seeds, winners)
        if b.rank < a.rank:
            a, b = b, a
        ties.append(Tie(tie.id, round_index, a, b))
    return ties


def series_winner(club_a: int, club_b: int, games: int,
                  results: list[tuple[int, int, int, int, int | None, int | None]]
                  ) -> int | None:
    """A best-of-``games`` series' winner, from its played games (home, away, home goals, away
    goals, home pens, away pens), or None while undecided. Every game has a winner."""
    wins = {club_a: 0, club_b: 0}
    for home, away, hg, ag, hp, ap in results:
        if hg != ag:
            wins[home if hg > ag else away] += 1
        elif hp is not None and ap is not None:
            wins[home if hp > ap else away] += 1
    need = games // 2 + 1
    return next((club for club, won in wins.items() if won >= need), None)


def legs_for(tie: Tie, rnd: PlayoffRoundDef) -> list[Leg]:
    """Every match a tie can take. A series' games carry their number in ``leg``: the better
    seed hosts the odd ones."""
    if rnd.games > 1:
        better, other = (tie.a, tie.b) if rnd.host == "higher_ranked" else (tie.b, tie.a)
        return [Leg(*((better.club_id, other.club_id) if game % 2 else
                      (other.club_id, better.club_id)), game, neutral=False)
                for game in range(1, rnd.games + 1)]
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

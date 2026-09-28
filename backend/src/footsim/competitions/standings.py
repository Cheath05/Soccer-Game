"""League tables with configurable tiebreakers.

Tiebreakers refine groups of level clubs one criterion at a time. Head-to-head criteria are
computed only among the clubs still level at that point, and are recomputed as groups split,
which covers both "overall first" (Premier League) and "head-to-head first" (La Liga) rules.
"""

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

from footsim.core.rng import derive_seed
from footsim.defs.competitions import PointsRule, Tiebreaker


@dataclass(frozen=True)
class Result:
    home: int
    away: int
    home_goals: int
    away_goals: int


@dataclass
class TableRow:
    club_id: int
    played: int = 0
    won: int = 0
    drawn: int = 0
    lost: int = 0
    goals_for: int = 0
    goals_against: int = 0
    away_goals_for: int = 0
    points: int = 0
    position: int = 0

    @property
    def goal_difference(self) -> int:
        return self.goals_for - self.goals_against


def _tally(
    clubs: Iterable[int], results: Iterable[Result], points: PointsRule
) -> dict[int, TableRow]:
    rows = {c: TableRow(c) for c in clubs}
    for r in results:
        if r.home not in rows or r.away not in rows:
            continue
        home, away = rows[r.home], rows[r.away]
        for row, scored, conceded in ((home, r.home_goals, r.away_goals),
                                      (away, r.away_goals, r.home_goals)):
            row.played += 1
            row.goals_for += scored
            row.goals_against += conceded
            if scored > conceded:
                row.won += 1
                row.points += points.win
            elif scored == conceded:
                row.drawn += 1
                row.points += points.draw
            else:
                row.lost += 1
                row.points += points.loss
        away.away_goals_for += r.away_goals
    return rows


def league_table(
    clubs: Sequence[int],
    results: Sequence[Result],
    points: PointsRule,
    tiebreakers: Sequence[Tiebreaker],
    lots_seed: int = 0,
) -> list[TableRow]:
    rows = _tally(clubs, results, points)

    def key_for(tb: Tiebreaker, group: list[int]) -> Callable[[int], float]:
        if tb is Tiebreaker.POINTS:
            return lambda c: rows[c].points
        if tb is Tiebreaker.GOAL_DIFFERENCE:
            return lambda c: rows[c].goal_difference
        if tb is Tiebreaker.GOALS_FOR:
            return lambda c: rows[c].goals_for
        if tb is Tiebreaker.WINS:
            return lambda c: rows[c].won
        if tb is Tiebreaker.AWAY_GOALS_FOR:
            return lambda c: rows[c].away_goals_for
        if tb is Tiebreaker.DRAWING_OF_LOTS:
            return lambda c: derive_seed(lots_seed, c)
        members = set(group)
        mini = _tally(group, [r for r in results if r.home in members and r.away in members],
                      points)
        return {
            Tiebreaker.H2H_POINTS: lambda c: mini[c].points,
            Tiebreaker.H2H_GOAL_DIFFERENCE: lambda c: mini[c].goal_difference,
            Tiebreaker.H2H_GOALS_FOR: lambda c: mini[c].goals_for,
            Tiebreaker.H2H_AWAY_GOALS_FOR: lambda c: mini[c].away_goals_for,
        }[tb]

    groups: list[list[int]] = [sorted(rows)]
    for tb in tiebreakers:
        refined: list[list[int]] = []
        for group in groups:
            if len(group) == 1:
                refined.append(group)
                continue
            key = key_for(tb, group)
            ordered = sorted(group, key=lambda c: (-key(c), c))
            run = [ordered[0]]
            for club in ordered[1:]:
                if key(club) == key(run[-1]):
                    run.append(club)
                else:
                    refined.append(run)
                    run = [club]
            refined.append(run)
        groups = refined

    table = [rows[c] for group in groups for c in sorted(group)]
    for position, row in enumerate(table, start=1):
        row.position = position
    return table

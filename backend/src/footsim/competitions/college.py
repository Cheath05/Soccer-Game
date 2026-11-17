"""The college season's pure parts: the regular season's schedule and the RPI ranking.

**Schedule:** each conference is a single round robin, played in the season's last match days
(each conference's own number of them, so a small conference starts later). The other days are
filled with non-conference games: on each day the teams still short of their total, and free,
are paired with a team of another conference they haven't met, the neediest first. A team can end
a game or two short when no partner is left; there are a couple of spare days for that.

**RPI** (the Rating Percentage Index, as the NCAA ranks soccer teams): a quarter the team's own
winning share, half its opponents' (their games against it left out), a quarter its opponents'
opponents'. A draw, and a game won on penalties, count as a draw."""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from footsim.competitions.fixtures import Round, round_robin


def regular_season(conferences: Sequence[Sequence[int]], matches: int, slots: int,
                   rng: np.random.Generator) -> list[Round]:
    """``slots`` match days of (home, away) pairs for the teams of ``conferences`` (each a list
    of club ids; a conference of one plays only non-conference games)."""
    days: list[Round] = [[] for _ in range(slots)]
    conference_of: dict[int, int] = {}
    busy: list[set[int]] = [set() for _ in range(slots)]
    played: dict[int, int] = defaultdict(int)
    homes: dict[int, int] = defaultdict(int)
    met: set[tuple[int, int]] = set()
    for c, teams in enumerate(conferences):
        for t in teams:
            conference_of[t] = c
        if len(teams) < 2:
            continue
        rounds = round_robin(sorted(teams), 1, rng)
        if len(rounds) > slots:
            raise ValueError(f"a conference of {len(teams)} needs {len(rounds)} match days")
        first = slots - len(rounds)
        for k, games in enumerate(rounds):
            for home, away in games:
                days[first + k].append((home, away))
                busy[first + k].update((home, away))
                played[home] += 1
                played[away] += 1
                homes[home] += 1
                met.add((min(home, away), max(home, away)))
    teams = sorted(conference_of)
    for day in range(slots):
        free = [t for t in teams if t not in busy[day] and played[t] < matches]
        order = [free[int(i)] for i in rng.permutation(len(free))]
        order.sort(key=lambda t: -(matches - played[t]))  # stable: shuffled within a need
        while order:
            t = order.pop(0)
            partner = next((u for u in order if conference_of[u] != conference_of[t]
                            and (min(t, u), max(t, u)) not in met), None)
            if partner is None:
                continue
            order.remove(partner)
            if homes[t] != homes[partner]:
                home, away = (t, partner) if homes[t] < homes[partner] else (partner, t)
            else:
                home, away = (t, partner) if rng.random() < 0.5 else (partner, t)
            days[day].append((home, away))
            for x in (t, partner):
                played[x] += 1
            homes[home] += 1
            met.add((min(t, partner), max(t, partner)))
    return days


@dataclass(frozen=True)
class Game:
    """A played college game for the ranking: ``score`` is the first team's (1 a win, 0 a loss,
    the draw value for a draw or a shoot-out)."""

    a: int
    b: int
    score: float


def rpi(games: Sequence[Game], weights: tuple[float, float, float]) -> dict[int, float]:
    """Every team's RPI from ``games`` (a team without games has none)."""
    record: dict[int, list[tuple[int, float]]] = defaultdict(list)  # team -> (opponent, score)
    for g in games:
        record[g.a].append((g.b, g.score))
        record[g.b].append((g.a, 1.0 - g.score))

    def wp(team: int, without: int | None = None) -> float | None:
        scores = [s for o, s in record[team] if o != without]
        return sum(scores) / len(scores) if scores else None

    own = {t: wp(t) or 0.0 for t in record}
    owp: dict[int, float] = {}
    for t, games_t in record.items():
        values = [v for o, _ in games_t if (v := wp(o, t)) is not None]
        owp[t] = sum(values) / len(values) if values else 0.0
    result = {}
    for t, games_t in record.items():
        oowp = sum(owp[o] for o, _ in games_t) / len(games_t)
        result[t] = weights[0] * own[t] + weights[1] * owp[t] + weights[2] * oowp
    return result


def ranked(ratings: dict[int, float]) -> list[int]:
    """Teams best first; level ratings by club id (stable, deterministic)."""
    return sorted(ratings, key=lambda t: (-ratings[t], t))

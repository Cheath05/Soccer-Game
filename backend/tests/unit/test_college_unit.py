"""College soccer's formats (W9a, the NCAA season): brackets by seed with byes, the regular
season's schedule, the RPI, and the definitions."""

from collections import Counter
from datetime import date
from itertools import combinations

import numpy as np
import pytest

from footsim.competitions.bracket import (
    BYE,
    advanced,
    champion,
    first_round,
    matches_in,
    rounds_for,
    seed_order,
    sides,
)
from footsim.competitions.college import Game, ranked, regular_season, rpi
from footsim.defs.college import on
from footsim.defs.loader import load_definitions


def _play_out(entrants: int, better_wins: bool = True) -> tuple[dict[tuple[int, int], int],
                                                               list[tuple[int, int, int]]]:
    """Every match of a bracket played, the better (or the worse) seed winning; the matches."""
    winners: dict[tuple[int, int], int] = {}
    played = []
    for rnd in range(rounds_for(entrants)):
        for index in range(matches_in(entrants, rnd)):
            a, b = sides(entrants, rnd, index, winners)
            assert a is not None and b is not None
            if b == BYE:
                continue
            winners[(rnd, index)] = a if better_wins else b
            played.append((rnd, a, b))
    return winners, played


def test_seed_order_keeps_the_top_seeds_apart() -> None:
    assert seed_order(2) == [1, 2]
    assert seed_order(8) == [1, 8, 4, 5, 2, 7, 3, 6]
    order = seed_order(64)
    assert sorted(order) == list(range(1, 65))
    assert order.index(2) >= 32 > order.index(1)  # 1 and 2 in different halves
    with pytest.raises(ValueError):
        seed_order(48)


def test_the_ncaa_bracket_gives_the_top_sixteen_byes() -> None:
    pairs = first_round(48)
    assert len(pairs) == 32
    byes = sorted(a for a, b in pairs if b == BYE)
    assert byes == list(range(1, 17))
    played = sorted((a, b) for a, b in pairs if b != BYE)
    assert len(played) == 16 and (17, 48) in played and (32, 33) in played
    # Seed 1 meets the winner of 32 v 33 in the second round; 16 the winner of 17 v 48.
    assert advanced(48, 0, 0, {}) == 1
    second = {sides(48, 1, i, {(0, j): min(first_round(48)[j]) for j in range(32)})
              for i in range(16)}
    assert (1, 32) in second and (16, 17) in second
    assert rounds_for(48) == 6


def test_a_bracket_played_out_by_seed() -> None:
    winners, played = _play_out(48)
    assert champion(48, winners) == 1
    assert len(played) == 47  # every team but the champion loses once
    final = [m for m in played if m[0] == 5]
    assert final == [(5, 1, 2)]
    winners, _ = _play_out(48, better_wins=False)
    assert champion(48, winners) not in (None, 1)


@pytest.mark.parametrize("entrants, byes, first", [
    (6, [1, 2], [(3, 6), (4, 5)]),
    (8, [], [(1, 8), (2, 7), (3, 6), (4, 5)]),
    (4, [], [(1, 4), (2, 3)]),
    (10, list(range(1, 7)), [(7, 10), (8, 9)]),
])
def test_conference_tournament_shapes(entrants: int, byes: list[int],
                                      first: list[tuple[int, int]]) -> None:
    pairs = first_round(entrants)
    assert sorted(a for a, b in pairs if b == BYE) == byes
    assert sorted((a, b) for a, b in pairs if b != BYE) == first
    winners, played = _play_out(entrants)
    assert champion(entrants, winners) == 1
    assert len(played) == entrants - 1


def test_no_bracket_before_its_matches_are_decided() -> None:
    assert sides(8, 1, 0, {}) == (None, None)
    assert champion(8, {}) is None
    assert sides(6, 1, 0, {}) == (1, None)  # the top seed's bye, waiting for 4 v 5


SIZES = [13, 15, 8, 9, 9, 11, 12, 8, 7, 10, 11, 8, 13, 7, 6, 9, 8, 7, 10, 7, 6, 10, 9]  # 2026's
CONFERENCES = [list(range(1 + sum(SIZES[:k]), 1 + sum(SIZES[:k + 1])))
               for k in range(len(SIZES))]


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_the_regular_season(seed: int) -> None:
    days = regular_season(CONFERENCES, 17, 19, np.random.default_rng(seed))
    assert len(days) == 19
    conference_of = {t: c for c, teams in enumerate(CONFERENCES) for t in teams}
    games: Counter[int] = Counter()
    pairs: Counter[tuple[int, int]] = Counter()
    for day in days:
        playing = [t for g in day for t in g]
        assert len(playing) == len(set(playing))  # once a day at most
        for home, away in day:
            games[home] += 1
            games[away] += 1
            pairs[(min(home, away), max(home, away))] += 1
    assert max(pairs.values()) == 1  # nobody meets twice
    for teams in CONFERENCES:  # every conference a single round robin
        for a, b in combinations(teams, 2):
            assert pairs[(a, b)] == 1
    assert all(15 <= games[t] <= 17 for t in conference_of)
    assert sum(games[t] == 17 for t in conference_of) >= 0.9 * len(conference_of)
    # Conference games come last: a team's last game is in its conference.
    last: dict[int, tuple[int, int]] = {}
    for k, day in enumerate(days):
        for home, away in day:
            last[home], last[away] = (k, away), (k, home)
    assert all(conference_of[o] == conference_of[t] for t, (_, o) in last.items())
    assert regular_season(CONFERENCES, 17, 19, np.random.default_rng(seed)) == days


def test_the_rpi() -> None:
    # A beat B, B beat C, A and C drew: winning shares .75, .5, .25; opponents' (without the
    # games against the team) .5 each, and so their opponents'.
    games = [Game(1, 2, 1.0), Game(2, 3, 1.0), Game(1, 3, 0.5)]
    ratings = rpi(games, (0.25, 0.5, 0.25))
    assert ratings == pytest.approx({1: 0.5625, 2: 0.5, 3: 0.4375})
    assert ranked(ratings) == [1, 2, 3]
    # A strong schedule counts: two teams with one win each, against a strong and a weak side.
    games = [Game(10, 11, 1.0), Game(11, 12, 1.0), Game(11, 13, 1.0), Game(14, 15, 1.0),
             Game(16, 15, 1.0)]
    ratings = rpi(games, (0.25, 0.5, 0.25))
    assert ratings[10] > ratings[14]


def test_season_dates() -> None:
    start = date(2026, 7, 1)
    assert on("08-20", start) == date(2026, 8, 20)
    assert on("12-14", start) == date(2026, 12, 14)
    assert on("02-15", start) == date(2027, 2, 15)


def test_the_college_definitions() -> None:
    college = load_definitions().college
    teams = [t for c in college.conferences.values() for t in c.teams]
    assert 195 <= len(teams) <= 220 and 20 <= len(college.conferences) <= 25
    assert len({t.name for t in teams}) == len(teams)
    bids = sum(c.auto_bid for c in college.conferences.values())
    assert bids < college.rules.ncaa.teams == 48 and college.rules.ncaa.seeds == 16
    assert {t.tier for t in teams} == {1, 2, 3, 4, 5}
    powers = {t.school for t in teams if t.tier == 1}
    assert {"Indiana", "Wake Forest", "Maryland"} <= powers

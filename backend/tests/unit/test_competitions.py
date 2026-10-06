from collections import Counter
from datetime import date

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from footsim.competitions.calendars import shift_keep_weekday, shifted_calendar
from footsim.competitions.fixtures import round_robin
from footsim.competitions.playoffs import Entrant, legs_for, round_ties
from footsim.competitions.scheduling import league_round_dates, playoff_dates
from footsim.competitions.standings import Result, league_table
from footsim.defs.competitions import PointsRule, Tiebreaker
from footsim.defs.loader import load_definitions


@settings(max_examples=30, deadline=None)
@given(st.integers(min_value=2, max_value=24), st.integers(min_value=0, max_value=10_000))
def test_double_round_robin_meets_everyone_home_and_away(n: int, seed: int) -> None:
    rounds = round_robin(list(range(1, n + 1)), legs=2, rng=np.random.default_rng(seed))
    games = [g for rnd in rounds for g in rnd]
    assert len(games) == n * (n - 1)
    assert len(set(games)) == len(games)  # each ordered pairing exactly once
    for rnd in rounds:
        clubs = [c for g in rnd for c in g]
        assert len(clubs) == len(set(clubs))  # nobody plays twice in a round
    assert all(v == n - 1 for v in Counter(h for h, _ in games).values())


def _longest_venue_run(rounds: list[list[tuple[int, int]]], club: int) -> int:
    venues = [("H" if h == club else "A") for rnd in rounds for h, a in rnd if club in (h, a)]
    longest = run = 1
    for prev, cur in zip(venues, venues[1:], strict=False):
        run = run + 1 if cur == prev else 1
        longest = max(longest, run)
    return longest


@pytest.mark.parametrize("n", [20, 24])
def test_no_long_home_or_away_runs(n: int) -> None:
    rounds = round_robin(list(range(n)), legs=2, rng=np.random.default_rng(1))
    assert max(_longest_venue_run(rounds, c) for c in range(n)) <= 3


def test_league_dates_fit_the_real_calendar() -> None:
    defs = load_definitions()
    cal = defs.calendars["ENG-2026-27"]
    for key, rounds in (("ENG1", 38), ("ENG2", 46), ("ENG3", 46), ("ENG4", 46)):
        comp = cal.competitions[key]
        days = league_round_dates(comp, cal, rounds)
        assert len(days) == len(set(days)) == rounds
        assert days[0] >= comp.start and days[-1] <= comp.end
        assert all((b - a).days >= 3 for a, b in zip(days, days[1:], strict=False))
        if comp.pause_for_international_windows:
            assert not any(cal.in_international_window(d) for d in days)


def test_every_league_fits_its_own_calendar() -> None:
    """W2: each country's leagues are scheduled on its calendar (winter breaks included)."""
    from footsim.competitions.fixtures import round_robin as rr

    defs = load_definitions()
    for key, league in defs.leagues.items():
        cal = defs.calendars[league.calendar]
        comp = cal.competitions[key]
        rounds = len(rr(list(range(league.clubs)), league.format.legs, np.random.default_rng(0)))
        days = league_round_dates(comp, cal, rounds)
        assert len(days) == len(set(days)) == rounds, key
        assert days[0] >= comp.start and days[-1] <= comp.end, key
        assert not any(b.contains(d) for b in cal.blackout for d in days), key
        assert cal.season_start == defs.calendars["ENG-2026-27"].season_start, key


def test_playoff_dates_end_on_final_day() -> None:
    playoff = load_definitions().leagues["ENG2"].playoffs[0]
    dates = playoff_dates(date(2027, 5, 1), date(2027, 5, 29), playoff.rounds)
    assert [len(d) for d in dates] == [1, 2, 1]
    assert dates[-1] == [date(2027, 5, 29)]
    flat = [d for legs in dates for d in legs]
    assert flat == sorted(flat) and flat[0] > date(2027, 5, 1)


def test_table_orders_by_points_then_goal_difference() -> None:
    results = [Result(1, 2, 3, 0), Result(2, 3, 1, 0), Result(3, 1, 1, 1)]
    table = league_table([1, 2, 3], results, PointsRule(),
                         [Tiebreaker.POINTS, Tiebreaker.GOAL_DIFFERENCE])
    assert [r.club_id for r in table] == [1, 2, 3]
    assert table[0].points == 4 and table[0].goal_difference == 3


def test_head_to_head_decides_level_clubs() -> None:
    # 1 and 2 both finish on 6 points with goal difference +2; 2 beat 1.
    results = [Result(2, 1, 1, 0), Result(1, 3, 2, 0), Result(1, 4, 1, 0),
               Result(2, 3, 2, 0), Result(4, 2, 1, 0)]
    order = [Tiebreaker.POINTS, Tiebreaker.GOAL_DIFFERENCE, Tiebreaker.H2H_POINTS]
    table = league_table([1, 2, 3, 4], results, PointsRule(), order)
    top, second = table[0], table[1]
    assert (top.points, top.goal_difference) == (second.points, second.goal_difference)
    assert [r.club_id for r in table] == [2, 1, 4, 3]


def test_drawing_of_lots_is_deterministic() -> None:
    order = [Tiebreaker.POINTS, Tiebreaker.DRAWING_OF_LOTS]
    a = league_table([1, 2, 3, 4], [], PointsRule(), order, lots_seed=5)
    b = league_table([1, 2, 3, 4], [], PointsRule(), order, lots_seed=5)
    assert [r.club_id for r in a] == [r.club_id for r in b]


def test_championship_playoff_bracket() -> None:
    playoff = load_definitions().leagues["ENG2"].playoffs[0]
    ranks = {r: 100 + r for r in range(3, 9)}  # club id = 100 + league position
    eliminators = round_ties(playoff, 0, ranks, {})
    assert {(t.a.rank, t.b.rank) for t in eliminators} == {(5, 8), (6, 7)}
    # 8th and 6th win their eliminators: 3rd plays 8th, 4th plays 6th.
    winners = {"E1": Entrant(108, 8), "E2": Entrant(106, 6)}
    semis = {t.tie_id: t for t in round_ties(playoff, 1, ranks, winners)}
    assert (semis["SF1"].a.rank, semis["SF1"].b.rank) == (3, 8)
    assert (semis["SF2"].a.rank, semis["SF2"].b.rank) == (4, 6)
    legs = legs_for(semis["SF1"], playoff.rounds[1])
    assert [(leg.home, leg.leg) for leg in legs] == [(108, 1), (103, 2)]  # 3rd hosts leg 2
    final = round_ties(playoff, 2, ranks, {"SF1": Entrant(108, 8), "SF2": Entrant(104, 4)})
    assert legs_for(final[0], playoff.rounds[2])[0].neutral


def test_later_calendars_keep_weekdays() -> None:
    assert shift_keep_weekday(date(2026, 8, 22), 1).weekday() == date(2026, 8, 22).weekday()
    base = load_definitions().calendars["ENG-2026-27"]
    later = shifted_calendar(base, 3)
    assert later.season == "2029-30"
    assert later.competitions["ENG1"].start.weekday() == base.competitions["ENG1"].start.weekday()
    assert abs((later.competitions["ENG1"].start - date(2029, 8, 21)).days) <= 3

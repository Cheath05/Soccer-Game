"""Fast results (match/fast.py): one draw per match for the leagues not fully simulated. Their
scores follow the fast engine's on the same sheets, every goal has its scorer, every side plays
its 90 minutes with its substitutes, knockouts always find a winner, and a seed gives the same
match every time."""

import numpy as np
import pytest

from footsim.core.rng import derive_rng
from footsim.match.report import Decider, MatchReport
from footsim.match.synthetic import synthetic_squad
from footsim.match.teams import TeamSheet
from footsim.world.context import World, get_world


@pytest.fixture(scope="module")
def world() -> World:
    return get_world()


def _sheet(world: World, club_id: int, level: float) -> TeamSheet:
    squad = synthetic_squad(world.defs, club_id, level)
    return world.picker.pick(club_id, f"Club {club_id}", squad, world.defs.formations["4-3-3"])


def _goals(report: MatchReport, club_id: int) -> int:
    return sum(1 for e in report.events
               if e.club_id == club_id and e.type in ("goal", "penalty_goal", "own_goal"))


@pytest.mark.parametrize(("home_level", "away_level"), [(70.0, 70.0), (76.0, 64.0)])
def test_scores_follow_the_fast_engine(world: World, home_level: float,
                                       away_level: float) -> None:
    home, away = _sheet(world, 1, home_level), _sheet(world, 2, away_level)
    n = 4000
    quick = np.array([[r.home_goals, r.away_goals] for r in (
        world.quick.play(home, away, derive_rng(3, "q", k)) for k in range(n))])
    fast = np.array([[r.home_goals, r.away_goals] for r in (
        world.fast.play(home, away, derive_rng(3, "f", k)) for k in range(n))])
    # Each side's mean goals within about four standard errors of the difference (a side's goals
    # have a standard deviation of about 1.3, so 0.03 for 4,000 matches each).
    assert fast[:, 0].mean() == pytest.approx(quick[:, 0].mean(), abs=0.12)
    assert fast[:, 1].mean() == pytest.approx(quick[:, 1].mean(), abs=0.12)
    wins = (fast[:, 0] > fast[:, 1]).mean(), (quick[:, 0] > quick[:, 1]).mean()
    assert wins[0] == pytest.approx(wins[1], abs=0.04)


def test_a_fast_match_adds_up(world: World) -> None:
    home, away = _sheet(world, 1, 72.0), _sheet(world, 2, 68.0)
    for k in range(200):
        report = world.fast.play(home, away, derive_rng(5, "m", k))
        assert _goals(report, 1) == report.home_goals and _goals(report, 2) == report.away_goals
        assert not report.injuries and not report.fitness
        assert all(e.type in ("goal", "penalty_goal", "own_goal", "sub") for e in report.events)
        for sheet in (home, away):
            lines = [ln for ln in report.players.values() if ln.club_id == sheet.club_id]
            squad = {sp.player_id for sp in [*sheet.starters, *sheet.bench]}
            assert {ln.player_id for ln in lines} <= squad
            assert sum(ln.started for ln in lines) == 11
            # Eleven on the pitch for the whole match: the substitutes play the rest.
            assert sum(ln.minutes for ln in lines) == 11 * 90
            scored = sum(ln.goals for ln in lines)
            own = sum(1 for e in report.events if e.type == "own_goal" and e.club_id ==
                      sheet.club_id)
            assert scored + own == (report.home_goals if sheet is home else report.away_goals)
            assert all(3.5 <= ln.rating <= 10.0 for ln in lines)
        # The unused substitutes are named for their development credit.
        assert set(report.bench) >= {pid for pid, ln in report.players.items() if not ln.started}


def test_knockouts_find_a_winner(world: World) -> None:
    home, away = _sheet(world, 1, 70.0), _sheet(world, 2, 70.0)
    decider = Decider(extra_time=True, penalties=True, first_leg=(1, 1))
    extra = 0
    for k in range(300):
        report = world.fast.play(home, away, derive_rng(7, "ko", k), decider=decider)
        assert report.winner(decider) is not None
        extra += report.extra_time
        if report.extra_time:
            assert sum(ln.minutes for ln in report.players.values() if ln.club_id == 1) == 1320
    assert extra > 0


def test_a_seed_gives_the_same_match(world: World) -> None:
    home, away = _sheet(world, 1, 70.0), _sheet(world, 2, 69.0)
    first = world.fast.play(home, away, derive_rng(9, "same"))
    again = world.fast.play(home, away, derive_rng(9, "same"))
    assert first == again

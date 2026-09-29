"""The calibration probe must agree with the engine's own statistics."""

import numpy as np
import pytest

from footsim.core.rng import derive_rng
from footsim.match.engine.actions import cut_out
from footsim.match.engine.engine import MatchEngine
from footsim.match.engine.probe import aggregate, summarize
from footsim.match.engine.state import PassInfo
from footsim.match.synthetic import synthetic_sheet
from footsim.world.context import World, get_world


@pytest.fixture(scope="module")
def world() -> World:
    return get_world()


@pytest.fixture(scope="module")
def played(world: World) -> MatchEngine:
    home = synthetic_sheet(world.defs, world.picker, 1, 74)
    away = synthetic_sheet(world.defs, world.picker, 2, 71, formation="4-2-3-1")
    engine = MatchEngine(world.defs, home, away, derive_rng(5, "probe"), record=False)
    engine.run(max_ticks=18000)  # half an hour
    return engine


def test_log_matches_team_statistics(played: MatchEngine) -> None:
    summary = summarize(played)
    shots = [s for s in summary["shots"]]
    for t in (0, 1):
        team = summary["teams"][t]
        assert team["shots"] == sum(1 for s in shots if s["team"] == t)
        assert team["goals"] == played.score[t]
        passes = sum(1 for e in played.log if e.kind == "pass" and e.team == t
                     and e.data["kind"] != "clearance")
        assert team["passes"] == passes
    assert len(summary["goals"]) == sum(played.score)


def test_possessions_alternate_and_cover_the_match(played: MatchEngine) -> None:
    possessions = played.possessions
    assert len(possessions) > 20
    for before, after in zip(possessions, possessions[1:], strict=False):
        assert before.team != after.team
        assert before.end_t is not None and before.end_t <= after.start_t + 1e-6


def test_ball_in_play_is_part_of_the_match(played: MatchEngine) -> None:
    summary = summarize(played)
    assert 0 < summary["ball_in_play_min"] <= summary["duration_min"]
    agg = aggregate([summary])
    assert agg["matches"] == 1 and 0 <= agg["pass_accuracy"] <= 1


def test_interceptions_are_only_passes_cut_out(played: MatchEngine) -> None:
    summary = summarize(played)
    lost = [e for e in played.log if e.kind == "pass_result" and e.data["result"] != "complete"]
    for t in (0, 1):
        team = summary["teams"][t]
        won = [e for e in lost if e.team == 1 - t]  # the other side's passes that t took
        assert team["interceptions"] == sum(e.data["result"] == "intercepted" for e in won)
        assert team["recoveries"] == sum(e.data["result"] == "recovered" for e in won)
    # player lines count real interceptions only: no recoveries, no clearances
    assert sum(line.interceptions for line in played.lines.values()) == sum(
        summary["teams"][t]["interceptions"] for t in (0, 1))
    assert sum(summary["teams"][t]["recoveries"] for t in (0, 1)) > 0


def test_a_pass_is_cut_out_only_on_course_and_short_of_its_target(world: World) -> None:
    home = synthetic_sheet(world.defs, world.picker, 1, 70)
    away = synthetic_sheet(world.defs, world.picker, 2, 70)
    engine = MatchEngine(world.defs, home, away, derive_rng(1, "cut_out"), record=False)
    radius = world.defs.passing.target_area
    info = PassInfo(passer=0, receiver=5, target=(60.0, 30.0), lofted=False, kind="pass")
    engine.ball_v = np.array([12.0, 0.0])
    for ball, expected in (((45.0, 30.0), True),  # on its way
                           ((60.0 + 0.5 * radius, 30.0), True),  # arriving in the target area
                           ((60.0 + 2 * radius, 30.0), False),  # overhit: past the target
                           ((45.0, 30.0 + 2 * radius), False)):  # off target
        engine.ball = np.array(ball)
        assert cut_out(engine, info) is expected

"""The calibration probe must agree with the engine's own statistics."""

import pytest

from footsim.core.rng import derive_rng
from footsim.match.engine.engine import MatchEngine
from footsim.match.engine.probe import aggregate, summarize
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

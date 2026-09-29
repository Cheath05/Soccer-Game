"""Calibration batches: synthetic fixtures, paired A/B differences and bootstrap spreads."""

import math
from typing import Any

import pytest

from footsim.calibration.engine_batch import BASELINE, Arm, bootstrap_ci, make_tasks, paired_deltas
from footsim.core.rng import derive_rng
from footsim.match.engine.engine import MatchEngine
from footsim.match.engine.probe import summarize
from footsim.match.synthetic import synthetic_sheet
from footsim.world.context import World, get_world


def _result(index: int, arm: str, score: tuple[int, int], xg_for: float,
            focus: int = 0) -> dict[str, Any]:
    team = {"xg": 0.0, "shots": 10, "possession": 0.5, "ppda": 10.0, "high_regains": 5,
            "fast_break_shots": 1, "passes_completed": 400, "passes": 480, "distance_km": 110.0,
            "end_stamina": 0.8, "fouls": 10, "reds": 0}
    teams = [dict(team), dict(team)]
    teams[focus]["xg"] = xg_for
    return {"index": index, "arm": arm, "focus": focus, "score": list(score), "teams": teams}


def test_paired_deltas_compare_the_same_fixtures() -> None:
    results = [
        _result(0, "base", (1, 1), 1.0), _result(0, "press", (2, 1), 1.5),
        _result(1, "base", (0, 2), 0.5), _result(1, "press", (1, 2), 1.0),
        _result(2, "base", (1, 0), 1.2), _result(2, "press", (1, 0), 1.7),
        _result(3, "press", (5, 0), 3.0),  # no baseline for fixture 3: not paired
    ]
    deltas = paired_deltas(results, "base", "press")
    mean, half = deltas["xg_for"]
    assert mean == pytest.approx(0.5) and half == pytest.approx(0.0)  # identical shifts
    mean, half = deltas["goal_diff"]
    assert mean == pytest.approx(2 / 3)
    assert half == pytest.approx(1.96 * math.sqrt(1 / 3) / math.sqrt(3))
    assert deltas["win"][0] == pytest.approx(1 / 3)


def test_paired_deltas_use_the_focus_side() -> None:
    results = [_result(0, "base", (2, 0), 1.0, focus=1), _result(0, "arm", (1, 0), 2.0, focus=1)]
    deltas = paired_deltas(results, "base", "arm")
    assert deltas["goals_against"][0] == pytest.approx(-1.0)  # the away side conceded one fewer
    assert deltas["xg_for"][0] == pytest.approx(1.0)


@pytest.fixture(scope="module")
def world() -> World:
    return get_world()


def test_bootstrap_intervals_cover_every_metric(world: World) -> None:
    summaries = []
    for seed in (1, 2, 3):
        home = synthetic_sheet(world.defs, world.picker, 1, 74)
        away = synthetic_sheet(world.defs, world.picker, 2, 71)
        engine = MatchEngine(world.defs, home, away, derive_rng(seed, "ci"), record=False)
        engine.run(max_ticks=6000)  # ten minutes is plenty for the arithmetic
        summaries.append(summarize(engine))
    ci = bootstrap_ci(summaries, reps=50)
    assert "matches" not in ci and "goals_sd" not in ci
    assert ci["passes"] > 0 and ci["pass_accuracy"] >= 0
    assert bootstrap_ci(summaries, reps=50) == ci  # reports are reproducible
    assert bootstrap_ci(summaries[:1]) == {}


def test_equal_synthetic_sides_share_a_quality() -> None:
    arms = [BASELINE, Arm("press", {"pressing": "high"})]
    equal = make_tasks(20, 5, arms, None, quality=(58.0, 66.0), equal=True)
    unequal = make_tasks(20, 5, arms, None, quality=(58.0, 66.0))
    for task in equal:
        assert task.home_quality is not None and 58.0 <= task.home_quality <= 66.0
        assert task.away_quality == task.home_quality
    assert any(task.away_quality != task.home_quality for task in unequal)
    # the same draws either way, so a run without --equal is reproduced exactly
    assert [t.home_quality for t in equal] == [t.home_quality for t in unequal]
    # every arm replays each fixture with the same teams and seed
    for index in range(20):
        replays = {(t.seed, t.home, t.away, t.home_quality, t.away_quality)
                   for t in equal if t.index == index}
        assert len(replays) == 1

"""Calibration batches: synthetic fixtures, paired A/B differences and bootstrap spreads."""

import math
from typing import Any

import pytest
import yaml

from footsim.calibration.engine_batch import (
    BASELINE,
    TARGET_KINDS,
    TARGETS,
    Arm,
    bootstrap_ci,
    by_rating,
    compare,
    load_targets,
    make_tasks,
    paired_deltas,
)
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


def test_targets_are_tagged_by_kind() -> None:
    raw = yaml.safe_load(TARGETS.read_text("utf-8"))
    for section in ("ENG1", "EFL"):
        assert raw[section]["_exposure"]["ball_in_play_min"] > 0
    for section, targets in raw.items():
        for metric, target in targets.items():
            if metric != "_exposure":
                assert target.get("kind", "rate") in TARGET_KINDS, (section, metric)
    # A division's own section holds references only: never a behaviour, never a tuning target.
    assert all(t["kind"] == "reference" for t in raw["ENG4"].values())


def test_league_two_references_sit_on_top_of_the_efl() -> None:
    assert load_targets("ENG4")["throw_ins"]["kind"] == "reference"
    assert load_targets("ENG2")["throw_ins"]["kind"] == "volume"
    assert load_targets("ENG1")["_exposure"]["ball_in_play_min"] > 55


def test_volumes_are_judged_per_minute_of_ball_in_play() -> None:
    targets = {"_exposure": {"ball_in_play_min": 50.0},
               "passes": {"range": [850, 1000], "kind": "volume", "ref": "x"},
               "pass_accuracy": {"range": [0.80, 0.85], "ref": "y"},
               "throw_ins": {"range": [50, 62], "kind": "reference", "ref": "z"}}
    # 1,100 passes a match looks like plenty, but the range per minute of ball in play is
    # 850/50-1000/50 = 17-20, so 16 a minute is too slow despite the high count.
    agg = {"passes": 1100.0, "passes_per_bip_min": 16.0, "pass_accuracy": 0.82,
           "throw_ins": 40.0, "tackles": 30.0}
    sections = compare(agg, targets)
    (passes,) = sections["volume"]
    assert passes[0] == "passes" and passes[5] == "OFF" and passes[4] == "17.0–20.0"
    assert sections["rate"][0][4] == "ok"
    assert sections["reference"][0][0] == "throw_ins" and sections["reference"][0][4] == "OFF"
    assert [row[0] for row in sections["other"]] == ["tackles"]  # the rate isn't repeated


def test_results_group_by_starting_xi_rating() -> None:
    def team(passes: int, completed: int) -> dict[str, float]:
        return {"passes": passes, "passes_completed": completed, "goals": 1, "xg": 1.2,
                "interceptions": 10, "fouls": 11, "high_regains": 7}
    results = [{"xi_rating": [72.3, 64.9], "teams": [team(400, 340), team(300, 230)]},
               {"xi_rating": [71.0, 61.2], "teams": [team(420, 370), team(350, 270)]}]
    rows = by_rating(results)
    assert [r["xi_rating"] for r in rows] == ["60-65", "70-75"]
    assert [r["team_matches"] for r in rows] == [2, 2]
    assert rows[1]["pass_accuracy"] == pytest.approx(710 / 820)

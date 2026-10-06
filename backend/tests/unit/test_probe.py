"""The calibration probe must agree with the engine's own statistics."""

import numpy as np
import pytest

from footsim.core.rng import derive_rng
from footsim.match.engine.actions import cut_out
from footsim.match.engine.engine import MatchEngine
from footsim.match.engine.log import EngineEvent
from footsim.match.engine.probe import (
    BANDS,
    ENTRY_WAYS,
    FAILURES,
    SHAPE_METRICS,
    SHAPE_ZONES,
    ShapeSampler,
    _pass_outcomes,
    aggregate,
    reliability,
    summarize,
)
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
    assert not any(e.data["kind"] == "clearance" for e in lost if e.data["result"] == "intercepted")


def test_misplaced_passes_are_recovered(world: World) -> None:
    """Recoveries happen. Judged over three half-hours: one alone can be free of them."""
    total = 0
    for seed in (5, 6, 7):
        home = synthetic_sheet(world.defs, world.picker, 1, 74)
        away = synthetic_sheet(world.defs, world.picker, 2, 71, formation="4-2-3-1")
        engine = MatchEngine(world.defs, home, away, derive_rng(seed, "probe"), record=False)
        engine.run(max_ticks=18000)
        total += sum(team["recoveries"] for team in summarize(engine)["teams"])
    assert total > 0


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


def test_every_pass_gets_one_outcome(played: MatchEngine) -> None:
    # Each pass lands in exactly one band and either completes or fails once, so the probe's
    # pairing agrees with the engine's own pass counts.
    summary = summarize(played)
    outcomes = summary["pass_outcomes"]
    passes = sum(summary["teams"][t]["passes"] for t in (0, 1))
    completed = sum(summary["teams"][t]["passes_completed"] for t in (0, 1))
    assert sum(outcomes["bands"][b][0] for b in BANDS) == passes
    assert sum(outcomes["bands"][b][1] for b in BANDS) == completed
    assert sum(outcomes["failures"].values()) == passes - completed
    assert set(outcomes["failures"]) <= set(FAILURES)
    assert sum(outcomes["offsides"].get(k, 0) for k in ("open_play", "free_kick")) == sum(
        summary["teams"][t]["offsides"] for t in (0, 1))
    throw_ins = sum(1 for e in played.log if e.kind == "restart_taken"
                    and e.data["kind"] == "throw_in")
    assert outcomes["bands"]["throw"][0] == throw_ins  # long throws included


def _ev(t: float, event: str, team: int, player: int, **data: object) -> EngineEvent:
    return EngineEvent(t, event, team, player, 0.0, 0.0, dict(data))


def test_outcomes_are_attributed_to_the_right_cause() -> None:
    passing = {"kind": "pass", "length": 10.0, "estimate": 0.9}
    # A pass lost as a loose ball: the opponent carries it before the ball goes out.
    lost = _pass_outcomes([_ev(1.0, "pass", 0, 3, **passing), _ev(3.0, "carry", 1, 14),
                           _ev(9.0, "restart", 1, 14, kind="goal_kick")])
    assert lost["failures"] == {"loose": 1}
    # A heavy touch gathered by someone else, then a one-two back to the fumbler: not a
    # self re-gather.
    one_two = _pass_outcomes([
        _ev(1.0, "pass", 0, 3, **passing), _ev(2.0, "heavy_touch", 0, 7),
        _ev(2.5, "pass_result", 0, 3, result="complete", kind="pass", by=9),
        _ev(3.0, "pass", 0, 9, **passing),
        _ev(4.0, "pass_result", 0, 9, result="complete", kind="pass", by=7)])
    assert one_two["heavy_touches"] == [1, 0]
    # A long throw is played as a cross but counts as a throw-in.
    throw = _pass_outcomes([_ev(1.0, "pass", 0, 3, kind="cross", length=25.0, estimate=0.4,
                                restart="throw_in")])
    assert throw["bands"]["throw"][0] == 1 and throw["bands"]["cross"][0] == 0


def test_pass_metrics_are_reported(played: MatchEngine) -> None:
    result = aggregate([summarize(played)])
    for band in ("short", "medium", "long"):
        assert 0.0 <= result[f"pass_acc_{band}"] <= 1.0
        assert result[f"pass_time_{band}"] > 0
    assert result["pass_time_short"] < result["pass_time_long"]
    assert 0.0 < result["long_ball_share"] < 0.5
    assert result["passes_per_bip_min"] == pytest.approx(
        result["passes"] / result["ball_in_play_min"])
    assert 0.0 <= result["possession_shot_share"] <= 1.0
    rows = reliability([summarize(played)], min_passes=5)
    assert rows and all(0.0 <= r["completed"] <= 1.0 for r in rows)


def test_watching_the_shape_changes_nothing_and_sees_every_box_entry(world: World) -> None:
    """The shape sampler only reads the match: the same seed plays out identically with it,
    and it records one box entry for every possession that reached the box."""

    def play(watch: bool) -> tuple[MatchEngine, ShapeSampler]:
        home = synthetic_sheet(world.defs, world.picker, 1, 74)
        away = synthetic_sheet(world.defs, world.picker, 2, 71, formation="4-2-3-1")
        engine = MatchEngine(world.defs, home, away, derive_rng(5, "probe"), record=False)
        sampler = ShapeSampler()
        engine.run(max_ticks=9000, observe=sampler.observe if watch else None)
        return engine, sampler

    watched, sampler = play(True)
    plain, _ = play(False)
    assert watched.score == plain.score and np.array_equal(watched.pos, plain.pos)
    summary = summarize(watched, sampler)
    shape = summary["shape"]
    assert len(shape["entries"]) == sum(p.box for p in watched.possessions) > 0
    for zone in SHAPE_ZONES:
        assert set(SHAPE_METRICS) <= set(shape["zones"][zone])
    agg = aggregate([summary])
    middle = agg["shape_middle_behind_ball"]
    assert 0 <= middle <= 10 and agg["shape_middle_length"] > 0
    assert sum(agg[f"box_entry_by_{way}"] for way in ENTRY_WAYS) == pytest.approx(1.0)

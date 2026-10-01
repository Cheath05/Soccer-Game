"""Pass resolution: how readily an opponent near a pass takes it, how the receiver reads a
pass, and what happens to a heavy touch or a cross that lands clear."""

from dataclasses import replace
from typing import Any

import numpy as np
import pytest

from footsim.core.rng import derive_rng
from footsim.match.engine import actions, behaviours
from footsim.match.engine.engine import MatchEngine
from footsim.match.engine.state import PassInfo
from footsim.match.synthetic import synthetic_sheet
from footsim.world.context import World, get_world


@pytest.fixture(scope="module")
def world() -> World:
    return get_world()


class _Rolls:
    """The engine's generator, except that every plain roll comes up ``value``."""

    def __init__(self, rng: np.random.Generator, value: float) -> None:
        self.rng, self.value = rng, value

    def random(self) -> float:
        return self.value

    def __getattr__(self, name: str) -> Any:
        return getattr(self.rng, name)


def _opponent_takes_it(world: World, scale: float) -> bool:
    """One opponent at the very edge of reach of a pass, on a roll of 0.03: only the floor
    of his chance can be high enough."""
    home = synthetic_sheet(world.defs, world.picker, 1, 70)
    away = synthetic_sheet(world.defs, world.picker, 2, 70)
    engine = MatchEngine(world.defs, home, away, derive_rng(1, "floor"), record=False)
    engine.defs = replace(engine.defs, passing=engine.defs.passing.model_copy(
        update={"intercept_scale": scale}))
    passer, receiver, opponent = 5, 8, 16
    engine.pos[:] = (-50.0, -50.0)  # everyone else far away
    engine.pos[passer], engine.pos[receiver] = (30.0, 34.0), (60.0, 34.0)
    engine.prev_ball, engine.ball = np.array([40.0, 34.0]), np.array([41.0, 34.0])
    engine.pos[opponent] = (41.0, 34.0 + actions.CONTROL_RADIUS * 0.9999)
    engine.ball_v, engine.ball_z = np.array([15.0, 0.0]), 0.0
    engine.owner, engine.state = -1, "pass"
    engine.pass_info = PassInfo(passer, receiver, (60.0, 34.0), False, "pass", tried={passer})
    engine.rng = _Rolls(engine.rng, 0.03)  # type: ignore[assignment]
    actions.resolve_loose_or_pass(engine)
    return engine.owner == opponent


def test_intercept_scale_covers_the_last_chance(world: World) -> None:
    # A 5% floor at scale 1.0 beats the roll; at 0.5 the floor is 2.5% and doesn't.
    assert _opponent_takes_it(world, 1.0)
    assert not _opponent_takes_it(world, 0.5)


def _empty_engine(world: World, seed: int) -> MatchEngine:
    home = synthetic_sheet(world.defs, world.picker, 1, 70)
    away = synthetic_sheet(world.defs, world.picker, 2, 70)
    engine = MatchEngine(world.defs, home, away, derive_rng(seed, "reception"), record=False)
    engine.pos[:] = (-50.0, -50.0)  # everyone far away unless placed
    return engine


def test_the_receiver_reads_a_pass_after_his_read_delay(world: World) -> None:
    # He sets off for where the pass was meant to go, and follows the ball's real path only
    # once he has read it, sooner with better anticipation.
    engine = _empty_engine(world, 3)
    passer, receiver = 5, 8
    engine.pos[passer], engine.pos[receiver] = (30.0, 34.0), (50.0, 34.0)
    engine.ball, engine.owner = np.array([30.5, 34.0]), passer
    actions.start_pass(engine, passer, receiver, engine.to_att(0, 50.0, 34.0), False, "pass")
    info = engine.pass_info
    assert info is not None and info.intended is not None
    assert np.allclose(info.intended, (50.0, 34.0))
    assert np.allclose(engine.target[receiver], (50.0, 34.0))
    best, worst = world.defs.passing.control.read_delay
    assert best <= info.read_at - engine.t <= worst
    engine.ball_v = np.array([10.0, 6.0])  # the pass has gone astray
    assert np.allclose(behaviours._meet_ball(engine, receiver), (50.0, 34.0))
    engine.t = info.read_at + 0.01
    assert not np.allclose(behaviours._meet_ball(engine, receiver), (50.0, 34.0))


def test_a_receiver_stops_on_the_balls_line_instead_of_running_through_it(
        world: World) -> None:
    # A pass struck 3 m off line: once he has read it he gets across to its path and waits there
    # for it, rather than running through the line at full speed (30 Sep: safe short passes
    # failed twice as often as they should, receivers overrunning the ball).
    engine = _empty_engine(world, 7)
    passer, receiver = 5, 8
    engine.pos[passer], engine.pos[receiver] = (30.0, 34.0), (50.0, 34.0)
    engine.ball, engine.owner = np.array([30.5, 34.0]), passer
    actions.start_pass(engine, passer, receiver, engine.to_att(0, 50.0, 34.0), False, "pass")
    info = engine.pass_info
    assert info is not None
    off_line = np.array([50.0, 37.0]) - engine.ball
    engine.ball_v = off_line / np.linalg.norm(off_line) * float(np.linalg.norm(engine.ball_v))
    info.target = (50.0, 37.0)
    engine.rng = _Rolls(engine.rng, 0.0)  # type: ignore[assignment]  # every roll succeeds
    for _ in range(40):
        engine.step()
        if engine.owner == receiver:
            break
    assert engine.owner == receiver
    assert float(np.linalg.norm(engine.vel[receiver])) < 3.5  # braking onto the line


def test_a_heavy_touch_gets_away_from_the_player(world: World) -> None:
    # After a heavy touch he can't touch the ball again until his lockout ends, however close
    # it is: it's a contest, not a free second go.
    engine = _empty_engine(world, 4)
    c = 8
    engine.pos[c] = (40.0, 34.0)
    actions._heavy_touch(engine, c, PassInfo(5, c, (40.0, 34.0), False, "pass", tried={5}))
    engine.owner, engine.state = -1, "loose"
    engine.prev_ball = engine.ball = np.array([40.5, 34.0])  # still at his feet
    engine.ball_v, engine.ball_z = np.array([0.5, 0.0]), 0.0
    engine.rng = _Rolls(engine.rng, 0.0)  # type: ignore[assignment]  # every roll succeeds
    actions.resolve_loose_or_pass(engine)
    assert engine.owner != c
    engine.t = float(engine.touch_ready[c]) + 0.01
    actions.resolve_loose_or_pass(engine)
    assert engine.owner == c


def test_a_cross_that_lands_clear_can_still_be_completed(world: World) -> None:
    # Nobody attacks the ball where it lands: it runs loose, and a teammate gathering it in time
    # completes the cross, as with a ground pass that stops short.
    engine = _empty_engine(world, 5)
    info = PassInfo(5, 8, (95.0, 34.0), True, "cross", tried={5})
    engine.pass_info, engine.state = info, "pass"
    engine.ball, engine.ball_z = np.array([95.0, 34.0]), 1.0
    assert actions._aerial(engine, info)
    assert engine.stopped_pass is not None and engine.stopped_pass[0] is info
    before = engine.stats[0].passes_completed
    actions._take(engine, 9, None)
    assert engine.stats[0].passes_completed == before + 1


def test_a_passer_gathering_his_own_ball_completes_nothing(world: World) -> None:
    # He keeps the ball for his side, but a pass to himself isn't a completed pass, and it
    # can't make him the provider of his own goal.
    engine = _empty_engine(world, 6)
    info = PassInfo(5, 8, (40.0, 34.0), False, "pass", tried={5})
    engine.stopped_pass, engine.last_completed_pass = (info, engine.t), None
    before = engine.stats[0].passes_completed
    actions._take(engine, 5, None)
    assert engine.owner == 5
    assert engine.stats[0].passes_completed == before and engine.last_completed_pass is None


def test_the_honest_estimate_reads_the_balls_own_models(world: World) -> None:
    # Step 2.3c, work in progress (off by default): the estimate built from the ball's own
    # models gives a probability, and an opponent standing in the passing line lowers it.
    engine = _empty_engine(world, 7)
    passer, receiver = 5, 8
    engine.pos[passer], engine.pos[receiver] = (30.0, 34.0), (50.0, 34.0)

    def estimate() -> float:
        pts = engine.att_points(0, engine.pos)
        opps = engine.team_indices(1)
        ball = pts[passer]
        target = pts[[receiver]]
        length = np.array([float(np.hypot(*(target[0] - ball)))])
        return float(actions._estimate_success(
            engine, passer, 0, [receiver], ["pass"], target, length, np.array([False]), ball,
            opps, pts[opps], pts, 0.0)[0])

    clear = estimate()
    assert 0.02 <= clear <= 0.98
    engine.pos[16] = (40.0, 34.0)  # an opponent right in the line
    assert estimate() < clear


def _honest(engine: MatchEngine, passer: int, receiver: int, target: tuple[float, float],
            kind: str) -> float:
    pts = engine.att_points(0, engine.pos)
    opps = engine.team_indices(1)
    ball = pts[passer]
    aim = np.array([target])
    length = np.array([float(np.hypot(*(aim[0] - ball)))])
    return float(actions._estimate_success(
        engine, passer, 0, [receiver], [kind], aim, length, np.array([True]), ball, opps,
        pts[opps], pts, 0.0)[0])


def test_a_cross_is_anyones_who_gets_to_it(world: World) -> None:
    # 2.3c: _aerial lets any attacker within 3 m of where a cross drops win it, so a second
    # attacker in the box makes it likelier, and a defender there makes it less likely.
    engine = _empty_engine(world, 10)
    passer, receiver, other = 5, 8, 9
    engine.pos[passer], engine.pos[receiver] = (90.0, 6.0), (70.0, 55.0)  # he can't get there
    alone = _honest(engine, passer, receiver, (95.0, 30.0), "cross")
    engine.pos[other] = (94.0, 31.0)  # but a teammate is where it's going
    two = _honest(engine, passer, receiver, (95.0, 30.0), "cross")
    assert two > alone + 0.2
    engine.pos[13] = (94.5, 31.5)  # and now he's marked
    assert _honest(engine, passer, receiver, (95.0, 30.0), "cross") < two


def test_a_long_ball_is_whoevers_gets_to_where_it_drops(world: World) -> None:
    # 2.3c: a long ball's estimate follows it to where it drops (any of its error grid): a
    # defender next to the receiver contests it, one closer to it takes it.
    engine = _empty_engine(world, 11)
    passer, receiver = 5, 8
    engine.pos[passer], engine.pos[receiver] = (30.0, 34.0), (72.0, 34.0)
    free = _honest(engine, passer, receiver, (72.0, 34.0), "pass")
    engine.pos[16] = (74.0, 35.0)
    marked = _honest(engine, passer, receiver, (72.0, 34.0), "pass")
    assert 0.02 < marked < free
    engine.pos[16] = (66.0, 34.0)  # goal-side and nearer to where it drops on average
    assert _honest(engine, passer, receiver, (72.0, 34.0), "pass") < free


def test_a_ball_in_the_air_goes_astray_more_than_one_on_the_ground(world: World) -> None:
    # Round 5's long-ball errors (e2) are a lofted ball's; a calm ground pass keeps the
    # original, smaller ones (P7, 1 Oct: e2 on every pass mis-hit half of all 20 m passes).
    engine = _empty_engine(world, 8)
    ex = world.defs.passing.execution
    ground = actions.pass_error(engine, 0, 75.0, 0.0, 0.0, 30.0, False, 60.0, crowd=False)
    lofted = actions.pass_error(engine, 0, 75.0, 0.0, 0.0, 30.0, True, 60.0, crowd=False)
    assert lofted[0] - ground[0] == pytest.approx(ex.lofted + ex.lofted_per_metre * 15)
    assert lofted[1] - ground[1] == pytest.approx(ex.lofted_length_per_metre * 30)


def test_composure_decides_what_pressure_costs(world: World) -> None:
    engine = _empty_engine(world, 9)

    def spread(pressure: float, composure: float) -> float:
        return float(actions.pass_error(engine, 0, 75.0, pressure, 0.0, 20.0, False, composure,
                                        crowd=False)[0])

    assert spread(1.0, 35.0) > spread(1.0, 85.0)  # a nervous passer suffers more under it
    assert spread(0.0, 35.0) == pytest.approx(spread(0.0, 85.0))  # nobody near: no difference


def test_a_long_ball_risks_the_ball_where_it_lands_not_at_the_passers_feet(world: World) -> None:
    # 1 Oct: every pass was costed as if lost where it was played, so a long ball out of trouble
    # was never worth it (League Two sides played 3% long balls). Its failure is costed where it
    # comes down, far from our goal.
    from footsim.match.engine.behaviours import offside_line
    from footsim.match.engine.pitch import loss_cost, threat

    engine = _empty_engine(world, 10)
    passer, striker = 3, 9  # a defender and a forward of the home side
    engine.pos[passer], engine.pos[striker] = (25.0, 34.0), (70.0, 34.0)
    keeper, defender = engine.keeper(1), [int(i) for i in engine.team_indices(1)][3]
    assert keeper is not None
    engine.pos[keeper], engine.pos[defender] = (100.0, 34.0), (75.0, 20.0)  # he's onside
    engine.ball, engine.owner = np.array([25.5, 34.0]), passer
    team = 0
    pts = engine.att_points(team, engine.pos)
    opps = engine.team_indices(1)
    options = actions._pass_options(
        engine, passer, team, [striker], pts, engine.vel * engine.attack_dir[team],
        np.array([25.5, 34.0]), opps, pts[opps], 0.0, offside_line(pts[opps], 25.5), None)
    utility, _, option = next(o for o in options if o[2].receiver == striker)
    s = option.estimate
    role = 0.01 * engine.role[passer].on_ball.pass_risk * (
        float(threat(*option.target)) - float(threat(25.5, 34.0)))
    w = world.defs.passing.loss_where_lost  # how far the cost moves to where it's lost
    lost_at = w * np.array(option.target) + (1 - w) * np.array([25.5, 34.0])
    expected = s * (float(threat(*option.target)) + actions.RETAIN) \
        - (1 - s) * float(loss_cost(*lost_at)) + role
    at_feet = s * (float(threat(*option.target)) + actions.RETAIN) \
        - (1 - s) * float(loss_cost(25.5, 34.0)) + role
    assert option.lofted
    assert utility == pytest.approx(expected, abs=0.001)  # (plus the directness term)
    assert w > 0 and utility > at_feet + 0.002


def test_a_passer_sees_a_clear_offside_but_may_miss_a_marginal_one(world: World) -> None:
    # 1 Oct: the passer re-rolled whether he noticed an offside at every decision, so sooner
    # or later he played it (14 offsides a match once long balls came in). Now a receiver
    # offside by more than the passer's blind spot is never played to; one level-ish may be.
    from footsim.match.engine.behaviours import offside_line

    engine = _empty_engine(world, 11)
    passer, clear, marginal = 5, 9, 10
    engine.pos[passer] = (60.0, 34.0)
    keeper, defender = engine.keeper(1), [int(i) for i in engine.team_indices(1)][3]
    assert keeper is not None
    engine.pos[keeper], engine.pos[defender] = (100.0, 34.0), (80.0, 30.0)
    blind = world.defs.passing.offside_blind_spot * (1 - engine.a(passer, "decisions") / 100)
    engine.pos[clear] = (80.3 + blind + 1.0, 28.0)  # within a throw's reach too
    engine.pos[marginal] = (80.3 + blind / 2, 48.0)
    engine.ball, engine.owner = np.array([60.5, 34.0]), passer
    pts = engine.att_points(0, engine.pos)
    opps = engine.team_indices(1)
    assert offside_line(pts[opps], 60.5) == pytest.approx(80.0)

    def receivers(mode: str | None) -> set[int]:
        options = actions._pass_options(
            engine, passer, 0, [clear, marginal], pts, engine.vel * engine.attack_dir[0],
            np.array([60.5, 34.0]), opps, pts[opps], 0.0, 80.0, mode)
        return {o[2].receiver for o in options if o[1] == "pass"}

    assert receivers(None) == {marginal}
    assert receivers("throw") == {clear, marginal}  # no offside from a throw-in

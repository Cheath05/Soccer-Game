"""Attack against defence by rating (2.3f): a defender's own ratings decide how much he puts an
opponent off. Golden values can't show a response going the wrong way; these pin it."""

from dataclasses import replace

import numpy as np
import pytest

from footsim.core.rng import derive_rng
from footsim.domain.attributes import ATTR_INDEX
from footsim.match.engine import actions
from footsim.match.engine.engine import MatchEngine
from footsim.match.synthetic import synthetic_sheet
from footsim.world.context import World, get_world


@pytest.fixture(scope="module")
def world() -> World:
    return get_world()


def _engine(world: World) -> MatchEngine:
    home = synthetic_sheet(world.defs, world.picker, 1, 70)
    away = synthetic_sheet(world.defs, world.picker, 2, 70)
    engine = MatchEngine(world.defs, home, away, derive_rng(1, "defending"), record=False)
    engine.pos[:] = (-50.0, -50.0)  # everyone far away unless placed
    return engine


def _set(engine: MatchEngine, i: int, **values: float) -> None:
    for name, value in values.items():
        engine.attr[i, ATTR_INDEX[name]] = value


def test_a_better_marker_puts_a_receiver_off_more(world: World) -> None:
    engine = _engine(world)
    receiver, marker = 9, 14
    engine.pos[receiver], engine.pos[marker] = (60.0, 34.0), (59.0, 34.0)
    _set(engine, marker, marking=40)
    loose = actions._touch_pressure(engine, receiver)
    _set(engine, marker, marking=85)
    assert actions._touch_pressure(engine, receiver) > loose > 0


def test_a_better_defender_puts_a_shooter_off_more(world: World) -> None:
    engine = _engine(world)
    shooter, defender = 9, 14
    engine.pos[shooter], engine.pos[defender] = (90.0, 34.0), (91.5, 34.5)
    bx, by = engine.to_att(0, 90.0, 34.0)
    _set(engine, defender, def_positioning=40, standing_tackle=40)
    weak = actions.shot_pressure(engine, shooter, 0, bx, by)
    _set(engine, defender, def_positioning=88, standing_tackle=88)
    assert actions.shot_pressure(engine, shooter, 0, bx, by) > weak > 0


def test_a_carrier_expects_less_against_a_better_tackler(world: World) -> None:
    engine = _engine(world)
    carrier, defender = 9, 14
    engine.pos[carrier], engine.pos[defender] = (60.0, 34.0), (64.5, 34.0)
    engine.ball, engine.owner = np.array([60.0, 34.0]), carrier
    ball = np.array(engine.to_att(0, 60.0, 34.0))

    def best_carry() -> float:
        options = actions._carry_options(engine, carrier, 0, ball, 0.0)
        return max(u for u, kind, payload in options
                   if kind == "carry" and payload.target != (float(ball[0]), float(ball[1])))

    _set(engine, defender, standing_tackle=40, def_positioning=40, strength=40)
    easy = best_carry()
    _set(engine, defender, standing_tackle=90, def_positioning=90, strength=90)
    assert best_carry() < easy


def _keeper(engine: MatchEngine) -> int:
    keeper = engine.keeper(1)
    assert keeper is not None
    return keeper


def test_a_keeper_is_no_outfield_marker_shooter_pressure_or_blocker(world: World) -> None:
    """The keeper's part is the save and his own claims: he never counts as an outfield
    defender, read with outfield ratings he hasn't got."""
    engine = _engine(world)
    shooter, keeper = 9, _keeper(engine)
    engine.pos[shooter], engine.pos[keeper] = (92.0, 34.0), (94.0, 34.0)  # right in the way
    bx, by = engine.to_att(0, 92.0, 34.0)
    chance = actions.shot_chance(engine, shooter, 0, bx, by)
    assert chance.pressure == 0 and chance.blockers == 0 and chance.block == 0
    assert actions._touch_pressure(engine, shooter) == 0


def test_the_shooter_weighs_up_the_bodies_in_the_way_as_the_shot_plays_them(world: World) -> None:
    """One model for the shot and the choice to take it: a defender in the shot's line makes
    the chance smaller (in the cone) and blockable, for both."""
    engine = _engine(world)
    shooter, defender = 9, 14
    engine.pos[shooter] = (88.0, 34.0)
    bx, by = engine.to_att(0, 88.0, 34.0)
    clear = actions.shot_chance(engine, shooter, 0, bx, by)
    engine.pos[defender] = (94.0, 34.0)  # 6 m out, in the line, beyond pressure range
    blocked = actions.shot_chance(engine, shooter, 0, bx, by)
    assert clear.blockers == 0 and clear.block == 0
    assert blocked.blockers == 1 and 0 < blocked.block < 1
    assert blocked.pressure == clear.pressure == 0
    assert blocked.xg < clear.xg


def test_the_choice_to_shoot_sees_the_bodies_in_the_way(world: World) -> None:
    """decide weighs the shot up as start_shot will play it: a defender in the line, too far
    off to put the shooter off, still makes the shot worth less to him."""

    def shot_utility(blocked: bool) -> float:
        engine = _engine(world)
        assert engine.attack_dir[0] > 0
        shooter, defender = 9, 14
        engine.pos[shooter] = (94.0, 34.0)
        if blocked:
            engine.pos[defender] = (100.0, 34.0)  # 6 m out, in the line
        engine.ball, engine.owner = np.array([94.0, 34.0]), shooter
        engine.debug = True
        actions.decide(engine, shooter)
        assert engine.decision_debug is not None
        return float(next(o["utility"] for o in engine.decision_debug["options"]
                          if o["kind"] == "shot"))

    assert shot_utility(blocked=True) < shot_utility(blocked=False)


def test_a_keeper_in_his_way_is_no_tackler_to_a_carrier(world: World) -> None:
    """Keepers never challenge a carrier (duels.contest), so a carrier's options are the same
    with the keeper in front of him as without."""
    engine = _engine(world)
    carrier, keeper = 9, _keeper(engine)
    engine.pos[carrier] = (88.0, 34.0)
    engine.ball, engine.owner = np.array([88.0, 34.0]), carrier
    ball = np.array(engine.to_att(0, 88.0, 34.0))
    alone = actions._carry_options(engine, carrier, 0, ball, 0.0)
    engine.pos[keeper] = (92.5, 34.0)
    assert actions._carry_options(engine, carrier, 0, ball, 0.0) == alone


def test_the_pass_estimate_reads_markers_as_the_physics_does(world: World) -> None:
    """The passer's estimate of the receiver securing the ball (2.3c, behind its switch): a
    keeper near the target is no marker, and even a top marker on the target leaves a heavy
    touch some chance of being won back, so securing it is never less likely than the first
    touch alone."""
    engine = _engine(world)
    passer, receiver, marker, keeper = 5, 9, 14, _keeper(engine)
    engine.pos[passer], engine.pos[receiver] = (50.0, 34.0), (65.0, 34.0)
    engine.ball, engine.owner = np.array([50.0, 34.0]), passer

    def secure() -> float:
        pts = engine.att_points(0, engine.pos)
        opps = engine.team_indices(1)
        target = pts[[receiver]]
        length = np.linalg.norm(target - pts[passer], axis=1)
        parts = actions._estimate_parts(engine, passer, 0, [receiver], ["pass"], target, length,
                                        np.array([False]), pts[passer], opps, pts[opps], pts,
                                        0.0)
        return float(parts.secure[0])

    nobody = secure()
    engine.pos[keeper] = (65.5, 34.0)
    assert secure() == nobody
    engine.pos[keeper] = (-50.0, -50.0)
    engine.pos[marker] = (65.5, 34.0)
    _set(engine, marker, marking=100)
    marked = secure()
    estimate = engine.defs.passing.estimate.model_copy(update={"regather": (0.0, 0.0)})
    engine.defs = replace(engine.defs, passing=engine.defs.passing.model_copy(
        update={"estimate": estimate}))  # the first touch alone
    assert secure() <= marked < nobody


def test_a_defender_under_pressure_in_his_box_clears_first_time(world: World) -> None:
    """D6: in his own box with an attacker on him a defender often clears first time; with
    nobody near, or out of his danger zone, he never does (he controls it)."""
    engine = _engine(world)
    defender, attacker = 14, 9
    team = int(engine.team_of[defender])

    def clears(ball_att: tuple[float, float], attacker_att: tuple[float, float] | None) -> float:
        engine.ball[:] = engine.to_pitch(team, *ball_att)
        engine.pos[defender] = engine.ball
        engine.pos[attacker] = (engine.to_pitch(team, *attacker_att) if attacker_att
                                else (-50.0, -50.0))
        return sum(actions._clears_first_time(engine, defender) for _ in range(200)) / 200

    assert clears((8.0, 34.0), None) == 0.0                 # nobody near
    assert clears((60.0, 34.0), (60.5, 34.0)) == 0.0        # not his danger zone
    assert clears((8.0, 34.0), (8.5, 34.0)) > 0.5           # pressed in his own box
    assert 0.0 < clears((28.0, 34.0), (28.5, 34.0)) < clears((8.0, 34.0), (8.5, 34.0))


def test_a_counter_is_on_only_after_winning_it_against_an_unset_defence(world: World) -> None:
    """Phase E: a side that won the ball in open play in its own half is on a counter for the
    counter window, while fewer than ``counter_unset`` outfield opponents are goal-side of
    the ball; never from a restart, and not once the defence is set."""
    from footsim.match.engine.log import Possession

    engine = _engine(world)
    rules = world.defs.tactics.transition
    opps = engine.outfield_indices(1)
    engine.t = 100.0

    def place(goal_side: int) -> None:  # that many of them between the ball (40 m) and goal
        for n, k in enumerate(opps):
            x = 70.0 + n if n < goal_side else 20.0 + n
            engine.pos[k] = engine.to_pitch(0, x, 30.0)

    engine.possessions[:] = [Possession(0, 98.0, 30.0, "interception")]
    place(rules.counter_unset - 2)
    assert actions._countering(engine, 0, 40.0)
    place(rules.counter_unset + 1)
    assert not actions._countering(engine, 0, 40.0)               # the defence is set
    place(rules.counter_unset - 2)
    engine.t = 98.0 + rules.counter_window + 0.1
    assert not actions._countering(engine, 0, 40.0)               # too late
    engine.t = 100.0
    engine.possessions[:] = [Possession(0, 98.0, 30.0, "goal_kick")]
    assert not actions._countering(engine, 0, 40.0)               # not from a restart
    engine.possessions[:] = [Possession(0, 98.0, 70.0, "interception")]
    assert not actions._countering(engine, 0, 40.0)               # won in their half

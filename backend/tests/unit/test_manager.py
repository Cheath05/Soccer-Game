"""The in-match AI manager changes instructions in response to the game, never ability, and
leaves the user's side alone unless handed the job."""

import pytest

from footsim.core.rng import derive_rng
from footsim.match.engine.engine import MatchEngine
from footsim.match.synthetic import synthetic_sheet
from footsim.world.context import World, get_world


@pytest.fixture(scope="module")
def world() -> World:
    return get_world()


def _engine(world: World, seed: int = 7, *, ai_manager: tuple[bool, bool] = (True, True),
            home: dict[str, str] | None = None,
            away: dict[str, str] | None = None) -> MatchEngine:
    h = synthetic_sheet(world.defs, world.picker, 1, 75, instructions=home)
    a = synthetic_sheet(world.defs, world.picker, 2, 75, formation="4-2-3-1", instructions=away)
    return MatchEngine(world.defs, h, a, derive_rng(seed, "manager"), record=False,
                       ai_manager=ai_manager)


def _late(engine: MatchEngine, minute: int, score: tuple[int, int]) -> None:
    """Jump to ``minute`` of the second half with ``score``, then let the managers react."""
    engine.run(max_ticks=50)
    engine.clock.period = 2
    engine.clock.elapsed = (minute - 46) * 60.0
    engine.score = list(score)
    engine.run(max_ticks=20)


def test_a_side_behind_late_goes_for_it(world: World) -> None:
    engine = _engine(world)
    _late(engine, 85, (0, 1))
    home = engine.instructions[0]
    assert (home["mentality"], home["tempo"], home["passing"], home["pressing"]) == (
        "attacking", "fast", "direct", "high")
    assert any("push more players forward" in item["text"] for item in engine.feed)


def test_a_side_one_up_late_protects_its_lead(world: World) -> None:
    engine = _engine(world, away={"line": "high", "pressing": "high"})
    _late(engine, 85, (0, 1))
    away = engine.instructions[1]
    assert (away["mentality"], away["tempo"], away["pressing"], away["line"]) == (
        "defensive", "slow", "normal", "normal")


def test_a_comfortable_lead_is_managed_not_defended(world: World) -> None:
    engine = _engine(world, home={"mentality": "attacking", "pressing": "high"})
    _late(engine, 75, (3, 0))
    home = engine.instructions[0]
    assert (home["mentality"], home["tempo"], home["pressing"], home["line"]) == (
        "balanced", "slow", "normal", "normal")


def test_nothing_changes_before_the_late_stage(world: World) -> None:
    engine = _engine(world)
    before = [dict(i) for i in engine.instructions]
    _late(engine, 60, (0, 2))
    assert engine.instructions == before


def test_the_users_side_is_left_alone(world: World) -> None:
    engine = _engine(world, ai_manager=(False, True))
    before = dict(engine.instructions[0])
    _late(engine, 85, (0, 1))
    assert engine.instructions[0] == before
    assert engine.instructions[1]["tempo"] == "slow"  # the computer's side still manages


def test_handing_over_to_the_assistant(world: World) -> None:
    engine = _engine(world, ai_manager=(False, True))
    engine.set_instruction(0, "width", "wide")  # the user's own choice
    engine.set_ai_manager(0, True)
    assert engine.managers[0].plan["width"] == "wide"
    _late(engine, 85, (0, 1))
    assert engine.instructions[0]["mentality"] == "attacking"
    assert engine.instructions[0]["width"] == "wide"  # kept from the user's plan
    engine.set_instruction(0, "tempo", "slow")  # the user overrules: it becomes the plan
    assert engine.managers[0].plan["tempo"] == "slow"


def test_changes_are_logged_with_who_made_them(world: World) -> None:
    engine = _engine(world)
    engine.set_instruction(0, "width", "narrow")
    _late(engine, 85, (0, 1))
    changes = [(e.team, e.data["key"], e.data["by"]) for e in engine.log
               if e.kind == "instruction"]
    assert (0, "width", "user") in changes
    assert (0, "mentality", "manager") in changes


def test_reads_a_high_line_from_the_pitch(world: World) -> None:
    high = _engine(world, away={"line": "high"}, ai_manager=(True, False))
    usual = _engine(world, ai_manager=(True, False))
    for engine in (high, usual):
        engine.run(max_ticks=7200)  # past the ten-minute review: he needs enough looks first
    p = world.defs.tactics.manager
    assert high.managers[0].opponent_high_line(high.t, p)
    assert high.instructions[0]["passing"] == "direct"
    assert not usual.managers[0].opponent_high_line(usual.t, p)
    assert usual.instructions[0]["passing"] == "mixed"


def test_reads_a_high_press_from_the_pitch(world: World) -> None:
    pressed = _engine(world, away={"pressing": "high"}, ai_manager=(True, False))
    usual = _engine(world, ai_manager=(True, False))
    for engine in (pressed, usual):
        engine.run(max_ticks=15000)  # he judges the press only near his own goal: give it time
    p = world.defs.tactics.manager
    assert pressed.managers[0].opponent_pressing(pressed.t, p)
    assert pressed.instructions[0]["passing"] == "direct"
    assert not usual.managers[0].opponent_pressing(usual.t, p)


def test_a_side_down_to_ten_steps_back(world: World) -> None:
    engine = _engine(world, away={"pressing": "high"})
    engine.run(max_ticks=100)
    victim = next(i for i in engine.team_indices(1) if i != engine.keeper(1))
    engine.send_off(int(victim), "violent conduct")
    engine.run(max_ticks=5)
    away = engine.instructions[1]
    assert (away["mentality"], away["pressing"]) == ("defensive", "normal")
    assert any("sit deeper with a man down" in item["text"] for item in engine.feed)


def test_commentary_follows_the_direction_of_the_change(world: World) -> None:
    engine = _engine(world)
    _late(engine, 85, (0, 1))
    assert any("slow the game down" in item["text"] for item in engine.feed)
    engine.score = [1, 1]  # an equaliser: the side that was ahead goes back to its plan
    engine.run(max_ticks=5)
    assert engine.instructions[1]["tempo"] == "normal"
    assert any("go back to their usual mentality, defensive line and tempo" in item["text"]
               for item in engine.feed)


def test_same_seed_same_decisions(world: World) -> None:
    first, second = _engine(world), _engine(world)
    for engine in (first, second):
        _late(engine, 83, (1, 1))
        engine.score = [1, 2]
        engine.run(max_ticks=1500)
    assert first.instructions == second.instructions
    assert first.pos.tobytes() == second.pos.tobytes()
    assert [(f["t"], f["text"]) for f in first.feed] == [(f["t"], f["text"]) for f in second.feed]

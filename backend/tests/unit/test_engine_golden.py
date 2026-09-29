"""Golden-seed regression for the agent match engine.

Fixed teams and seeds must keep producing exactly these results, so any change in how a
match plays out is a deliberate decision. When a change is intended, update the expected
values here in the same commit and say why in its message.

History: added time from the stoppage ledger replaced the random draw (match clock work);
restarts became a state machine with real setup time (restart work); one-challenge duels,
pass execution error and first touch, and instruction costs from tactics.yaml (calibration
and tactical guardrails).
"""

from dataclasses import asdict

import numpy as np
import pytest

from footsim.core.rng import derive_rng
from footsim.match.engine.engine import MatchEngine
from footsim.match.synthetic import synthetic_sheet
from footsim.world.context import World, get_world


@pytest.fixture(scope="module")
def world() -> World:
    return get_world()


def _engine(world: World, seed: int) -> MatchEngine:
    home = synthetic_sheet(world.defs, world.picker, 1, 75)
    away = synthetic_sheet(world.defs, world.picker, 2, 72, formation="4-4-2")
    return MatchEngine(world.defs, home, away, derive_rng(seed, "golden"), record=False)


def test_first_twenty_minutes(world: World) -> None:
    engine = _engine(world, 11)
    engine.run(max_ticks=12000)
    home, away = (asdict(s) for s in engine.stats)
    keys = ("shots", "passes", "passes_completed", "fouls")
    assert engine.score == [0, 0]
    assert tuple(home[k] for k in keys) == (0, 116, 101, 0)
    assert tuple(away[k] for k in keys) == (4, 80, 69, 3)
    assert round(home["xg"], 4) == 0.0 and round(away["xg"], 4) == 0.2575
    assert round(float(np.abs(engine.pos).sum()), 2) == 1598.91


def test_full_match(world: World) -> None:
    engine = _engine(world, 12)
    engine.run()
    report = engine.report()
    assert (report.home_goals, report.away_goals) == (1, 1)
    assert engine.tick_count == 58802
    home, away = asdict(report.home_stats), asdict(report.away_stats)
    keys = ("shots", "shots_on_target", "passes", "fouls")
    assert tuple(home[k] for k in keys) == (19, 3, 405, 7)
    assert tuple(away[k] for k in keys) == (6, 2, 619, 5)
    assert (home["xg"], away["xg"]) == (1.02, 0.36)

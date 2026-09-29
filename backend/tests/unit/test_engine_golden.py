"""Golden-seed regression for the agent match engine.

Fixed teams and seeds must keep producing exactly these results, so any change in how a
match plays out is a deliberate decision. When a change is intended, update the expected
values here in the same commit and say why in its message.

Each platform pins its own values. The Mac (arm64) and Linux (x86-64) builds of NumPy and
the maths libraries round a few operations differently, and a match amplifies the smallest
difference into a different game; on one platform results never vary (see
test_engine_determinism.py). A platform without values skips these tests, and the skip
reason (`pytest -rs`) prints its values, ready to paste in. A behaviour change re-captures
every platform it can and removes the values it can't re-capture.

History: added time from the stoppage ledger replaced the random draw (match clock work);
restarts became a state machine with real setup time (restart work); one-challenge duels,
pass execution error and first touch, and instruction costs from tactics.yaml (calibration
and tactical guardrails); computer-controlled sides' in-match managers (tactical guardrails);
values pinned per platform once a Linux run showed the Mac's values don't carry over.
"""

import platform
import sys
from dataclasses import asdict
from typing import Any

import numpy as np
import pytest

from footsim.core.rng import derive_rng
from footsim.match.engine.engine import MatchEngine
from footsim.match.synthetic import synthetic_sheet
from footsim.world.context import World, get_world

PLATFORM = f"{sys.platform}-{platform.machine()}"

# Seed 11, first 20 minutes. Home and away: shots, passes, passes completed, fouls.
FIRST_TWENTY: dict[str, dict[str, Any]] = {
    "darwin-arm64": {"score": (0, 0), "home": (0, 117, 103, 1), "away": (7, 61, 49, 1),
                     "xg": (0.0, 0.3453), "abs_pos": 1139.74},
    "linux-x86_64": {"score": (0, 0), "home": (3, 123, 109, 0), "away": (4, 84, 75, 1),
                     "xg": (0.0449, 0.1745), "abs_pos": 1991.28},
}

# Seed 12, full match. Home and away: shots, shots on target, passes, fouls.
FULL_MATCH: dict[str, dict[str, Any]] = {
    "darwin-arm64": {"score": (0, 0), "ticks": 58202, "home": (18, 2, 433, 5),
                     "away": (12, 4, 532, 9), "xg": (1.03, 0.55)},
    "linux-x86_64": {"score": (0, 1), "ticks": 58202, "home": (15, 3, 420, 6),
                     "away": (10, 3, 544, 3), "xg": (0.76, 0.67)},
}


@pytest.fixture(scope="module")
def world() -> World:
    return get_world()


def _engine(world: World, seed: int) -> MatchEngine:
    home = synthetic_sheet(world.defs, world.picker, 1, 75)
    away = synthetic_sheet(world.defs, world.picker, 2, 72, formation="4-4-2")
    return MatchEngine(world.defs, home, away, derive_rng(seed, "golden"), record=False)


def _check(golden: dict[str, dict[str, Any]], actual: dict[str, Any]) -> None:
    expected = golden.get(PLATFORM)
    if expected is None:
        pytest.skip(f"no golden values for {PLATFORM}; here they are {{{PLATFORM!r}: {actual!r}}}")
    assert actual == expected


def test_first_twenty_minutes(world: World) -> None:
    engine = _engine(world, 11)
    engine.run(max_ticks=12000)
    home, away = (asdict(s) for s in engine.stats)
    keys = ("shots", "passes", "passes_completed", "fouls")
    _check(FIRST_TWENTY, {
        "score": tuple(engine.score),
        "home": tuple(home[k] for k in keys), "away": tuple(away[k] for k in keys),
        "xg": (round(home["xg"], 4), round(away["xg"], 4)),
        "abs_pos": round(float(np.abs(engine.pos).sum()), 2),
    })


def test_full_match(world: World) -> None:
    engine = _engine(world, 12)
    engine.run()
    report = engine.report()
    home, away = asdict(report.home_stats), asdict(report.away_stats)
    keys = ("shots", "shots_on_target", "passes", "fouls")
    _check(FULL_MATCH, {
        "score": (report.home_goals, report.away_goals), "ticks": engine.tick_count,
        "home": tuple(home[k] for k in keys), "away": tuple(away[k] for k in keys),
        "xg": (home["xg"], away["xg"]),
    })

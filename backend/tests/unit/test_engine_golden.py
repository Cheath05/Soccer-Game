"""Golden-seed regression for the agent match engine.

Fixed teams and seeds must keep producing exactly these results, so any change in how a
match plays out is a deliberate decision. When a change is intended, record the new values
in the same commit and say why in its message.

Each platform pins its own values in engine_golden.json. The Mac (arm64) and Linux (x86-64)
builds of NumPy and the maths libraries round a few operations differently, and a match
amplifies the smallest difference into a different game; on one platform results never vary
(see test_engine_determinism.py). A platform without values skips these tests.

To record this platform's values: `FOOTSIM_UPDATE_GOLDEN=1 uv run pytest
tests/unit/test_engine_golden.py`, then commit engine_golden.json. After a behaviour change,
also delete the values of any platform you couldn't re-record.

History: added time from the stoppage ledger replaced the random draw (match clock work);
restarts became a state machine with real setup time (restart work); one-challenge duels,
pass execution error and first touch, and instruction costs from tactics.yaml (calibration
and tactical guardrails); computer-controlled sides' in-match managers (tactical guardrails);
values pinned per platform once a Linux run showed the Mac's values don't carry over; home
advantage from the referee and the crowd (Step 2.1, recorded on Linux only); saved shots placed
within the keeper's reach, and the keeper going for them (Step 2.5, Linux only);
synthetic players' attributes fitted to real players' (recorded on the Mac only);
forward runners easing off to stop on their mark (Step 2.3, Mac only); a substitute no
longer inheriting the outgoing player's duel engagements, and a restart's taker chosen again
if he goes off (quick fix 0c, Mac only).
"""

import json
import os
import platform
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from footsim.core.rng import derive_rng
from footsim.match.engine.engine import MatchEngine
from footsim.match.synthetic import synthetic_sheet
from footsim.world.context import World, get_world

GOLDEN_FILE = Path(__file__).with_name("engine_golden.json")
PLATFORM = f"{sys.platform}-{platform.machine()}"
UPDATE = os.environ.get("FOOTSIM_UPDATE_GOLDEN") == "1"


@pytest.fixture(scope="module")
def world() -> World:
    return get_world()


def _engine(world: World, seed: int) -> MatchEngine:
    home = synthetic_sheet(world.defs, world.picker, 1, 75)
    away = synthetic_sheet(world.defs, world.picker, 2, 72, formation="4-4-2")
    return MatchEngine(world.defs, home, away, derive_rng(seed, "golden"), record=False)


def _check(case: str, values: dict[str, Any]) -> None:
    actual = json.loads(json.dumps(values))  # tuples become lists, as they're stored
    golden: dict[str, dict[str, Any]] = json.loads(GOLDEN_FILE.read_text("utf-8"))
    if UPDATE:
        golden.setdefault(PLATFORM, {})[case] = actual
        GOLDEN_FILE.write_text(json.dumps(golden, indent=1, sort_keys=True) + "\n", "utf-8")
        return
    expected = golden.get(PLATFORM, {}).get(case)
    if expected is None:
        pytest.skip(f"no golden values for {PLATFORM}: record them with FOOTSIM_UPDATE_GOLDEN=1")
    assert actual == expected


def test_first_twenty_minutes(world: World) -> None:
    """Seed 11, first 20 minutes. Home and away: shots, passes, passes completed, fouls."""
    engine = _engine(world, 11)
    engine.run(max_ticks=12000)
    home, away = (asdict(s) for s in engine.stats)
    keys = ("shots", "passes", "passes_completed", "fouls")
    _check("first_twenty", {
        "score": engine.score,
        "home": [home[k] for k in keys], "away": [away[k] for k in keys],
        "xg": [round(home["xg"], 4), round(away["xg"], 4)],
        "abs_pos": round(float(np.abs(engine.pos).sum()), 2),
    })


def test_full_match(world: World) -> None:
    """Seed 12, full match. Home and away: shots, shots on target, passes, fouls."""
    engine = _engine(world, 12)
    engine.run()
    report = engine.report()
    home, away = asdict(report.home_stats), asdict(report.away_stats)
    keys = ("shots", "shots_on_target", "passes", "fouls")
    _check("full_match", {
        "score": [report.home_goals, report.away_goals], "ticks": engine.tick_count,
        "home": [home[k] for k in keys], "away": [away[k] for k in keys],
        "xg": [home["xg"], away["xg"]],
    })

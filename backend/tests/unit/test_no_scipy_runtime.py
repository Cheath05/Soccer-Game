"""The game runs without SciPy, which has no iOS build.

``uv run pytest`` can't show this on its own, because the dev group installs SciPy. So a fresh
interpreter blocks every ``scipy`` import first, then loads the API and plays part of an
agent-engine match.
"""

import os
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"

SCRIPT = """
import sys

for name in ("scipy", "scipy.optimize", "scipy.special", "scipy.linalg", "scipy.sparse",
             "scipy.stats", "scipy.spatial", "scipy.interpolate", "scipy.integrate",
             "scipy.signal", "scipy.ndimage", "scipy.fft"):
    sys.modules[name] = None  # any later ``import scipy...`` raises ImportError

import footsim.api.app  # noqa: F401
from footsim.core.rng import derive_rng
from footsim.match.engine.engine import MatchEngine
from footsim.match.synthetic import synthetic_sheet
from footsim.world.context import get_world

world = get_world()
home = synthetic_sheet(world.defs, world.picker, 1, 70)
away = synthetic_sheet(world.defs, world.picker, 2, 70, formation="4-2-3-1")
engine = MatchEngine(world.defs, home, away, derive_rng(3, "no-scipy"), record=False)
engine.run(max_ticks=3000)
engine.set_formation(0, "4-4-2")  # the engine's own use of the assignment solver
engine.run(max_ticks=600)
assert engine.tick_count == 3600, engine.tick_count

loaded = sorted(m for m, mod in sys.modules.items()
                if (m == "scipy" or m.startswith("scipy.")) and mod is not None)
assert not loaded, loaded
print("PLAYED", engine.tick_count, sum(s.passes for s in engine.stats))
"""


def test_api_imports_and_a_match_plays_without_scipy() -> None:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(SRC), env.get("PYTHONPATH", "")]))
    result = subprocess.run([sys.executable, "-c", SCRIPT], capture_output=True, text=True,
                            env=env, timeout=300, check=False)
    assert result.returncode == 0, result.stderr[-4000:]
    played, ticks, passes = result.stdout.split()[-3:]
    assert played == "PLAYED" and int(ticks) == 3600
    assert int(passes) > 0

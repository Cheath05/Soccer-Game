---
name: repro-match
description: Reproduce a footsim agent-engine match deterministically and inspect it at a given match-clock time. It covers synthetic teams by seed, a calibration-batch fixture, or a fixture from a copy of a save, and exposes the event log, positions, targets, possession and restart state. Use for bug reports like "at 62:14 the left winger teleports" or to explain a calibration anomaly.
---

# Reproducing and inspecting a match

The engine is deterministic: the same team sheets, seed and commands give the same match, tick for tick. Run the snippets from `backend/` with `uv run --frozen python - <<'EOF' … EOF`.

## 1. Build the match

**Synthetic teams** (fast, no data files needed):

```python
from footsim.world.context import get_world
from footsim.match.synthetic import synthetic_sheet
from footsim.match.engine.engine import MatchEngine
from footsim.core.rng import derive_rng

w = get_world()
home = synthetic_sheet(w.defs, w.picker, 1, 78)                 # club id, average quality
away = synthetic_sheet(w.defs, w.picker, 2, 78, formation="4-2-3-1",
                       instructions={"pressing": "high"})
eng = MatchEngine(w.defs, home, away, derive_rng(SEED, "repro"), record=False)
```

**A calibration-batch fixture:** the same tasks as `footsim calibrate-engine`. For N fixtures × A arms, task index = fixture × A + arm.

```python
from footsim.calibration import engine_batch as eb
from footsim.core.paths import data_dir
world = data_dir() / "worlds" / "base-2026-27.sqlite"
eb._init(str(world))
clubs = eb.division_clubs(world, "ENG1")
tasks = eb.make_tasks(200, SEED, [eb.BASELINE], clubs)          # same --n/--seed/arms as the run
t = tasks[INDEX]
home = eb._sheet(t.home, None, t.home_quality)
away = eb._sheet(t.away, None, t.away_quality)
(home if t.focus == 0 else away).instructions.update(t.arm.instructions)
eng = MatchEngine(eb._WORLD.defs, home, away, derive_rng(t.seed, "calibrate", t.index), record=False)
```

**A fixture from the user's save.** Work on a copy, never the real file. Copy the `-wal` and `-shm` files too.

```python
import shutil, tempfile
from datetime import date
from pathlib import Path
from sqlalchemy import create_engine, select
from footsim.persistence.schema import fixture
from footsim.world.meta import read_meta
from footsim.world.career import agent_match

src = Path("/Users/alexbenton/Developer/Soccer-Game/saves/slot_1/autosave.sqlite")
tmp = Path(tempfile.mkdtemp(dir="/private/tmp")) / src.name
for suffix in ("", "-wal", "-shm"):
    if Path(f"{src}{suffix}").exists():
        shutil.copy(f"{src}{suffix}", f"{tmp}{suffix}")
with create_engine(f"sqlite:///{tmp}").connect() as conn:
    meta = read_meta(conn)
    fx = conn.execute(select(fixture).where(fixture.c.id == FIXTURE_ID)).one()
    eng = agent_match(conn, w, meta, fx, date.fromisoformat(fx.date), record=False)
```

Squads, fitness and suspensions come from the save's current state. A match that was already played therefore won't replay exactly from a later save, until replay records exist (plan section P). A watched match's commands (`formation`, `instruction`, `sub`) live only in the LiveSession's in-memory log for now.

## 2. Go to a clock time

```python
from footsim.match.engine.clock import PERIOD_START_MINUTE   # {1: 0, 2: 45, 3: 90, 4: 105}

def goto(eng, period: int, mmss: str) -> None:
    m, s = (int(v) for v in mmss.split(":"))
    target = (m - PERIOD_START_MINUTE[period]) * 60 + s
    while not eng.finished and (eng.clock.period < period or
                                (eng.clock.period == period and eng.clock.elapsed < target)):
        eng.step()

goto(eng, 2, "62:14")          # headless matches play straight through half-time
print(eng.clock.display(), eng.clock.label(), eng.score)
```

## 3. Inspect

- **State per tick:**
  - `eng.pos`, `eng.vel` and `eng.target`: (22, 2) arrays in metres. Indices 0–10 are home, 11–21 away.
  - `eng.urgent` (sprinting) and `eng.running` (making a forward run).
  - `eng.owner` (−1 when nobody has the ball) and `eng.state` (`dead`, `owned`, `pass`, `loose` or `shot`).
  - `eng.restart`, `eng.pass_info` and `eng.shot_info`.
- **Who is who:** `eng.players[i].player.short_name`, `eng.slot[i]`, `eng.position[i]`, `eng.role[i].key` and `eng.group[i]`.
- **Attacking frame:** `eng.to_att(team, x, y)` gives coordinates where that team attacks towards x = 105.
- **Event log:** `eng.log` is a list of `EngineEvent(t, kind, team, player, x, y, data)`. The kinds are listed in `match/engine/log.py`. `eng.possessions` lists `Possession`s with their source, start_x, final_third, box and shots.
- **Metrics:** `from footsim.match.engine.probe import summarize; summarize(eng)`. The same numbers feed the calibration report.
- **Teleports:** step one tick at a time and flag `np.linalg.norm(eng.pos - before, axis=1) > 1.1 * eng.max_speed * 0.1`.

Look at the events just before the moment, not only the moment itself. Most bugs are in the decision or the positioning that led to it.

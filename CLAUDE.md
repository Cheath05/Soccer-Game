# footsim

A local, single-player football (soccer) manager simulator. The core is a Python simulation (FastAPI API, SQLite saves) with a React match viewer on top. The user's matches run on an agent-based engine that simulates all 22 players at 10 Hz; the rest of the world runs on a fast statistical engine.

## Where things are

- **The real checkout is `/Users/alexbenton/Developer/Soccer-Game`.** The `Soccer-Game/` folder inside it is an unrelated empty clone of `main`: never work in it or stage it.
- **Branch:** `phase-1-match-believability`, where the match believability work happens. `main` has only the initial commit.
- **Plans:**
  - `docs/plans/match-believability.md` is the approved design (sections A–V).
  - `docs/plans/recovery-and-continuation.md` sets the current order of work.
  - `docs/plans/progress.md` is the checklist: resume from the first unticked item.
- **Design:** `docs/design.md`, plus ADRs in `docs/adr/`.
- **Backend** (`backend/src/footsim/`):
  - `match/engine/`: the agent engine (`engine`, `actions`, `behaviours`, `duels`, `restarts`, `set_pieces`, `clock`, `probe`, `log`);
  - `match/quick.py`: the fast engine;
  - `match/live/session.py`: LiveSession, which turns playback time into simulation time;
  - `api/`: REST and the live WebSocket;
  - `world/`: career, season and results;
  - `persistence/`: saves and migrations;
  - `calibration/engine_batch.py`: the calibration harness.
- **Config:** YAML under `data/config/`, validated by the Pydantic models in `backend/src/footsim/defs/`.
  - Match parameters are in `data/config/match/*.yaml`.
  - Real-football targets are in `data/config/calibration/match_targets.yaml`.
- **Frontend** (`frontend/src/`): the match viewer is in `match-viewer/`, the screens in `pages/`.
- **Never committed:** `data/raw` (EA FC data, which is EA's IP), `data/worlds`, `saves/` and `reports/`.

## Commands

- `just lint` runs ruff and strict mypy.
- `cd backend && uv run pytest` runs the tests.
- `cd frontend && npm run build` builds the viewer.
- `just calibrate-engine --n 200 --division ENG1` runs a calibration batch (see the `calibrate-engine` skill).
- The user's game runs on :8000. Automated browser checks use a throwaway server on :8765 with `FOOTSIM_SAVES_DIR` set to a temporary folder (see the `run-footsim` skill).

## Rules

- **Commit and push at the end of every sub-step.** Stage explicit paths, and tick `docs/plans/progress.md` in the same commit.
- **Determinism.** The engine never reads wall-clock time, and all randomness goes through `eng.rng` (from `core/rng.derive_rng`). Playback speed never changes a result.
- **Tactics change behaviour, never ability.** They change positions, timing, choices, risk, effort and fatigue. Every upside has a cost that plays out in the simulation. Effects live in `data/config/match/tactics.yaml`.
- **Tunable numbers live in YAML, not code.**
- **No teleports.** Players move only through their targets, except in flagged resets (kickoffs).
- **Golden values** in `backend/tests/unit/test_engine_golden.py` change only in the commit that intends the behaviour change, with a History note explaining it.
- **Calibration.** A tuning decision needs at least 200 paired fixtures on a fixed seed, read with CIs; phase acceptance needs 1,000. Run one heavy batch at a time.
- **Never touch the user's saves** (`saves/slot_1` is their Grimsby career). Tests and browser checks use temporary save folders.
- **Project agents:**
  - `engine-calibrator` runs batches in the background;
  - `match-investigator` reproduces a match and explains a behaviour;
  - `engine-reviewer` checks a diff against these rules before each commit.

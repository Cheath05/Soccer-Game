# footsim

A local, single-player football (soccer) manager simulator. The core is a Python simulation (FastAPI API, SQLite saves) with a React match viewer on top. The user's matches run on an agent-based engine that simulates all 22 players at 10 Hz; the rest of the world runs on a fast statistical engine.

## Where things are

- **The real checkout is `/Users/alexbenton/Developer/Soccer-Game`.** The `Soccer-Game/` folder inside it is an unrelated empty clone of `main`: never work in it or stage it.
- **Branch:** `phase-1-match-believability`, where the match believability work happens. `main` has only the initial commit.
- **Plans:**
  - `docs/plans/match-believability.md` is the approved design (sections A–V).
  - `docs/plans/continuation-plan.md` (approved 30 Sep) sets the order of work from Step 2.3 on and holds the **calibration principles**. It supersedes `recovery-and-continuation.md` from that point.
  - `docs/plans/progress.md` is the checklist: start from its **Continuation checkpoint** section, then the first unticked item.
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
- `footsim calibrate-engine --n 200 --division ENG1` runs a calibration batch.
  - Run it from the measurement worktree `.worktrees/measure`, pinned to a commit, never from the checkout being edited (see the `calibrate-engine` skill).
  - Don't run other heavy work alongside a batch.
    - This Mac has only 4 performance cores and 8 GB of RAM, and its swap was nearly full on 29 Sep.
    - Test suites, browser runs and agents simulating matches can double a batch's time.
    - Light work (editing, static review) is fine.
- The user's game runs on :8000. Automated browser checks use a throwaway server on :8765 with `FOOTSIM_SAVES_DIR` set to a temporary folder (see the `run-footsim` skill).
- **Never run `just e2e` without a :8765 URL** until quick fix 0 in `progress.md` lands. Its default URL is the user's :8000 game, and starting a career there overwrites save slot 1, the Grimsby career.

## Rules

- **Every major completed change is its own checkpoint.** A major change is any meaningful behaviour change or finished sub-step.
  - Commit and push it before starting the next one. Never keep several major changes in one uncommitted tree.
  - Deliberately unfinished work goes into a clearly labelled WIP commit, never only into the working tree.
  - The repo must stay runnable at every checkpoint, so the user can pull and play-test.
  - Stage explicit paths, and update `docs/plans/progress.md` in the same commit.
- **At each checkpoint, `progress.md` records:**
  - the exact commit and branch;
  - what was completed;
  - which tests and measurements passed;
  - what failed or remains;
  - the exact next task;
  - any running or required calibration command;
  - which server to play-test on (:8000 or :8765).
- **Calibration principles** (full text in `docs/plans/continuation-plan.md`):
  - **One engine for every league.** No league-specific mechanics or engine paths. League quality comes from player ratings first, then team and tactical context, then a small, bounded, measured league-environment parameter.
  - **Targets:** rates and rating responses. League aggregates are validation references only.
  - **Conflicts:** when a target conflicts with believable mechanics, flag it; never patch it with an exception.
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

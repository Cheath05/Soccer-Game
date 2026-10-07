# Phase P: simulation performance (a late phase: planned here, not implemented)

**Status: planned only.** Written on 6 Oct, from a read-only study of the code. Nothing here gets built before its place in the roadmap ("Where it goes" below).

On the production VM (Proxmox, i5-9500T, 4 vCPUs), sim-to-date holds one core at 100% while the other three sit idle. The sims finish correctly, but more slowly than on the M3 MacBook Air. That speed is acceptable for now: the game systems come first.

**Rules for when this is done:**
- **No loss of quality.** The simulation stays as detailed as it is. There are no shortcuts by league or for speed, and the same engines stay authoritative.
- **The same results.** A seed must give the same career, sequentially or optimised, on the same machine:
  - fixtures, tables, cups and promotions;
  - injuries, bans and statistics;
  - development and saves.
- **Measured first, measured after.** No change is claimed faster without before-and-after numbers.
- **Any machine.** Nothing is tuned to exactly four cores. Footsim must still work on one core.
- **Production stays as it is:** ports, Tailscale Serve, the systemd services and the update timer (`deploy/README.md`).

## 1. How sim-to-date runs today

### The steps

`api/sim.py:_run` is one daemon thread, one job at a time. It loops on `world/career.py:sim_step` while holding `session.lock`. Each step is **one SQLite write transaction** (`session.write()`; WAL, `synchronous=NORMAL`; one SQLAlchemy Engine with a pool, so reads such as the viewer's polling use other connections).
- If the user has a match today, `sim_step` plays it with `play_user_instant`. That's the **agent engine** (`MatchEngine.run()` headless), about 6.6 s a match on the M3, with `behaviours.update_targets` taking about half of it (`continuation-plan.md`).
- Otherwise it calls `advance()`, which runs day by day until the user's next match day, the season's end or `until`.
- **So one step can span many days** (a summer break, a run of weeks between matches) in a single transaction, and cancelling waits for it to end.
- **Autosave** follows every user match, under the lock (`api/session.py:autosave`, `persistence/saves.py`): an online `sqlite3.backup` of a 12–22 MB save, `PRAGMA integrity_check`, fsync, `os.replace` and a sha256.

### Each day (`career.advance`)

1. **`_play_day`:** the day's AI fixtures, **in fixture-id order, one after another in a Python loop**. Each goes through `play_fixture`:
   - **`squads.team_sheet`, twice.**
     - `load_squad` runs 3 queries, plus 1 for the tactic and 1 for the club name.
     - `LineupPicker.pick` then runs an N×11 Python scoring loop (`slot_rating`, with a linear `list.index` in `role_index`) and `linear_sum_assignment`.
   - **`world.quick.play`:** the fast engine. It's minute-by-minute scalar Python: 4 random draws per side per minute, and a stamina loop over 22 players.
   - **`results.record_result`:** about 45 statements per match. That's one fixture UPDATE, bulk inserts of events and player lines, then one `player_state` UPDATE per player and per injury, issued one at a time.
   - **Measured:** 5,242 league matches in 71 s with `footsim sim-season`, about 13.5 ms each with the database work (`progress.md`, W2).
2. **`season.after_day`:**
   - `cups.progress_cups`, every day;
   - on the 1st of each month, `develop_players`. It's numpy over every player (about 18–26k), but it selects minutes played with a correlated `SUM` over `player_match JOIN fixture`, a table that grows by about 28 rows a match without limit. Measured at 0.7–1 s a month;
   - league finalisation and play-off checks: two count queries per league per day.
3. **`results.daily_recovery`:** two global `player_state` UPDATEs.
4. **`meta.write_meta`:** 6 DELETEs and 6 INSERTs on `game_meta`, every day.

### At the season's end

`season.rollover` runs:
- promotion and relegation;
- `lifecycle.season_turnover`: retirements, youth intake and squad trimming, each with a full-table player query;
- contract renewals;
- `refresh_ai_tactics`: `load_squad` plus `best_formation` (3 × `pick`) for every club;
- the next season's fixtures.

### Why it uses one core

- Everything above runs on one thread, in Python and SQLite. numpy vectorises only inside individual calculations.
- The CPU-bound work is Python bytecode, so the GIL means threads wouldn't help.

### What makes concurrency possible later (checked in the code)

- **Randomness never depends on processing order.** Every draw has its own generator from `core/rng.derive_rng(seed, *parts)` (keyed with blake2b):
  - a match: `("match", fixture_id)`, or `("live-match", fixture_id)` for the user's;
  - development: by date;
  - retirements: by date; the youth intake: by date and club;
  - renewals: by contract; cup draws and drawing lots: by competition and round.
- **Same-day fixtures touch disjoint clubs and players:**
  - a match reads and writes only its two clubs' `player_state`, `tactic` and attributes;
  - every player has one active contract, and transfers don't exist yet.
- **Days depend on each other:** today's results change tomorrow's condition, injuries and bans.
- **Gap: nothing asserts that a club plays at most once a day.** `cups._free_day` can fail to find a date and leave a clash, though `test_cups_season` checks the spacing.
- **Write order matters for identical saves:** `match_event` ids autoincrement, so rows must be written in fixture-id order.
- **No wall clock in the simulation:** `datetime.now` appears only in save timestamps.

### Existing pieces to reuse

- **`calibration/engine_batch.py:run_tasks`:**
  - a `ProcessPoolExecutor` with the spawn method, and an initializer that loads the world and opens the database read-only (`?immutable=1`);
  - frozen task dataclasses, each seeded with its own `derive_rng`;
  - results returned as plain data, and written only by the parent;
  - `cpu_count() - 1` workers by default, running inline when one is asked for.
- **Timing:** `cli.py:_sim_season` holds the only timer (`perf_counter` per season).
- **Budgets** (`design.md` §35): a quick match ≤ 5 ms, a normal day ≤ 250 ms, a season rollover ≤ 60 s for five countries; an agent match ≤ 8 s (Phase D's gate).

## 2. P1: profile first

`footsim bench` runs on a copy of the base world with a fixed seed, never a user's saves. For each scenario it records:
- wall clock, CPU%, peak RSS and matches played;
- time split between the agent engine, the quick engine, `team_sheet`, `record_result`, `after_day` (`develop_players` and `progress_cups` apart), `daily_recovery` and `write_meta`, autosave, and `rollover`;
- SQL statements issued, through a SQLAlchemy event hook in bench mode only.

**Scenarios:**
1. One agent-engine match, headless, with `update_targets`' share.
2. One quick match, split into team sheets, the match and recording.
3. One busy matchday, with every league playing.
4. Sim-to-date for a week, a month and a whole season, with a user club and without (`sim-season`).
5. One rollover.

**Tools:**
- `cProfile` and `pyinstrument` for call trees;
- `time.perf_counter` sections in the bench harness only. The engine stays free of wall-clock reads, by the determinism rule.

**Machines:** the M3 and the VM. The baseline goes in `docs/calibration/performance-baseline.md` before anything changes.

**Decision rule:** the largest measured share goes first. The likeliest candidate is the user's own matches: about 6.6 s each on the agent engine, roughly once a week, against about 13.5 ms per AI match. That's a hypothesis to measure, not a result.

## 3. P2: single-core improvements (low risk, each behaviour-neutral)

- **D-pre (vectorising `update_targets`):** already planned in Phase D. It keeps the golden values identical and targets ≤ 1.5 s, and it speeds up both live and instant matches. It stays in Phase D as a gate: do it when the engine work nears the 8 s budget.
- **Team sheets:** attributes and positions change only monthly (development) and at the season's end. Reuse them within a day or a month, and rebuild only the parts that depend on state (condition, injuries, bans). Remove the linear `role_index` lookups from the scoring loop.
- **`record_result`:** batch the per-player and per-injury UPDATEs (`executemany`, or one `CASE` statement per match).
- **`write_meta`:** upsert only the keys that changed.
- **`develop_players`:** a running minutes total per player for the 12-month window, instead of a correlated `SUM` over all of `player_match`.
- **`progress_cups`:** skip cups and calendars with nothing due today (partly done).
- **`refresh_ai_tactics`:** reuse each club's loaded squad at rollover.
- **Smaller sim steps:** commit (and allow cancelling) after each day, instead of one transaction for many days. P3 needs this anyway.

Each change is measured before and after with `footsim bench`, and keeps the career result hash identical (see Validation).

## 4. P3: multi-core, only if P1 and P2's measurements show it pays

**What can run at the same time:**
- one day's AI fixtures, with each other;
- the user's agent-engine match, with that day's AI fixtures (disjoint clubs; randomness keyed by fixture).

**What can't:**
- different days;
- `after_day` and `rollover`;
- any database write;
- autosave.

**The design, reusing the `engine_batch` pattern:**
1. **The parent prepares each day.**
   - The sim thread commits the previous day first. Workers can't see the parent's uncommitted transaction, which is what multi-day steps hold today.
   - Then either the parent builds the team sheets and passes them pickled, or workers build them from a snapshot committed at the day's start. Bench decides: pickling cost against the cost of building the sheets.
2. **Workers only compute.** A persistent pool (spawn; the world loaded once in the initializer) runs `quick.play`, or the agent engine for the user's match. Each uses `derive_rng(seed, "match" | "live-match", fixture_id)` exactly as now, and returns the `MatchReport`.
3. **The parent records every report in fixture-id order,** inside its transaction, so rows and autoincrement ids are identical to a sequential run. Then it runs `after_day`.
4. **Each day is checked first:** if a club appears twice that day, the day runs sequentially.

**Workers:**
- the count is `FOOTSIM_SIM_WORKERS` (a setting or env var; production can set it in `~/.config/footsim/deploy.env`);
- the default is conservative, `min(4, os.cpu_count() - 1)`, and capped by measured memory per worker;
- `≤ 1` means inline: exactly today's code path.

**Failures:** a worker that crashes or times out sends its day back to a sequential run. Nothing was written yet, so that's safe. The pool is restarted and the event logged.

**Memory:** each worker holds the world definitions and numpy. Measure the RSS per worker on the VM before choosing defaults.

**Is it worth it?**
- **AI matches:** at about 13.5 ms each, per-day parallelism only pays if the pickling and process overhead per fixture is well below the match itself. Busy days carry tens to 100+ fixtures across 19 leagues. Bench measures this.
- **The user's match:** overlapping it with that day's AI matches in a worker is cheaper to build and likelier to pay.
- **Threads:** no gain for this CPU-bound Python, because of the GIL.

## 5. Validation (before any optimisation is switched on)

- **A career-level determinism test.** This is new: today only single matches are tested for determinism.
  - Run the same seed and world for N days twice: sequentially, and with the optimisation or the workers on.
  - Compare the fixture results, a hash of `player_state`, league tables, cup ties, injuries and bans, development and `game_meta`.
  - It must be identical on the same machine. Mac and Linux already differ in the last float bits, which is why golden values are pinned per platform.
- **Keep passing:**
  - `test_engine_golden.py` and `test_engine_determinism.py`;
  - `test_cups_season.py` and `test_lifecycle_season.py` (whole seasons);
  - `test_sim_to_date.py` (stops on the date, cancelling, the user's matches played and autosaved).
- **Add:**
  - cancelling mid-step;
  - a worker failure falling back with an identical result;
  - a day with a double-booked club running sequentially;
  - stopping and resuming from the autosave giving the same state.
- **Performance:** bench before and after every change, on the M3 and the VM, with the numbers recorded in `docs/calibration/performance-baseline.md` and `progress.md`.

## 6. Rollout

- **One change per checkpoint,** each committed with its bench numbers and the career hash test passing.
- **Execution changes go behind a setting:** `FOOTSIM_SIM_WORKERS` defaults to 1, and is raised only after the equality tests pass on both machines.
- **Regression watch:** bench numbers at each checkpoint; the career hash in the test suite.
- **Fallback:** setting the workers back to 1 restores sequential running at once. No migration is needed, since the saves are identical.

## 7. Expected impact (all to be confirmed by measurement)

- **Likely large:**
  - D-pre (`update_targets` is measured at half the agent engine's time);
  - overlapping the user's match with the day's AI matches;
  - cheaper team sheets and database writes, if bench shows them dominating the quick-match cost.
- **Likely moderate:**
  - multi-process AI matches per day (overhead-bound at about 13.5 ms a match);
  - development's minutes total, which grows with a career's length.
- **Likely small:** `write_meta`, `daily_recovery` and the per-day checks, unless bench shows otherwise.

## Where it goes in the roadmap

Phase P comes **after** these, in order (`progress.md`, "The approved order (1 Oct)", with the user's 6 Oct additions):
1. the engine work still needed for believable matches: D6, then Phase E. D-pre stays in Phase D as its own gate, per the 8 s budget;
2. W3 finances and W4 transfers;
3. the user's play-test gate;
4. W5 academies, W6 European competitions, W7 other continental competitions, W8 international football;
5. integration and polish of those systems.

It's late on purpose. Transfers, Europe and international football change what a simulated day does (more fixtures, transfer-window processing, new tables), so profiling earlier would measure a workload that's about to change.

**Allowed before then, as observation only:** at engine checkpoints, record the timings that already exist (an agent match's seconds against the 8 s budget; `footsim sim-season`'s time), so regressions show up.

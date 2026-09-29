# Handoff: cloud session → local session (29 Sep)

While the local session was at its usage limit, a cloud session (claude.ai/code, Linux) carried on from 8a5d319 on branch `claude/eloquent-ramanujan-ho29ch`. This file says how to bring that work in, check it on the Mac, and carry on with the plan. `progress.md` stays the checklist; this file explains the cloud part of it.

## 1. Bring the cloud work in

```bash
cd /Users/alexbenton/Developer/Soccer-Game
git switch phase-1-match-believability
git fetch origin
git merge --ff-only origin/claude/eloquent-ramanujan-ho29ch
git push
```

- The cloud branch is `phase-1-match-believability` plus its own commits. It can push only there.
- If `--ff-only` refuses, something was committed locally after 8a5d319. Merge instead (`git merge origin/claude/eloquent-ramanujan-ho29ch`), and never rebase or force-push.
- No dependencies changed, but `cd backend && uv sync --frozen --group dev --group data` does no harm.

## 2. Check it on the Mac (about 10 minutes)

1. **Record the Mac's golden values.** The only follow-up the cloud work needs.
   - Golden values are now kept per platform in `backend/tests/unit/engine_golden.json`, and only Linux values are in it. The cloud changed behaviour and couldn't record the Mac's.
   - Until they're recorded, the two golden tests skip on the Mac.
   ```bash
   cd backend && FOOTSIM_UPDATE_GOLDEN=1 uv run pytest tests/unit/test_engine_golden.py
   git add tests/unit/engine_golden.json && git commit -m "Record the Mac's golden values" && git push
   ```
2. **Lint and the full suite:** `just lint`, then `cd backend && uv run pytest`.
   - The six integration tests that need the built world skipped in the cloud, so they run here for the first time since these changes (`test_api_flow`, `test_clubs`, `test_live_safety`).
   - If a test fails because it expects one match's exact outcome, that's the platform difference, not a bug. Make the test judge over a few seeds, as `test_reads_a_high_press_from_the_pitch` now does; don't hunt for a seed that happens to pass.
3. **Time one match (budget 8 s).** The cloud machine takes about 17.8 s per match, so it couldn't check this.
   ```bash
   cd backend && PYTHONPATH=src uv run python -c "import time; from footsim.core.rng import derive_rng; from footsim.match.engine.engine import MatchEngine; from footsim.match.synthetic import synthetic_sheet; from footsim.world.context import get_world; w=get_world(); e=MatchEngine(w.defs, synthetic_sheet(w.defs,w.picker,1,75), synthetic_sheet(w.defs,w.picker,2,72,formation='4-4-2'), derive_rng(12,'golden'), record=False); t=time.perf_counter(); e.run(); print(round(time.perf_counter()-t,1),'s')"
   ```
4. `cd frontend && npm run build`. The cloud didn't touch the frontend, so this is only a sanity check.

## 3. What the cloud changed

| Commit | Step | Change | Behaviour |
|---|---|---|---|
| 94d5de3 | tooling | Golden values per platform. `calibrate-engine --quality LOW-HIGH --equal` makes equal synthetic sides, the cloud's stand-in for Grimsby | unchanged |
| dd38365 | 2.2 | Interceptions separated from recoveries (Opta's definitions); clearances no longer credited as interceptions; the probe reports `recoveries`; PPDA no longer counts recoveries | unchanged |
| 44bcb81 | 2.1 | Home advantage from the referee (foul and card bias) and the crowd (away decision noise and pass error under pressure), in `home_advantage.yaml`, split evenly between the sides. **Values provisional.** New metrics `home_goal_diff` and `away_card_gap`. Golden values moved to JSON | changed |
| 63a27d0 | 2.5 | Saved shots are placed within the keeper's dive (the same random draw, remapped). A keeper with no shot on target in reach is beaten, and he keeps going for the shot until it resolves | changed |
| 39af248 | 2.1 | `engine-reviewer` fix: no referee bias on the defender's own tactical-foul decision | changed |
| 3112110 | 2.2 | An opponent collecting a clearance makes a recovery, not an interception | unchanged |
| 046b242 | 2.3 | `passing.yaml` `intercept_scale`: scales the in-flight interception chance and the passer's lane estimate together. 1.0 is the old model | unchanged |

Later cloud commits, if any, are listed at the top of `progress.md`.

## 4. Findings to know before carrying on

- **Platforms.** The Mac and Linux round some floating-point operations differently, so the same seed plays a different match on each (same NumPy and SciPy; it isn't SIMD). Averages agree; single matches don't. Tests must never depend on one match's chaotic outcome.
- **Interceptions (2.2 → 2.3). This contradicts the plan's assumption.**
  - The counting fix changed little: 82 interceptions, 4.5 recoveries and 5 clearances a match (real interceptions: 14–26).
  - The Step 2.3 diagnostic (six 64 v 64 matches):
    - 59 high regains a match (real ~14), 86% of them from build-up passes by CMs, FBs, DMs and CBs, 15–30 m long and played 20–40 m from their own goal.
    - Passers' estimates are honest: passes estimated at 0.8–0.9 complete 90%.
    - Opponents cut out about 8% of all passes, against about 2% in real football.
  - So the leak is physics, not decisions. The model turns failed passes into interceptions where real football has misplaced balls and balls out of play. That also explains too few throw-ins (12 v 32–42), too much ball in play (68 v 54–60 min) and too high a pass accuracy (87%; the EFL is 74–81%).
  - The plan had left throw-ins and ball in play for Phase D. This suggests they respond to Step 2.3's calibration: lower `intercept_scale`, then raise pass execution error until accuracy and throw-ins land.
- **Home advantage** must be fitted after 2.3. It acts through pass error and decision noise, so a change to the passing physics moves it.
- **The AI manager still reads a press correctly with home advantage on:** 15 of 15 high presses spotted, and 1 of 18 false alarms (20 seeds, 25-minute reads).
- **Fixed:** `duels._counter_on` read `eng.possessions` (rule 7). It and `gain_possession` now read `eng.possession_start`, simulation state set at the same moment, so behaviour is unchanged.

## 5. Carry on with the plan

In this order. Each sub-step ends as `progress.md` says (reviewer, lint and tests, golden values, tick, commit and push).

1. **Step 1.3, C1: read where it stands (what the last local session was doing when it hit the limit). Don't tune yet.**
   - **First look for reports you already have.** The last local session ran the C1 A/B batches on Grimsby while it built the club pages. Check `reports/engine/` for `ENG4-n200-ab` reports from 29 Sep, before running anything new.
   - Then read the cloud's C1 report and verdict, `docs/calibration/20260929T195539-synthetic-n200-q58-66-equal-ab.md`. **It fails section S:** aggressive +1.07 goal difference; direct alone +0.91; fast, press and high line too costly. Much of direct play's edge comes from the opponent's leaky build-up, so do Step 2.3 before tuning any tactic costs.
   - Its setup: equal synthetic sides (quality 58–66) at 94d5de3, with the aggressive arm plus the six single-instruction arms, managers on. The manager-off comparison was dropped to save time.
   - Judge against section S:
     - one instruction moves goal difference by at most ±0.35 and win rate by at most 10 points;
     - all-aggressive gains at most +0.6 goal difference and +15 points of win rate, concedes at least 10% more xG, and ends at least 5 points lower in stamina.
2. **Step 2.3,** ahead of the C1 tuning and of fitting 2.1: both depend on the passing physics.
   - Baseline: `footsim calibrate-engine --division ENG4 --n 200 --seed 21` and `--division ENG1 --n 200 --seed 21`, from the measurement worktree.
   - Lower `intercept_scale` until interceptions land in 14–26. The cloud measured 0.35 on synthetic sides: interceptions 68→29, high regains 57→36, throw-ins 19→26, ball in play 73→69 min, fast-break shots up; but goals 2.43→2.14 and offsides 19→39 (see `docs/calibration/20260929T202538-step2.3-intercept0.35-synthetic-n200.md`). Start at about 0.3 and watch offsides.
   - Then raise pass execution error (`passing.yaml` `execution`, mainly `per_metre` and `length_*`, so long balls miss more than short ones) until pass accuracy and throw-ins land.
   - Watch `high_regains`, `ball_in_play_min`, `goals` and `shots`. Every decision needs 200 paired fixtures on the same seed.
3. **Back to Steps 1.3 and 1.4, C1.**
   - Run the Grimsby A/B at the new head (about 40 min). The command is in the `calibrate-engine` skill; run it from `.worktrees/measure` pinned to the head.
   - A setting still over the line gets extra costs in `tactics.yaml`, `duels.yaml` or `passing.yaml`, never less ability.
   - Then tick 1.3 and 1.4: golden values, commit and push, and restart the :8000 game (`run-footsim` skill).
4. **Step 2.1, fit home advantage.**
   - `--division ENG4 --n 400 --seed 31` and ENG1 the same, real squads, no focus club.
   - Fit `home_advantage.yaml` to `home_win`, `draw`, `away_win`, `home_goal_diff` (about +0.3) and `away_card_gap` (0.1–0.4).
   - Referee values stay small; the crowd carries most of it.
5. **Step 2.4.** Read `reds` (target 0.08–0.18) from the same batches.
6. **Step 2.6.** Pre-D baselines, ENG1 and ENG4 at 200 each, saved to `docs/calibration/`. These need the real world, so they're local only.
7. **Make synthetic teams realistic** (recommended, local only because it needs the EA data). Synthetic players' secondary attributes sit 10 below their quality, so synthetic sides foul about a quarter as often as real ones and stray offside five times as often. Fit per-position attribute offsets from the FC 27 data, and store only the aggregated offsets, never player rows. Cloud and test calibration would then match real squads. Golden values change.
8. **Step 3, Phase D,** starting with D0 (debug overlay), as `recovery-and-continuation.md` describes. The rest of the order is in `progress.md`.

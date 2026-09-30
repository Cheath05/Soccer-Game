---
name: calibrate-engine
description: Measure the footsim agent match engine against real football. Covers running `just calibrate-engine` batches and paired tactic or formation A/B arms, reading the report and its confidence intervals, batch-size rules, the standard arms (including the user's all-aggressive Grimsby setup), metric definitions and caveats, and where reports go. Use before and after any engine or match-config change, and for every tuning decision.
---

# Calibrating the agent engine

The harness is `backend/src/footsim/calibration/engine_batch.py`, run through `footsim calibrate-engine` (or `just calibrate-engine`).
- It plays many matches in parallel, summarises each with `match/engine/probe.summarize`, and averages them with `probe.aggregate`.
- It compares the averages with the ranges in `data/config/calibration/match_targets.yaml`.

For long runs, delegate to the `engine-calibrator` agent in the background and keep coding.

## Where batches run: the measurement worktree

A batch loads the engine code when it starts, and its worker processes keep that version. Editing engine files while a queue of batches is waiting would silently measure a mix of versions. So batches run from a separate checkout pinned to a commit, `.worktrees/measure`:

```bash
cd /Users/alexbenton/Developer/Soccer-Game
git add ... && git commit ...                               # measure committed code only
git -C .worktrees/measure checkout -q --detach <commit>     # usually the branch head
cd .worktrees/measure/backend && uv sync --frozen -q        # only if dependencies changed
uv run --frozen footsim calibrate-engine ... --out /Users/alexbenton/Developer/Soccer-Game/reports/engine
```

- Every report is then tied to an exact commit; put the commit hash in the report's label or in your summary.
- **Name the commit or the branch, never `HEAD`.** Inside the worktree, `HEAD` means the worktree's own head. `git -C .worktrees/measure checkout -q --detach phase-1-match-believability` pins it to the branch.
- **Parameter sweeps without a commit per value:** copy the config and change the one value, then point the batch at the copy. The code stays pinned; only the named value differs.
  ```bash
  cp -R .worktrees/measure/data/config /private/tmp/claude-502/cfg-VARIANT
  # edit one value in /private/tmp/claude-502/cfg-VARIANT/match/<file>.yaml
  FOOTSIM_CONFIG_DIR=/private/tmp/claude-502/cfg-VARIANT uv run --frozen footsim calibrate-engine ... \
    --out /Users/alexbenton/Developer/Soccer-Game/reports/engine/<step>/<variant>
  ```
  Keep `--seed`, `--n` and the division the same across variants so they pair up, and commit only the value you settle on.
- If the worktree is missing, recreate it:
  ```bash
  git worktree add --detach .worktrees/measure HEAD
  ln -s /Users/alexbenton/Developer/Soccer-Game/data/worlds .worktrees/measure/data/worlds
  ```
- The main checkout stays free for development while a batch runs.

## Commands

The examples below show the harness flags. Run them from `.worktrees/measure/backend` (see above).

```bash
# Real squads, one division (ENG1 Premier League … ENG4 League Two)
uv run --frozen footsim calibrate-engine --division ENG1 --n 200 --seed 1 --workers 7
# Synthetic teams (no world file needed; qualities drawn from 62-86)
uv run --frozen footsim calibrate-engine --synthetic --n 200 --seed 1 --workers 7
# Equal synthetic sides in a League Two-like band: the stand-in for Grimsby where there's no
# world file (the cloud). --quality sets the band, --equal gives both sides one draw.
uv run --frozen footsim calibrate-engine --synthetic --division ENG4 --quality 58-66 --equal \
  --n 200 --seed 11 --workers 4 --ab "aggressive:mentality=attacking,pressing=high,line=high,width=wide,tempo=fast,passing=direct"
# Paired A/B on the user's club: every arm replays the same fixtures and seeds
uv run --frozen footsim calibrate-engine --division ENG4 --n 200 --seed 11 --workers 7 --focus-club 218 \
  --ab "aggressive:mentality=attacking,pressing=high,line=high,width=wide,tempo=fast,passing=direct" \
  --ab "fast:tempo=fast" --ab "direct:passing=direct" --ab "press:pressing=high" \
  --ab "high_line:line=high" --ab "wide:width=wide" --ab "attacking:mentality=attacking"
```

- `--ab NAME:KEY=VALUE,...` sets instructions for the focus side. A `formation=4-4-2` key changes the formation for a formation A/B.
- The first arm is always the unchanged baseline.
- Instruction keys and levels are in `data/config/match/instructions/`, and what each level does is in `data/config/match/tactics.yaml`.
- Reports are written as `<UTC stamp>-<label>.md` and `.json`:
  - development runs go to `reports/engine/` (the default, gitignored);
  - phase-acceptance runs go to `--out /Users/alexbenton/Developer/Soccer-Game/docs/calibration`, and are committed.
- **Time.** This Mac has 8 cores, but only 4 are performance cores; the other 4 are efficiency cores.
  - A match takes about 6.7 s on a performance core, and 7 workers give roughly 5 performance cores' worth.
  - Expect about 4–5 min for 200 matches, and 35–40 min for an A/B with 7 arms × 200.
  - That's only true if nothing else heavy runs. Test suites, e2e runs or agents simulating matches alongside a batch can double its time: on 29 Sep the load average reached 75.

## Rules

1. **Batch size.** At least 200 fixtures for any tuning decision; 1,000 for phase acceptance.
   - At n=70, goals per match have a standard error of about ±0.2. The crashed session tuned on runs that small and chased noise.
2. **Pairing.** Compare runs with the same `--seed`, `--n` and division. Read differences with their CI, not bare means.
3. **One heavy batch at a time.** Check `ps -eo pid,etime,command | grep "[c]alibrate-engine"` first. Parallel batches skew timings and starve each other.
4. **What to change.** Change one subsystem at a time, and put tunable numbers in `data/config/match/*.yaml`.
   - Tactics may gain costs, never lose ability (see `tactics.yaml`'s header).
5. **Keep the full-length match.** The engine always simulates the full 90 minutes plus added time. Never fix scoring through match length or playback speed.

## Reading the metrics

All values are per match with both teams combined, unless the name says `per_team`.

| Metric | Definition (probe.py) | Caveat |
|---|---|---|
| `high_regains` | open-play possession won within 40 m of the opponent's goal (Opta's high turnover) | |
| `fast_break_shot_share` | shot within 15 s of winning the ball in own half, in open play | |
| set-piece shots and goals | shot within 10 s of a restart, in the same possession | |
| `interceptions` | passes an opponent took while they were still on course for their target area (`passing.yaml` `target_area`) | real 14–26 (approx.); before Step 2.2 every pass an opponent collected counted |
| `recoveries` | passes an opponent collected after they went astray: overhit or off target (Opta's ball recovery) | no target yet |
| `ppda` | opponent passes in their own 60% per defensive action in that zone (tackles, interceptions, fouls; not recoveries) | per team; read higher from Step 2.2 on, when recoveries stopped counting |
| `teleports` | keeper saves made more than 1.5 m from the ball (the catch snaps him to it), plus restarts flagged `teleported` | must be 0; this is not a general per-tick check (see the `repro-match` skill for that) |
| `ball_in_play_min` | ticks with the ball live | real 55–58 |
| `corner_attackers_in_box` | attackers in the box when a corner is taken | real 4–5 |
| `wait_*` | seconds from the ball going dead to the restart | from Opta |

The home, draw and away shares show no home advantage. The agent engine had none until Step 2.1 of the recovery plan.

## How a report is organised (since Step 2.3a)

The report follows the calibration principles in `docs/plans/continuation-plan.md`:
- **One engine.** League differences come from ratings first, then team context, then at most a small, bounded league-environment parameter.
- **Rates, not raw counts.**
- **League figures validate; they are never tuned towards.**

Its sections:
- **Rates:** judged as they are. They include pass accuracy, conversion, shares and waits.
- **Volumes, judged per minute of ball in play:** each count per match (goals, shots, passes, fouls, throw-ins and so on) is compared with the target range divided by the league's real ball-in-play minutes (`_exposure` in `match_targets.yaml`). A batch that keeps the ball in play too long can look right per match while its rate is wrong, and the reverse; judge the rate.
- **League references:** validation only. `ENG4` adds League Two's own figures on top of the EFL section. A miss is diagnosed down to rates and ratings. If it can't be reached without a league-specific rule or an implausible mechanic, record it as a conflict.
- **Pass reliability:** completion against the passer's own estimate, by length band and estimate decile. Estimates should be honest: each row's gap within about ±0.05.
- **By starting XI rating:** team-level results grouped by XI rating, both divisions on one scale. League quality should show up here, through the players.

The pass metrics: `pass_acc_*`, `estimate_gap_*`, `pass_time_*` (seconds from the kick to a completed reception), `long_ball_share`, `cross_share`, and `pass_fail_*` (where failed passes went).
- The bands are short <14 m, medium 14–32 m, long ≥32 m (Opta's long ball), cross, and throw (long throws included).
- `heavy_touch_self_regather`: the share of heavy touches the receiver gathered again himself within 3 s.
- `offsides_*`: offsides by kind.

**The quality sweep (rating responses).** Run equal synthetic sides at four quality levels, same seed, one at a time:
```bash
for q in 58 66 74 82; do
  uv run --frozen footsim calibrate-engine --synthetic --division ENG4 --quality $q-$q --equal \
    --n 200 --seed 21 --workers 7 --out /Users/alexbenton/Developer/Soccer-Game/reports/engine/<step>/sweep-q$q
done
```
Read the same metric across the four reports (pass accuracy, completion by band, miscontrols): it should change clearly and in the right direction, with the CIs separated.

## Targets and sources

`match_targets.yaml` holds per-division ranges with sources: football-data.co.uk 2023/24–2025/26, Opta Analyst, the Premier League and the IFAB Laws. The acceptance thresholds are in section S of `docs/plans/match-believability.md`.

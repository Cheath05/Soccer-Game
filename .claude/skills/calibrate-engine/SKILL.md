---
name: calibrate-engine
description: Measure the footsim agent match engine against real football. Covers running `just calibrate-engine` batches and paired tactic or formation A/B arms, reading the report and its confidence intervals, batch-size rules, the standard arms (including the user's all-aggressive Grimsby setup), metric definitions and caveats, and where reports go. Use before and after any engine or match-config change, and for every tuning decision.
---

# Calibrating the agent engine

The harness is `backend/src/footsim/calibration/engine_batch.py`, run through `footsim calibrate-engine` (or `just calibrate-engine`).
- It plays many matches in parallel, summarises each with `match/engine/probe.summarize`, and averages them with `probe.aggregate`.
- It compares the averages with the ranges in `data/config/calibration/match_targets.yaml`.

For long runs, delegate to the `engine-calibrator` agent in the background and keep coding.

## Commands

```bash
cd /Users/alexbenton/Developer/Soccer-Game/backend
# Real squads, one division (ENG1 Premier League … ENG4 League Two)
uv run --frozen footsim calibrate-engine --division ENG1 --n 200 --seed 1 --workers 7
# Synthetic teams (no world file needed; qualities drawn from 62-86)
uv run --frozen footsim calibrate-engine --synthetic --n 200 --seed 1 --workers 7
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
- Time: about 6.7 s per match per worker. 200 matches on 7 workers take about 3–4 min; an A/B with 7 arms × 200 takes about 25–30 min.

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
| `interceptions` | **currently every pass collected by an opponent**, misplaced ones included | over-counts until Step 2.2 separates recoveries |
| `ppda` | opponent passes in their own 60% per defensive action in that zone | per team |
| `teleports` | keeper saves made more than 1.5 m from the ball (the catch snaps him to it), plus restarts flagged `teleported` | must be 0; this is not a general per-tick check (see the `repro-match` skill for that) |
| `ball_in_play_min` | ticks with the ball live | real 55–58 |
| `corner_attackers_in_box` | attackers in the box when a corner is taken | real 4–5 |
| `wait_*` | seconds from the ball going dead to the restart | from Opta |

The home, draw and away shares show no home advantage. The agent engine had none until Step 2.1 of the recovery plan.

## Targets and sources

`match_targets.yaml` holds per-division ranges with sources: football-data.co.uk 2023/24–2025/26, Opta Analyst, the Premier League and the IFAB Laws. The acceptance thresholds are in section S of `docs/plans/match-believability.md`.

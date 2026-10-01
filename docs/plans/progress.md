# Match believability: progress

**Start with the "Continuation checkpoint" below, then resume from the first unticked item.**
- Since 30 Sep, the order of work and its details are in `continuation-plan.md`, which also holds the calibration principles.
- It supersedes `recovery-and-continuation.md` from Step 2.3 on.
- The design is in `match-believability.md`; section letters (for example "section S") refer to it.

**Every major completed change is its own checkpoint** (behaviour change or finished sub-step):
1. `engine-reviewer` checks the diff;
2. lint and tests pass, plus the relevant calibration;
3. the golden values are re-captured if behaviour changed on purpose;
4. this file is updated: the checkpoint section below, and the ticks;
5. commit and push to `phase-1-match-believability` before starting the next change.
   - Unfinished work goes into a labelled WIP commit, never only into the working tree.

## Continuation checkpoint (update at every checkpoint)

- **Branch:** `phase-1-match-believability`.
- **In progress: the user's play-test fixes** ("Play-test fixes" below), each its own commit. They come before 2.3c continues.
  - P1 (hand-picked starters shown as 99): 85a20ce.
  - P2 (the set-piece taker running back and forth): 36fbd4f.
  - P3 (the live viewer skipping actions): d981315.
  - P4 (goal pause and banner): 17635e6.
  - :8000 restarted on 17635e6 (P1–P4) at 01:28 on 1 Oct, after checking it had no connections and that nothing was unsaved: the last play, fixture 211, was autosaved.
  - P5 (sim to date): 66a92c7.
  - :8000 restarted on 66a92c7 (P1–P5) at 01:40 on 1 Oct. It had no connections, and nothing had happened on it since the 01:28 restart.
  - **Next task:** the user's play-test round 2 (below), in its order: P6 9b3635a; P7 is done in the commit that ticks it, measurement next; then P8. Check `lsof -nP -iTCP:8000 -sTCP:ESTABLISHED` before any batch: a batch slows a match the user is watching (use `--workers 3` then).
  - The P-fixes change behaviour only where the play-test found bugs, so no 200-match batch runs while the user is playing. The next batch (2.3c's) re-measures them.
- **Checkpoint commit:** 1de6591, the play-test build (30 Sep): round 5's measured passing values are now the committed defaults. The commit right after it only filled in this hash and recorded the :8000 restart.
  - The values are `intercept_scale` 0.2, `per_metre` 0.008 and `length_per_metre` 0.022, called "f020e2".
  - Earlier: Step 2.3c WIP iteration 2 0f96176 (iteration 1 eeb5239); 2.3b complete at d7ccf17; 2.3a a9a8ced.
- **Engine:** behaviour changed on purpose. The Mac's golden values were re-recorded, with a History note. 2.3c is still behind `estimate.honest` (off).
  - **Why:** every Step 2.3 measurement used f020e2 through a variant config, while the committed defaults stayed at the original values.
    - Nobody had measured those since round 5, where they gave 64–74 interceptions a match (real 14–26), 13–15 throw-ins and 69–77 minutes of ball in play.
    - So a play-test of the latest commit showed a state no step was working on.
  - **Measured:** `ref-2.3b2-p40` (200 matches per division, seed 21) is this exact build. Everything since d7ccf17 is behind the switch, and the golden values didn't move until this commit. Figures are in "The play-test build" below.
  - **Still provisional:** 2.3e sets the final values.
    - Conflict, already flagged in the continuation plan: e2's length spread is wider than real long passes plausibly are, and distance terms can't make weaker passers less accurate.
    - It stays until 2.3e's rating terms take over part of it.
- **2.3c, WIP, unchanged by this commit. Done in iteration 2** (from the reviewer's notes on iteration 1):
  - `_run_distance`: receivers and chasers move as `_move_players` runs an urgent player (top speed from stamina, own acceleration), replacing a flat 0.9 share.
  - The receiver runs for the intended point during his read delay, and only the ground beyond that is slack for a pass that's off.
  - A keeper in his own box reaches 2.4 m and gathers about 95%.
  - Only defenders already at a dropping ball, plus the one quickest to it, contest it.
  - Short throws are estimated with skill 85, as `start_pass` plays them.
- **Quick check with the switch on, iteration 2** (`scratchpad/honesty_check.py`: 6 synthetic matches, f020e2 settings; indicative):
  - throw-ins are honest (estimate gaps −0.03 to −0.01);
  - long balls are now slightly overrated (+0.05);
  - medium passes are still overrated (+0.10; the 0.8–0.9 decile completes 69%);
  - short passes are overrated (+0.06);
  - crosses are underrated (−0.13).
- **Key finding, which changes 2.3c's scope:** with honest estimates, long balls vanish (0.2% of passes, against Opta's 11.7%).
  - Their estimate is now about right (~0.5), but the decision values (`threat`, `RETAIN`, `loss_cost`) never make a 50% long ball worth playing.
  - Real teams go long mostly under pressure in their own half, against a high press, or when the short options are covered: situations where losing a short pass is costly.
  - The old estimate's +0.10–0.16 optimism about long balls had been standing in for that.
  - **So 2.3c needs a second half: calibrate the decision values with honest estimates.** Candidates:
    - the loss cost of a short pass under pressure deep in our own half, which also covers the high-regain leak;
    - the territorial value of a long ball;
    - the passing-direction instruction's weight.
  - The acceptance check must include the pass mix (long-ball share and cross share in range), not only the reliability table.
- **Iteration 3 (1 Oct, behind the switch), with `.claude/skills/calibrate-engine/estimate_parts.py`:**
  - That diagnostic splits the estimate into its parts (`EstimateParts`: path, reach, arrive, secure) and compares each with what happened to the passes played.
  - **What it found:**
    - The overrating of ground passes was almost all balls that never reached the receiver: medium passes predicted .032, actual .115.
    - Mostly that was physics: receivers overran the ball's line (fixed as P6), and e2's length error applies to ground passes too (P7).
  - **The estimate now follows ground passes through their errors** (`_ground_arrival`):
    - a 5×5 Gauss-Hermite grid over the angle and length errors;
    - meeting points 0, 3, 6 or 10 m on along the path;
    - soft balls stopping short;
    - the arrival pace feeding the first touch.
  - **Also:**
    - first-touch pressure uses the marker's distance at the ball's arrival;
    - the path counts an opponent from the ball's first metre (blocks) and one just beyond the receiver.
    - Two fitted shares in `passing.yaml`: `estimate.adjust` 1.0 (a receiver's running after his read delay goes into getting to a pass that's off) and `estimate.closing` 0.25 (how much opponents close a pass's path and the receiver).
  - **Result** (12 synthetic matches, qualities 62 and 78, P6 in; estimate against completed):

    | Band | Estimate | Completed |
    |---|---|---|
    | Short | .942 | .926 |
    | Medium | .906 | .876 |
    | Throws | .842 | .829 |

    - The 0.8–0.9 deciles are within +4.
    - Medium's 0.6 decile is −9: interceptions and pressured touches are still over-predicted for risky passes.
    - These move again with P7, so re-run the diagnostic after it.
- **What remains for 2.3c, in order:**
  1. Ground passes: re-check after P7, and tune `adjust` and `closing` if the deciles moved.
  2. Crosses underrated (estimate .03 against .15–.20 completed). Make `_landing_chance` and the arrival for crosses follow `_aerial`:
     - any attacker within 3 m of where it drops can win it;
     - with no defender there, he wins it outright, without a first-touch roll.
  3. Calibrate the decision values, as above.
  4. Then the reliability table within ±5 points per decile **and** the pass mix in range. Then the slow honesty test, switch it on, a 200-match measurement, golden values, delete `_heuristic_success`, and commit.
- **Tests:**
  - `just lint` is clean;
  - all 139 backend tests pass, with the golden values re-recorded for the new defaults;
  - `just e2e` (smoke and live) passes against a fresh :8765 with no browser errors;
  - copies of both save slots load on a :8765 server and play their next match (about 6 s each):
    - slot 1, Grimsby: the manual save and the autosave;
    - slot 2, Chelsea: the autosave.
  - The saves are schema 3, the same as the old :8000 build, so no migration runs.
- **Next task:** 2.3c remaining items 1–4 above. The quick check recipe:
  - `cfg-dev` = the checkout's `data/config` with `honest: true` (f020e2 is now the default);
  - then `FOOTSIM_CONFIG_DIR=/private/tmp/claude-502/cfg-dev uv run python <scratchpad>/honesty_check.py`;
  - the script is also described in this checkpoint, if the scratchpad is gone: 6 synthetic matches (3 at q62, 3 at q78), then `probe.aggregate` and `probe.reliability`.
- **Calibration:** nothing is running. Pin the worktree first for any batch.
- **Unresolved:** 2.3c (WIP), 2.3d–2.3f, C1, 2.4, 2.1 and 2.6. The verified engine bugs still open:
  - onside through balls are dropped;
  - offside awareness re-rolls every decision;
  - slow tempo gets an accuracy bonus;
  - the card rules;
  - stale duel engagements (2.4);
  - counter holds after the side already in possession gains a loose ball (E).
- **Play-testing on :8000, the user's game.** It runs 66a92c7 (play-test fixes P1–P5), restarted at 01:40 on 1 Oct after a check showed no connections. Earlier: 17635e6 from 01:28, and 1de6591 from 21:37 on 30 Sep.
  - The log is `/private/tmp/claude-502/demo-server.log`. Earlier builds' logs are kept next to it as `demo-server-20260928-build.log`, `demo-server-1de6591-build.log` and `demo-server-17635e6-build.log`.
  - A restart clears the loaded career, so the user loads it again from the start page. Both slots were listed unchanged after the restart.
  - Until 30 Sep its backend dated from 28 Sep (Phase A), while it served the 30 Sep frontend from `frontend/dist`. The frontend is read from disk; the backend isn't.
  - To update it later: `cd frontend && npm run build`, then restart :8000 with the `run-footsim` skill, once `lsof -nP -iTCP:8000 -sTCP:ESTABLISHED` shows no connections.
  - Automated checks use a throwaway :8765 with a temporary `FOOTSIM_SAVES_DIR`; none is running now.
  - **Note:** this is an intermediate calibration state; see "The play-test build" below.
- **Housekeeping:** `stash@{0}` (local 2.1/2.2/2.5 work from before the cloud merge) is superseded by the cloud versions and can be dropped.

## The play-test build (what to expect)

**Measured:** `ref-2.3b2-p40`, real squads, seed 21, 200 matches per division. Per match:

| | League Two (ENG4) | Premier League (ENG1) | Real |
|---|---|---|---|
| Goals | 2.92 | 3.67 | PL 2.65–3.05; EFL 2.45–2.85 |
| Shots | 30.0 | 37.1 | PL 23–27.5; EFL 22–26 |
| Pass accuracy | .817 | .812 | PL .80–.85; EFL .74–.81 |
| Long-ball share | .039 | .103 | PL .095–.14 |
| Interceptions | 15.7 | 15.7 | 14–26 |
| High regains | 41.8 | 31.2 | 10–17 |
| Throw-ins | 37.8 | 52.2 | PL 32–42; EFL 32–44 |
| Ball in play (min) | 65.3 | 58.1 | PL 54–60; EFL 52–60 |
| Offsides | 6.4 | 4.9 | 2.5–4.5 |
| Fouls | 8.4 | 14.1 | 20–24.5 |

**Known issues, and the step that addresses each,** so play-test notes can focus on anything new:
- **Too many shots, and too many goals in the Premier League.** One striker can take 10 or more shots: 13 in both 30 Sep test matches.
  - No step owns shot selection yet.
  - 2.3c's honest estimates should cut the overrated crosses and long balls that feed it.
  - Re-measure after 2.3c, and add a step if it's still high.
- **Too many turnovers high up the pitch** (high regains): 2.3c's decision values, then 2.3e.
- **Few fouls, so few cards:** 2.4.
- **Too many offsides:** 2.3d.
- **Too many Premier League throw-ins:** 2.3e.
- **League Two:** too much ball in play, and it goes long too rarely. 2.3e's rating terms, then C2's styles.
- **Static shape:** players hold a fixed shape, and team phases flicker. Phase D.
- **Tactics:** aggressive and direct are too strong, and slow tempo gets an accuracy bonus. C1.

## Play-test fixes (the user's play-test of 1de6591, 30 Sep; each is its own checkpoint)

The user also said save files may be deleted if they ever get in the way of the new engine. Not needed so far: both slots load on the current build.

- [x] P1 **Hand-picked starters showed as 99.** `LineupPicker.pick` forces a fixed player into his slot with a score of 1e6, and reported that score, capped at 99, as his rating.
  - It reached the tactics screen, the live subs panel's OVR and the tie-break in a mid-match formation change.
  - Results were never inflated: the user's matches run on the agent engine, which plays from attributes.
  - Saves store only slot → player, so nothing stored was wrong.
  - Fixed: fixed players keep their real slot rating. `test_lineup.py` fails without the fix. Golden values unchanged.
- [x] P2 **The set-piece taker ran back and forth before the restart.**
  - **Cause:** the taker was an urgent player, and urgent players run at full speed with no braking, so he ran past the spot and back until the restart was due.
  - **Traced** in 2 synthetic matches: 6–19 turns a restart (corners 19, throw-ins 9) at up to 8 m/s, overshooting by 3–6 m.
  - **Fixed:** a `settle` flag gives the taker the arrival braking that forward runners already have. He jogs to the ball and runs only if jogging would make him late (`restarts.yaml` `taker_hurry_margin` 2 s).
  - **After:** 0 turns, at most about 1 m of overshoot.
  - **Restart waits are unchanged** on 4 seeds: throw-ins 15.6 s (before 16.3), goal kicks 27.1 (28.0), corners 31.7 (32.1). Ball in play 62.4 minutes (61.8).
  - **Tests:** `test_a_taker_waits_on_the_ball_instead_of_running_past_it` fails without the fix. Mac golden values re-recorded with a History note.
- [x] P3 **The live viewer skipped actions:** a pass reached a player, then the picture jumped to the other side in possession.
  - **Cause:** the server runs the engine a little ahead of the screen (`lookahead_seconds`), and pausing, resuming and changing speed or mode restarted its clock from the engine's time, not the screen's.
    - So the screen fell behind by up to `lookahead × rate` with each change: 18 match seconds when slowing from 8×.
    - The viewer then jumped ahead once it was too far behind.
  - **Simulated** with the real LiveSession and the viewer's playback ported line for line (scratch `viewer_sync.py`, a typical watch with speed changes and pauses): jumps of 12.9, 14.9 and 18.3 match seconds, each on slowing to 1×.
  - **Fixed:**
    - `LiveSession.shown(now)` is the one timeline. Pause, resume, speed and mode carry on from the moment on screen, and `pause()` is also used on connect and disconnect.
    - Every message carries `shown` and `play_rate`, and the viewer steers its playhead to them, snapping only when far out (a highlight, a hidden tab).
    - Highlights replay at `presentation.yaml` `highlight_rate` (18) on both ends, and the next skip waits until the viewer has seen the whole highlight.
    - At high speeds every frame where the ball changes hands is kept, so a pass is seen from foot to foot.
  - **After:** the same simulation shows no jumps and no frame step faster than 1.6× the rate.
    - In Chromium (`e2e/live.mjs`, which now samples the time the pitch draws via `canvas.dataset.t`): the largest step in about 100 ms after slowing from 8× to 1× is 2.7 match seconds, a smooth catch-up.
  - **Tests:** `test_the_picture_carries_on_through_speed_changes_and_pauses`; the frame-limit test now also checks that every touch is sent. Golden values unchanged (presentation only).
  - **Also:** `e2e/smoke.mjs` no longer reports the 409 a fresh server's start page gets for `/api/career` (no career loaded yet, as intended).
- [x] P4 **Goals: a 3-second pause and a banner with the scorer and any assist.**
  - **The hold:** `LiveSession` collects each goal from the engine's log, which now carries `scorer_id` and `assist_id`; a substitution can follow at the kick-off in the same tick, so slots won't do.
    - It adds a `Hold` to the timeline, and `shown` stops there for `presentation.yaml` `goal_pause` (3) real seconds at any speed, highlights included.
    - The engine runs ahead of the screen, so the hold is in place before the picture gets there.
    - Pausing or changing speed during a hold keeps only the time it has left.
  - **Messages:** each one carries `holding` (scorer, assist, own goal, penalty, clock, score), `hold_at` and `server_time`.
  - **The viewer:**
    - its playhead stops on `hold_at`;
    - it puts the server's `shown` at the moment the server meant, using the smallest clock offset seen. This removes the lag from message delivery: about 2 match seconds at 8×.
    - `GoalBanner` shows once the picture reaches the goal.
    - The scoreboard counts a goal only once it has been seen; the commentary already did.
  - **Tests:**
    - `test_a_goal_holds_the_picture_while_the_scorer_is_shown` and `test_goal_pauses_never_change_the_result`;
    - `e2e/live.mjs` watches for the banner at 8× (into the second half if need be) and checks the picture holds still, as it did for "GOAL! Evanilson, Assist: Ryan Christie";
    - after slowing from 8× to 1×, the largest step in about 100 ms is 1.3 match seconds;
    - golden values unchanged.
- [x] P5 **Sim to date** (Phase I, basic).
  - **Where:** a "Sim to…" menu beside Continue: one week, one month, end of season, or a chosen date.
  - **The step:** `world/career.py` `sim_step` either plays the user's match of the day as Instant does, or advances to his next match day or the target, whichever comes first.
    - The target day itself is left to the user, so its match can still be watched.
    - The season's end (rollover after the play-offs) stops it too.
  - **The job** (`api/sim.py`): `POST /api/career/sim {until}`, `GET` for progress, `POST /api/career/sim/stop`.
    - A background thread takes the write lock per step only.
    - It autosaves after each of the user's matches and at the end, and is abandoned if another career is loaded.
    - Continue, instant play and live matches are refused while it runs, and it won't start during a live match.
  - **The page:** a progress window (bar, current day, results as they come, Stop), then a summary with the results and the news. `CareerOut` gained `season_end`.
  - **Stop conditions:** the date, the season's end, Stop. More can follow (injuries, offers) once those systems exist.
  - **Tests:**
    - `tests/integration/test_sim_to_date.py`: plays every user match before the date and none after; refuses Continue meanwhile; autosaves; stops on request; refuses a date not ahead.
    - `e2e/smoke.mjs` sims a week from the browser.
- Later (the user agrees): transfers and the other management systems.

## Play-test round 2 (the user, 1 Oct; each is its own checkpoint)

The user asked whether the engine or the management features (transfers, academy) should come first, and to do whatever makes the game a finished product most effectively.

**The order chosen:**
1. **First, the engine problems the user can see in a match:** misplaced passes in build-up (P6, P7).
2. **Then the cheap, visible fixes:**
   - the sim summary covering the season summary (P8);
   - more formations (P9);
   - players developing during the season (P10).
3. **Then 2.3c's remaining calibration and the rest of the plan.** The invisible parts are time-boxed.
4. **Transfers and the academy come later,** each as its own phase once matches feel right. They are big systems, and half-built ones help nobody.

- [x] P6 **Receivers ran through the ball's line.**
  - A pass receiver is an urgent player, and urgent players never brake, so after reading a pass he sprinted at the nearest point of its path and overran it. The physics then had him miss passes he should take.
  - **Found by 2.3c's honesty diagnostics:** safe-looking short passes (estimated 0.96) failed 8.0%. Two thirds of the failures were balls the receiver never got within 1.3 m of.
  - **Fixed:** the receiver gets the arrival braking from P2 (`settle`), and stops on the line.
  - **After:** those passes fail 4.1%, matching the estimate. Medium passes complete .92 against .84 in the same synthetic matches.
  - Overall pass accuracy will rise, likely above the real ranges. P7 and 2.3e bring it back through mechanisms (execution by ratings, composure, pressure), not by undoing this.
  - **Tests:** `test_a_receiver_stops_on_the_balls_line_instead_of_running_through_it` (4.8 m/s at the ball without the fix). Mac golden values re-recorded with a History note.
- [x] P7 **Misplaced passes from the back without pressure** (the user: real teams rarely do it; suggested composure or pressure).
  - **Cause, measured:** e2's length error (`length_per_metre` 0.022) applies to ground passes too. A 20 m ground pass has a 44% length spread, so 48% are mis-hit by more than 30%, and soft back passes stop short.
  - **Done:**
    - `execution` splits each distance term: `per_metre` 0.0015 and `length_per_metre` 0.008 for any pass (the original values), plus `lofted_per_metre` 0.0065 and `lofted_length_per_metre` 0.014 for a ball in the air. Lofted balls keep e2 exactly (0.008 / 0.022).
    - `execution.composure` 0.5: pressure costs (1 − w) + w · 2 · (1 − composure/100), so 1 at composure 50, 0.7 at 80 and 1.2 at 30. With no opponent near, composure makes no difference.
    - The estimate uses the same `pass_error`.
  - **Tests:** `test_a_ball_in_the_air_goes_astray_more_than_one_on_the_ground` and `test_composure_decides_what_pressure_costs`. Mac golden values re-recorded with a History note.
  - **Measured** (P6 and P7 together, real squads, seed 21, 200 matches per division, `reports/engine/step2.3/ref-p7`; before → after):

    | | ENG4 | ENG1 | Real |
    |---|---|---|---|
    | Pass accuracy | .817 → .922 | .812 → .905 | PL .80–.85; EFL .74–.81 |
    | Medium completed | .810 → .938 | .829 → .946 | ~.83–.87 |
    | High regains | 41.8 → 19.5 | 31.2 → 15.8 | 10–17 |
    | Throw-ins | 37.8 → 19.8 | 52.2 → 31.5 | PL 32–42; EFL 32–44 |
    | Ball in play (min) | 65.3 → 75.3 | 58.1 → 65.8 | 52–60 |
    | Goals | 2.92 → 1.61 | 3.67 → 3.11 | PL 2.65–3.05; EFL 2.45–2.85 |
    | Shots | 30.0 → 20.7 | 37.1 → 37.5 | PL 23–27.5; EFL 22–26 |
    | Long-ball share | .039 → .034 | .103 → .094 | PL .095–.14 |

    - **Better:** the build-up leak is gone (high regains in range for ENG1, near it for ENG4), and ENG1's throw-in conflict is resolved.
    - **Worse:** passing is too clean, so the ball is in play too long and ENG4 scores too little.
    - **Not undone:** both fixes removed unrealistic mechanics, and undoing them would bring back the user's complaint.
    - **The missing realism is the pass mix:** ENG4 plays fewer long balls than ENG1, the reverse of real football. See P11.
- [x] P11 **Decision values: a failed pass is lost where it fails** (2.3c item 3, brought forward).
  - `_pass_options` charged every option the loss cost of the passer's own position, so a 40 m ball out of trouble was costed as if lost at the centre-back's feet. Long balls were almost never worth it.
  - **Done:**
    - a pass's failure is costed where it's lost: a lofted ball where it lands, a ground pass midway (`pitch.loss_cost` takes arrays now);
    - a shot is charged the possession it gives up when it doesn't go in, (1 − xG) × the loss cost where it's taken. Shots had ignored that, so players shot too readily.
  - **Indicative** (4 synthetic matches at quality 62, before → after):

    | | Before | After |
    |---|---|---|
    | Pass accuracy | .913 | .836 |
    | Long-ball share | .052 | .163 |
    | Throw-ins | 24 | 38 |
    | Ball in play (min) | 73 | 61.5 |
    | High regains | 19 | 14 |
    | Shots | 22 | 31.5 |
    | xG per shot | .073 | .075 |

    - Without the shot term, shots were 35 at .056 xG each.
  - **Shots stay too many.** Attacks reach the box too easily against static defensive shapes: Phase D.
  - **Tests:** `test_a_long_ball_risks_the_ball_where_it_lands_not_at_the_passers_feet`. Mac golden values re-recorded with a History note.
  - **Measurement:** 200 matches per division, `reports/engine/step2.3/ref-p11`. Recorded in the next commit.
- [x] P8 **Sim to the season's end:** its summary sat over the season summary, and closing it closed both.
  - The results now come first, in their own window. Its button opens a separate "Season summary" (or "News") window with every item, where only the last 12 were shown before. That window stays until it's closed.
  - At the season's end the summary leads with the user's finish: position, record, goals, points and outcome. The job reads `league_final` and reports it as `SimStatusOut.season_final`.
  - **Checked:** `e2e/smoke.mjs` (one week; no news that week). Still to check: a season-end sim in a browser, after the P7 batch.
- [x] P9 **Only 3 formations:** eight more, as data: 3-5-2, 3-4-3, 3-4-2-1, 5-3-2, 5-4-1, 4-1-4-1, 4-4-1-1 and 4-1-2-1-2 (diamond), 11 in all.
  - Wing-backs take their attacking width from the `wing_back` role. The slots only drop them into a back five without the ball.
  - The user picks them on the tactics screen and during matches.
  - **AI clubs still choose from 4-3-3, 4-2-3-1 and 4-4-2** (`world/context.py` `AI_FORMATIONS`), so calibration is unchanged. Widen that once Phase D gives formations real phase shapes.
  - `test_formations.py` plays five minutes in each. One synthetic match each against a 4-4-2 ran clean.
- [x] P10 **Players develop as the season goes,** not only at its end.
  - The yearly model (`people/development.py`) now runs a twelfth at a time on the first of each month (`season.after_day` → `develop_players`), and the rollover no longer develops.
    - Growth is compounded so twelve months add up to the year's.
    - Decline is spread evenly, and the noise is scaled by √(1/12).
    - Minutes count over the past twelve months.
  - **News for the user:** a monthly "Player development." item names his players whose overall moved ("Improved: Harvey Cartwright 61→62 …").
  - **Cost:** about 1 s per month on the full world (17,849 players).
  - **Tests:** `test_development.py` (twelve months make a year; decline evenly). A year of monthly steps on a fresh Grimsby career changed 99% of players.

## Quick fixes (do first; each is its own checkpoint)

- [x] 0a `just e2e` defaults to :8765. The e2e scripts refuse :8000, and any server whose `/api/health` doesn't confirm `default_saves: false`; `FOOTSIM_E2E_ALLOW_REAL_SAVES=1` overrides. Also fixed the start page staying on screen after starting a career from `/start`. Verified with `just e2e` on a fresh :8765 server; the user's saves are unchanged
- [x] 0b A substitute starts with no yellow card: `_load` resets the slot's `yellows` and `tackle_ready` (`engine.py:183-202`). Tested by `test_a_substitute_starts_unbooked`, which fails without the fix. The golden values are unchanged: no golden match makes such a substitution
- [x] 0c Two more per-slot carry-overs on a substitution, found by the reviewer. Done: `_load` drops the slot's `engaged` and `take_on_ready` entries, and `_bring_on` re-picks a restart taker who goes off. Two tests; Mac golden values re-recorded with a History note
  - Clear the slot's `engaged` state (`engine.py:93`; `duels.py:56-59`); this moves the seed-12 golden, so re-record it with a History note.
  - Re-pick a pending restart's taker in `_bring_on` when the slot it named has been substituted (`restarts.py:58-60`, `engine.py:763-764`).
  - Both with tests.

## Cloud session (29 Sep, claude.ai/code)

The local session reached its usage limit, and a cloud session carried on from 8a5d319.
- **Start here: `docs/plans/cloud-handoff.md`.** It says how to bring the cloud work in, check it on the Mac (including the one golden-value command), and carry on.
- **Branch.** Cloud sessions can push only to their own branch, `claude/eloquent-ramanujan-ho29ch`. It is `phase-1-match-believability` plus the cloud commits, so to pick up locally: `git switch phase-1-match-believability && git fetch origin && git merge --ff-only origin/claude/eloquent-ramanujan-ho29ch && git push`.
- **No EA data or built world in the cloud,** so batches there use synthetic teams. `--synthetic --division ENG4 --quality 58-66 --equal` stands in for Grimsby in League Two: equal sides, as section S asks, in a League Two-like band. Re-run a result on Grimsby locally before treating it as accepted.
- **Speed.** The cloud machine has 4 cores and takes about 17.8 s per match (the Mac: 6.7 s), so the 8 s budget can only be checked on the Mac.
- **Golden values are pinned per platform** in `backend/tests/unit/engine_golden.json`. The Mac and Linux round some floating-point operations differently, and a match amplifies the difference. A cloud commit that changes behaviour can record only the Linux values, and deletes the Mac's, so the golden tests skip on the Mac. **The only local follow-up:** `cd backend && FOOTSIM_UPDATE_GOLDEN=1 uv run pytest tests/unit/test_engine_golden.py`, then commit `engine_golden.json`.
- **Tests must hold on both platforms.** The same seed plays out differently on the Mac and on Linux, so a test must never depend on one match's chaotic outcome (as `test_reads_a_high_press_from_the_pitch` did: it now judges the manager's average reading over four seeds).

## Before the 29 Sep crash (checkpoint commit 24207eb)

- [x] Phase 0: measurement and safety (probe, harness, targets, synthetic teams, golden and determinism tests, live-match safety, migrations)
- [x] Phase A: MM:SS clock, 5-minute halves, LiveSession, protocol v2, half-time, speeds, OVR beside the live rating in the subs panel, player card
- [x] Phase F1: restart state machine (setup times, set-piece layouts, 5 attackers at corners, substitutions at stoppages)
- [ ] Phase B1: calibration pass 1. **Partial**; the rest is in Step 2
- [ ] Phase C1: tactical guardrails. `tactics.yaml` costs and the turnover reaction delay are written; the rest is in Step 1

## Step 0: secure and tool up

- [x] 0a Branch `phase-1-match-believability`; golden values re-captured; checkpoint committed and pushed (24207eb)
- [x] 0b Tooling: plugins (`pyright-lsp`, `typescript-lsp`, `context7`), the `chrome-devtools` MCP, project agents and skills, `CLAUDE.md`, `pyrightconfig.json`, and the plans in `docs/plans/`

## Step 1: finish C1

- [x] 1.1 Harness CIs: a ±95% CI column, and paired CIs for A/B differences
- [x] 1.2 `ManagerAI`: reads the opponent from observed behaviour; an assistant toggle; events and commentary; tests
- [ ] 1.3 C1 A/B at 200 paired fixtures per arm, against section S (costs tuned if needed). **Measured in the cloud (synthetic equal sides, 94d5de3): fails section S.** Aggressive +1.07 goal difference and +23 points of win rate; direct passing alone +0.91; fast, press and high line now too costly (−0.44 to −0.62). The report and its verdict are in `docs/calibration/20260929T195539-synthetic-n200-q58-66-equal-ab.md`. Much of direct play's edge comes from the opponent's leaky build-up, so **fix 2.3 first**, then re-run C1 on Grimsby at the head and tune costs from there. Check `reports/engine/` for the Grimsby runs from before the limit
  - **Grimsby on real squads agrees (local, b6dce71, ENG4, seed 11, 200 paired per arm, opponents' managers on).**
    - All-aggressive: +0.89 goal difference, +21.5 win points. Its costs pass: xG against +12%, fast-break shots against ×3.3, stamina −5.7.
    - Direct: +0.79 / +23.5. High line −0.57, press −0.40, fast −0.35. Attacking, wide and all six cautious settings are within limits.
    - With every manager off, aggressive was +1.59 / +36.5: the opponent going long against the press halves the exploit.
    - Reports: `reports/engine/20260929T171031-ENG4-n200-ab-nomanager`, `…T181944-ENG4-n200-ab` (bold), `…T221425-ENG4-n200-ab` (cautious), local only.
  - **Next for 1.3:** after 2.3, re-run both sets of Grimsby arms at the new head. Remove slow tempo's `hurry: -0.1` accuracy bonus, then tune costs mechanism-first (`continuation-plan.md`, "C1").
    - Direct's edge today is almost all defensive: shots against −4.65, xG against −0.40.
- [ ] 1.4 Golden values re-captured; commit and push; restart the :8000 game

## Step 2: close the B1 gaps

- [ ] 2.1 Home advantage (referee and crowd mechanisms), fitted to the real home, draw and away split. **Now done after 2.4:**
  - one set of values for every league;
  - 400 matches each in ENG4 and ENG1, seed 31, pooled for `home_goal_diff`. **Mechanisms in (cloud), values provisional:** `home_advantage.yaml` (referee foul and card bias, crowd decision noise and pass error under pressure, each split evenly between the sides so totals stay put), `MatchEngine.venue_bias`, and the `home_goal_diff` and `away_card_gap` metrics and targets. (The earlier cloud idea of fitting on unequal synthetic sides is replaced by the real-squad fit above.) The manager still reads a press correctly with it on: 15/15 high presses spotted and 1/18 false alarms (20 seeds, 25-minute reads)
- [x] 2.2 Interceptions separated from recoveries in stats, ratings and commentary (cloud). **Finding:** the counting was only a small part of the problem. Two full 64 v 64 matches had 82 interceptions, 4.5 recoveries and 5 clearances a match (real interceptions: 14–26). The engine really does cut out about 80 passes a match, so the excess is behaviour, not labels, and goes to 2.3 and D
- Fixed (cloud): `duels._counter_on` and `gain_possession` read `eng.possessions` (rule 7). They now read `eng.possession_start`, simulation state set at the same moment. Behaviour is unchanged (the golden values hold)
- [ ] 2.3 Build-up leak: high regains broken down by cause; decision-level causes fixed. **Diagnosed and measured (cloud):** it's physics, not decisions. Passers' estimates are honest, but opponents cut out about 8% of passes (real about 2%). `passing.yaml` `intercept_scale` 0.35 against 1.0 (synthetic sides, 200 paired matches): interceptions 68→29, high regains 57→36, throw-ins 19→26, ball in play 73→69 min, fast-break shots 1.4→3.5%, but goals 2.43→2.14 and offsides 19→39. Not applied: tune it on real squads from about 0.3, then long-pass execution error. See `docs/calibration/20260929T202538-step2.3-intercept0.35-synthetic-n200.md`
  - **Real squads at 0.3 (local, b548f33, seed 21, 200 each).**
    - ENG4: interceptions 74→34, high regains 58→36, goals 2.00→2.13, but offsides 6→21.
    - ENG1: interceptions 65→30, high regains 47→25, goals 3.92→3.15, shots 40→30, throw-ins 13→22, but offsides 8→27 and fouls 22→16.5.
  - **Why offsides exploded:** all 107 calls in three diagnostic matches were sprinting forward runners, a median 2.0 m past the line. A sprinting player never slowed down, so runners overshot their mark (line − 1 m).
  - **Fixed:** runners holding the line now ease off to stop on their mark. Chasers and the ball carrier keep full speed. Offsides went from about 36 to 5 a match on synthetic sides at 0.3.
  - **With the fix, at 65b3b8f (seed 21, 200 each).**
    - 0.3 → ENG4: interceptions 36, high regains 37, offsides 6.0, goals 2.26, shots 24.4. ENG1: 32, 26, 4.6, 3.55, 40.
    - 0.2 cut interceptions only about 3 more (33 and 30), while ENG1 goals rose to 3.97.
  - **Why 0.2 barely helps:** an opponent near a pass took it with probability max(0.05, p), and intercept_scale never touched that 5% floor. Now it scales the floor for opponents too (inert at 1.0: golden values unchanged).
  - **Rounds 4–5** (local, 50e3cf1, seed 21, 200 each, both divisions). The variants:
    - f030: 0.3 with the floor fix;
    - f030e1: plus per_metre 0.004 and length_per_metre 0.014;
    - f020e2: 0.2 with 0.008 / 0.022;
    - f020e3: 0.2 with 0.012 / 0.032.
  - **What they show:**
    - 0.2 lands interceptions in both divisions (about 20 ±0.7).
    - Long-ball error lands ENG1's accuracy and throw-ins only by overshooting its goal kicks (24–26), and it needs implausible length spreads.
    - It can't make weaker passers less accurate: synthetic 62- and 78-rated sides both complete 94% of short passes.
    - The table and its reading are in `continuation-plan.md`, status section 5.
  - **Why (30 Sep diagnostics and design review): the passing physics hides the ratings.**
    - The receiver is sent to the true landing point at the kick.
    - Heavy touches are re-gathered at once and count as complete.
    - Passes are slow, and the estimate misjudges their timing.
    - The estimates ignore `passing.yaml`, and at 0.2 they overrate crosses (45–48% estimated against 20–23% completed).
    - So 2.3 continues as 2.3a–2.3e, as the plan describes.
  - [x] **2.3a Measure (behaviour-neutral).** Split into four checkpoints. Summary: `docs/calibration/20260930-step2.3a-summary.md`:
    - [x] Part 1, probe metrics: pass bands and outcomes, the reliability table, failure causes, travel times, heavy touches, offside kinds, rates per minute of ball in play, and possessions ending in a shot
    - [x] Part 2, targets and report: `kind` rate / volume / reference; volumes judged per minute of ball in play; references listed separately; the reliability table in the report; the synthetic quality sweep
    - [x] Part 3, refactors: the `pass_error()` helper, one aerial-score helper, `control.touch_skill` (bit-identical), and the no-league-names guard test
    - [x] Part 4, measurements: the ENG1–ENG4 ratings gap, the Metrica pass-pace reference, and the 2.3a reference batch
  - The original 2.3a list:
    - pass bands, the reliability table, failure causes, travel times, heavy touches, offside tags;
    - rates per minute of ball in play, and rating responses (a synthetic quality sweep, 58/66/74/82);
    - the ENG1–ENG4 ratings gap, and a pass-pace reference from Metrica's open data;
    - `match_targets.yaml` tagged rate / volume / reference;
    - the refactors, and the no-league-names guard test (it checks keys, values and code, not comments citing real-world sources).
    - The f020e2 re-run must reproduce round 5 exactly.
  - [x] **2.3b Physics shortcuts,** in two checkpoints:
    - [x] Part 1, reception (code): the read delay from anticipation, the re-touch lockout, crosses landing clear, and no completion for a passer's own re-gather. Tests pass; golden values re-recorded. Measured: accuracy ENG4 .819 / ENG1 .815; quality gradient 0.5 → 2.1 points; high regains up to 47 / 36. See `docs/calibration/20260930-step2.3b1-reception.md`
    - [x] Part 2, pass pace: `pace.arrive` 6.0 + 0.17 m/s per metre (friction 4.0), matching Metrica's travel times. Interceptions 16 / 16 (in range); high regains 42 / 31; ENG1 throw-ins too many (a recorded conflict). See `docs/calibration/20260930-step2.3b2-pace.md`
  - [ ] **2.3c Honest pass estimates** (WIP, behind `estimate.honest`, off; see the checkpoint for what remains): P_path × p_reach × P_arrive × P_secure, a landing grid for lofted balls and crosses, and a slow honesty test.
  - [ ] **2.3d Offside decisions:**
    - through balls judged at the runner's position;
    - awareness as a risk, not a per-decision re-roll;
    - free-kick positions, if measured.
  - [ ] **2.3e Ratings that matter:**
    - sweep the rating terms (the same values for every league) and check the rating responses first;
    - then measure the league residual. Only if it's justified and bounded, add the league-environment layer with its guard tests;
    - league references are validated last, and conflicts are flagged.
  - [ ] **2.3f Attack against defence, by rating** (new, from 2.3a's quality sweep):
    - equal sides' goals (3.1 to 4.5) and shots (28.5 to 41.2) grow with quality from q58 to q82, where real goals and shots are similar across leagues;
    - trace which creation or finishing mechanic outgrows defending (shot selection, pressure on the shooter, blocks, keepers), then fix it through ratings;
    - behind ENG1's shot excess;
    - do it after 2.3e, measured with the quality sweep.
- [ ] **2.4 Discipline, now done before 2.1** (the card-gap fit depends on foul volume):
  - measure fouls by source, and fix `take_ons`;
  - duels come from situations, adding the missing foul sources (holding a runner, 50-50s, fouls on a shielding carrier, every contested header);
  - DOGSO reds;
  - `booked_caution` applied once, not twice;
  - the aggression > 80 red-card cliff made smooth;
  - fit to fouls per minute of ball in play, and cards per foul;
  - **stale duel engagements** (from 0c's review): `engaged` entries survive between engagements, so a defender meeting the same carrier again skips the sizing-up delay (`duels.py:50-59`). Decide it here, measured, since fixing it changes duel volume.
- [x] 2.5 Teleports down to zero (keeper-catch snaps) (cloud). A saved shot is placed where the keeper can reach it (the same random draw, mapped into his dive window); a keeper with no shot on target in reach is beaten; and he keeps going for the shot until it resolves. Four full matches: 1 of 22 saves needed any correction, and it was 0.4 m (a teleport is over 1.5 m). **Confirmed:** 0 teleports in 400 synthetic matches (0.09 a match before)
- [ ] 2.6 Pre-D baseline reports (ENG1 and ENG4, 200 each) in `docs/calibration/`
- [x] Synthetic players fitted to real ones (handoff section 5, item 7; done early, while batches ran).
  - `footsim fit-synthetic` fits each position's attributes to real players: attribute = a + b × overall, plus the spread, over 17,847 players.
  - It writes only those aggregates to `data/config/calibration/synthetic_attributes.yaml`.
  - A synthetic centre-back is now as aggressive as a real one (it was 10 below its overall), and a striker tackles like one.
  - Golden values: Mac re-recorded, Linux deleted.

## Step 3: Phase D, dynamic movement

- [x] D0 Debug overlay (`?debug=1`): team phase and lines, offside line, targets (red when sprinting), pressers, the ball carrier's five best options with scores, and a text panel. Built early, while the Step 2.3 batches ran; `frontend/e2e/debug.mjs` checks it
- [ ] D-pre Vectorise `update_targets` in two behaviour-neutral commits (golden values unchanged). Today it takes 3.3 s of a 6.6 s match; the target is 1.5 s or less
- [ ] D1 `phases.py`: team phases with hysteresis. D1a is behaviour-neutral: `PhaseState` and `movement.yaml` with today's thresholds, plus flicker metrics. D1b adds the margin, dwell and blending
- [ ] D2 `shape.py`: TeamShape (line heights, compactness, width, ball-side shift, cover depth)
- [ ] D3 `intents.py`: MovementIntent; role runs; `press_bias`, `hold_line`, `track_runners`
- [ ] D4 Structural jobs in possession (width, depth, support, rest defence, box occupation)
- [ ] D5 Positional discipline
- [ ] D6 Defending: runner handover, curved pressing runs, cover man, far full-back tuck, holding midfielder screen
- [ ] D7 Movement speed bands, turning, stamina drain by band
- [ ] D gates (section S), an acceptance report, and a restart of the :8000 game

## Step 4: Phase E, transitions

- [ ] E Counter-press, rest-defence delay, recovery sprints, the ball-winner's first action, runners and support
- [ ] E gates: fast breaks give 6–12% of shots; the aggressive setup concedes at least 30% more fast-break shots

## Step 5: the remaining phases, in the approved order

- [ ] C2 Full TacticalState, a utility-based manager, and the A/B suite at 400+ paired matches
- [ ] F2 Set-piece routines, marking schemes, long throws, goal-kick patterns, and set-piece UI
- [ ] B2 1,000-match acceptance, the fast engine as a surrogate, cross-engine tests
- [ ] G Substitution windows and the queued-substitution UI
- [x] H Other-club pages (done early, while the C1 batches used the CPU)
- [ ] I Sim-to-date
- [ ] J Match analytics
- [ ] K Full validation (10,000 matches); then reassess before transfers and other management systems

## Acceptance checks

The user's 12 questions, answered at the end of each phase:

1. A believable normal match?
2. Aggressive tactics have downsides?
3. A formation change is visible?
4. Natural movement?
5. Transitions look different?
6. Corners set up?
7. Goal kicks and throw-ins are real restarts?
8. The best substitute can be picked from the ratings?
9. Another club's squad can be viewed?
10. Sim to a date?
11. About 5 minutes per half?
12. Plausible statistics?

| Phase | Date | Answers and notes |
|---|---|---|

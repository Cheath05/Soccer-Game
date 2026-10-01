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
- **Checkpoint commit:** 0f96176, **WIP**: Step 2.3c iteration 2, still behind `estimate.honest` (off). The commit right after it only filled in this hash.
  - Earlier: iteration 1 eeb5239; 2.3b complete at d7ccf17; 2.3a a9a8ced.
- **Engine:** behaviour unchanged. With the switch off, the game plays exactly as at d7ccf17, and the golden values pass unchanged.
- **Done in iteration 2** (from the reviewer's notes on iteration 1):
  - `_run_distance`: receivers and chasers move as `_move_players` runs an urgent player (top speed from stamina, own acceleration), replacing a flat 0.9 share.
  - The receiver runs for the intended point during his read delay, and only the ground beyond that is slack for a pass that's off.
  - A keeper in his own box reaches 2.4 m and gathers about 95%.
  - Only defenders already at a dropping ball, plus the one quickest to it, contest it.
  - Short throws are estimated with skill 85, as `start_pass` plays them.
- **Quick check with the switch on** (`scratchpad/honesty_check.py`: 6 synthetic matches, f020e2 settings; indicative):
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
- **What remains for 2.3c, in order:**
  1. Ground passes overrated by 6–10 points. Likely causes:
     - the marker closes in during the pass, so first-touch pressure at arrival is higher than at the decision; use the marker's closing distance by the arrival;
     - about 5% of passes are gathered late or loose;
     - the flat re-gather [0.65, 0.2] may be generous.
  2. Crosses underrated by about 13 points: check `_landing_chance` for crosses against `_aerial`'s attackers-near rule.
  3. Calibrate the decision values, as above.
  4. Then the reliability table within ±5 points per decile **and** the pass mix in range. Then the slow honesty test, switch it on, a 200-match measurement, golden values, delete `_heuristic_success`, and commit.
- **Tests:**
  - `just lint` is clean;
  - all 139 backend tests pass;
  - the golden values are unchanged.
- **Next task:** 2.3c remaining items 1–4 above. The quick check recipe:
  - `cfg-dev` = the checkout's `data/config`, with `intercept_scale` 0.2, `per_metre` 0.008, `length_per_metre` 0.022 and `honest: true`;
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
- **Play-testing:**
  - :8000 is the user's game. Its backend process dates from 28 Sep, the Phase A era, so it has none of this session's work.
  - To play the latest commit, run `cd frontend && npm run build`, then restart :8000 with the `run-footsim` skill once `lsof -nP -iTCP:8000 -sTCP:ESTABLISHED` shows no connections.
  - Automated checks use a throwaway :8765 with a temporary `FOOTSIM_SAVES_DIR`; none is running now.
  - **Note:** this is an intermediate calibration state.
- **Housekeeping:** `stash@{0}` (local 2.1/2.2/2.5 work from before the cloud merge) is superseded by the cloud versions and can be dropped.

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

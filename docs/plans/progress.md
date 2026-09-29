# Match believability: progress

Resume from the first unticked item.
- The order of work and its details are in `recovery-and-continuation.md`.
- The design is in `match-believability.md`; section letters (for example "section S") refer to it.

Every sub-step ends the same way:
1. `engine-reviewer` checks the diff;
2. lint and tests pass;
3. the golden values are re-captured if behaviour changed on purpose;
4. this file is ticked;
5. commit and push to `phase-1-match-believability`.

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
- [ ] 1.4 Golden values re-captured; commit and push; restart the :8000 game

## Step 2: close the B1 gaps

- [ ] 2.1 Home advantage (referee and crowd mechanisms), fitted to the real home, draw and away split. **Mechanisms in (cloud), values provisional:** `home_advantage.yaml` (referee foul and card bias, crowd decision noise and pass error under pressure, each split evenly between the sides so totals stay put), `MatchEngine.venue_bias`, and the `home_goal_diff` and `away_card_gap` metrics and targets. Still to do: fit the values with 400-match batches on unequal synthetic sides (`--quality 58-66`, no `--equal`). The manager still reads a press correctly with it on: 15/15 high presses spotted and 1/18 false alarms (20 seeds, 25-minute reads)
- [x] 2.2 Interceptions separated from recoveries in stats, ratings and commentary (cloud). **Finding:** the counting was only a small part of the problem. Two full 64 v 64 matches had 82 interceptions, 4.5 recoveries and 5 clearances a match (real interceptions: 14–26). The engine really does cut out about 80 passes a match, so the excess is behaviour, not labels, and goes to 2.3 and D
- Fixed (cloud): `duels._counter_on` and `gain_possession` read `eng.possessions` (rule 7). They now read `eng.possession_start`, simulation state set at the same moment. Behaviour is unchanged (the golden values hold)
- [ ] 2.3 Build-up leak: high regains broken down by cause; decision-level causes fixed. **Diagnosed and measured (cloud):** it's physics, not decisions. Passers' estimates are honest, but opponents cut out about 8% of passes (real about 2%). `passing.yaml` `intercept_scale` 0.35 against 1.0 (synthetic sides, 200 paired matches): interceptions 68→29, high regains 57→36, throw-ins 19→26, ball in play 73→69 min, fast-break shots 1.4→3.5%, but goals 2.43→2.14 and offsides 19→39. Not applied: tune it on real squads from about 0.3, then long-pass execution error. See `docs/calibration/20260929T202538-step2.3-intercept0.35-synthetic-n200.md`
  - **Real squads at 0.3 (local, b548f33, seed 21, 200 each).**
    - ENG4: interceptions 74→34, high regains 58→36, goals 2.00→2.13, but offsides 6→21.
    - ENG1: interceptions 65→30, high regains 47→25, goals 3.92→3.15, shots 40→30, throw-ins 13→22, but offsides 8→27 and fouls 22→16.5.
  - **Why offsides exploded:** all 107 calls in three diagnostic matches were sprinting forward runners, a median 2.0 m past the line. A sprinting player never slowed down, so runners overshot their mark (line − 1 m).
  - **Fixed:** runners holding the line now ease off to stop on their mark. Chasers and the ball carrier keep full speed. Offsides went from about 36 to 5 a match on synthetic sides at 0.3.
  - **Next:** real-squad batches at 0.3 and 0.2 on the new head, then long-pass execution error.
- [ ] 2.4 Red cards measured after the booked-player caution change
- [x] 2.5 Teleports down to zero (keeper-catch snaps) (cloud). A saved shot is placed where the keeper can reach it (the same random draw, mapped into his dive window); a keeper with no shot on target in reach is beaten; and he keeps going for the shot until it resolves. Four full matches: 1 of 22 saves needed any correction, and it was 0.4 m (a teleport is over 1.5 m). **Confirmed:** 0 teleports in 400 synthetic matches (0.09 a match before)
- [ ] 2.6 Pre-D baseline reports (ENG1 and ENG4, 200 each) in `docs/calibration/`
- [x] Synthetic players fitted to real ones (handoff section 5, item 7; done early, while batches ran).
  - `footsim fit-synthetic` fits each position's attributes to real players: attribute = a + b × overall, plus the spread, over 17,847 players.
  - It writes only those aggregates to `data/config/calibration/synthetic_attributes.yaml`.
  - A synthetic centre-back is now as aggressive as a real one (it was 10 below its overall), and a striker tackles like one.
  - Golden values: Mac re-recorded, Linux deleted.

## Step 3: Phase D, dynamic movement

- [x] D0 Debug overlay (`?debug=1`): team phase and lines, offside line, targets (red when sprinting), pressers, the ball carrier's five best options with scores, and a text panel. Built early, while the Step 2.3 batches ran; `frontend/e2e/debug.mjs` checks it
- [ ] D1 `phases.py`: team phases with hysteresis
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

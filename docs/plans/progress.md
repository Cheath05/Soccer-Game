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
- [ ] 1.3 C1 A/B at 200 paired fixtures per arm, against section S (costs tuned if needed)
- [ ] 1.4 Golden values re-captured; commit and push; restart the :8000 game

## Step 2: close the B1 gaps

- [ ] 2.1 Home advantage (referee and crowd mechanisms), fitted to the real home, draw and away split
- [ ] 2.2 Interceptions separated from recoveries in stats, ratings and commentary
- [ ] 2.3 Build-up leak: high regains broken down by cause; decision-level causes fixed
- [ ] 2.4 Red cards measured after the booked-player caution change
- [ ] 2.5 Teleports down to zero (keeper-catch snaps)
- [ ] 2.6 Pre-D baseline reports (ENG1 and ENG4, 200 each) in `docs/calibration/`

## Step 3: Phase D, dynamic movement

- [ ] D0 Debug overlay (`?debug=1`)
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

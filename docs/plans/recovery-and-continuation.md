# Recovery and Continuation: Match Believability Phase

## Context

**What happened.**
- The last session got this same request on 28 Sep at 22:44.
- It inspected the code, ran 492 instrumented matches and wrote `~/.claude/plans/i-want-to-build-fizzy-lynx.md` (sections A–V). You approved it unchanged at 23:18.
- It then implemented that plan in order until 02:46. The session ended while it was writing the in-match AI manager (`manager.py`).

**That approved plan stays the design reference.** This plan doesn't redesign anything. It covers four things:
- securing the recovered work;
- adding tooling that makes the rest of the work faster and safer;
- fixing gaps found while recovering it;
- the order for resuming.

**Your decisions (29 Sep):**
- Commit and push the recovered work to a new branch, then commit and push after every step.
- The interrupted AI manager was part of the crash, so build it.
- Keep going through the phases without pausing, and add whatever Skills, subagents, plugins and MCP servers help.

**Where the work is.**
- **Everything is uncommitted** in `/Users/alexbenton/Developer/Soccer-Game`, on branch `phase-0-foundation` (3a7fa33, level with origin).
  - 23 files are modified (+1,011 / −946 lines) and 36 are new (~3,800 lines).
  - It exists only on this disk: none of it is committed or pushed.
- The folder open in VS Code, `…/Soccer-Game/Soccer-Game`, is not the project.
  - It's a fresh clone of `main` made at 02:50 and holds only the initial README.
  - There's nothing to recover from it. It shows up as an untracked folder inside the real checkout and will never be staged.
- The game on port 8000, started by the old session, still runs the Phase A code.

**Checked today (read-only):**
- ruff and strict mypy are clean (98 files), and the frontend `tsc` is clean.
- **pytest: everything passes except the two golden-seed tests** (`tests/unit/test_engine_golden.py`).
  - Those tests pin exact scores, and the B1 duel and passing changes made them stale.
  - That's expected: they're meant to be re-captured deliberately when behaviour changes on purpose.
- One headless match takes 6.7 s (about 8,800 ticks/s), inside the 8 s budget.

### Phase status

| Phase (approved order) | Status |
|---|---|
| 0: Measure and make safe | **Done.** `probe.py`, `log.py`, `calibrate-engine` and `match_targets.yaml`; synthetic teams (`match/synthetic.py`); golden and determinism tests; live-match registry, double-record guard and autosave; migrations to schema v3 |
| A: Clock and 5-minute halves | **Done.** `clock.py`; `match/live/session.py` (LiveSession); protocol v2; MM:SS clock with added time; half-time panel; 0.5×–8× and Instant; subs panel with OVR beside the live rating; player card |
| F1: Restart state machine | **Done.** `restarts.py`, `set_pieces.py` and `restarts.yaml`; realistic restart waits; 5 attackers in the box at every corner; substitutions wait for a stoppage |
| B1: Calibration pass 1 | **Partial.** `duels.py` and `duels.yaml`, `passing.yaml`, and shot selection. The gaps are listed below |
| C1: Tactical guardrails | **Code written, not measured.** `tactics.yaml` (a cost on every setting), `MatchEngine.effect()`, a reaction delay after turnovers (`behaviours._react`) and counter runners. Still missing: the in-match AI manager and the A/B measurement |
| D, E, C2, F2, B2, G, H, I, J, K | Not started |

### Where calibration stands

The last full batch was 70 Premier League matches, run at 02:31, before the booked-player fix and C1.

**Already on target:**
- fouls 21.8 and yellow cards 4.4;
- own goals 4.7% and set-piece goals 25% of all goals;
- 5.0 attackers in the box at corners, and every restart wait;
- match length 98 min, distance 107 km per team and save rate 72%.

**Still off:**

| Metric | Engine | Target |
|---|---|---|
| Goals | 3.61 | 2.65–3.05 |
| Shots | 41.5 | 23–27.5 |
| High regains | 46 | 11–17 |
| Interceptions | 70 | 14–26 |
| Throw-ins | 12 | 32–42 |
| Ball in play | 68 min | 54–60 min |
| Red cards | 0.39 | 0.08–0.18 |
| Offsides | 6.4 | 2.5–4.5 |
| Pass accuracy | 87% | 80–85% |
| Shots from fast breaks | 0.9% | 6–12% |
| Teleports | 0.07 | 0 |

### What recovery turned up

1. **The agent engine has no home advantage.**
   - `MatchEngine.neutral` is stored but never read; only the fast engine applies `home_advantage: 1.15`.
   - Across the session's runs, home and away wins came out about level (42% against 38%). Real football is 41–47% home wins against 28–35% away.
2. **B1 was tuned on noise.**
   - Each batch was 70 matches on a different seed, so goals moved between 3.3 and 4.7 from run to run, with a standard error of about ±0.2.
   - The approved method, 200 paired matches, was skipped for speed.
3. **The build-up leaks.**
   - Each team concedes about 23 high regains a match, against a real ~7, so teams keep losing the ball near their own goal.
   - 78% of box entries end in a shot, and shots rose from 31 to 41 during B1.
   - This is the "turnovers in dangerous areas" suspect from your list. Part of it is decision-making, which can be fixed now; part is structure, which is Phase D.
4. **"Interceptions" is a counting bug, and it leaks into ratings and commentary.**
   - `actions._take` labels any opponent collecting a pass as an interception, including an overhit or misplaced one, and commentates "reads it and intercepts" for all of them.
   - Clearances are also credited as interceptions (`actions.py` around line 665).
   - Opta counts these as ball recoveries.
   - `match/ratings.py` adds 0.07 per interception, so the live ratings in the subs panel are inflated for defenders.

---

## Step 0a: Secure the recovered work (before any code change)

1. Work only in `/Users/alexbenton/Developer/Soccer-Game`. Leave the nested clone untouched: you can delete it and reopen VS Code on the parent folder.
2. `git switch -c phase-1-match-believability`. The uncommitted work comes along.
3. Re-capture the golden values, and add "duel model, pass execution, tactics costs (B1/C1)" to the History note in the test's docstring.
4. Get `just lint` and the full `uv run pytest` green.
5. Commit with explicit paths (`backend frontend data/config justfile`) so the nested `Soccer-Game/` folder is never staged. The message records the phase status above.
6. Push with `-u origin phase-1-match-believability` as an off-machine backup.

## Step 0b: Tooling (your request), then commit and push

Everything here is chosen for a concrete use later in this plan.

**Plugins** from Anthropic's official marketplace (`anthropics/claude-plugins-official`). Add the marketplace with the bundled CLI (`…/anthropic.claude-code-2.1.284-darwin-arm64/resources/native-binary/claude plugin marketplace add …`), then install:
- **`pyright-lsp`: go-to-definition, find-references and type errors across the ~6,000-line engine.**
  - Most needed while Phase D splits `behaviours.py` into new modules.
  - Needs the language server installed: `npm install -g pyright`.
  - A repo-root `pyrightconfig.json` points it at `backend/.venv` in basic mode, so strict mypy stays the gate.
- **`typescript-lsp`:** the same for the match viewer. Needs `npm install -g typescript-language-server typescript`.
- **`context7`:** current documentation for the fast-moving frontend stack (Mantine 9, TanStack Router and Table, React 19). Mostly for phases G to J.

**Browser MCP server: `chrome-devtools`** (`chrome-devtools-mcp`), user scope, headless, with an isolated profile. Chrome is already installed.
- Lets me open the viewer and take timed screenshots, read the clock and click controls.
- Also reads console errors, inspects the live WebSocket, and records performance traces at 8×.
- This is how I check the visual gates (shape changes, corners setting up, no teleports, the debug overlay) against the :8765 test server, instead of trusting numbers alone.

**Project subagents** (`.claude/agents/`, committed):
- **`engine-calibrator`** (Sonnet; runs commands and reads files, never edits):
  - runs `just calibrate-engine` batches and A/B arms in the background while I keep coding;
  - compares each run with the previous report;
  - returns a compact table with CIs and verdicts against `match_targets.yaml`;
  - enforces at least 200 paired fixtures and one heavy batch at a time.
- **`match-investigator`** (read-only on source; scratch scripts only):
  - reproduces a match from its seed (or fixture) and runs it to a given clock time;
  - explains an event from the engine log, the positions and, after D, the phases and intents;
  - first jobs: the build-up leak and the remaining teleports.
- **`engine-reviewer`** (read-only): reviews each sub-step's diff against this project's invariants before the commit:
  - determinism: no wall-clock time, all randomness through `eng.rng`, nothing that depends on set ordering;
  - tactics change behaviour, never ability;
  - constants live in YAML;
  - players move only through targets (no teleports);
  - per-tick work is vectorised, within the 8 s budget;
  - the golden-value policy is followed.

**Project skills** (`.claude/skills/`, committed):
- **`calibrate-engine`:**
  - the commands and flags;
  - the standard arms: your all-aggressive string, and Grimsby as club 218 in ENG4;
  - batch-size rules and how to read the CIs;
  - metric definitions and their caveats;
  - where acceptance reports go.
- **`run-footsim`:**
  - rebuild and restart the :8000 game safely, checking for unsaved state first;
  - run a throwaway :8765 server with `FOOTSIM_SAVES_DIR=<temp dir>`;
  - run `e2e/smoke.mjs` and `e2e/live.mjs`.
  - The built-in `run` skill looks for exactly this kind of project skill.
- **`repro-match`:** replay a match from its seed (plus the LiveSession command log for a watched match), jump to a clock time, and dump the events and positions.

**Orientation files** (committed), so a crash costs minutes, not hours:
- **`CLAUDE.md` at the repo root:** the real checkout path, the branch, commands, working rules, and pointers to the plan files. It loads even from the nested clone, because Claude Code reads CLAUDE.md files in parent folders.
- **`docs/plans/`:**
  - `match-believability.md`, the approved plan;
  - `recovery-and-continuation.md`, this plan;
  - `progress.md`, a checklist ticked at every sub-step. A new session resumes from the first unticked item.
- **`.gitignore`** gains `.claude/settings.local.json`.
- **Memory** records your preferences: commit and push every step, keep going, use tooling. It also records where the real checkout is.

**When they take effect.** Plugins and MCP servers load when a session starts, and project agents and skills load from the folder VS Code has open.
- All of it becomes fully active in the next session opened on `/Users/alexbenton/Developer/Soccer-Game`.
- Until then, this session keeps going and delegates through the general-purpose agent, pointed at the same agent files.

## Step 1: Finish C1 (the exact point the crash interrupted)

1. **Confidence intervals in the harness** (`calibration/engine_batch.py`).
   - Add a ±95% CI column to the baseline table.
   - Add CIs on the paired differences between A/B arms. The arms already replay identical fixtures and seeds.
2. **In-match manager: `match/engine/manager.py`** (`ManagerAI`), built from the recovered draft.
   - **When it reviews:** every 5 match minutes, and after every goal or red card.
   - **Ahead from 70':** slower tempo, a step deeper (defensive when one goal up), and no more high pressing.
   - **Behind from 70':** attacking mentality and fast tempo. From 82' it also goes direct and presses high.
   - **One change from the draft:** it judges the opponent only from what it can observe. It samples once a second and uses the last 5 minutes of two things: the opponent's average back-line height, and how many opponents close down its ball carrier. The draft read `eng.instructions[rival]`, which is your tactics screen.
   - **It only calls `eng.set_instruction`,** the same path your commands use, so no player ability ever changes.
   - **Wiring:**
     - `MatchEngine(..., ai_manager=(home, away))`, ticked from `_clock`;
     - `world/career.agent_match` switches it off for your side;
     - an `assistant` command in `LiveSession`, plus a toggle on the live page (same pattern as Auto subs in `SubsPanel.tsx`), lets you hand your side to it;
     - every change emits an event and a commentary line, such as "<Club> throw more men forward".
   - **Tests:**
     - a trailing side changes approach late;
     - a leading side slows the game down;
     - switched off, instructions never change;
     - results stay deterministic with it on.
3. **Measure C1.**
   - Grimsby (club 218) in League Two, 200 paired fixtures per arm.
   - Arms: default; your all-aggressive setup; each instruction at its extreme; and all-aggressive against opponents with the manager off and then on.
   - **Pass marks** (from section S):
     - a single instruction changes goal difference by at most ±0.35 and win rate by at most 10 points;
     - the all-aggressive setup gains at most +0.6 goal difference and +15 points of win rate;
     - it concedes at least 10% more xG;
     - its players finish with at least 5 points less stamina at 90'.
   - The "more fast-break shots conceded" check waits for Phase E, because fast breaks are only ~1% of shots today.
   - Where a setting is over the line, add costs in `tactics.yaml`, `duels.yaml` or `passing.yaml`. Never subtract ability.
4. Re-capture the golden values, then commit and push "C1".
5. Rebuild the frontend and restart the :8000 game, after checking it has nothing unsaved, so you can replay the aggressive setup whenever you like. Carry straight on to Step 2.

## Step 2: Close the B1 gaps that skew every later measurement

1. **Home advantage, built from real mechanisms rather than a strength bonus.**
   - Parameters go in a new `data/config/match/home_advantage.yaml`, loaded as `HomeAdvantageDef` in `defs/match.py`. Neutral venues skip it.
   - **Referee:** fouls and cards are given against the away side a little more readily, decided in `duels.py`. Studies of matches behind closed doors found that crowds mainly bias card decisions (see Sources).
   - **Crowd:** the away side gets slightly more decision noise and execution error when under pressure.
   - Fit both to the real home/draw/away split and home goal difference in `match_targets.yaml`. B2 later puts the fast engine on the same parameters.
2. **Interceptions vs recoveries** (`actions._take`, `probe.py`).
   - A pass counts as intercepted only when the defender got into its path before it reached the target area. Otherwise it's a recovery, and a clearance counts as a clearance.
   - Commentary names the real event.
   - This corrects the player stats, the match ratings built from them, and the subs panel.
3. **The build-up leak.**
   - Break high regains down by cause (heavy touch, short pass cut out, goal kick lost, tackle) and by who lost the ball.
   - Fix the decision-level causes now, in `actions.decide` and its pass options. One likely example: a pressed centre-back or keeper passing short into the press instead of going long or clearing.
   - Structural causes, such as a lack of support angles, go to Phase D.
4. **Discipline:** measure the booked-player caution change against the red-card target.
5. **Teleports:** find the remaining source from the probe's teleport records and fix it to zero.
6. **Pre-D baseline:** 200 matches each in ENG1 and ENG4, saved under `docs/calibration/`.
7. **Not tuned here:**
   - Throw-ins and ball-in-play time. The cause is too few stoppages, not restarts that are too short; revisit after D changes how play reaches the touchlines.
   - Shots and goals, which should move with Phase D.

## Step 3: Phase D, dynamic movement (approved plan section I)

Every sub-step ends with lint, tests, a golden re-capture, a 200-match report and a commit.

- **D0 ★ Debug overlay first.** It moves up from section Q because it's the tool for building D.
  - Switched on with `?debug=1` or a Developer toggle.
  - The engine adds a debug block to frames only when asked, through a LiveSession `debug` command.
  - It shows:
    - the phase and restart state;
    - the team lines and offside line;
    - each player's target, intent and discipline;
    - pressing assignments;
    - the ball carrier's top options with their scores.
- **D1: `phases.py`.**
  - The team phases:
    - in possession: BUILD_UP, PROGRESSION, FINAL_THIRD;
    - out of possession: HIGH_PRESS, MID_BLOCK, LOW_BLOCK;
    - ATTACKING_TRANSITION, DEFENSIVE_TRANSITION and SET_PIECE.
  - Hysteresis stops a team flickering between phases.
  - This replaces `behaviours._phase`. The formation YAML phase offsets stay keyed by the six settled phases, and the transition phases blend between them.
- **D2: `shape.py` (`TeamShape`).**
  - The back line's height comes from the line instruction, the ball, offside and danger.
  - When defending, the lines keep 10–15 m apart and the block is 40–45 m wide. In possession, width follows the width instruction.
  - The block shifts towards the ball, and the far side narrows more.
  - The far centre-back sits 1–3 m deeper as cover, and a defender steps out when a forward drops into his zone.
  - Slot anchors are mapped onto these lines, replacing the single back/front stretch in `behaviours._team`.
- **D3: `intents.py` (`MovementIntent`).**
  - Each intent has a target generator, an urgency band, a minimum and maximum duration, and hysteresis.
  - Role data that is defined in YAML but unused today becomes real:
    - the runs in `RunType` (in behind, overlap, underlap, invert, drop deep, drift wide, arrive late);
    - `press_bias`, `hold_line` and `track_runners`.
- **D4: Structural jobs in possession.**
  - The jobs:
    - a width provider on each flank and a depth provider;
    - two ball-side supports;
    - a rest defence, sized by mentality;
    - in the final third, 2–4 players in the box plus one on the edge and one for cut-backs.
  - Jobs are reassigned about every 2 s with `scipy.optimize.linear_sum_assignment`, which `set_formation` already uses. The assignment weighs distance, role fit and discipline.
- **D5: Positional discipline,** from 0 to 1, built from role `freedom` and the decisions, teamwork, concentration and positioning attributes.
- **D6: Defending.**
  - Runners are handed over between zones.
  - Pressers curve their run to cut the passing lane, with a cover man 5–8 m behind them.
  - The far full-back tucks in, and the holding midfielder screens the defence.
- **D7: Movement.**
  - `_move_players` uses speed bands: walk 1.5 m/s, jog 3.5, run 5.5, and sprint at the player's own top speed.
  - Turning depends on agility and balance, and stamina drains by speed band.
- **Gates (section S):**
  - line set to high raises the back line by 6–10 m;
  - width set to wide spreads the team 6–10 m wider in possession;
  - a high press brings the nearest defender at least 1.5 m closer to the ball;
  - a formation change settles within 8 s;
  - no teleports;
  - 4-3-3, 4-4-2 and 4-2-3-1 differ measurably in width, possession, final-third entries and PPDA;
  - a headless match takes at most 8 s, profiled at every sub-step.
- **Expected calibration movement:** fewer shots per box entry, fewer high regains and more throw-ins.

## Step 4: Phase E, transitions (approved plan section J)

Built on D's transition phases and C1's reaction delay.

- **The team that loses the ball:**
  - the nearest 1–3 players counter-press, for as long as the pressing instruction says;
  - the rest defence delays instead of diving in;
  - players caught behind the ball sprint back.
- **The team that wins it:**
  - the ball-winner acts after 0.3–0.8 s, with passes into space weighted up;
  - 1–3 players run in behind and 1–2 support.
- **Tactical fouls** come from the existing `tactical_foul_chance`.
- **Gates:**
  - fast breaks produce 6–12% of all shots;
  - the all-aggressive setup concedes at least 30% more fast-break shots (the check deferred from C1).

## Step 5: The rest, in the approved order

The specifications are in the approved plan: sections H, K, G, L, M, N, Q, R and S.

1. **C2:** the full TacticalState and tactical context, the manager upgraded to utility-based decisions, and the A/B suite at 400+ paired matches.
2. **F2:** set-piece routines, marking schemes, long throws, goal-kick patterns and set-piece instructions in the UI.
3. **B2:** 1,000-match acceptance, the fast engine refitted as a surrogate of the agent engine, and cross-engine tests.
4. **G:** substitution windows and the queued-substitution UI. Most of the ratings work already shipped in A.
5. **H:** other-club pages.
6. **I:** sim-to-date, with jobs and a progress view.
7. **J:** match analytics.
8. **K:** full validation, including 10,000-match runs.

## Working rules (so a crash can't cost more than one step)

- **Cadence (your decision):** keep going through the approved order without waiting. Stop only when a decision genuinely needs you. At the end of each phase, restart the :8000 game so you can play the latest version whenever you like.
- **Every sub-step ends the same way:**
  1. `engine-reviewer` checks the diff;
  2. lint and tests pass;
  3. the golden values are re-captured if behaviour changed on purpose;
  4. `docs/plans/progress.md` is ticked;
  5. commit and push on `phase-1-match-believability`.
- Golden values change only in the commit that intends the change, with the reason in the test's History note.
- **Calibration:**
  - `engine-calibrator` runs batches in the background while the next piece of code is written;
  - every tuning decision uses at least 200 paired fixtures on a fixed seed set, with CIs;
  - phase acceptance uses 1,000 matches;
  - heavy batches run one at a time;
  - acceptance reports go to `docs/calibration/` (not a folder named `reports/`, which `.gitignore` excludes).
- **Visual gates:** checked in the browser through the Chrome DevTools MCP against the :8765 server, with screenshots, alongside the numeric gates.
- **Your saves:** browser tests run against a throwaway server on port 8765 with a temporary saves folder (`FOOTSIM_SAVES_DIR`). Your saves and the :8000 game are touched only to restart the demo at the end of a phase.

## Critical files

- **Engine:** `backend/src/footsim/match/engine/{engine,actions,behaviours,duels,restarts,set_pieces,probe}.py`, plus new `manager.py`, `phases.py`, `shape.py` and `intents.py`.
- **Config:**
  - `data/config/match/{tactics,duels,passing,restarts}.yaml`, plus new `home_advantage.yaml`;
  - `data/config/calibration/match_targets.yaml`;
  - `backend/src/footsim/defs/match.py` and `defs/loader.py`.
- **Live and career:** `backend/src/footsim/match/live/session.py`, `api/live.py` and `world/career.py` (`agent_match`).
- **Harness:** `backend/src/footsim/calibration/engine_batch.py`.
- **Reused as-is:**
  - `MatchEngine.effect()` and `set_instruction()`;
  - `probe.summarize` and `probe.aggregate`;
  - `match/synthetic.synthetic_sheet`;
  - `core/rng.derive_rng`;
  - `linear_sum_assignment`, as `set_formation` already uses it.
- **Tests:** `backend/tests/unit/test_engine_golden.py` and `test_engine_determinism.py`, plus new `test_manager.py` and tests for each D module.
- **Viewer:** `frontend/src/match-viewer/*`, plus new `DebugOverlay.tsx`.
- **Tooling and orientation (new):**
  - `.claude/agents/{engine-calibrator,match-investigator,engine-reviewer}.md`;
  - `.claude/skills/{calibrate-engine,run-footsim,repro-match}/SKILL.md`;
  - `CLAUDE.md`, `pyrightconfig.json` and `docs/plans/{match-believability,recovery-and-continuation,progress}.md`.

## Verification

- **Tooling (Step 0b):**
  - `claude plugin list` shows `pyright-lsp`, `typescript-lsp` and `context7`;
  - `claude mcp list` shows `chrome-devtools` connected;
  - `claude plugin validate .claude` passes for the new agents and skills;
  - a trial `engine-calibrator` run on 14 synthetic matches returns its table.
- **Every step:** `just lint`, `cd backend && uv run pytest`, and `cd frontend && npm run build`.
- **Engine steps:** `just calibrate-engine --n 200 --division ENG1`, then `--division ENG4`. Compare each with the previous report (paired seeds, with CIs).
- **C1:**
  - Run `just calibrate-engine --division ENG4 --n 200 --focus-club 218 --ab "aggressive:mentality=attacking,pressing=high,line=high,width=wide,tempo=fast,passing=direct"`, plus one `--ab` arm per instruction.
  - Then watch the Grimsby save at 1× with the aggressive setup, and confirm that a trailing AI side changes its approach late.
- **Browser:** `node e2e/smoke.mjs` and `node e2e/live.mjs` against the 8765 server.
- **At the end of each phase:**
  - I run the 12 acceptance questions myself in the browser against :8765 and record the answers in `progress.md`;
  - you can run the same checklist on the restarted :8000 game whenever you like, and your feedback takes priority over the plan.

### Sources (added during recovery)

- [Eliminating supportive crowds reduces referee bias (Reade, Singleton et al.)](https://centaur.reading.ac.uk/101715/1/closeddoors_reade_singleton.pdf)
- [Home-bias in referee decisions: evidence from "ghost matches" (Economics Letters)](https://www.sciencedirect.com/science/article/pii/S0165176520303815)
- [Losing the home field advantage when playing behind closed doors during COVID-19 (PMC)](https://pmc.ncbi.nlm.nih.gov/articles/PMC8081822/)
- [The impact of crowd effects on home advantage of football matches (PLOS One)](https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0289899)
- Tooling: [Anthropic's official plugin marketplace](https://github.com/anthropics/claude-plugins-official), [pyright-lsp](https://github.com/anthropics/claude-plugins-official/tree/main/plugins/pyright-lsp) and [typescript-lsp](https://github.com/anthropics/claude-plugins-official/tree/main/plugins/typescript-lsp).
- All other sources: the approved plan's Sources section.

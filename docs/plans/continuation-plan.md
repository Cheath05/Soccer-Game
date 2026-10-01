# Continuation plan (30 Sep): finish Step 2.3, then C1, discipline, home advantage, baselines, Phase D

> **Revised order, approved by the user on 1 Oct ("Start the plan").** From now on the order of
> work is the list in `progress.md`, section "The approved order (1 Oct)". It keeps
> this plan's calibration principles and working rules, and changes what comes after Step 2.3:
> 1. Believable matches first: 2.3f, switching 2.3c on, 2.3e, then 2.4.
> 2. B2, the fast engine as a surrogate of the agent engine, moves up from the end. It plays
>    every match the user doesn't watch, and will play every match in the leagues added next.
> 3. Then the world and the manager game, in order: retirement and a yearly youth intake, other
>    leagues, finances, transfers, full academies, European competitions.
> 4. Phase D, Phase E and the remaining engine steps (2.3d, C1, 2.1, 2.6, C2, F2, G, J, K) run
>    alongside the management phases: their calibration batches run while management code is
>    written.
>
> League quality comes from player ratings, as the principles below say. The EA FC 27 data
> already ranks the leagues (best-XI averages: Premier League 79.7, La Liga 78.0, Serie A 77.0,
> Bundesliga 76.8, Ligue 1 75.5). A league-environment setting is added only where real stats
> show a residual that ratings don't explain. Leagues differ off the pitch through money and
> prestige, which arrive with finances and transfers.

## Context

You re-briefed the project after the compaction: the full vision, your play-test feedback, and the order of work (2.3 → C1 → 2.1 → 2.4 → 2.6 → Phase D). You asked for a status assessment first, then to carry on without restarting anything.

Everything below comes from:
- the repo and the calibration reports;
- two small diagnostics run today (nothing written to disk);
- three code explorations and a design review.

**Revised twice after your reviews.** The "Calibration principles" section makes three things explicit:
- one engine for every league, with no league-specific mechanics;
- **league quality = player ratings first → team and tactical context second → a small, measured league-environment parameter third;**
- targets are rates, with league figures as validation only.

2.3a, 2.3e and every acceptance list now follow those principles.

**Where the data contradicts the old recommendation, I follow the data.**
- **Step 2.3 grows from "one more tuning round" to five sub-steps.** The passing physics hides player ratings: the receiver always knows where a misplaced pass will go, and a miscontrolled ball comes straight back. No tuning value can fix that.
- If you'd rather move to Phase D sooner, this is the part to redirect.

---

## Now: checkpoint only (the context is nearly full)

No implementation, and no calibration batch. The repo is already clean at f347e8c, the same as origin. Make this plan recoverable from the repo:

1. **Add this plan to the repo** as `docs/plans/continuation-plan.md`. From Step 2.3 on it supersedes `recovery-and-continuation.md`'s order of work.
2. **Update `CLAUDE.md`:**
   - the checkpoint working rule;
   - a pointer to the calibration principles;
   - the new plan in the "Plans" list;
   - a warning: never run `just e2e` without a :8765 URL until quick fix 0 lands.
3. **Update `.claude/agents/engine-reviewer.md`:** add the principles to its checklist (no league-specific mechanics or engine paths; the environment layer is the only way a competition enters; ratings drive execution; conflicts are flagged).
4. **Update `progress.md`:**
   - a continuation checkpoint covering the 7 items above;
   - the new sub-steps (quick fixes, 2.3a–2.3e, C1, 2.4 before 2.1, 2.6, Phase D starting with the vectorising commits) as unticked items;
   - the round-5 reading and today's diagnostic findings;
   - the verified bugs;
   - the next action: quick fix 0.
5. **Stop the two stale background waiters** left from the previous context. Check that no batch is running.
6. **Checks:** `just lint` and the full pytest (docs only, so they should be unchanged), and the reviewer on the diff.
7. **Commit the docs and push.** Then put that hash into `progress.md` in a second commit, and push again.
8. **Update the commit-and-push memory** with the checkpoint rule.

---

## Status assessment (your checkpoint, section 48)

### 1. Where the project is

- **Branch:** `phase-1-match-believability` is at f347e8c, the same as origin. The tree is clean, and the nested clone stays untracked.
- **Other work in flight:**
  - the cloud branch (58b4af2) is already merged;
  - no other Claude session is working on this checkout, and no batch is running.
- **Tests:** all 119 backend tests pass on today's head.
- **Measurement worktree:** at 50e3cf1.
- **The :8000 game** still runs the old Phase A build (since Monday night), with no connections open.
- **Where the plan stands:** Phase 1 (match believability), Step 2.3. The round-5 reports have been read. The C1 tactic measurements exist but fail section S.

### 2. Already implemented

- **Agent engine (10 Hz):**
  - passing, carrying, shooting, pressure, interceptions vs recoveries, tackles, fouls, cards, offsides, saves;
  - restarts, substitutions, and tactical and formation changes.
- **Fast engine** for the rest of the world.
- **Live session:** pause, speed, formation, instructions, subs, auto-subs, the assistant (AI manager for your side) and finish.
- **Clock (A):**
  - MM:SS, 5-minute halves (9 match seconds per real second), added time and a half-time panel;
  - speeds 0.5×–8×, plus Highlights and Instant;
  - playback speed never changes a result.
- **Restarts (F1):**
  - awarded → players reposition → taken, with Opta-like waits (throw-in 17 s, goal kick 28 s, corner 32 s);
  - at least 4 attackers in the box before a corner, averaging 5;
  - 0 teleports in 400 matches.
- **In-match AI manager (1.2):** reacts to the score, the clock, red cards, and the opponent's *observed* line and press. It only changes instructions.
- **Other clubs' pages (H):** table position, squad with OVR, age, form, status and contract.
- **Debug overlay (D0).**
- **Measurement kit:**
  - a batch harness with 95% CIs and paired A/B arms;
  - synthetic teams fitted to real players (aggregates only);
  - determinism, and golden values per platform.
- **Home advantage:** referee and crowd mechanisms (values provisional).
- **Saves:** 3 slots, autosave, 5 rotating backups and integrity checks.
- **Promotion and relegation** with play-offs.
- **Data safety:** the EA data stays local and gitignored.

### 3. Partial

- **Calibration:**
  - 2.3 (passing) is in progress;
  - C1 is measured and fails;
  - 2.1 isn't fitted;
  - 2.4 isn't started.
- **Sim-to-date (I).** Only "Continue" exists: day by day to your next match.
  - It covers other matches, injuries, bans, play-offs, and the season-end development and renewals.
  - Missing: week, month, a chosen date, midseason and season end; stop conditions; progress.
- **Substitutions (G).** On the pitch the panel shows position, slot OVR, live rating, energy, condition and cards.
  - Missing: role in the panel, cancelling a queued sub, and the three-window rule.
- **Two engines (B2).**
  - The fast engine uses a flat 1.15× home bonus and knows only mentality and pressing.
  - Measured earlier, it gave 3.51 goals against the agent engine's 2.66, and no test compares the two.
  - Your league table mixes both engines.
- **Other-club pages.** The manager is blank: AI managers don't exist as people yet.
- **Management.**
  - Partly there: contracts renew themselves, scouting shows ranges, development runs yearly, and AI sides pick formations.
  - Missing: transfers, finances, board, youth, cups, Europe.

### 4. Broken or poorly calibrated

**Tactics** (Grimsby, ENG4, 200 paired matches; section S allows at most ±0.35 goal difference and ±10 win points per instruction):

| Setting | Goal difference | Win rate |
|---|---|---|
| All-aggressive | +0.89 | +21.5 pts |
| Direct passing | +0.79 | +23.5 pts |
| High line | −0.57 | |
| Press | −0.40 | |
| Fast | −0.35 | |

**Direct's edge is almost all defensive:** shots against −4.65 and xG against −0.40, but xG for only +0.18. It avoids the engine's leaky build-up.

**Rates, per minute of ball in play** (see the principles below for why):
- **Shots:** the Premier League (ENG1) takes too many.
- **Fouls:** far too few everywhere, and falling as turnovers fall.
- **Offsides:** too many.
- **High regains:** too many.
- **Fast-break shots:** 2% of shots, against 6–12%.
- **Ball in play:** too long, 59–77 minutes against 54–60.

**Ratings barely matter.** A League Two-level side passes as accurately as a Premier League-level one (diagnostic below). So the divisions can't differ as real football does; real League Two is less accurate, more direct, and has less ball in play.

**Bugs, verified in the code:**
- **A substitute inherits the booked player's yellow card.**
  - `self.yellows` is per slot (`engine.py:100`), and `_bring_on` → `_load` (`engine.py:183-198`) never resets it.
  - So the sub plays under the booked-player caution, his first yellow sends him off, and your subs panel shows him as booked (`session.py:265`).
- **Onside through balls are thrown away.** The passer tests the landing point (runner + 7 m) against the line (`actions.py:299, 308`), not the runner's position, which the law and the engine's own call use (`actions.py:415-429`).
- **Offside awareness re-rolls every decision** (`actions.py:304`), so a forward left offside is eventually "missed" and found. The miss rate is 31% at decisions 60, against 18% at 80.
- **Slow tempo is an ability bonus:** `hurry: -0.1` makes passes 10% more accurate (`tactics.yaml:34`, `actions.py:369`).
- **Red cards:**
  - there are no DOGSO reds;
  - a booked player's foul rate is ×0.09 (the caution is applied twice), so second yellows almost never happen;
  - reds hinge on an aggression > 80 cliff.
- **`just e2e` could wipe your career.** It defaulted to :8000 (`justfile:48`), and a new career always overwrites slot 1 (`api/session.py:62`). *Fixed in quick fix 0a.*
- **Metrics:**
  - `take_ons` counts every duel;
  - fouls can't be split by source;
  - offside events don't say whether they came from a free kick.

**Passing physics hides the ratings** (design review, verified):
- **The receiver always knows where a pass will go.** At the kick his target is the pass's true, erroneous landing point, and `_meet_ball` puts him on the ball's exact path (`actions.py:413-414`, `behaviours.py:178-193`). A misplaced ground pass is simply met.
- **A miscontrolled ball comes straight back.** After a heavy touch the same player re-gathers almost at once, and it still counts as a completed pass (`actions.py:525, 491, 546-551`). In two matches, 100 of 114 heavy touches were re-gathered by the receiver himself, 97 of them within 0.3 s.
- **Passes are slow, and the passer misjudges their timing.**
  - Physics: 4 m/s² friction (`engine.py:50`), weighted to arrive at 5 m/s, so a 20 m pass takes 2.15 s.
  - The passer's estimate assumes 17 m/s, which would take 1.18 s.
  - Slow passes give defenders time. They may be part of the interception excess that `intercept_scale` 0.2 is covering for.

**Movement.** Formations are static:
- the phase is a bare x threshold with no hysteresis. In one match profiled today, it flipped 7–8 times per team per minute of play, and 10% of phases lasted under 1 s;
- the formation offsets are too sparse for a 3-2-5;
- six run types, `press_bias` and `hold_line` are unused;
- there are no speed bands;
- `update_targets` takes 3.3 s of a 6.6 s match (profiled today), in per-player Python loops. That leaves about 1.4 s of headroom under the 8 s budget.

### 5. What the latest measurements show

**Round 5** (real squads, seed 21, 200 matches per cell; per match, as the reports give them; bold means inside the target):

| | ENG4 f030 | ENG4 f020e2 | ENG4 f020e3 | ENG1 f030 | ENG1 f020e2 | ENG1 f020e3 | Target PL / EFL |
|---|---|---|---|---|---|---|---|
| Interceptions | 29.7 | **20.4** | **19.8** | 28.5 | **20.1** | **19.3** | 14–26 |
| Pass accuracy | .897 | .878 | .871 | .890 | .863 | **.852** | .80–.85 / .74–.81 |
| Throw-ins | 15.6 | 30.4 | **34.5** | 24.3 | **42.0** | 46.4 | 32–42 / 32–44 |
| Goal kicks | 13.9 | 20.7 | 22.0 | 18.6 | 24.2 | 26.5 | 14–20 / 14–21 |
| Ball in play (min) | 77.5 | 68.5 | 65.8 | 69.2 | 61.5 | **59.3** | 54–60 / 52–60 |
| Goals | 2.20 | 2.33 | 2.43 | 3.32 | 3.40 | 3.41 | 2.65–3.05 / 2.45–2.85 |
| Shots | 23.1 | 27.3 | 26.9 | 39.5 | 36.9 | 36.0 | 23–27.5 / 22–26 |
| Offsides | 5.9 | 6.95 | 7.2 | 4.7 | 5.1 | 5.0 | 2.5–4.5 |
| Fouls | 10.4 | 9.4 | 8.9 | 19.0 | 15.3 | 13.7 | 20–24.5 |
| High regains | 33.1 | 29.3 | 28.9 | 24.4 | 23.6 | 23.4 | 10–17 |

**Pass diagnostic** (synthetic sides; League Two-level = 62, Premier League-level = 78; 6 matches per cell, so indicative only):

| | Committed L2-level | Committed PL-level | f020e2 L2-level | f020e2 PL-level | Real PL |
|---|---|---|---|---|---|
| Short <14 m completed | 89% | 90% | 94% | 94% | ~87–91% |
| Medium 14–32 m completed | 87% | 89% | 88% | 90% | ~83–87% |
| Long ≥32 m completed (share of passes) | 66% (7%) | 65% (6%) | 52% (12%) | 55% (14%) | ~47% (11.7%) |
| Crosses: completed vs passer's estimate | 17 vs 18% | 25 vs 23% | **20 vs 45%** | **23 vs 48%** | |
| Long balls: completed vs estimate | 66 vs 46% | 65 vs 56% | 52 vs 59% | 55 vs 67% | |

**What it means:**
- **Keep `intercept_scale` at 0.2 for now.** Interceptions land at about 20 in both divisions (±0.7). Re-check it once passes travel at a realistic pace.
- **Long-ball error at e2 makes long balls realistic, but it's the wrong lever for the rest.**
  - It turns long balls into throw-ins and goal kicks.
  - It needs implausible length spreads: at 40 m, a standard deviation of 0.9–1.3 times the pass length.
  - It can't make weaker passers less accurate than stronger ones.
- **Ratings barely matter.** The L2-level side passes as accurately as the PL-level one: 94% of short passes each. That's why the divisions can't differ as real ones do.
- **Passers' estimates stopped being honest at 0.2.**
  - The estimate is hard-coded (`actions.py:280`) and ignores `passing.yaml`.
  - The scaled lane risk had been standing in for the aerial contest, so crosses now look twice as safe as they are.
  - The result is too many crosses and long balls. That likely feeds ENG1's shot count and direct play's edge.

### 6. What comes next

0. **Quick fixes:**
   - `just e2e` defaults to :8765, and the scripts run only against a server whose `/api/health` confirms it isn't using the default saves folder. :8000 is refused outright; `FOOTSIM_E2E_ALLOW_REAL_SAVES=1` overrides;
   - substitutes no longer inherit a yellow card, with a test.
1. **2.3a:** measure; restructure the targets into rates, rating responses and references; behaviour-neutral refactors.
2. **2.3b:** fix the physics shortcuts.
3. **2.3c:** honest pass estimates.
4. **2.3d:** offside decisions.
5. **2.3e:** ratings that matter, and the final values.
6. **C1:** re-measure Grimsby and tune the costs, including removing slow tempo's bonus.
7. **2.4:** fouls and cards. It comes before 2.1 because the card-gap fit depends on foul volume.
8. **2.1:** fit home advantage.
9. **2.6:** baselines.
10. **Phase D,** vectorised first. Then E and the rest of `progress.md`.

### 7. Explicitly not now

- **Management systems:** transfers, contracts, finances, board, youth, scouting, AI manager careers, cups, Europe, more countries.
- **Features:**
  - sim-to-date (I);
  - analytics (J);
  - UI beyond what a step needs;
  - fast-engine work before B2.
- **No parameter changes** without a 200-paired-match reading.

---

## Calibration principles (added after your review)

1. **One engine for every league: no league-specific mechanics or separate engine paths.**
   - **Today** the engine has no league input at all: `MatchEngine` takes two team sheets and a random generator (`engine.py:61-65`), and no engine code reads a division (checked today). The harness uses the division only to pick squads and targets.
   - **League quality comes in this order:**
     1. **player ratings first;**
     2. **team and tactical context second:** choices a squad makes because of its players, never because of its league;
     3. **a small league-environment parameter third.** It's centralised, and permitted only because it modifies the same formulas and is empirically justified (see "The league-environment layer" below).
   - **Nothing may be keyed to a league:** no `if league == …` branch, and no league-specific formula, threshold or tuning value anywhere else.
2. **Ratings decide execution.**
   - Each mechanic reads the ratings of the players involved:
     - passing and vision for the pass;
     - first touch for control;
     - anticipation for reading a pass;
     - pace and acceleration for a foot race;
     - strength, jumping and heading for duels;
     - stamina for decline;
     - aggression for fouls;
     - decisions for choices.
   - The same situation gives different outcomes for different ratings.
   - A League Two side with Premier League-quality players must pass like a Premier League side. A weak Premier League side gets no Premier League execution for being in ENG1.
   - The only exception is the small, measured environment adjustment, which works the same way in both directions.
3. **Three kinds of target,** each tagged in `match_targets.yaml`:
   - **`rate`, which carries over directly:**
     - pass completion, overall and by length;
     - long-ball and cross shares;
     - share of possessions ending in a shot;
     - conversion and xG per shot, and save rate;
     - cards per foul;
     - ball-in-play share;
     - home, draw and away rates.
   - **`volume`, judged as a rate over the engine's own exposure.**
     - A per-match count (passes, shots, fouls, throw-ins, corners, goal kicks, offsides) is stored as a rate per minute of ball in play (or per possession). The rate is derived from the real per-match figure and the ball-in-play time it came with.
     - The report still shows the per-match count, but the verdict comes from the rate.
   - **`reference`, for validation only:** league aggregates such as PL and EFL averages, or League Two's "over 56 throw-ins".
     - They check the emergent result when real squads play, and they're never inputs.
     - A miss is diagnosed down to rates and rating responses.
4. **Rating responses are targets too.**
   - They cover pass completion, miscontrols, interceptions, foot races, duels and fouls, each as a function of the ratings involved.
   - They're measured with controlled synthetic A/Bs (one rating group changed), and with real squads grouped by rating rather than by division.
   - Where real data gives a size, that's the target. For example, the pyramid's accuracy gap set against the ratings gap between ENG1 and ENG4 players in the world data.
   - Otherwise the response must be clear (CIs separated) and in the right direction.
5. **Mechanics beat aggregates.**
   - A target that can only be reached with an implausible mechanic, or a league exception, is flagged instead: in the report, in `progress.md`, and to you.
   - The number isn't forced.

### The league-environment layer (small, measured, auditable)

The idea: `outcome = same_engine(mechanics, player ratings, tactics, environment)`. It's never `if league == ENG4: use a different formula`.

- **One config:** a new `data/config/match/environment.yaml`, validated by a Pydantic model in `defs/match.py`.
  - **`mechanics`:** a closed list of the mechanics the layer may touch. Candidates: pass and shot execution error, first-touch control, decision noise (tempo and consistency), and referee strictness where data supports it.
    - Each has one sensitivity, a hard cap, and a required `evidence` note once it's non-zero.
  - **`competitions`:** exactly **one number per competition**, a level in [−1, 1], with 0 for the reference level.
- **One way in.**
  - The career and the harness look up the fixture's competition level and pass the engine a resolved `MatchEnvironment`: one multiplier per mechanic.
  - The engine never sees a league name.
  - The formulas read the multiplier where they already combine their other terms (for example the execution spread in `start_pass`).
  - At the neutral default, the golden values are unchanged.
- **Bounds:**
  - no multiplier moves a mechanic by more than a few percent (the cap is set in the model, about 5–8%);
  - its biggest swing must be smaller than the effect of a 5-point rating difference on the same mechanic.
  - So a better League Two player is never worse than a weaker Premier League player just for his league, and a Premier League-quality player in League Two still plays like his ratings.
- **It starts neutral: every level is 0.** A level becomes non-zero only in 2.3e's residual step, and only for mechanics with evidence.
- **Guard tests** keep it a layer rather than a second engine:
  - the config has one scalar per competition, and never a per-league table of mechanic values;
  - mechanic names come from the closed list, and every non-zero sensitivity has evidence;
  - every multiplier is within its cap, and the rating-dominance check holds (computed from the engine's own formulas);
  - no engine module or other match config uses a league or division name as a key, value or condition. Comments citing real-world sources are fine, and only the environment lookup outside the engine resolves competitions;
  - `MatchEngine` takes a `MatchEnvironment`, never a league name.
- **The fast engine (B2)** will read the same levels.

**The accelerated clock: a conflict with your premise, flagged.**
- **Football time isn't compressed.** The engine plays the full 90 minutes plus added time, second by second at 10 Hz (`clock.py:17`, `engine.py:48`). Only playback is compressed: 300 real seconds per half (`presentation.yaml`). Simulated matches last 97.6 minutes (target 95–101), so per-match counts are comparable in principle.
- **Normalising still matters, for another reason.** The engine keeps the ball in play too long, and that inflates every count. Round 5 per minute of ball in play:

| ENG1 f020e2 / ENG4 f020e2 | Per match | Per minute of ball in play | Real, per minute of ball in play |
|---|---|---|---|
| Passes | 829 / 929 | 13.5 / 13.6 | PL ≈ 15.4–15.7 (849 ÷ 55.0; 893 ÷ 57.0) |
| Shots | 36.9 / 27.3 | 0.60 / 0.40 | PL ≈ 0.45–0.47; EFL ≈ 0.40–0.50 (ball-in-play approximate) |
| Fouls | 15.3 / 9.4 | 0.25 / 0.14 | ≈ 0.37–0.45 |

- **What that changes:**
  - Per match, ENG4's shots look too many; per minute of play they're at or below the real rate.
  - Passing is too *slow* in both divisions, which fits the slow-pass finding.
  - ENG1's shot excess and the foul shortfall are real at any normalisation.

---

## Step 2.3: five sub-steps, each committed and pushed

### 2.3a Measure, restructure the targets, behaviour-neutral refactors (golden values unchanged)

**Probe** (`summarize` and `aggregate`), pairing each pass with its outcome by walking the event log:
- **Bands:** short <14 m, medium 14–32 m, long ≥32 m (Opta's long ball), cross and throw. Record attempts, completion, long-ball share and cross share.
- **A reliability table:** completion by estimate decile and pass kind. This is the real honesty check; per-band averages hide the winner's curse.
- **Failure causes:** intercepted, recovered, loose, out of play (by restart kind), aerial lost, offside.
- **Pass travel time and arrival speed** by band, and heavy touches (who re-gathers them, and how fast).
- **Offside events** tagged with the restart kind, the pass kind, and runner or not.
- **Every volume metric** also as a rate per minute of ball in play, plus the share of possessions ending in a shot.

**Targets:**
- Every entry in `match_targets.yaml` gets a `kind` (`rate`, `volume` or `reference`).
- Volumes are stored as rates, with the real count and ball-in-play time shown in their reference.
- The sourced rates:
  - PL `long_ball_share` 0.095–0.14 (Opta: 99.7 of 849 passes, 25/26);
  - `pass_acc_long` 0.42–0.55 (FBref 46.6%).
  - Rates without a source yet are reported, not judged, until they have one.
- **League Two specifics** become references in the validation section, never a behaviour: "over 56 throw-ins", and about 6 minutes less ball in play than the PL (The Analyst).
- **The harness** (`engine_batch.py:207-209`, `write_report`) judges rates and volume-rates, and lists references separately.

**Rating responses in the report:**
- **Real squads grouped by squad rating** (thirds of each division, and both divisions pooled on one curve) for completion, long-ball share, interceptions and fouls.
- **Equal synthetic sides at qualities 58, 66, 74 and 82**, a small harness addition that reuses `--synthetic --equal --quality`.
- **The ratings gap between ENG1 and ENG4 players** for each attribute the mechanics read (short and long passing, first touch, anticipation, and so on). Aggregates only, recorded in `docs/calibration/`. It shows how steep each response must be to produce the real pyramid gap, and whether that steepness is plausible.

**Also in 2.3a:**
- **A real pass-pace reference:** pass travel times by distance band from Metrica Sports' public sample tracking data (3 matches, events plus 25 Hz tracking), computed with a scratch script; the figures and method go in `docs/calibration/`.
- **Refactors:**
  - a `pass_error()` helper that `start_pass` uses;
  - one aerial-score helper, replacing the two copies (`actions.py` ~613 and ~655);
  - `control.touch_skill: 0.1`, written as (1 − w) + w·ft/100, which is bit-identical to today.
- **The first guard test:** no engine module or match config uses a league or division name as a key, value or condition (comments citing real-world sources are fine). The environment layer, if 2.3e adds it, brings its own tests.
- **Check:** the f020e2 re-run (seed 21, both divisions) reproduces round 5 exactly, and adds the new metrics.

### 2.3b Fix the physics shortcuts (behaviour change)

- **The receiver reads the pass.** At the kick he heads for the *intended* target. He switches to the ball's real path after a read delay, set by his anticipation rating (`control.read_delay` in YAML).
- **A heavy touch is a real contest.** The player who miscontrolled can't touch the ball again during a short lockout (`control.retouch_lockout`). His first touch then decides more than it does today.
- **Crosses that land clear follow the ground-pass rule:** a teammate collecting within 3 s completes them.
- **Pass pace.** If 2.3a shows engine passes much slower than Metrica's, the rolling friction and the arrival pace move to YAML (`passing.yaml` `pace`, done) and are set from those figures (the physics is the same for everyone).
- **Measure:** 200 paired matches, both divisions, at 0.2/e2, against 2.3a, including the rating responses. If interceptions leave their range, re-check `intercept_scale` in the same round.
- Golden values: record the Mac's, delete Linux's, add a History note. Then commit and push.

### 2.3c Honest pass estimates (behaviour change)

- **One movement budget, with timing from the physics:** success = P_path × p_reach × P_arrive × P_secure.
  - **p_reach** spends the receiver's budget (speed × T) on reaching the led target.
  - **P_arrive** gets only what's left over. For ground passes: erf((CONTROL_RADIUS + surplus) / (√2 · length · σθ)). For lofted passes, multiply in the length term.
  - **P_path** keeps today's lane geometry, but uses the physics' own chance of each opponent picking the ball up (from his interceptions and anticipation ratings), × `intercept_scale`, only up to where the receiver meets the ball. The marker and contest terms go: today they count the nearest opponent three times.
  - **P_secure** = c + (1 − c)·r. c is the control chance, as in `resolve_loose_or_pass`; r is the re-gather rate measured after 2.3b, in YAML.
  - **Lofted balls and crosses** use a fixed 3×3 grid of landing points over the angle and length errors, with no random draws. At each point: the keeper's claim; otherwise the aerial duel against the best defender expected there (with `header_to_feet` and the foul share); otherwise a pickup.
- **What the estimate includes:**
  - the passer's and receiver's own ratings, which is how a weaker passer comes to prefer safer options;
  - tempo hurry, because players feel that trade-off;
  - not the crowd's extra error, a stress effect players don't correct for.
  - Decision quality stays in the softmax temperature, which reads `decisions` (`actions.py:165-170`).
- **Tests:**
  - a slow-marked honesty test: at least 1,000 plays each for short, medium, long and cross; bystanders inactive; completion judged as `_take` judges it;
  - in-match acceptance from the probe's reliability table: every decile with enough passes within ±5 points.
- **Measure** 200 paired matches; golden values; commit.

### 2.3d Offside decisions (behaviour change)

- **Through balls** are judged onside by the runner's position when the ball is played, not by the landing point.
- **Awareness:** the per-decision re-roll gives way to an offside risk inside the honest estimate. The passer reads it more sharply with better `decisions`; runners' timing stays with their ratings.
- **Free kicks:** if 2.3a's tags show offsides there, set-piece attackers stay onside until the kick (`set_pieces.py` ~97–104; the line cap skipped during restarts, `behaviours.py:129-134`).
- **Accept** (200 paired matches, both divisions):
  - offsides per minute of ball in play within range;
  - more through balls, and a higher fast-break shot share;
  - goals and shots no worse beyond their CIs.
- Golden values; commit.

### 2.3e Ratings that matter, and the final values (tuning)

- **Round 6** at the 2.3d head sweeps the rating terms: `execution.skill` (0.10 → about 0.25–0.40), `length_skill`, `control.touch_skill`, and the anticipation weight in `read_delay`.
  - These are the same values for every player in every league.
  - Distance terms stay near e1–e2.
  - Extend `make_variant.sh` for the new values.
- **Accept when** (200 paired matches of real squads in both divisions, plus the synthetic quality sweep):
  1. **Rating responses:**
     - completion rises with passing ratings, and miscontrols fall with first touch, CI-separated across qualities 58, 66, 74 and 82;
     - real squads from both divisions fall on one curve of completion against squad rating;
     - the curve, at the measured ENG1–ENG4 ratings gap, explains most of the real pyramid gap. What's left is the residual below.
  2. **Honesty and offsides hold,** and goals, shots and high regains (as rates) are no worse than f020e2 beyond their CIs.
  3. **After the residual step,** the rates land at each quality level through ratings, plus at most the bounded environment:
     - pass completion, overall and by band, is in the real range for PL-level and EFL-level squads;
     - long-ball and cross shares are in range;
     - interceptions, throw-ins and goal kicks per minute of ball in play are in range;
     - long balls are 42–55% complete.
     - League references are validated, and conflicts recorded.
- **Then the residual, the third factor.** The rating terms are fitted with every environment level at 0. Then:
  1. **What ratings explain:** for each division, read the quality sweep's curve at that division's measured ratings (from 2.3a's ratings gap).
  2. **The residual:** each division's real-squad rates minus its references, less the part ratings explain. It's reported per mechanic, with CIs.
  3. **If it's consistent across related metrics and within the layer's bounds:**
     - add the environment layer first, neutral (plumbing, config, guard tests; golden values unchanged);
     - then fit the competition levels for the mechanics with evidence;
     - then confirm on 200 paired matches: the rating responses must be unchanged, and ratings must still dominate.
  4. **If it's larger than the bounds:** it's a conflict. It's recorded with its likely cause, and the bounds aren't widened.
     - League Two's throw-ins, for instance, may come from style, long throws or pitches.
     - Or the FC data may compress lower-league ratings.
  5. **Provisional until C2.** Once managers choose a style from their squads, the residual is measured again; style may explain part of it.
- Commit `passing.yaml` (golden values and History note), tick 2.3, push.
- **If ENG4 sides still play like ENG1 sides** because every AI side uses one style, the follow-up belongs to C2: a manager picks a style from his squad's strengths (for example, technically weaker squads go more direct), never from the league.

## C1: Steps 1.3 and 1.4 (re-measure Grimsby, then tune)

1. **Pin the worktree:** `git -C .worktrees/measure checkout -q --detach phase-1-match-believability`.
2. **Bold arms:** ENG4, seed 11, `--focus-club 218`, 200 paired matches, managers on. Arms: aggressive, fast, direct, press, high line, wide, attacking. About 50 minutes; the command is in the calibrate-engine skill.
3. **Cautious arms:** defensive, low press, deep line, narrow, slow, short. About 45 minutes.
4. **Judge against section S:**
   - each instruction within ±0.35 goal difference and ±10 win points;
   - aggressive at most +0.6 and +15, conceding at least 10% more xG, and at least 5 stamina points lower.
5. **Remove slow tempo's accuracy bonus** (`hurry: -0.1` → 0). Slow tempo's benefit is its `hold` time. Fast keeps its hurry cost, which the honest estimate now sees.
6. **Fix what's over the line, mechanism first.**
   - `match-investigator` explains where an arm's extra goals come from, using paired fixtures where it gained 3 or more.
   - Then add behavioural costs in `tactics.yaml`: support distances, rest defence, second-ball losses, space behind. Never less ability, and the same costs in every league.
   - Settings that cost too much get their costs trimmed.
   - Re-run only the arms that changed.
7. **Step 1.4:** golden values, tick 1.3 and 1.4, commit and push. Then restart :8000 (`run-footsim` skill; check `lsof -nP -iTCP:8000 -sTCP:ESTABLISHED` first).

## 2.4 Discipline (before 2.1): fouls, then cards

**Why fouls are low.** Nearly all fouls come from ground duels (`duels.py:110-122`, about 30% of challenges), so fouls ÷ tackles is 0.43–0.46 in every run.
- **Duel volume depends on absolute ratings in the wrong way.** Tackle attempts shrink with anticipation, aggression and stamina (`duels.py:42-99`), so games between weaker players have fewer duels (ENG4 21–27 against ENG1 30–51). Counter-press duels also fall as interceptions fall.
- **Missing sources:** holding a runner, loose-ball 50-50s, fouls on a shielding carrier, and aerial duels beyond crosses and lofted passes over 32 m.

**Steps:**
1. **Measure:**
   - fouls by source;
   - fix `take_ons`;
   - aerial duels;
   - fouls per minute of ball in play;
   - yellows and reds per foul;
   - second yellows as a share of reds.
2. **Duels come from situations:** loose balls, second balls, contested headers and players tracking runners.
   - Ratings decide who wins and who fouls, not whether football happens.
   - New foul sources:
     - a beaten defender pulling his runner back (likelier in the box at set pieces);
     - 50-50s;
     - fouls on a shielding carrier;
     - every contested header.
   - Chances come from aggression, strength and position, with the referee's venue bias. The values go in `duels.yaml`, the same for all.
3. **Cards:**
   - DOGSO reds;
   - `booked_caution` applied once, not twice;
   - the aggression > 80 red-card cliff becomes a smooth function of the rating.
4. **Fit** on 200 paired matches in both divisions:
   - fouls per minute of ball in play in range;
   - yellows about 0.17–0.19 per foul;
   - reds per foul consistent with 0.08–0.18 a match.
   - Per-match references validate the result.
   - **Referee tendencies:** if the per-division data shows a residual after ratings (football-data's fouls and yellows by division), it can only go through the environment layer's referee mechanic, and only within its bounds.
   - Then golden values, and commit.

## 2.1 Home advantage, then 2.6 baselines

- **2.1:**
  - ENG4 and ENG1 at `--n 400 --seed 31`, on real squads with no focus club.
  - Fit one set of `home_advantage.yaml` values for every league to home, draw and away rates, `home_goal_diff` (about +0.3, pooled over 800 matches: at 200 its CI is wider than the band) and `away_card_gap`.
  - The crowd carries most of it; the referee values stay small.
  - League-by-league home-win figures are references.
  - Confirm 2.4's discipline figures in the same batches.
- **2.6:** ENG1 and ENG4 at 200 each, plus the synthetic quality sweep, saved to `docs/calibration/` as the pre-D baselines.

## Phase D: dynamic movement

**Vectorise first: two behaviour-neutral commits** (golden values unchanged).
- **Why:** `update_targets` takes half the match time, so D has no budget until this is done.
- **Commit 1:** cached slot tables, rebuilt in `_load` and `set_formation`, plus vectorised anchors and write-back.
- **Commit 2:** one batched candidate search for `_attack`, and vectorised `_defend` and `_react`.
- **Keep the bits identical:**
  - use stable argsorts, matching Python's `sorted`;
  - keep the arithmetic in the same order;
  - keep today's quirks (a chaser flagged urgent skips marking; `_react`'s nearest two can include the keeper).
- **Target:** `update_targets` at 1.5 s or less.

**The layered target** (your concept list, made explicit; section I doesn't define it):
1. **In formation coordinates, additive:** base slot + phase offsets + role offsets. They scale with compactness, as today.
2. **TeamShape (D2):** maps them onto the pitch with line heights, width, compactness and the ball-side shift.
3. **In pitch space:**
   - structural jobs blend in and replace the anchor;
   - the support search;
   - marking blends in;
   - press and cover override;
   - movement intents override.
4. **Constraints last:** offside cap, pitch bounds, restart distances.
5. **Transition is a timing gate, not a layer.** Nobody re-plans before his reaction time, which comes from his ratings. This avoids double-counting `_react` and `counter_window`.
6. **Discipline replaces the current `freedom` term.** It never limits pressing, receiving, marking or recovering.
7. **Ratings drive the movement layers:**
   - positioning and anticipation for where he goes;
   - pace, acceleration and agility for how he gets there;
   - work rate and stamina for how long he keeps doing it.
8. **The overlay** shows each layer's point, the intent and the speed band for a selected player.
9. **Phase state:** a `PhaseState` dataclass per team in `state.py`, holding plain floats and enums. It's updated only in `update_targets`, its timers run on `eng.t`, and it resets at kick-offs. It uses no randomness.

| Sub-step | What it builds | Its gate |
|---|---|---|
| D1a `phases.py` | `PhaseState`, and a new `movement.yaml` holding today's thresholds (35/70/32/60) with zero margin. Behaviour-neutral. Flicker metrics in the probe | Golden values unchanged |
| D1b | Hysteresis margin, minimum dwell time, and blending within one side of possession | Phases under 1 s near 0%; match statistics unchanged |
| D2 `shape.py` | TeamShape: line heights, width, compactness, ball-side shift, far side narrower, far CB deeper | High line +6–10 m; wide +6–10 m; block 40–45 m wide; lines 10–15 m apart |
| D3 `intents.py` | MovementIntent with a band, duration and hysteresis. The unused runs, `press_bias`, `hold_line` and `track_runners` come alive. Transition intents are gated by reaction time | Each run type seen and counted |
| D4 Jobs and phase shapes | Width, depth, 2 supports, rest defence by mentality, box occupation, reassigned about every 2 s with `linear_sum_assignment`. Fuller full-back, DM and winger offsets in the formation YAML, so a 4-3-3 becomes about 3-2-5 in build-up and 2-3-5 in attack. Shapes are data | Players per line in each phase; the three formations differ measurably |
| D5 Discipline | From role freedom plus decisions, teamwork, concentration and positioning | Low-discipline players drift further |
| D6 Defending | Runner handover, curved pressing runs, a cover man 5–8 m behind the presser, the far full-back tucking in, the DM screening | Press ≥1.5 m closer; PPDA ≤10 for a high press, ≥14 for a low one |
| D7 Movement | Walk, jog, run and sprint bands; turning from agility and balance; stamina by band. Constants in YAML | Distance 100–118 km; no teleports; ≤8 s a match |

**Every sub-step:** a 200-match report for ENG4 and ENG1, rating responses where the sub-step touches a rating, overlay screenshots on :8765 through the Chrome DevTools MCP, golden values, and a commit.

**The phase ends with:** the D gates, a 1,000-match acceptance report and a restart of :8000.

**Then E:** transitions, built on the reaction-gated intents. After that come C2, F2, B2 (the fast engine as a surrogate of this one, on the same ratings and environment levels), G, I, J and K, as `progress.md` orders them.

## Working rules

- **Every major completed change is its own checkpoint: commit and push before starting the next.** A major change is any meaningful behaviour change or finished sub-step. Each checkpoint:
  1. implement the change;
  2. run the relevant tests and calibration;
  3. run the reviewer and lint;
  4. update `progress.md`;
  5. commit, and push to the current branch.
  - Never keep several major changes in one uncommitted tree.
  - Deliberately unfinished work goes into a clearly labelled WIP commit, never only into the working tree.
  - The repo must stay runnable at every checkpoint.
- **After every checkpoint, `progress.md` records:**
  1. the exact commit and branch;
  2. what was completed;
  3. which tests and measurements passed;
  4. what failed or remains;
  5. the exact next task;
  6. any running or required calibration command;
  7. which server to play-test on (:8000 or :8765).
  - A fresh session must be able to resume from it without repeating or redesigning anything.
- **Before each commit:** `engine-reviewer`, lint and tests, golden values if behaviour changed, and a tick in `progress.md`. Then commit and push with explicit paths. Never rebase or force-push; never stage the nested clone.
- **Batches:** one heavy batch at a time, from `.worktrees/measure` pinned by branch name, with 7 workers. Tuning needs 200 paired matches with CIs; acceptance needs 1,000.
- **Your saves:** never touched. Browser checks use :8765 with a temporary `FOOTSIM_SAVES_DIR`.
- **The engine-reviewer's checklist** gains the principles:
  - no league-specific mechanics or engine paths;
  - a competition enters only as the environment layer's bounded number;
  - ratings, not labels, drive execution;
  - conflicts are flagged, not patched.

## Critical files

- **Passing:**
  - `backend/src/footsim/match/engine/actions.py`: `_pass_options` ~200–318, `start_pass` 354, `resolve_loose_or_pass` 432, `_take` 544, `_aerial` 589;
  - `behaviours.py`: `_meet_ball` 178;
  - `engine.py`: `_load` 183, the ball update (`roll_friction` from `passing.yaml` `pace`);
  - `probe.py`;
  - `data/config/match/passing.yaml` and `defs/match.py`.
- **Targets and harness:** `data/config/calibration/match_targets.yaml` and `calibration/engine_batch.py` (`load_targets` 207, `write_report` 312, and the synthetic quality sweep).
- **League environment, only if 2.3e's residual justifies it:**
  - new `data/config/match/environment.yaml` and its model in `defs/match.py`;
  - a small lookup outside the engine, resolving a competition to a `MatchEnvironment`;
  - the `MatchEngine(..., environment=)` parameter;
  - `world/career.py` (`agent_match`) and the harness pass it in;
  - new guard tests in `tests/unit/test_environment_layer.py`.
- **Discipline and home advantage:** `duels.py`, `duels.yaml` and `home_advantage.yaml`.
- **Tactics:** `tactics.yaml`.
- **Phase D:**
  - `behaviours.py`, `engine.py` and `state.py`;
  - new `phases.py`, `shape.py`, `intents.py` and `data/config/match/movement.yaml`;
  - `data/config/formations/*.yaml` and `roles/*.yaml`.
- **Safety:** `justfile` and `frontend/e2e/*.mjs`.
- **Rules:** `.claude/agents/engine-reviewer.md` and `CLAUDE.md`.
- **Reuse, don't rebuild:**
  - `eng.effect()`, `set_instruction()`, `venue_bias()` and `derive_rng`;
  - the softmax choice in `actions.decide`;
  - `linear_sum_assignment`;
  - `norms`;
  - the harness's `--synthetic --equal --quality`;
  - `make_variant.sh`.

## Verification

- **Every sub-step:** `just lint` and `cd backend && uv run pytest`. When the viewer changes, also `cd frontend && npm run build`.
- **Quick fixes:**
  - `just e2e` targets :8765, and the scripts refuse :8000 unless allowed;
  - a unit test shows a substitute starts with no yellow card;
  - smoke passes on :8765 with a temporary saves folder.
- **2.3a:**
  - the f020e2 re-run matches round 5 exactly, plus the new metrics;
  - the report shows rates, rating responses and references separately;
  - the guard test passes;
  - the Metrica pace figures and the ENG1–ENG4 ratings gap are recorded.
- **2.3b:** heavy touches are no longer re-gathered at once; receivers read passes late, and sooner with better anticipation; reports compared with CIs.
- **2.3c:** the slow honesty test passes, and every decile of the reliability table is within ±5 points.
- **2.3d:** offsides are in range, with more through balls.
- **2.3e:**
  - the acceptance list above, with rating responses first and league references validated last;
  - the residual reported per division and mechanic;
  - if the environment layer is added: its guard tests pass (one scalar per competition, closed mechanic list with evidence, caps, rating dominance, no league names in the engine), its neutral commit keeps the golden values, and the fitted levels leave the rating responses unchanged;
  - any conflicts are recorded.
- **C1:** the bold and cautious arms pass section S.
- **2.4, 2.1 and 2.6:** reports against the rate targets, with CIs and references.
- **Phase D:**
  - the vectorising commits keep the golden values identical, with `update_targets` at 1.5 s or less;
  - the gates in the table;
  - overlay screenshots;
  - 1,000-match acceptance.
- **End of each phase:** the 12 acceptance questions are answered in `progress.md`, and :8000 is restarted after checking for connections.

### Sources

- Opta Analyst / premierleague.com, [2025/26 tactical trends](https://www.premierleague.com/en/news/4426039/opta-analyst-on-long-balls-long-throws-key-tactical-trends-spotted-in-2025-26-season): 849 passes a game at 82.6%, 99.7 long balls (32 m or more), 11.5 high turnovers.
- The Analyst, [down the English pyramid](https://theanalyst.com/articles/how-does-the-style-of-football-change-as-you-journey-down-the-english-football-league): League Two has over 56 throw-ins a game against just over 30 in the Premier League, about 6 minutes less ball in play, and lower accuracy.
- FBref, [2022-23 Premier League passing](https://fbref.com/en/comps/9/2022-2023/passing/2022-2023-Premier-League-Stats): long passes (30+ yards) completed 46.6%.
- Metrica Sports' [open sample data](https://github.com/metrica-sports/sample-data), used in 2.3a for pass travel times.
- The ball-in-play times behind the rates are the Opta figures already in `match_targets.yaml`: 58:11 (23/24), 56:59 (24/25), 55:00 (25/26).

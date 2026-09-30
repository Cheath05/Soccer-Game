# Match Believability Phase: Technical Improvement Plan

## Context

**The code today.**
- The foundation lives on `phase-0-foundation`, 5 commits ahead of `main`, which holds only the initial commit. The working tree is clean.
- A career plays end to end: the detailed agent engine (Tier 0) runs the user's matches, and the fast engine (Tier 1) runs everyone else's.
- The user played a League Two career as Grimsby Town and reported several problems:
  - A watched match takes about 90 real minutes.
  - Scores run high, and one tactical setup wins 6-0.
  - Formations look frozen, and set pieces happen instantly.
  - Substitutions show no ratings.
  - There's no club browsing and no way to simulate to a date.

**The goal of this phase.** Make the match believable, consistent and debuggable by improving the existing engine, not rewriting it. New management features wait.

**How the current code was examined (read-only):**
- Read the design doc and ADR-0002, the whole match engine, the fast engine, the career, season and results code, the API and live WebSocket, the save manager, the live viewer and the tests.
- Ran the test suite: 55 passed. No unit test covers the match engine.
- Instrumented the engine with runtime probes, changing no source, and ran **492 headless matches with real squads**:
  - 70 Premier League matches;
  - 70 League Two matches;
  - 240 tactic A/B matches;
  - 112 fixtures played on both engines.
- Read the user's save (slot 1, Grimsby, League Two). With mentality attacking, pressing high, line high, width wide, tempo fast and passing direct, they won 11-0, 4-0, 9-0 and 8-0 (instant) and 6-0 (watched), taking 42–56 shots to their opponents' 0–6.
- Real-world targets come from:
  - football-data.co.uk: all four English divisions, 2023-24 to 2025-26, 6,108 matches;
  - Opta Analyst;
  - Premier League data;
  - the IFAB Laws of the Game.

### Evidence: agent engine vs real football (per match, both teams)

| Metric | Engine PL (n=70) | Engine L2 (n=70) | Real PL 23/24–25/26 | Real EFL 23/24–25/26 |
|---|---|---|---|---|
| Goals | 3.40 | 3.51 | 2.99 (2.75 in 25/26) | 2.45–2.98 |
| 0-0 / 6+ goals / margin ≥4 | 2.9% / 11.4% / 4.3% | 4.3% / 11.4% / **10.0%** | 4.7% / 6.7% / 5.7% | ~7% / ~4.6% / ~4.4% |
| Shots / on target | 30.5 / 10.0 | 25.8 / 8.0 | 26.2 / 9.1 | ~24 / ~8 |
| Shots from inside the box, mean distance | **86%, 12 m** | 88%, 12.5 m | ~60–65%, ~16 m (approx.) | |
| Passes / accuracy | 1,087 / **89%** | 1,090 / 89% | 873–941 / ~82–84% (accuracy approx.) | |
| Fouls / yellows / **reds** | 27.9 / 3.9 / **0.87** | 21.1 / 2.8 / **0.49** | 21.9 / 4.0 / 0.13 | ~22.5 / ~3.8 / ~0.13 |
| Corners / throw-ins | 7.8 / **13** | 8.7 / 18 | 10.4 / 33–38 | ~10.2 / – |
| Tackle duels (won + dribbled past) | **187 + 452** | 148 + 407 | ~30–40 tackles, ~35–45 take-ons (approx.) | |
| Ball in play | **90 of 96 min** | 91 of 96 min | 55–58 of ~100 min | |
| Restart wait: throw / goal kick / corner / FK / after goal | 3.2 / 4.6 / 8.0 / 3.8 / 7.4 s | same | 16–18 / 28–30 / 34–37 / ~30 / ~72 s | |
| Attackers in box when the corner is taken | **2.2** (65% of corners have ≤2) | 2.3 | 4–5 (corner-kick studies) | |
| Goals from set pieces, incl. penalties | ~9% | ~9% | 21–30% | |
| Shots from fast breaks | **1%** | 0% | 10.2% (1.84 per match, 24/25) | |
| Own goals (share of goals) | 7% | 7% | ~3% (approx.) | |
| Distance per team | 127 km | 124 km | 105–115 km | |

**Measured per live minute of play, the engine is actually slower than real football:** 0.34 shots per minute against 0.46, and 12 passes per minute against 16. Totals run high because the ball is in play for 90 minutes instead of 57. So adding realistic dead-ball time alone would under-score. Calibration has to work per live minute and per possession.

### Evidence: tactics A/B

Grimsby played a 4-2-3-1 against 23 League Two opponents, half home and half away. Opponents used default instructions, and each row is 30 matches.

| Grimsby variant | Win | GF–GA | xG F–A | Shots F–A | Possession | Km run | Fast-break shots conceded |
|---|---|---|---|---|---|---|---|
| All default | 37% | 1.77–1.83 | 1.61–1.52 | 14.0–12.1 | 47% | 129 | 0.07 |
| **All aggressive** | **97%** | **7.10–0.67** | 7.34–0.42 | **49.1–3.8** | 37% | **172** | **0.00** |
| Only mentality attacking | 37% | 1.77–1.83 | 1.74–1.39 | 14.9–10.6 | 46% | 133 | 0.20 |
| Only pressing high | 43% | 2.13–1.63 | 2.39–1.47 | 19.0–12.8 | 51% | 140 | 0.13 |
| Only line high | 43% | 2.00–1.47 | 2.13–1.53 | 18.8–12.5 | 53% | 136 | 0.03 |
| Only width wide | 37% | 1.77–1.50 | 1.56–1.34 | 14.3–11.1 | 48% | 128 | 0.13 |
| **Only tempo fast** | **67%** | 2.30–1.47 | 2.39–1.19 | 17.6–**8.5** | 40% | 134 | 0.17 |
| **Only passing direct** | **77%** | 2.30–**0.67** | 2.46–0.54 | 22.0–**5.0** | 35% | 135 | 0.07 |

### Evidence: are the two engines compatible?

Each fixture was played once on the agent engine and 40 times on the fast engine.
- **Level teams** (rating gap under 4, n=35): both engines give 43% home wins and a home goal difference of about +0.3. Totals differ: 3.51 goals on the agent engine against 2.66 on the fast engine.
- **Premier League against League Two** (rating gap of 12 or more, n=71): the agent engine averages 6.65 goals and 47.5 shots, with a margin of 4 or more in 58% of matches. The fast engine averages 4.4–4.8 goals.
- **Goal difference per rating point:** 0.274 on the agent engine, 0.219 on the fast engine.
- **Conclusion:** the two agree on direction but not on volume or sensitivity to strength, because they're unrelated models. The fast engine uses minute-by-minute Poisson draws on slot ratings and invents its secondary stats afterwards.

---

## A. Current architecture assessment

**Sound, and worth keeping:**
- The simulation core is pure Python with no I/O, and randomness is deterministic (`core/rng.derive_rng`).
- Definitions are YAML validated by Pydantic, and each save slot is its own SQLite file.
- The API layer is thin, and the canvas viewer only draws what the engine sends.

**The weak points this phase has to address:**
1. **The agent engine is three large files with about 80 hard-coded constants:** `engine.py` (641 lines), `actions.py` (915) and `behaviours.py` (314).
   - The engine has no instrumentation, so it can't be calibrated without editing code.
   - It has no unit tests.
2. **Time.** There is one timeline (`eng.t`), and `minute` is an integer.
   - A restart is just a `Restart(ready_at)` delay.
   - There is no half-time state.
   - Playback speed is defined as "ticks per 100 ms loop".
3. **Movement.** Player positions come from one rigid template that moves with the ball. The only role run implemented is `in_behind`, and there are no transition phases.
4. **Tactics are scattered and one-sided.**
   - Instruction constants are spread across `behaviours.py` (`LINE_HEIGHT`, `PRESS`, `MENTALITY_PUSH`, `WIDTH_IN`), `actions.py` (`TEMPO_DELAY`, `MENTALITY_SHOOT`, `DIRECTNESS`) and `engine.py` (`PRESS_FATIGUE`).
   - Almost every effect is a bonus with no matching cost.
5. **The two engines use unrelated models,** so a matchup doesn't produce the same kind of result on both.
6. **Live matches are fragile.**
   - The registry (`api/live.py:_matches`) is a module global keyed only by fixture id.
   - Commands aren't logged, and there is no replay.
7. **The career loop** (`world/career.advance`) always stops on the user's match day. It runs as one synchronous request, with no job or progress mechanism.

## B. Systems to preserve unchanged

- **Data and ratings:**
  - the importers and world build (`importers/*`, `calibration/overall.py`);
  - `ratings/overall.py` (role overalls, familiarity);
  - `defs/loader.py` and the YAML-first approach.
- **Competitions:** `competitions/*` (fixtures, scheduling, standings and tiebreakers, play-offs, calendars) and `world/season.py` (finalising, play-offs, rollover).
- **Persistence:** `persistence/saves.py` (backup API, integrity check, atomic replace). Migrations get added alongside it; nothing is replaced.
- **Engine building blocks to keep and extend:**
  - the attacking-frame transforms (`to_att`, `att_points`);
  - NumPy kinematics (`_move_players`) and ball physics (`_ball_tick`);
  - physical pass execution (`start_pass`) and pass-lane success estimates (`_pass_options`);
  - the xG model (`pitch.expected_goal`) and shot outcome logic (`start_shot`);
  - softmax decisions (`decide`) and Hungarian slot re-assignment (`set_formation`);
  - the `MatchReport` contract and `record_result`.
- **Frontend:** the stack (Mantine, TanStack) and the canvas drawing (`drawPitch`, `drawFrame`).

## C. Systems that need modification

- **`match/engine/engine.py`:**
  - Move clock and period handling to `clock.py`, and restarts to `restarts.py`.
  - Apply substitutions at the next dead ball.
  - Add live player status, a command log and debug snapshots.
- **`match/engine/actions.py`:**
  - Move the duel and foul model to `duels.py`, and restart taking to `restarts.py`.
  - Replace hard shot gating with a utility-based decision, and make decision timing depend on the phase.
- **`match/engine/behaviours.py`:** stays as the coordinator, but its target model is rebuilt around new `phases.py`, `shape.py` and `intents.py`.
- **New engine files:**
  - `tactics.py` (TacticalState);
  - `set_pieces.py`;
  - `probe.py` (metrics and event log);
  - `debug.py`.
- **Config:**
  - `defs/match.py` gains `AgentEngineParams`, instruction `effects`, a presentation config and set-piece definitions.
  - The engine constants move to `data/config/match/agent_engine.yaml`.
- **`match/quick.py`:** refit it as a surrogate of the agent engine, with its stats derived from the same chance model. It shares with the agent engine:
  - a team-strength model built from player attributes and role weights, reusing `ratings/overall.py`;
  - the TacticalState parameters;
  - the fatigue and condition model and home advantage;
  - competition context through `GameState`: knockouts, aggregate scores, extra time.
- **`api/live.py`:** keep only the WebSocket handling. Match control moves to `match/live/session.py` (LiveSession), and the registry moves onto `app.state`.
- **`world/career.py`:** add `simulate_until` and automatic resolution of the user's matches. `advance()` becomes a thin wrapper around them.
- **`api/routes.py`, `queries.py` and `schemas.py`:** add clubs, jobs, extended statistics and replay endpoints.
- **`persistence/`:** a forward-migration registry, `SCHEMA_VERSION` 3, and the new columns and table.
- **Frontend:**
  - Split `LivePage.tsx` into components.
  - Add club pages, a simulate menu with a progress view, and extend the match report.

## D. Root causes of each observed behaviour

| Observed | Root cause (file:function) |
|---|---|
| A watched match takes ~90+ real minutes at 1× | `api/live.py:_advance` steps `speed` ticks per 100 ms loop, so 1× is real time. `LivePage.tsx` advances the playhead by `dt*speed`. |
| The clock shows minutes only | `MatchEngine.minute` is an integer plus one. `minuteLabel()` in the viewer, `MatchEvent.minute` and the `match_event` table store minutes only. |
| No half-time | `engine._end_period` calls `_start_period(2)` immediately, and the live loop never pauses. |
| Added time is random | `stoppage = rng.integers(1,4)*60` and `(2,7)*60`, unconnected to what happened in the match. |
| **High scoring and inflated totals** | See the six causes below this table. |
| **Aggressive tactics win 7-0** | See the causes below this table. |
| Formations look frozen | See the causes below this table. |
| **Corners with 1–2 attackers** | `behaviours._set_piece` sends only the 5 best headers to box spots and the rest to x=58. Players walk at cruise speed, and the corner is taken 5 s after it's awarded. |
| Throw-ins and goal kicks feel instant | 2.5 s and 4 s delays, and no layouts for teammates. `take_restart` just passes to the nearest teammate. |
| **Teleports** | `_restart_tick` snaps the taker to the spot (`pos[taker]=spot`) after 6 s. `shot_tick` sets `pos[keeper]=ball` on a catch. A substitute appears at the outgoing player's position (`_load`). The viewer snaps any jump over 8 m. |
| No ratings when substituting | `bench_info()` sends only name, number and position, and `lineup()` sends stamina only. Match ratings exist only at full time (`actions.rate_players`). |
| No club browsing | There's no club route or page, and league rows aren't links. `GET /clubs/{id}/squad` returns full own-squad data for any club. |
| No sim-to-date | `career.advance()` always stops on the user's match day and runs as a synchronous request. There's no job or progress mechanism. |
| **Save and live bugs** | See the causes below this table. |
| Engines disagree in volume | Two unrelated models. The fast engine's tactics are flat multipliers: attacking gives ×1.12 to own goals and ×1.10 to the opponent's; high press gives ×1.04. Line, width, tempo and passing have no effect in it. |

**Why scoring and totals run high:**
1. **90 minutes of live play.** Restart delays are only 2.5–5 s, and the taker teleports.
2. **Duel storm.** `actions._tackles` rolls every tick for every defender within 2 m, with a 0.12–0.4 chance each time. That's about 640 duels per match.
3. **Cards.** `actions._foul` books 12–22% of fouls regardless of context, and booked players keep tackling. The result is 0.87 red cards per match, and matches where one side is down to ten men feed blowouts.
4. **Shot selection.** `MIN_SHOT_XG=0.05` means almost no long shots.
5. **Pass accuracy is 89%.**
6. **Own goals are 7% of goals.**

**Why aggressive tactics win 7-0:**
1. **Bonuses with no cost:**
   - fast tempo: `TEMPO_DELAY` 1.15 s against 1.6 s, with no execution penalty;
   - direct passing: the `DIRECTNESS` utility bonus;
   - high pressing: 2 pressers, a 21 m trigger, marking extended to wingers and attacking midfielders, and ×1.25 eagerness in `_tackles`.
2. **Counters can't happen.** `behaviours._defend` sends every player who is more than 9 m out of position into an instant full sprint. Meanwhile the ball-winner waits the full `TEMPO_DELAY` plus first-touch time (`gain_possession`).
3. **Fatigue is nearly free.** 33% more running leaves stamina at 0.75 against 0.81, and stamina only scales speed by `0.78+0.22*stamina`.
4. **The AI opponent never adapts.**

**Why formations look frozen:**
- **Positioning:** `behaviours._team` builds anchors from one template. `back = bx−32+push`, and the sideways shift is 0.22 in possession and 0.42 out of it.
- **Space-seeking:** only players within 28 m of the ball look for space, and only among 8 candidate points.
- **Unused role and formation data:** overlap, underlap, invert, drop-deep, drift-wide and arrive-late runs, `press_bias`, `hold_line`, `cross_bias` and formation `relationships` are never read.
- **Phases:** there are no transition phases.

**Save and live bugs:**
- A live match left in memory from one save is reused and written into another save after loading (`live._open`, `_finish`).
- `POST /fixtures/{id}/play` doesn't check for a live match in progress. That leads to a double `record_result`: duplicate rows, and bans served twice.
- There's no autosave after a live match.
- Snapshot copies leave `*.tmp-wal` and `*.tmp-shm` files behind.

## E. Recommended match-clock architecture

**A new file, `match/engine/clock.py`, containing:**
- **`Period` (StrEnum):** `PRE_MATCH, FIRST_HALF, HALF_TIME, SECOND_HALF, ET_BREAK, ET_FIRST, ET_HALF_TIME, ET_SECOND, PENALTIES, FULL_TIME`.
- **`MatchClock`:**
  - fields: `period`, `period_elapsed` (float seconds, advanced only by ticks), `regulation` (2,700 s or 900 s in extra time), `added_announced` and a `StoppageLedger`;
  - `display()` gives `"MM:SS"`, and `"45:00 +1:37"` during added time;
  - `event_label()` gives `"45+2'"`.
- **`StoppageLedger`** accumulates time by cause, following IFAB Law 7:
  - goal celebrations beyond 30 s;
  - substitutions (~30 s each), injury assessments and cards;
  - the time from a penalty being awarded to the kick;
  - time-wasting (restart delays beyond normal by the side that's ahead late on).
- **Announcing added time:** the minimum is announced at 45:00 and 90:00, and it may be increased but never reduced. In v1 it's capped at 1–5 minutes for the first half and 2–9 for the second, so added time can't inflate scoring.
- **Ending a period:** after regulation plus the added time, the half ends at the next neutral moment: no shot in flight, no pending penalty, at most 30 s over.

**Half-time.** The engine enters `HALF_TIME` and stops stepping play.
- `start_second_half()` swaps ends and kicks off (a deliberate reset).
- A headless run continues automatically, with the AI making half-time changes.
- A watched match pauses.

**Compatibility.** `MatchEngine.minute` stays for existing reports. `MatchEvent` gains `second` (the match second) and a clock label. Extra time and penalties move into the same period machine.

## F. Recommended simulation-time architecture

There are three separate notions of time:
1. **Simulation time:** `eng.t` with a fixed 0.1 s tick. It's the only time the engine knows, and it drives physics, decisions and the clock.
2. **Football clock:** derived from simulation time plus the period state (section E). It keeps running through dead balls, as in real football.
3. **Playback time:** belongs to the viewer session.
   - `rate = compression × speed`, where `compression = 2700 / real_seconds_per_half`. It comes from `data/config/match/presentation.yaml` (`real_seconds_per_half: 300`), which makes 1× equal to 9 game seconds per real second.
   - Speeds: 0.5×, 1×, 2×, 4×, 8× and Instant.

**`LiveSession`,** in a new `match/live/session.py`, has no web framework code and can be unit-tested with a fake clock:
- **Anchoring:** `anchor(sim_t, wall_t)` re-anchors on pause, resume and speed changes, so there are no jumps.
- **Advancing:** `pump(now)` steps the engine until `eng.t ≥ due + lookahead`. The lookahead is at most 0.25 s of real time (about 2 s of game time at 1×), so a command applies within a quarter of a second of what the user sees.
- **Frames:** at most 30 per real second (`k = ceil(rate*10/30)`), stamped with simulation time and flagged when they're deliberate resets.
- **Commands:** queued and applied at the next tick boundary, logged as `(tick, command)`, and acknowledged to the viewer with that tick.
- **Instant:** runs the rest of the match on a worker thread with progress messages. It's the same engine, so the result matches watching it.

**Speed never changes the outcome.** The engine never reads wall-clock time or the speed setting, and highlights mode only drops frames. Tests assert identical results at 0.5×, 1×, 8× and Instant for the same command log.

**`api/live.py` becomes a thin 20 Hz WebSocket loop:** receive, `session.apply`, `session.pump`, send.

**Budget.** 1× needs 90 ticks per real second and 8× needs 720. The engine runs about 8,000 ticks per second headless, so there's ten times the headroom. Lag is measured and reported.

## G. Recommended scoring and chance calibration strategy

1. **Measure before changing anything.** Build a first-class `match/engine/probe.py` (MatchProbe), fed by engine hooks rather than patched in from outside. It collects:
   - possessions and the funnel from possession to final third, box, shot, xG and goal;
   - passes by zone and type, duels, and shots with context (goal-side defenders, nearest defender, rebound, set-piece or fast-break origin);
   - restarts and their waits, ball-in-play time, distance run and PPDA.

   The same data later feeds the debug overlay and the match analytics.
2. **Build a calibration harness.**
   - Add `footsim calibrate-engine` (`calibration/engine_batch.py`) and `just calibrate-engine`.
   - Each run is a multiprocessing batch of real squads by division, or synthetic teams, with seeded pairs.
   - It writes a markdown and JSON report against `data/config/calibration/match_targets.yaml`, which holds per-division ranges and cites its sources.
3. **Fix structural causes in order, and run a 200-match batch after each fix:**
   - a. Dead-ball time, via the restart machine (section K): ball in play 55–60 minutes.
   - b. Duel model (`duels.py`):
     - A defender decides to engage and gets one challenge per engagement window.
     - Between challenges, the defender jockeys, which slows the carrier and adds pressure.
     - Taking a player on becomes an explicit option for the ball carrier.
   - c. Discipline model:
     - A foul's severity decides the card: careless, reckless or excessive.
     - Tactical fouls happen to stop counters.
     - Booked players become cautious, and straight reds come from about 0.5% of fouls.
   - d. Tempo per live minute: time on the ball and one-touch passing in transitions. Target 15–17 passes per live minute.
   - e. Pass accuracy through pressure, receiver contests, first touch and realistic long-ball success.
   - f. Shot selection: a long-shot tendency from role, attributes and instructions, replacing the hard `MIN_SHOT_XG` cut-off.
   - g. Set pieces (section K) and transitions (section J).
   - h. A final global fit: goalkeeper, finishing noise and home advantage.
4. **Diagnose along the chain, not at the end.** The report shows the full funnel per team per live minute. It compares with known real values: Opta sequences average 9.5 s, there are 13–15 high turnovers per match, and 10% of shots come from fast breaks.
5. **Batch sizes:**

   | Purpose | Matches | Time on 7 workers |
   |---|---|---|
   | Development loop | 200 | ~4 min |
   | Phase acceptance | 1,000 | ~17 min |
   | Full distributions (scorelines, margins, 0-0) | 10,000 | ~3 h, overnight |
6. **Keep comparisons fair.** Use the same random seeds across variants and paired A/B runs, and report 95% confidence intervals.
7. **The shorter watching time is not a fix for scoring.** The engine always simulates 90 minutes plus added time, and every metric is per 90 minutes or per live minute. A test asserts the simulated duration is at least 5,400 s at every playback speed.
8. **Strength sensitivity** is calibrated against betting-market odds, which football-data includes. The spread of home-win probabilities across a league's fixtures in the engines must match the market's spread for that league.

## H. Recommended tactical model

**Principle:** an instruction changes behaviour parameters only, never player attributes or success probabilities. Every upside must create a measurable downside through the simulation itself.

**`match/engine/tactics.py`: `TacticalState`.** Each team's state is recomputed every 5 s of game time and whenever something changes. It draws on:
- the instruction levels, each carrying a data-defined `effects` block in `data/config/match/instructions/team.yaml`;
- formation and roles;
- `GameState`: score difference, minute, red cards and aggregate score;
- the side's manager layer;
- team fatigue, since tired players automatically press less and hold a looser line.

**The behaviour parameters it produces:**
- **Shape:** `line_height_m`, `engage_line_m`, `compactness_m`, `width_m`.
- **Pressing:** `press_trigger_m`, `pressers`, `counterpress_s`, `cover_depth_m`.
- **Commitment forward:** `rest_defence_n`, `fullback_advance`, `runs_rate`.
- **On the ball:** `hold_time_s`, `pass_risk_weight`, `forward_bias`, `long_ball_bias`, `shot_threshold`, `cross_bias`.
- **Effort and restarts:** `sprint_effort`, `tackle_commitment`, `restart_tempo`, `time_wasting`.

**What each instruction does:**

| Instruction | Behaviour and positioning | Decision tendencies | Risk created | Fatigue | Likely opponent response |
|---|---|---|---|---|---|
| **Mentality** | Rest-defence count (6/5/4 behind the ball); how often full-backs and centre-mids run forward; how many players attack the box; block height | More forward passes and more shots from range | Fewer players behind the ball, so more counters conceded | More box-to-box running | Stays compact and counters faster, with forwards held high |
| **Pressing** | Line of engagement, trigger distance, number of pressers, counter-press duration, cover-shadow runs | More willing to commit to tackles | Gaps behind the press; long balls bypass it; more fouls; beaten by composed passers with vision | High sprint load, then late-game decline | Goes direct, kicks goal kicks long, runners go in behind |
| **Defensive line** | Offside line height; when to step up or drop | Plays the offside trap more often | Space behind for through balls, especially against faster forwards | More recovery sprints | Plays passes over the top and runs channels |
| **Width** | Sideways spread in possession; players occupying the wide lanes | Switches and crosses when wide, central combinations when narrow | Wide: longer passes and a slower counter-press. Narrow: predictable and crowded | Wide players run more | Narrow block or pressing traps set out wide |
| **Tempo** | Time on the ball, one-touch passing rate, pass speed | Looks forward first | Faster play brings bigger execution errors and more turnovers. Slower play lets the opponent organise | Slightly higher | Counter-presses or sits deeper |
| **Passing** | Preferred pass length and directness; forwards stay higher and run more when direct | Chooses long-ball targets | Long balls complete only ~45–55% and lead to aerial duels and second balls | Direct play needs fewer support runs | Drops the line, sweeps behind it, wins headers |

**Context shapes the effect instead of any multiplier.** How well a press works emerges from:
- how quickly pressers arrive, which depends on acceleration, sprint speed and stamina;
- their cover-shadow angles and their tackling and defensive awareness;
- the ball carrier's first touch, composure, vision and passing, through decision quality and execution under pressure;
- whether the formation gives the pressing side extra players near the ball;
- fatigue, which lowers speed and acceleration and makes decisions noisier.

**Game-state awareness** comes from a `ManagerAI` in-match layer.
- It runs for AI teams, and for the user's team only if "assistant adjusts" is on.
- It makes utility-based changes at triggers: every 5 game minutes, after goals and red cards, at 60, 70 and 80 minutes, and at half-time.
- A team ahead late lowers tempo and risk, drops deeper, makes defensive substitutions and takes restarts slowly (the stoppage ledger records it).
- A team behind late does the opposite: more tempo and risk, more players forward, attacking substitutions and quick restarts.
- No team gets "+X attack". Manager personalities plug in later, in the AI managers phase.

**The fast engine consumes the same TacticalState** through its surrogate (section N, and phase B2 in section T).

## I. Recommended dynamic movement model

**Order of work within each tick** (a refinement of the user's decision loop, fitted to the current `step()`):
1. Clock and restart state.
2. Team phase and `TacticalState`, re-planned 3 times a second.
3. Structural jobs, reassigned every ~2 s.
4. Intents and target positions, 3 times a second, with each player's reaction delay applied.
5. The ball carrier's decision, only at decision points: `decide()`, with actions scored as options.
6. Carrying out the action: pass, shot, carry or duel.
7. Physics for the ball and players.
8. Event reactions: a turnover, a shot or the ball going out triggers the next re-plan immediately for the players nearby.

`behaviours.py` coordinates three new modules; each team re-plans three times per second:

1. **Phase (`phases.py`).**
   - In possession: `BUILD_UP`, `PROGRESSION`, `FINAL_THIRD`.
   - Out of possession: `HIGH_PRESS`, `MID_BLOCK`, `LOW_BLOCK`.
   - Transitions: `ATTACKING_TRANSITION` and `DEFENSIVE_TRANSITION`, which last until possession settles (about 6–8 s) or the shape is restored.
   - `SET_PIECE`, driven by the restart machine.
2. **Team shape (`shape.py`).**
   - Heights: back-line height comes from the line instruction, the ball, offside and danger. Midfield and forward lines keep a compact 10–15 m gap in blocks.
   - Width: the block is 40–45 m wide when defending and set by the width instruction in possession.
   - Ball-side shift: the block shifts towards the ball, and the far side narrows more than the near side.
   - Line depth: the defensive line is no longer a rail. The far-side centre-back sits 1–3 m deeper as cover, and a defender steps out when a forward drops into his zone.
3. **Slot anchors.** A formation's base position plus its phase offsets is mapped onto the team shape's lines, not one global stretch.
4. **Structural jobs in possession,** following positional-play principles:
   - one width provider per flank and one depth provider on the last line;
   - two ball-side support options at different angles and heights;
   - a rest defence of N players (from mentality), one more than the opponent's forwards;
   - 2–4 players in the box in the final third, plus someone on the edge for second balls and someone for cut-backs.

   These jobs are reassigned every ~2 s with the existing `scipy.linear_sum_assignment`, weighing distance, role fit and discipline. Rotations then emerge naturally: a centre-mid fills the wide lane when the full-back tucks inside.
5. **Intents (`intents.py`).** Each player carries a `MovementIntent`:
   - Support and structure: `HOLD_SHAPE, SUPPORT, WIDTH, PIN, CHECK_TO_BALL, DROP_DEEP`.
   - Runs: `RUN_IN_BEHIND, CHANNEL_RUN, OVERLAP, UNDERLAP, INVERT, ARRIVE_LATE, ATTACK_BOX, CUTBACK`.
   - Defending: `REST_DEFENCE, PRESS, COUNTERPRESS, COVER, MARK, TRACK_RUNNER, BLOCK_LANE, RECOVER`.
   - Restarts: `SET_PIECE`.

   Each intent has a target generator, an urgency band (walk, jog, run or sprint) and minimum and maximum durations, with hysteresis so players don't flicker between intents. The runs defined in the role YAML files finally become real, triggered by the situation.
6. **Positional discipline,** from 0 to 1, comes from:
   - role freedom;
   - decisions, teamwork, concentration and positioning attributes;
   - personality (team orientation);
   - later, player instructions and manager philosophy.

   It limits how far a player drifts from his anchor and how often he chases space, and it adds positioning error.
7. **Defending.** Players defend zones and hand runners over, and pressers curve their run to cut the passing lane.
   - A cover player sits 5–8 m behind the presser.
   - The far full-back tucks in, and the defensive midfielder screens the line from ball to goal.
   - The role fields `track_runners`, `hold_line` and `press_bias` are implemented.
8. **Movement.** Speed follows the intent's urgency band: walking 1.5 m/s, jogging 3.5, running 5.5, or a sprint at the player's own top speed.
   - Turning depends on agility and balance.
   - Stamina drains by speed band, which brings distance run down to a realistic 105–115 km per team.

## J. Recommended transition model

- **Transition phases.** A turnover at time t0 puts both teams into transition phases for a set window.
- **Reaction delay.** Each player reacts after 0.2–0.9 s, depending on anticipation, reactions, concentration and fatigue. Until then he keeps his old intent, so a full-back caught upfield really is caught.
- **The team that lost the ball.**
  - The nearest 1–3 players counter-press for `counterpress_s`, which comes from the pressing instruction.
  - The rest defence stays goal-side and delays rather than diving in.
  - Everyone else recovers: sprinting if they're behind the ball, jogging otherwise.
  - If the counter-press fails, the team drops into its block.
- **The team that won it.**
  - The ball-winner makes his first move after 0.3–0.8 s, depending on vision and decisions. Passes into the space behind are weighted up.
  - 1–3 players sprint forward in behind or into the channels, and 1–2 others support.
- **Tactical fouls.** Stopping a dangerous counter with a foul (and a yellow card) emerges from the defender's own decision-making.
- **Targets:** fast-break shots are 6–12% of all shots, and some teams regain the ball within 5 s of losing it through counter-pressing.

## K. Recommended restart state machine (set pieces)

**A new file, `match/engine/restarts.py`,** takes over `_out_of_play`, `_set_restart`, `_restart_tick`, `pick_taker` and `take_restart`. The states:
1. `LIVE`
2. `BALL_OUT`: up to 1 s while players slow down.
3. `AWARDED`: the kind, team and spot are decided under the Laws, with commentary and a stoppage-ledger entry.
4. `SETUP`: players move physically to their routine targets while the taker walks to the ball and places it. The duration comes from a config distribution adjusted for the game state. A quick restart is possible.
5. `READY`: the taker is set and the required players are in position, or a timeout of at most 1.5 s has passed.
6. `TAKEN`: the ball is in play once it's kicked and clearly moves, or once a throw enters the field.

**Other states:**
- **Goal celebration:** `GOAL_CELEBRATION` (45–70 s, recorded in the stoppage ledger) leads into the kick-off setup.
- **Substitutions:** queued ones happen at `AWARDED`. The outgoing player walks to the nearest touchline; the replacement enters at the halfway line and jogs to his position.
- **Injuries:** an injury stoppage ends with a drop ball.
- **Half-time:** handled by the clock (section E).

**Rules, checked against the current IFAB Laws:**
- **Throw-in:** opponents at least 2 m away.
- **Goal kick:** taken anywhere in the goal area, with opponents outside the box until it's in play.
- **Corner:** opponents at least 9.15 m from the arc.
- **Free kick:** opponents at least 9.15 m away; a wall of 3 or more players means attackers stay at least 1 m from it; quick free kicks are allowed.
- **Countdowns:** the 5-second countdowns for throw-ins and goal kicks, and the goalkeeper's 8-second rule, come later.

**Setup durations** are in game seconds, set in config, and tuned until the ball is in play 55–60 minutes:

| Restart | Starting value | Opta reference, 24/25–25/26 |
|---|---|---|
| Throw-in | 12 ± 4 s (long throw 20 ± 5 s) | 15.6–17.9 s |
| Goal kick | 22 ± 6 s | 28.3–30.3 s |
| Corner | 30 ± 6 s | 33.6–36.9 s |
| Free kick | quick 4 ± 2 s, normal 20 ± 6 s, dangerous 35 ± 8 s | ~30 s |
| Penalty | 60 ± 15 s | – |
| Goal celebration to kick-off | 55 ± 10 s | ~72 s |

**Layouts,** in `data/config/match/set_pieces/*.yaml`, define attacking and defending templates:
- **Attacking corner:**
  - Roles: near-post runner, far-post runner, a player screening the keeper in the six-yard box, penalty spot, edge of the box, a short option (real rate 11–18% short), and 2–3 rest defenders.
  - How many attack the box (4, 5 or 6) is an instruction. The delivery (in-swinger, out-swinger or short) and target zone follow the taker's foot and the routine.
- **Defending corner:** zonal (4–6 players on the six-yard line and penalty-spot zones), man-to-man, or mixed (4–5 zonal plus 3–5 markers). The marking scheme is an instruction, with 1–2 players left up as counter outlets.
- **Throw-in:** 2–3 nearby options (short forward, short back, infield) under marking. Players with a long throw who are within 35 m of the goal line use a mini-corner box layout.
- **Goal kick:** play it short (centre-backs split to the edges of the box, the defensive midfielder drops, full-backs go wide) or long (aerial target plus second-ball runners). It's chosen from a `goal_kicks` instruction, the keeper's kicking and the opponent's press.
- **Free kick:** defensive (quick), midfield (build-up), crossing (box layout plus the defensive line) or direct (a wall of 3–5 depending on angle and distance). The state machine supports all of them from the start; the routines themselves arrive in F2.

**Readiness.** A corner is taken when the taker is at the arc and at least the routine's number of attackers are within 2 m of their targets, or when the maximum setup time runs out. Late arrivals are allowed, and nobody teleports.

## L. Recommended substitution UI changes

- **A new `status` message on the live WebSocket,** one entry per player:
  - identity and position: name, number, position, role;
  - **OVR in his current slot** and his best OVR, next to his **live match rating**;
  - energy % (in-match stamina) and condition % (pre-match fitness);
  - cards: yellow and red;
  - stats: goals, assists, shots, passes, pass %, tackles, interceptions, fouls and xG.

  It updates every ~5 s of game time and after each event.
- **Live match ratings.** The rating formula moves out of `actions.rate_players` into a shared `match/ratings.py` and updates continuously. Both engines use it.
- **Bench players** show:
  - OVR at their natural position, and OVR if played in the chosen slot (`LineupPicker.slot_rating`);
  - how familiar they are with that slot (Natural, Accomplished and so on);
  - condition and age.
- **The Subs tab** becomes two sortable tables, On pitch and Bench, with columns # · Name · Pos · **OVR** · **Rating** · Energy · Cond · 🟨.
  - Choosing the player to take off re-scores the bench for that slot.
  - Changes are queued and apply at the next stoppage, following the 5-subs, 3-windows-plus-half-time rule.
- **Labelling.** OVR (long-term ability) is a neutral badge, while the match rating is coloured by band, and tooltips explain the difference.
- **No recommendations:** the screen gives information, not advice. The half-time panel reuses the same tables.

## M. Recommended other-club squad UI

- **A `/clubs/$clubId` page:**
  - Header: name, league, position and points, reputation, and stadium name and capacity (already in the `club` table).
  - Manager: shown as "—" until AI managers exist.
  - Budget: a labelled estimate from the wage bill and reputation.
  - Last 5 results (linking to reports) and the next 5 fixtures.
  - Recent transfers: a "none yet" placeholder.
  - A squad summary: average age, average OVR, top five players.
- **A simplified squad tab:** Name, Pos, OVR, Age, Status (available, injured or suspended), plus optional Value, Contract expiry and Form. There are no management controls. Rows link to the player page, which already hides exact potential for other clubs.
- **Links added from:** league table rows, fixture lists, match report and live team names, and the player page's club.
- **Ready for the transfer market:** keep value, wage and contract fields, and add nullable `transfer_status` and `interested_clubs` fields to the API schemas.

## N. Recommended sim-to-date architecture

- **`world/simulate.py`:** `simulate_until(conn, world, target, policy, on_progress) -> SimOutcome`.
  - It reuses `_play_day`, `after_day`, `daily_recovery` and `rollover`.
  - `play_user_fixture_auto()` resolves the user's own matches. It uses the user's saved tactic and a lineup picked by the assistant.
  - By default it uses the fast engine, which is aligned with the detailed one after phase B2 (section T). An optional "detailed" setting runs the agent engine headless, at about 7 s per match.
  - `advance()` ("Continue") becomes `simulate_until(next user match)`.
- **`StopPolicy`** decides where simulation pauses:
  - on by default: the user's match;
  - a major injury to one of the user's players (21 days or more);
  - a red card or suspension;
  - the end of the season or a play-off place;
  - future hooks for contracts, transfer offers, board warnings and cup draws.

  "Sim without interruptions" turns them all off.
- **Presets:** next fixture, 1 week, 1 month, 1 January, halfway through the season (the middle round of the user's league), end of season, or a custom date.
- **Execution:** a job runner (`api/jobs.py`) with one worker thread and one job at a time.
  - It commits after each simulated day, so progress stays consistent and cancelling between days is safe.
  - It autosaves at the end.
  - Progress reads like "Matchday 23/46 · 12 Dec 2026 · 1,034 matches played".
- **Speed:** about 0.5 s per matchday today, so 30–60 s for a full season.

## O. Recommended API changes

**REST:**
- `GET /api/clubs/{id}`: club overview.
- `GET /api/clubs/{id}/squad`: the full view for the user's club, a limited `ClubSquadPlayerOut` for other clubs.
- `POST /api/career/simulate {target|preset, stop_on[], user_matches: quick|detailed}` returns `{job_id}`. Also `GET /api/jobs/{id}` and `POST /api/jobs/{id}/cancel`.
- `GET /api/fixtures/{id}` gains:
  - team stats: tackles, interceptions, saves, offsides, pass %, fouls;
  - player lines: position, tackles, interceptions, fouls, saves, xG;
  - events with `second` and a clock label.
- `GET /api/fixtures/{id}/replay` for debugging: seed, engine and config versions, the input snapshot and the command log.
- `POST /api/debug/replay`: re-simulate up to a tick and return state or frames.
- `POST /fixtures/{id}/play` refuses when a live match for that fixture is in progress.

**WebSocket `/api/fixtures/{id}/live`, protocol v2:**
- **Server to client:**
  - `init`: teams, statuses, bench, formation and instruction options, presentation config;
  - `frames`: decimated frames, plus `clock {period, display, added}` and `state` (live, a restart kind and stage, half-time or full-time), plus debug data when enabled;
  - `event`, `status` (changes only), `ack {cmd_id, tick}`, `half_time`, `end`, `error`.
- **Client to server:** `pause`, `resume`, `speed`, `instant`, `mode`, `formation`, `instruction`, `sub` (queued), `cancel_sub`, `auto_subs`, `start_second_half`, `debug`. Every command carries a `cmd_id`.
- **The live match registry** lives on `app.state`, keyed by save slot, career seed and fixture.
  - Loading or starting a career discards any live match, with a warning.
  - `_finish` checks that the active career still matches before writing.
  - Idle matches expire after 30 minutes.

## P. Recommended database/schema changes

- **Forward migrations:** `persistence/migrations.py` holds ordered steps and applies them to the working copy on load, taking `SCHEMA_VERSION` to 3. The user's current Grimsby save stays playable, and a unit test migrates a version-2 database.
- **Version 3:**
  - `match_event`: add `second`, `x`, `y` and `xg`, all nullable.
  - `player_match`: add `position`, `fouls`, `offsides`, `dribbles`, `dribbles_won`, `key_passes`, `crosses`, `clearances`, `blocks`, `xg` and `distance_m`, defaulting to 0.
  - New table `match_replay(fixture_id PK, engine_version, config_hash, seed, inputs_json, commands_json, created_at)`, for the user's matches only, keeping the last 50.
  - `tactic`: add a nullable `set_pieces` JSON column (corner routine, marking scheme, takers, goal kicks).
  - `fixture.sim` gains the value `auto` for user matches resolved by sim-to-date.
- **Saving:** copied snapshots are set to `journal_mode=DELETE`, so no stray `*-wal` and `*-shm` files are left behind. Frames are never stored; replays re-simulate deterministically.

## Q. Recommended frontend changes

- **Split `LivePage.tsx`** into `match-viewer/` pieces:
  - hook and playback: `useLiveMatch` (the WebSocket protocol) and `PlaybackClock` (interpolates by simulation time at the server's rate);
  - pitch: `PitchCanvas` with its overlays;
  - controls and clock: `ScoreBar` (MM:SS clock, period and added-time badges) and `PlaybackControls` (0.5×–8×, Instant, Highlights, Pause);
  - panels: `HalfTimePanel`, `SubsPanel`, `TacticsPanel`, `CommentaryFeed` (MM:SS) and `StatsPanel`;
  - `PlayerCard`: click a player for a compact card that doesn't cover the pitch.
- **Debug overlay:** `DebugOverlay` and `DebugPanel`, switched on by Developer mode in settings or `?debug=1`. It shows:
  - timing and state: the clock and tick, the phase and the restart state;
  - ball: the owner and its coordinates;
  - shape: team lines and width, and the offside line;
  - per player: the target and actual position, and the intent, drawn as arrows;
  - pressing assignments;
  - the ball carrier's top options with their scores, and the last pass target and shot xG;
  - pressure and fatigue.
- **New club page:** `ClubPage.tsx` with a squad tab, linked from the league table, fixtures, reports and player pages.
- **Simulate:** a `SimulateMenu` beside Continue (presets, date picker, stop toggles) and a `SimulateProgress` modal with a Cancel button.
- **Match report:** the extended stats and player columns, and MM:SS event times.
- **Commentary tied to real events.** A new `match/engine/commentary.py` builds every commentary line from a structured probe event, never from a timer or free-floating text.
  - "Recover possession in midfield" appears only on a real regain in that zone.
  - "Drives into the box" appears only on a carry that enters the box.
  - Restart lines ("X takes it short") come from the restart machine.
  - Lines are rate-limited by choosing among real events. The periodic possession remark in `engine._clock` is removed.
- **Shared code:** `api/types.ts` and `api/hooks.ts` gain clubs, jobs and the protocol v2 types.

## R. Recommended tests

**Unit tests** run in well under a minute. They use synthetic teams from a new `tests/support/teams.py`, so they don't need the EA data file. Coverage:
- **Clock:** MM:SS formatting; half-time at 45:00 plus added time; the second half starting at 45:00; full time at 90:00 plus added time; extra time; the stoppage ledger and its caps.
- **Restarts:**
  - the correct restart after the ball crosses a touchline or goal line, by last touch, including a ball that barely crosses;
  - the right corner arc, placement within the goal area, and throw-ins taken from the crossing point;
  - every state transition;
  - distances respected when the ball is kicked: 9.15 m, 2 m, outside the box;
  - quick free kicks;
  - goal → celebration → kick-off, and the second-half kick-off;
  - the match clock never jumping.
- **No teleports:** no player moves more than 1.1 × top speed × tick in one tick, except in flagged resets.
- **Substitutions:** made only at dead balls, windows counted correctly, half-time substitutions free.
- **Determinism:**
  - the same seed, inputs and commands give an identical event-log hash;
  - LiveSession at 0.5×, 1×, 8× and Instant gives identical results;
  - a replay from `match_replay` is identical to the original.
- **Duels, fouls and cards:** small batches against loose bounds.

**Integration tests:**
- The WebSocket v2 flow: init → resume at 8× → half-time → formation change → start the second half → a queued substitution applied at a stoppage → Instant → end. Command acknowledgement timing is checked too.
- **Live-match safety:**
  - a live match is isolated when another save is loaded;
  - the instant-result endpoint refuses while a live match is in progress;
  - there's an autosave after a live match.
- **Save and load:**
  - checked before a match, after a live match, after sim-to-date and after the season rollover;
  - a version-2 save migrates.
- **Sim-to-date:** presets, the stop policy, cancelling, progress reporting, and simulating a month in one job giving the same result as advancing one day at a time.
- **Club endpoints and the restricted squad view.**

**Statistical tests** are marked slow and run with `just validate-engine`:
- a 100-match smoke test (about 2 minutes), 1,000-match acceptance and 10,000 overnight;
- tactical A/B for every instruction, with paired seeds;
- formation A/B for 4-3-3, 4-4-2 and 4-2-3-1: they must differ measurably in width, possession, final-third entries and PPDA, without one formation being best everywhere;
- quality: 90 vs 70, 80 vs 80, and strong attack vs strong defence;
- fatigue: matches every 3 days vs every 7 days, on both engines;
- cross-engine consistency.

**Frontend end-to-end tests** (`frontend/e2e/`): a live match including half-time and substitutions; browsing a club; simulating one month.

## S. Quantitative acceptance thresholds

Targets are the Premier League and the EFL, per match with both teams combined. Final checks use 1,000 matches unless stated otherwise.

**Results and events:**

| Area | Target |
|---|---|
| Goals | PL 2.65–3.05; EFL 2.45–2.85; mean within ±0.15 of target |
| Home / draw / away | 41–47% / 22–29% / 28–35% |
| 0-0 / 6+ goals / margin ≥4 | 4–9% / 3–7% / 2–6% |
| Shots / on target / xG | 23–27 / 7.8–9.5 / 2.5–3.1 |
| Conversion / xG per shot / shots from outside the box | 9.5–12% / 0.09–0.12 / 30–42% |
| Passes / accuracy | PL 850–1,000 / 80–85%; EFL 750–900 / 74–81% |
| Fouls / yellows / reds | 20–24 / 3.4–4.3 / 0.08–0.18 |
| Corners / throw-ins / goal kicks | 9–11.5 / 32–42 / 14–20 |
| Penalties | 0.15–0.30 per match, 75–85% scored |
| Tackles / take-ons (success rate) | 28–40 / 30–45 (45–60%). Approximate; the definitions are pinned in the targets file |
| Ball in play / total match length | 54–60 min / 97–101 min |
| Added time | 1st half 2–5 min, 2nd half 4–8 min; stoppage-time goals ≤ 12% of all goals |
| Goals from set pieces, incl. penalties / from fast breaks | 20–30% / 5–12% |
| Share of shots from fast breaks | 6–12% |
| Attackers in the box at corner delivery | mean 4.5–6; at least 4 in 80% or more of non-short corners |
| Distance per team | 100–118 km |

**Teleports:** zero outside flagged resets.

**Tactics,** for equal teams over at least 400 paired matches per setting:
- Any single instruction change moves goal difference by at most ±0.35 per match and win rate by at most 10 percentage points.
- **The all-aggressive setup (the user's):**
  - improves goal difference by no more than 0.6 and win rate by no more than 15 points;
  - raises xG against by at least 10% and fast-break shots conceded by at least 30%;
  - leaves the team with at least 5 points less stamina at 90 minutes.
- Pressing: a high press gives a PPDA of 10 or lower; a low press gives 14 or higher.
- Every instruction must also change at least one behaviour metric significantly (width, block height, PPDA, sprint distance). Tactics must not become meaningless.
- **Changes must be visible on the pitch,** within 10 s of game time:
  - line set to high moves the average back-line height up by 6–10 m;
  - width set to wide spreads the team 6–10 m wider in possession;
  - a high press brings the nearest defender at least 1.5 m closer to the ball carrier;
  - a formation change settles into the new slots within 8 s, with no teleports.

**Player quality:**
- A 90-rated side against a 70-rated side: the favourite wins 75–92% of 500 matches, never 100%. Margins of 4 or more stay under 35%, where today it's 58%.
- 80 against 80: home wins 41–47%.
- Strong attack against strong defence: fewer goals than strong attack against weak defence.
- Match-outcome probability spreads within the betting-market spread for the league.

**Fatigue** (10 matches, every 3 days vs every 7 days):
- The congested side ends each match 10–20 points lower in condition.
- It concedes a larger share of goals from the 75th minute on (+10–25% relative).
- Its injury risk is at least 1.3×, but its overall goal rate stays within ±15%.

**Cross-engine**, on the same fixtures:
- mean goals within ±0.15 and home-win rate within ±4 points;
- goal difference per rating point within ±20% of each other;
- shots within ±2.

**Viewing:**
- At 1×, the first half plus added time lasts 5:00–5:45 of real time, and the whole match 10–11.5 minutes (excluding pauses).
- Pause, speed and tactical commands take effect in under 250 ms of real time.
- There's no full-page reload.

**Performance:**
- A headless agent match takes at most 8 s (about 7 s today).
- Simulating a full season to date with the fast engine takes at most 90 s.

**Determinism:** 100% identical results for the same seed, inputs and command log.

## T. Recommended development order

The user's letters (A–K) are kept, with a few deviations based on dependencies, each marked with ★:

1. **Phase 0 – Measure and make safe.**
   - The probe, calibration harness, targets file, synthetic test teams and determinism test.
   - Engine constants moved to YAML.
   - Save and live-match safety fixes: the registry, the double-record guard, autosave after live matches, and the WAL leftovers.
2. **Phase A – Match clock and 5-minute halves.**
   - `clock.py`, half-time and the stoppage ledger.
   - LiveSession with time compression and speeds 0.5×–8× plus Instant.
   - Protocol v2 and the MM:SS UI.
   - Commentary generated from events.
   - ★ The player status data and ratings in the subs panel ride along, because the live page is being rebuilt anyway.
3. **Phase F1 – Restart state machine (★ moved ahead of calibration).**
   - Dead-ball time, setup with physical movement, no teleports, substitutions at stoppages.
   - Basic layouts for corners, throw-ins and goal kicks.

   Dead-ball time and set-piece structure change every rate in the game, so calibrating before them would be redone.
4. **Phase B1 – Calibration pass 1:** duels, fouls and cards, tempo per live minute, pass accuracy, shot selection and goalkeeper. Meets targets at 200-match batches.
5. **Phase C1 – Tactical guardrails (★ C split in two).**
   - Remove the free bonuses (tempo, direct, mentality shooting, press eagerness) and add real costs: execution error, fatigue effects and long-ball turnovers.
   - Give the AI basic in-match responses.
   - Stops the 7-0 problem quickly.
6. **Phase D – Dynamic movement:** phases, team shape, intents, lanes, role runs, discipline and defensive behaviour.
7. **Phase E – Transitions.**
8. **Phase C2 – The full tactical model:** TacticalState, context, game state and manager AI, plus the A/B suite with thresholds.
9. **Phase F2 – Set-piece routines:** corner routines and marking schemes, long throws, goal-kick build-up patterns, free-kick variants, and set-piece instructions in the UI.
10. **Phase B2 – Recalibration and engine alignment.**
    - 1,000-match acceptance.
    - Refit the fast engine as a surrogate of the agent engine, with shared team strength and tactical effects, and add the cross-engine tests.

    ★ This comes before I, so sim-to-date resolves the user's matches consistently.
11. **Phase G – Finish the substitution and half-time experience:** windows, queued substitutions, the player card.
12. **Phase H – Other-club pages.**
13. **Phase I – Sim to date.**
14. **Phase J – Match analytics:** extended report stats and player columns, a shot map from event x/y, and average positions. Heatmaps and pass maps come later.
15. **Phase K – Full validation:** 1,000 and 10,000-match runs; tactic, formation, quality, fatigue and cross-engine suites. Then reassess before transfers and the other management systems.

**Each phase is done only when:**
- the tests are green;
- the harness report is attached (for engine phases);
- a manual play checklist passes, drawn from the user's 12 acceptance questions.

**Recommended order, briefly:**
- **First:** Phase 0 (measure and make safe).
- **Second:** A (clock and 5-minute halves).
- **Third:** F1 (the restart machine).
- **Fourth:** B1 (calibration).
- **Fifth:** C1 (tactical guardrails).
- **Then:** D → E → C2 → F2 → B2 → G → H → I → J → K.

## U. Risks and regressions to watch

- **Calibration whack-a-mole.** Many parameters interact. Change one subsystem at a time, use paired seeds, and let the harness reports gate every merge.
- **Performance.** Richer movement could slow the engine past its 8 s budget. Keep re-planning at 3 Hz, re-plan less for players far from the ball, vectorise candidate scoring, and profile every phase.
- **Intents flickering or jittering.** Use minimum durations, hysteresis and smoothed targets.
- **Losing determinism.** Keep the simulation free of wall-clock time and of set or dict ordering. The playback loop mustn't touch the engine's random numbers. A command-log replay test guards this.
- **Save compatibility.** Test the migration on a copy of a version-2 save. Autosaves stay cheap, taking about 0.2 s.
- **Tactics over-corrected to meaningless.** The thresholds include minimum behaviour effects as well as maximums.
- **Added time producing late goals.** Watch when goals are scored in the match.
- **Watchability at 9× compression.** Tune the frame rate and interpolation, and make sure the ball's arcs look right at 8×.
- **The fast engine drifting from the detailed engine** as the engine keeps changing. Cross-engine tests run in `validate-engine`.
- **A mid-season feel change for existing careers.** Accepted; noted in the release notes.
- **Live matches left in memory** by abandoned sessions. They expire, and loading a save clears them.
- **Scope.** Each phase ends playable. New management features stay out of scope (§53).

## V. Exact first implementation tasks

1. **Metrics.** `backend/src/footsim/match/engine/probe.py`: `MatchProbe`, fed by explicit engine hooks at pass start, take, duel, shot, goal, restart set and taken, and the per-tick live and possession tracker. It's off by default, with no overhead when disabled.
2. **Harness.**
   - `backend/src/footsim/calibration/engine_batch.py` and `footsim calibrate-engine` in `cli.py`, with `--division`, `--n`, `--workers`, `--seed`, `--variant` and `--synthetic`.
   - `data/config/calibration/match_targets.yaml`, using the football-data and Opta numbers above with their sources.
   - `just calibrate-engine`.
3. **Constants to config.**
   - Move the agent-engine constants into `data/config/match/agent_engine.yaml`, loaded via `AgentEngineParams` in `defs/match.py` and the loader.
   - Behaviour must not change: a golden-seed test pins today's results before the move and must still pass afterwards.
4. **Test teams and determinism.**
   - `backend/tests/support/teams.py` builds synthetic team sheets.
   - `tests/unit/test_engine_determinism.py` checks the same-seed hash and that the headless `run()` result doesn't depend on step batching.
5. **Save and live safety.**
   - A live-match registry on `app.state`, keyed by slot, seed and fixture, and cleared in `CareerSession.load` and `new_career`.
   - A guard in `routes.play_now`, a slot check in `_finish`, and an autosave after a live match.
   - `journal_mode=DELETE` on snapshots.
   - Integration tests for each.
6. **Clock.**
   - `backend/src/footsim/match/engine/clock.py`: `Period`, `MatchClock` and `StoppageLedger`, wired into `MatchEngine` in place of `stoppage`, `_clock` and `_end_period`.
   - Half-time state and `start_second_half()`; `MatchEvent.second`.
   - Migration v3 with `persistence/migrations.py`, starting with the `match_event.second` column.
7. **Live session.**
   - `backend/src/footsim/match/live/session.py`: `LiveSession` with a clock-driven pump, speeds, decimated frames, commands with ticks, the command log and Instant.
   - Rewrite `api/live.py` onto it (protocol v2) and add `data/config/match/presentation.yaml`.
   - Frontend: `useLiveMatch`, `PlaybackClock`, `ScoreBar` (MM:SS), `PlaybackControls` and the half-time panel.
8. **Run the harness again** and record the new baseline; nothing here should have changed the statistics. Then start **F1**: `restarts.py` and the set-piece layouts.

## Verification

- **Every phase:**
  - `just test`: unit and integration tests, including determinism and migration;
  - `just lint`, which is ruff plus strict mypy;
  - `just calibrate-engine` with 200 matches, compared against the targets, with the report committed under `docs/calibration/`;
  - `just e2e` against a throwaway server on :8765 with a temporary saves folder, never against `just demo`, which plays from the real saves.
- **Phase acceptance:** `just validate-engine` (1,000 matches, the A/B suites, cross-engine), and the thresholds in section S must all pass.
- **Manual checklist,** answering the user's 12 questions each time:
  - watch a whole match at 1× and time it;
  - switch to the all-aggressive setup and check the A/B table;
  - change formation at half-time and watch the shape;
  - count attackers at five corners;
  - watch a goal kick and a throw-in set up;
  - pick a substitute using the OVR and rating columns;
  - browse another club's squad;
  - simulate to 1 January;
  - save and reload after each of these steps.

---

### Sources (research used in this plan)

- **Real match averages:** [football-data.co.uk](https://www.football-data.co.uk/) results files for E0, E1, E2 and E3 (2023/24, 2024/25, 2025/26), computed directly.
- **Opta Analyst:**
  - [Ball in play by season](https://theanalyst.com/articles/premier-league-ball-in-play-are-we-seeing-less-football-2025-26)
  - [Set-piece and throw-in delays](https://theanalyst.com/articles/premier-league-delays-set-piece-throw-in-stats)
  - [Time-wasting guide](https://theanalyst.com/articles/guide-to-premier-league-time-wasting)
  - [Passing, long balls and set-piece trends](https://theanalyst.com/articles/premier-league-teams-still-more-direct-2025-26)
  - [Fast breaks and transitions](https://theanalyst.com/articles/premier-league-counter-attacks-verticality-transitions-guardiola-iraola)
- **Premier League:**
  - [How new added time rules transformed the PL](https://www.premierleague.com/en/news/3860720)
  - [Tactical trends 2024/25](https://www.premierleague.com/en/news/4171114) (short vs long goal kicks, corners, high turnovers, penalties)
  - [Goal-kick law trends](https://www.premierleague.com/en/news/1657509)
  - [PPDA explained](https://www.premierleague.com/en/news/4250153/passes-per-defensive-action-explained)
- **IFAB Laws:** [Law 7](https://www.theifab.com/laws/latest/the-duration-of-the-match/), [Law 13](https://www.theifab.com/laws/latest/free-kicks/), [Law 15](https://www.theifab.com/laws/latest/the-throw-in/), [Law 16](https://www.theifab.com/laws/latest/the-goal-kick/), [Law 17](https://www.theifab.com/laws/latest/the-corner-kick/), and the [2025/26 goalkeeper 8-second rule](https://www.theifab.com/news/the-ifab-tackles-goalkeeper-time-wasting/).
- **Tactics, Coaches' Voice:** [mid-block](https://learning.coachesvoice.com/cv/mid-block-football-tactics-explained/), [low block](https://learning.coachesvoice.com/cv/low-block-football-tactics-explained-simeone-dyche-mourinho/), [rest defence](https://learning.coachesvoice.com/cv/rest-defence-explained/), [positional play](https://learning.coachesvoice.com/cv/positional-play-football-tactics-explained-guardiola-cruyff-manchester-city/), [inverted full-backs](https://learning.coachesvoice.com/cv/inverted-full-backs-guardiola-cancelo-trent-alexander-arnold-lahm-football-tactics/), [false nine](https://learning.coachesvoice.com/cv/what-is-a-false-nine-explained-messi-kane-firmino-fabregas/).
- **Set-piece research:**
  - [Corner-kick systematic review (MDPI 2025)](https://www.mdpi.com/2076-3417/15/9/4984): 4–5 attackers in the box; mixed marking concedes 3.7% against 6.0% for zonal.
  - [Throw-in tactical study, La Liga 2021/22 (PMC)](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10650988/)
- **Distance run:** [Man City running stats 2025/26](https://www.mancity.com/news/mens/premier-league-running-stats-2025-26-foden-bernardo-nico-63898472)

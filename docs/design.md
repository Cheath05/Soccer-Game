# Football Manager Simulator — Technical Design Document & Development Plan

## Context

The repo (`Soccer-Game/`) is empty (README only; `main`, one commit). Installed: Python 3.14.7. **Not installed:** Node, .NET, PostgreSQL. The user wants a local, non-commercial, long-horizon football management simulation: a living world of clubs and players, an agent-based match engine they can watch in 2D and control live, and the full management layer (transfers, contracts, youth, finances, board, AI managers, multi-country competitions). They asked for research and architecture before any code. This document is that plan. Nothing gets implemented until it's approved.

**Key research findings that shape the plan (verified Sept 2026):**
- **worldfootballR is archived (read-only since 18 Sep 2025) and no longer maintained.** FotMob support was dropped earlier because of ToS changes.
- **FBref lost all Opta advanced stats on 20 Jan 2026** (Stats Perform pulled the licence). Basic stats and results remain. So worldfootballR's FBref advanced functions return nothing for current seasons.
- **transfermarkt-datasets (dcaribou) is CC0** and has 12 tables (players, clubs, games, appearances, lineups, events, valuations, transfers…). Its pipeline **stalled in mid-July 2026. The data ends 6 Jul 2026**, which is a clean pre-season snapshot for a 2026-27 start. Summer-window moves after that date are missing.
- **FC 27 ratings:** a Kaggle dataset (`mikedpad/ea-sports-fc27-player-ratings`) holds all 19,789 players from EA's official ratings API: the 6 face stats, 34 detailed attributes and GK stats, snapshot 2026-09-12. EA owns this data. EA restricts API access to approved partners, and fan sites forbid redistribution. **Decision:** the game never scrapes EA. The user downloads files they are entitled to use, and we import them locally through a column-mapping profile. Those files are never committed or redistributed.
- **UEFA 2024–2028 cycle:** UCL, UEL and UECL use a 36-team league phase (8/8/6 matches). Places 1–8 go to the Round of 16, 9–24 to knockout play-offs, and 25–36 are out with no drop-down. "European Performance Spots" give an extra UCL place to the two associations with the best coefficient in the previous season.
- **Premier League replaced PSR with Squad Cost Ratio (85% of revenue) + SSR from 2026-27**. "Anchoring" (a hard cap) was rejected. UEFA's squad-cost rule is 70%.
- **Championship play-offs expand to six teams (3rd–8th) from 2026-27.** League Two stays at 4th–7th.

These facts are exactly why **every rule must be data**. Rules have changed several times in the last three seasons.

---

## Decisions made during implementation

These supersede the matching parts of the sections below.

- **2026-09-27. The FC 27 ratings file is the primary roster source; Transfermarkt only enriches.**
  - transfermarkt-datasets covers only first divisions (31 domestic leagues). It has no Championship, League One/Two, Segunda, 2. Bundesliga, Serie B or Ligue 2.
  - The FC 27 export (snapshot 2026-09-12, post-summer window) has full squads for every league we plan to simulate: 17,849 men's players in 670 clubs.
  - Transfermarkt adds height, birthplace, contract expiry and market value for matched players. That's 75% overall: 96% of the Premier League, 74% of the Championship, and 26–46% of League One/Two.
- **Our overall formula reproduces EA's overall** after a per-position-group linear scaling. R² ranges from 0.96 to 0.99 and the average error is 0.6–1.0 points, with scale factors between 0.95 and 1.02. The weights (§7) are ours; only the scale is borrowed (`footsim calibrate-overall`).
- **Entity resolution** blocks on birth date and prefers full-name matches. It allows a surname-only match only when the first names are compatible, which keeps twins apart (Timber, Murphy, Sessegnon, Bueno). A second pass tolerates birth dates up to 7 days apart when the full name is near-exact.
- **League One and League Two are imported as `simulated` leagues**, since their squads exist. League Two relegation is disabled until a National League exists.
- **Potential calibration.** Growth above 86 is compressed. The built world has 19 players with potential of 90+ and one with 93+ (Lamine Yamal).
- **Task runner:** `just` (see `justfile`).

## 1. Executive Summary

We build a **local web application** that runs on your Mac.
- **Python simulation core + FastAPI** service.
- **SQLite** database, **one file per save slot**.
- **React + TypeScript** UI with a **Canvas 2D match viewer** fed over WebSocket.

The heart of the project is a **multi-fidelity simulation**:
1. **Tier 0, the Agent Match Engine:** continuous-coordinate, 10 Hz, 22 agents. It runs the user's matches, which you can watch and control live.
2. **Tier 1, the Possession-Chain Engine:** a fast statistical engine (~2–5 ms per match). It runs every other match in playable leagues and produces full player stats. It is **calibrated as a surrogate of Tier 0**, so both tiers agree statistically.
3. **Tier 2, results-only:** for "background" leagues. Players there exist, age and move, but only results are simulated.

Everything that describes football (formations, roles, instructions, leagues, cups, qualification, calendars, finance tables, AI personalities, injury types, name pools) is **versioned YAML/JSON data validated by Pydantic schemas**. The engines are generic interpreters of that data. Per-competition quirks (for example the Serie B play-off points-gap rule) use named **rule hooks** referenced from the data.

We build **vertically**. The first playable milestone is "sim a Premier League season from a dashboard". The MVP is PL + Championship with promotion, relegation and play-offs, the agent engine with a live 2D viewer and tactical control, transfers, contracts, development, youth, AI clubs/managers, and saves. Cups, Europe and other countries come after, and they plug into an engine that was designed for them from day one.

## 2. Recommended Technology Stack

| Layer | Choice |
|---|---|
| Language (sim + server) | **Python 3.13** (managed by `uv`; move to 3.14 once numba/scipy wheels are confirmed) |
| Numerics | NumPy (vectorised movement and batch world updates), SciPy (`linear_sum_assignment` for role assignment), **Numba** for hot loops if needed |
| Performance escape hatch | **Rust via PyO3/maturin** for the Tier 0 inner loop, used **only if** the Phase 4 performance gate fails (see §35) |
| API | FastAPI + Pydantic v2 (REST + WebSocket), Uvicorn bound to `127.0.0.1` |
| Persistence | **SQLite 3** (WAL mode) via SQLAlchemy 2.0 Core/ORM; Alembic migrations |
| Config/mod data | YAML (authoring) + JSON Schema generated from Pydantic models |
| Data pipeline | pandas/polars + DuckDB (reads the transfermarkt-datasets DuckDB file directly), `kloppy`, `socceraction`, `statsbombpy` for calibration |
| Frontend | React 19 + TypeScript + Vite; TanStack Query/Router/Table; Mantine UI; Zustand; types generated from OpenAPI |
| Match viewer | HTML Canvas 2D (22 players + ball is trivial load); PixiJS only if effects demand it |
| Testing | pytest, Hypothesis (property tests), golden-seed regression tests, Vitest + Playwright for UI |
| Tooling | ruff, mypy (strict in `core`/`match`), pre-commit, `just` task runner |
| Install needed | `brew install node uv just` (SQLite ships with Python) |

## 3. Why That Stack

**Your preference (React/TS + FastAPI + Postgres + Python) is ~80% right.** I recommend two changes: **SQLite instead of PostgreSQL**, and a **planned performance gate** for the match engine.

**Why SQLite over PostgreSQL:**
- It's single-user and local, with no concurrency needs.
- **A save slot is just a file**, so save, copy, backup and restore are file operations. SQLite's online Backup API plus an atomic `os.replace` gives you corruption-resistant saves almost for free.
- Postgres would need schema-per-save or `pg_dump` gymnastics, plus a server to install and run (none is installed).
- SQLite comfortably handles ~60k players, ~3k matches per season and millions of stat rows, given proper indexes and batched writes.

**Python vs C# for the simulation:**

| Criterion | Python | C# (.NET) |
|---|---|---|
| Raw sim speed | Slow (≈30–80× slower loops) and needs NumPy/Numba discipline | Fast |
| Data science / calibration (StatsBomb, socceraction, kloppy, DuckDB, pandas) | **Best in class, same language as the engine** | Weak, so you'd run a second Python codebase anyway |
| Dev speed and iteration on sim logic | **Very high** | High |
| Debuggability / notebooks for inspecting behaviour | **Excellent** (Jupyter over live engine objects) | Good |
| Long-term maintainability | Good with typing + mypy | Excellent |

Verdict: **Python wins for this project** for three reasons.
1. The tiered engine means only one detailed match (yours) runs at a time.
2. Calibrating against real event data is central, and that tooling is all Python.
3. The hot loop is small and isolated, so it can be ported to Rust later without touching anything else.

If you were already fluent in C# and had no interest in the data side, ASP.NET Core + the same React UI would be an equally valid choice.

**Why not Unity/Unreal:** a manager game is ~85% dense UI (tables, filters, negotiations, inbox). Game-engine UI toolkits are painful for that. The match viewer is 2D. Unreal is heavy overkill. Unity only becomes interesting for a future 3D viewer, and **our architecture allows exactly that**: a Unity 3D client could consume the same frame/event stream later.

**Desktop app:** not needed. It runs in the browser at `localhost`. It can be wrapped with Tauri later for a double-click launcher (post-MVP).

Option comparison (5 = best):

| | Unreal | Unity | Web (Py) | Desktop native | Hybrid (Py sim + web UI + optional 3D client) |
|---|---|---|---|---|---|
| Simulation complexity | 3 | 3 | 4 | 4 | **4** |
| UI development | 1 | 2 | **5** | 3 | **5** |
| Match visualisation | 5 | 5 | 3 | 3 | **4** (2D now, 3D later) |
| DB access / saves | 2 | 3 | **5** | 4 | **5** |
| Dev speed / debugging | 2 | 3 | **5** | 3 | **5** |
| Modding / local hosting | 2 | 3 | **5** | 4 | **5** |

The recommendation is **Option E realised as Option C**: a self-hosted web app whose engine/output contract allows other clients later.

## 4. Overall Architecture

```
            ┌──────────────────────── data/config (YAML: formations, roles, rules, calendars, AI profiles…) ────────────────────────┐
            ▼                                                                                                                     │
  Raw datasets ──► Importers/Normalisers ──► base-world.sqlite (read-only template) ──clone──► saves/slot_N/career.sqlite       │
                                                                                                    ▲                              │
                                                                                                    │ repositories (UoW per day)   │
 ┌──────────────────────────────── SIMULATION CORE (pure Python, no I/O, no web) ──────────────────────────────────────────────┐ │
 │ GameClock + EventQueue ─► Daily Processor Pipeline:                                                                          │ │
 │   fixtures → match sim (Tier0/1/2) → condition/injury → training/dev → transfers/contracts → finance → board/AI → news       │◄┘
 │ Match Engine T0 (agent) ─► MatchOutput{frames, events(SPADL-like), stats, ratings, decision traces}                          │
 │ Match Engine T1 (possession chain) ─► MatchOutput{events-lite, stats, ratings}                                               │
 └──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
                     ▲ commands (DTOs)                       │ read models / event stream
 ┌───────────── FastAPI (REST: career, squad, tactics, transfers… | WS: live match frames/events/controls | debug API) ─────────┐
                     ▲                                       ▼
 ┌───────────── React UI (management screens) ─── Match Viewer (Canvas renderer, no logic; interpolates engine frames) ────────┘
```

Rules:
1. `core`/`match`/`world` never import FastAPI or SQLAlchemy. They operate on domain objects and repository interfaces, so they are unit-testable and scriptable from a CLI/notebook.
2. **A match is fully determined by (initial state, seed, ordered list of timestamped commands).** Instant, text, 2D and a future 3D view are all views of that same `MatchOutput`.
3. The viewer never computes football. It interpolates positions between 10 Hz frames and renders events.
4. All randomness comes from named, seeded RNG streams (`numpy.random.Generator(PCG64)`) per subsystem, stored in the save. The same save + the same inputs give the same world.
5. The long-running world advance runs in a worker process. The API reports progress over a WebSocket. The UI never blocks.

## 5. Database Architecture

Two database roles:
- **`base-world.sqlite`**: the built, validated world you start careers from. It's produced by the import pipeline and never mutated by play.
- **`career.sqlite`**: per save slot. It's a clone of the base world plus all career state. It is the **single source of truth** during play. Heavy batch jobs (weekly development of 60k players) load columns into NumPy arrays, compute, and write back with `executemany` inside one transaction.

Conventions:
- Integer surrogate PKs.
- Dates as ISO `TEXT` (game dates), and money as **int64 minor units in a base currency (EUR cents)**. Fixed exchange rates per save handle display in £/$/€. $10B = 1e12 cents fits in int64.
- The `external_id` table maps each entity to source IDs (Transfermarkt, EA, StatsBomb…).
- Wide attribute tables (columns, not EAV) for speed.
- JSON columns only for genuinely variable payloads (tactic instructions, clause conditions, decision reasons).

### Schema (grouped; PK first, → = FK)

**World reference**
- `confederation(id, code, name)`
- `nation(id, code, name, confederation_id→, eu_member, talent_index, youth_quality, name_pool_key, tax_rate_top)`
- `city(id, nation_id→, name, lat, lon)`
- `stadium(id, name, city_id→, capacity, pitch_len, pitch_wid, owner_club_id→)`
- `competition(id, key, name, type[league|cup|super_cup|continental|playoff], nation_id→ null, tier, sim_level[playable|simulated|dormant], rules_ref)`: the rules file key
- `formation(id, key, data_json, version)` / `role(id, key, data_json, version)`: cached copies of data files, for referential integrity

**People**
- `person(id, first_name, last_name, known_as, dob, nation_id→, nation2_id→, birth_city_id→, retired_on)`: shared by players, managers and staff, so a retired player can become a coach
- `player(person_id PK→, height_cm, weight_kg, pref_foot, weak_foot 1-5, skill_moves 1-5, pa_hidden, pa_profile_json, reputation_home, reputation_world, squad_level[senior|u21|u18], value_eur_cached, homegrown_status_json)`
- `player_attr(player_id PK→, <≈50 attribute columns SMALLINT>, updated_on)`: current values
- `player_attr_history(player_id→, date, <same columns>)`: monthly snapshot for the user's club and major leagues, yearly for the rest
- `player_position(player_id→, position_code, familiarity 0-20)`: PK(player_id, position_code)
- `player_role(player_id→, role_key, familiarity 0-20)`: learned familiarity grows by playing the role
- `player_personality(player_id PK→, professionalism, ambition, loyalty, determination, temperament, pressure, adaptability, leadership, controversy, sportsmanship, team_orientation, versatility, consistency, big_matches, injury_proneness)`: hidden, 1-20
- `player_trait(player_id→, trait_key)`: e.g. `cuts_inside`, `tries_killer_balls`, `long_shots`
- `player_state(player_id PK→, condition 0-100, fatigue_acute, fatigue_chronic, sharpness, form, morale, confidence, happiness_json, last_match_date, minutes_last_28d)`
- `injury(id, player_id→, type_key, body_part, context[match|training], match_id→ null, started, expected_return, returned, severity, recurrence_of→ null)`
- `manager(person_id PK→, is_user, reputation, attrs_json, philosophy_json, preferred_formations_json, ai_profile_key, learning_json)`
- `staff(person_id PK→, primary_role, attrs_json)`

**Clubs**
- `club(id, name, short_name, nation_id→, city_id→, stadium_id→, founded, colors_json, reputation, ai_profile_key, parent_club_id→ null)`: the parent link covers B-teams and reserve-team promotion constraints
- `club_league_membership(club_id→, competition_id→, season_id→)`: history of which league a club was in
- `club_facility(club_id PK→, training, youth_facilities, youth_recruitment, youth_coaching, medical, analytics, scouting_network_json)`
- `club_finance(club_id PK→, balance, debt, transfer_budget, wage_budget, owner_wealth, owner_generosity, sponsor_json)`
- `finance_tx(id, club_id→, date, category, amount, ref_type, ref_id)`: an append-only ledger. Monthly/seasonal summaries are derived views.
- `club_rivalry(club_a→, club_b→, intensity)`
- `board(club_id PK→, patience, ambition, youth_focus, financial_prudence, confidence, confidence_history_json)`
- `board_objective(id, club_id→, season_id→, type, target_json, weight, status)`

**Contracts & movement**
- `contract(id, person_id→, club_id→, kind[player|staff|youth|loan_temp], start, end, wage_weekly, signing_bonus, loyalty_bonus, squad_status, release_clause, is_active)`
- `contract_clause(id, contract_id→, type[appearance_fee|goal_bonus|promotion_wage_rise|relegation_wage_drop|optional_extension|min_fee_release_foreign…], params_json)`
- `transfer(id, player_id→, from_club_id→, to_club_id→, date, type[permanent|loan|free|end_of_loan|youth_promotion|retirement], fee, agent_fee, window_key)`
- `transfer_payment(id, transfer_id→, due_date, amount, paid)`: installments
- `transfer_clause(id, transfer_id→, type[add_on|sell_on_pct|buy_back|option_to_buy|obligation_to_buy|matching_right], params_json, triggered_on)`
- `loan(transfer_id PK→, end_date, loan_fee, wage_share_pct, recall_from_date, option_fee, obligation_condition_json)`
- `negotiation(id, kind[transfer|contract|loan], player_id→, buyer_id→, seller_id→, state, deadline, history_json)`: live negotiation state machines
- `promise(id, player_id→, club_id→, type, made_on, due_on, status)`

**Competition runtime**
- `season(id, label '2026-27', start, end)`
- `competition_season(id, competition_id→, season_id→, rules_snapshot_json)`: rules frozen per season, so later data edits don't rewrite history
- `stage(id, comp_season_id→, key, type[round_robin|swiss|knockout|group_round_robin|playoff_bracket], order, config_json)`
- `stage_group(id, stage_id→, name)`; `stage_entry(stage_id→, group_id→, club_id→, seed, pot)`
- `match(id, stage_id→, group_id→ null, round, leg, home_id→, away_id→, kickoff, venue_id→, status, hg, ag, et_hg, et_ag, pens_h, pens_a, sim_tier, seed, attendance, referee_id→, weather)`
- `match_lineup(match_id→, club_id→, player_id→, slot, role_key, is_start, on_min, off_min, rating, captain)`
- `match_event(match_id→, seq, t_ms, period, type, club_id, player_id, x, y, end_x, end_y, z_end, outcome, body_part, xg, xt_delta, extra_json)`: kept for Tier 0 (and optionally Tier 1) matches
- `match_frames(match_id PK→, codec, blob)`: zstd-compressed 10 Hz positions, ~1–3 MB, stored only for the user's matches with retention settings
- `player_match_stats(match_id→, player_id→, minutes, goals, assists, shots, sot, xg, xa, passes, passes_cmp, prog_passes, carries, prog_carries, dribbles, tackles, interceptions, blocks, clearances, aerials_won, fouls, yellow, red, saves, gk_xg_faced, distance_m, sprints)`
- `standing_row(stage_id→, group_id→, club_id→, p, w, d, l, gf, ga, pts, deductions, pos)`: a cache updated after every match. It can always be recomputed from `match`.
- `player_season_stats(player_id→, season_id→, competition_id→, club_id→, …aggregates…)`: career totals come from a view
- `coefficient(entity_type[association|club], entity_id, season_id→, points)`
- `honour(id, comp_season_id→, club_id→, manager_id→, placing)`
- `manager_spell(id, manager_id→, club_id→, start, end, reason, p, w, d, l, gf, ga)`

**Scouting, youth, knowledge**
- `scouting_knowledge(observer_club_id→, player_id→, knowledge 0-100, ca_lo, ca_hi, pa_lo, pa_hi, pa_verbal, bias_seed, last_obs)`: PK(observer, player)
- `scout_assignment(id, club_id→, scout_id→, target_type[region|competition|player|next_opponent], target_ref, start, end)`
- `youth_intake(id, club_id→, date, quality_roll, notes_json)`

**Tactics, inbox, debug, meta**
- `tactic(id, owner_type, owner_id, name, formation_key, team_instr_json, slots_json, set_pieces_json, is_active)`
- `inbox_item(id, date, type, payload_json, is_read, blocks_advance)`
- `decision_log(id, date, actor_type, actor_id, decision, subject_type, subject_id, reasons_json)`: explains AI transfers, sackings, tactic changes, development, unhappiness
- `external_id(entity_type, entity_id, source, source_id)`: unique on (source, source_id)
- `game_meta(key PK, value_json)`: current_date, world_seed, rng_states, schema_version, content_versions, difficulty, sandbox, user ids

Relationships in words:
- A **club** has many **contracts** (people over time) and memberships in **competition_seasons** via stage entries.
- A **competition** has many **competition_seasons**, each with ordered **stages**. A stage contains **matches**.
- A **match** has **lineups**, **events** and **player_match_stats**.
- A **transfer** links player + two clubs, plus **payments/clauses/loan**.
- **Knowledge** is per (observer club, player).
- History tables are append-only, so a player's full career (clubs, fees, loans, stats, honours) is a query.

Indexes:
- `match(kickoff)`, `match(stage_id, round)`
- `contract(club_id, is_active)`
- `player_match_stats(player_id)`
- `transfer(player_id, date)`
- `finance_tx(club_id, date)`
- `scouting_knowledge(observer_club_id)`

## 6. Player Model

A player has:
- **identity** (person)
- **physical profile**: height, weight, foot, weak foot, skill moves
- **~50 visible-ish attributes (1–99)**, grouped below
- **hidden attributes / personality (1–20)**
- **traits** (behavioural tendencies)
- **positions + role familiarity**
- **dynamic state**: condition, fatigue, sharpness, form, morale, confidence, happiness
- **potential**: a hidden scalar plus an attribute-growth profile
- **reputation** (home and world)

**Attributes (1–99):**
- **Physical:** acceleration, sprint_speed, agility, balance, strength, stamina, jumping, natural_fitness *(hidden-ish, drives recovery and decline)*
- **Technical:** first_touch (ball control), dribbling, short_passing, long_passing, crossing, finishing, shot_power, long_shots, volleys, curve, free_kicks, penalties, heading_accuracy
- **Mental:** vision, composure, reactions, off_ball (attacking positioning), anticipation, decisions, concentration, aggression, work_rate, teamwork, bravery, flair
- **Defensive:** marking (defensive awareness), def_positioning, interceptions, standing_tackle, sliding_tackle
  - Heading is shared with technical: aerial ability = heading_accuracy + jumping + height + bravery.
- **Goalkeeping:** gk_diving, gk_handling, gk_kicking, gk_throwing, gk_positioning, gk_reflexes, gk_one_on_ones, gk_command_of_area (cross claiming), gk_rushing_out

**Key principle: the match engine reads attributes directly, never the overall.** The overall is a UI/AI summary.

**Face stats (display only; our own formulas):**

| Face stat | Formula |
|---|---|
| PAC | .40 acc + .60 sprint |
| SHO | .40 fin + .18 power + .17 long + .12 off_ball + .07 volleys + .06 pens |
| PAS | .30 short + .22 vision + .18 long + .15 cross + .10 curve + .05 FK |
| DRI | .35 dribbling + .28 first_touch + .15 agility + .10 balance + .07 reactions + .05 composure |
| DEF | .25 marking + .22 def_pos + .20 stand + .18 intercept + .10 slide + .05 heading |
| PHY | .35 strength + .30 stamina + .20 aggression + .15 jumping |

## 7. Rating System

**Role overall** = Σ wᵢ·attrᵢ over a role's weight vector (weights sum to 1), plus:
- a small **physical-profile modifier** (e.g. height bonus for Target Man and CB aerial roles, ±2 max)
- a **weak-foot modifier** for wide roles and playmakers (±1)

**Position overall** = the best role overall within that position.

**Effective rating** (what AI selection and the UI's "suitability" use) = role overall × familiarity factor × condition factor.
- Familiarity factor: natural 1.00, accomplished .97, competent .93, awkward .85, unconvincing .75.

Base position weight tables (designed for this project; roles then shift the weights):

| Attr | ST | W | AM | CM | DM | FB | CB | GK |
|---|---|---|---|---|---|---|---|---|
| finishing | .20 | .08 | .07 | | | | | |
| off_ball | .14 | .07 | .08 | | | | | |
| composure | .09 | .03 | .07 | .06 | .06 | | .05 | .03 |
| reactions | .09 | .06 | .07 | .08 | .08 | .07 | .07 | .04 |
| sprint_speed | .07 | .09 | | | | .09 | .04 | |
| acceleration | .07 | .10 | | | | .07 | | |
| first_touch | .09 | .12 | .13 | .10 | | .06 | | |
| dribbling | .07 | .15 | .11 | .06 | | | | |
| shot_power | .07 | | | | | | | |
| heading_acc | .05 | | | | | | .10 | |
| strength | .03 | | | .02 | .06 | | .09 | |
| decisions | .03 | | .08 | .08 | .08 | | | |
| crossing | | .07 | | | | .09 | | |
| short_passing | | .08 | .14 | .16 | .12 | .09 | .03 | |
| vision | | .06 | .14 | .10 | | | | |
| agility | | .06 | .05 | | | | | |
| long_shots | | .03 | .06 | .03 | | | | |
| long_passing | | | | .08 | .07 | | | |
| stamina | | | | .07 | .05 | .08 | | |
| interceptions | | | | .06 | .13 | .09 | .10 | |
| standing_tackle | | | | .05 | .11 | .10 | .12 | |
| work_rate | | | | .05 | | .05 | | |
| def_positioning | | | | | .12 | .09 | .14 | |
| marking | | | | | .06 | .08 | .12 | |
| concentration | | | | | .06 | | .05 | |
| sliding_tackle | | | | | | .04 | | |
| jumping | | | | | | | .06 | |
| aggression | | | | | | | .03 | |
| gk_reflexes / diving / handling / positioning | | | | | | | | .21/.20/.15/.17 |
| gk_1v1 / command / kicking | | | | | | | | .08/.07/.05 |

(Each column sums to 1.00.)

Worked example, your winger (PAC 91, SHO 79, PAS 87, DRI 89, DEF 42, PHY 76) with plausible underlying attributes: the **W role scores ≈ 86–87**, the **CB role ≈ 52–56**. Same player, radically different suitability, which is exactly the behaviour you asked for.

**Role weight modifiers (data files)**, for example:
- **Ball-Playing Defender:** +short/long passing, +composure, +vision; −aggression
- **Sweeper Keeper:** +gk_rushing_out, +gk_kicking, +short_passing, +acceleration
- **False Nine:** +vision, +short_passing, +first_touch, +decisions; −heading, −strength
- **Pressing Forward:** +work_rate, +stamina, +aggression, +acceleration

After renormalisation these give the role overall.

**Calibration:**
- With EA-sourced attributes, the scale is already football-game-like.
- With generated attributes, a per-position linear scaling is fitted so that league-level distributions match targets. For example, an average PL starter is ~77–80 and a Championship starter ~68–71. These targets live in a data file.

**Hidden "current ability" (CA):** we do *not* use an FM-style CA budget. Development operates per attribute, bounded by the potential profile (see §16). Role overall is always computed, never stored as truth. It is cached for sorting only.

## 8. Player Roles

Roles are data files. Each role file contains:
- `position_family`, and the `duties` it allows (defend/support/attack)
- **attribute weight modifiers** (for suitability)
- **movement behaviour parameters** per phase: anchor offsets, freedom radius, run types and their probabilities (in-behind, overlap, underlap, drop-deep, drift-wide, invert, stay-back)
- **on-ball tendencies**: pass risk, shoot threshold shift, dribble propensity, cross propensity, preferred pass targets
- **defensive behaviour**: press trigger distance, track runner, hold line, step out

Initial roster (37):

| Position | Roles |
|---|---|
| GK | Goalkeeper, Sweeper Keeper |
| CB | Central Defender, Ball-Playing Defender, Stopper, Cover, Wide CB (back-3), Libero *(later)* |
| FB | Full-Back, Wing-Back, Inverted Full-Back, Complete/Attacking Wing-Back |
| DM | Defensive Midfielder, Anchor, Deep-Lying Playmaker, Half-Back, Regista *(later)* |
| CM | Central Midfielder, Box-to-Box, Mezzala, Roaming Playmaker, Carrilero |
| AM | Attacking Midfielder, Advanced Playmaker, Shadow Striker |
| W / WM | Winger, Inverted Winger, Inside Forward, Wide Midfielder, Wide Playmaker |
| ST | Poacher, Target Forward, Advanced Forward, Pressing Forward, False Nine, Complete Forward, Deep-Lying Forward |

Player role data:
- `player_position.familiarity` (0–20) comes from import/history.
- `player_role.familiarity` (0–20) grows with minutes in the role.
- **Tactical intelligence** = derived from decisions + anticipation + teamwork. It speeds up learning roles and new formations and reduces positional errors.
- **Adaptability** (hidden) governs moving to a new country and learning roles.

## 9. Formation System

A formation is **data describing spatial structure per phase**, not a bonus table.

```yaml
key: "4-3-3"
slots:
  - id: LCB   position: CB   default_role: central_defender
    base: {x: 0.20, y: 0.36}                       # normalised, own goal x=0 → opp goal x=1
    phase_offsets:                                 # added to base, before ball-relative shift
      build_up:        {x: -0.04, y: -0.08}
      progression:     {x:  0.06, y: -0.04}
      final_third:     {x:  0.14, y: -0.02}
      def_high_press:  {x:  0.10, y:  0.00}
      def_mid_block:   {x:  0.00, y:  0.02}
      def_low_block:   {x: -0.06, y:  0.03}
  ...
relationships:            # used for spacing/cover rules
  - {type: pivot_pair, slots: [LCM, RCM]}
  - {type: flank_unit, slots: [LB, LCM, LW]}
```

Anchor computation per tick for each player:

`anchor = base + phase_offset(phase) + role_offset(role, duty, phase) + instruction_offsets(width, line height, depth) + block_shift(ball_x, ball_y, compactness)`

`block_shift` moves the whole team toward the ball's side and depth. Compactness (vertical and horizontal) scales the distances between the defensive line, midfield and forwards. The defensive line height also includes an **offside-line rule**: the back line shares one x (with step-up/drop logic).

So a 4-3-3 and a 4-4-2 produce **different occupation of zones**:
- 4-3-3: 3 central midfielders cover the half-spaces; wingers pin the full-backs.
- 4-4-2: two banks of four; the second striker blocks the pivot.

**Roles transform the in-possession shape.** An inverted FB's build-up offset moves it into midfield (4-3-3 → 3-2-5). A False Nine's offset drops it to x≈0.62. Wing-backs push to the last line. All formation shapes are "live". Mid-match changes swap slot definitions, and players physically transition via steering, so a change at 65' is visible and matters.

Initial formations:
- 4-3-3 (DM and flat variants), 4-2-3-1, 4-4-2, 4-4-1-1, 4-1-4-1
- 3-4-3, 3-5-2, 5-3-2, 5-4-1
- 4-3-1-2, 4-2-2-2, 3-4-2-1

## 10. Tactical System

**Team instructions** (discrete levels, each mapped to engine parameters in `instructions.yaml`):

| Area | Instructions |
|---|---|
| Mentality (7 levels) | shifts risk tolerance, shot threshold, number committed forward, rest-defence count |
| In possession | width, tempo, passing directness, play out from back vs. go long, attacking focus (L/C/R), overlap/underlap preference, crossing style, dribble frequency, patience (work into box), shoot on sight |
| Transition | counter-press vs. regroup, counter vs. hold shape, GK distribution (quick/slow, short/long) |
| Out of possession | defensive line height, line of engagement (press height), pressing intensity (trigger distance & recovery), marking (zonal/man/mixed), tackling style, offside trap, force opponent (inside/outside), time-wasting |
| Set pieces | corner/FK routines (zonal/man, near/far post, short), takers, penalty order, number left back |

**Player instructions:**
- shoot more/less
- dribble more/less
- stay wider / sit narrower
- get forward / hold position
- roam
- cross early / from byline
- close down more/less
- tight marking
- **specific marking target** (man-mark player X; the engine's assignment override)
- take more risks

All of this is serialised in `tactic.team_instr_json` + `slots_json`. **Live changes** are commands sent to the engine: `ChangeFormation`, `ChangeRole`, `SetInstruction`, `Substitute`, `SwapPositions`, `SetMarking`, `SetPieceTakers`. The engine applies them at the next tick (see §29 for the buffering rule).

## 11. Player Movement Model

**Space:**
- The pitch is continuous, in metres. Length and width come from the stadium, default 105×68.
- Coordinates are normalised per team so the "attack direction" is +x.
- The ball has 3D state (x, y, z, v): passes, crosses and headers are physical; rolling friction and simple drag apply.

**Tick:** 10 Hz (0.1 s). Decisions are **not** made every tick:
- **Ball carrier** decides at decision points: on receiving, at the end of a carry segment (0.4–1.0 s), and when pressure crosses a threshold.
- **Off-ball players** re-plan targets at 2–5 Hz. The frequency scales with `reactions`, `anticipation` and `concentration`, and drops with fatigue.
- Steering/kinematics run every tick, **vectorised in NumPy across all 22 players**.

**Off-ball target selection:**
1. Start from the formation **anchor** (§9).
2. Run role behaviour: a probabilistic run selector. For example, an Inside Forward in the final third picks a run in behind with p∝ space_behind × off_ball × role_propensity × instruction.
3. **Space-seeking local search:** evaluate ~8–16 candidate points within the role's freedom radius. Score each for:
   - openness (a simplified pitch control: time-to-arrive for us vs. them)
   - passing-lane availability from the ball carrier
   - offside legality
   - distance from anchor (a tactical-discipline penalty scaled by teamwork and decisions)
   - team spacing (a repulsion from teammates)
4. **Defensive assignment layer:**
   - zonal cover of anchor zones
   - pressing: nearest 1–3 players by line of engagement and press intensity, with cover shadows
   - marking assignments (zonal, man, or specific)
   - rest-defence count kept behind the ball (mentality-dependent)
   - defensive line step-up/drop, and the offside trap
5. **Kinematics:**
   - max speed from sprint_speed (≈7.0–9.6 m/s mapped)
   - acceleration from acceleration (≈3.0–6.5 m/s²)
   - turn rate from agility/balance
   - all multiplied by a condition/fatigue factor
   - stamina drain per metre by speed band (walk/jog/run/sprint)

**Phases** are determined each tick by a small classifier:
1. Organised defence
2. Build-up
3. Progression
4. Chance creation / final third
5. Defensive transition
6. Attacking transition
7. Set piece

Signals: possession, ball zone, **time since turnover** (transition window ~6–8 s, or until the shape is re-established), and opponent compactness. Phase drives formation offsets and role behaviours.

**Controlled randomness:**
- Every choice is sampled from a softmax over utilities. The temperature falls with `decisions`/`composure` and rises with fatigue and pressure.
- Players have persistent tendencies (traits) and a per-match "day form" draw scaled by `consistency`.

## 12. Match Engine

**Action vocabulary (SPADL-aligned, so our output is directly comparable to real event data via `socceraction`):** pass, cross, through ball, carry, take-on/dribble, shot, header, tackle, interception, clearance, block, press/duel, foul, offside, save/claim/punch, recovery, throw-in, corner, free kick, goal kick, penalty, sub, card.

**Resolution is physical plus contextual, not a flat percentage roll.**
- **Pass:**
  1. Choose a target (feet or a space point) and a pass type.
  2. **Execution error** = angle/velocity noise σ = f(passing skill for that type, weak-foot use, pressure on the passer, fatigue, body orientation, distance, curve).
  3. The ball travels physically.
  4. Each opponent's **time-to-intercept** vs. ball arrival time plus a reaction draw (anticipation/interceptions) decides interception.
  5. The receiver's `first_touch` + pressure decides control quality (clean / heavy touch / lost).
  - So pass success *emerges* from lanes, distances and attributes.
- **Shot:**
  1. Take a baseline **xG** from our fitted xG model (distance, angle, body part, assist type, pressure, defenders in cone, GK position).
  2. Shooter skill modifies **placement accuracy and power**: finishing, composure, shot_power, technique for volleys/curve, weak foot.
  3. The resulting on-target placement and speed face a **GK save model** (reflexes, diving, positioning, handling for spills/rebounds, one-on-ones when close).
  4. Blocks are resolved geometrically against defenders in the shot cone.
- **Dribble/tackle duel:** attacker (dribbling, agility, balance, acceleration, flair) vs. defender (standing/sliding tackle, marking, strength, aggression, positioning), plus approach angle and relative speed. Outcomes: beat / tackled / foul (aggression, sliding, referee strictness) / loose ball.
- **Aerial duel:** heading_accuracy + jumping + height + strength + bravery + positioning to the drop point.
- **Referee:** strictness and advantage attributes. Offside is geometric at the moment of the pass. Card logic uses foul severity plus game context.
- **Set pieces:** a routine library (data) positions players. Delivery is a physical cross, and the aerial duel resolves it. Penalties are a taker-vs-GK mini-game (placement choice, composure, GK anticipation).
- **Match state affecting behaviour:** score, minute and cards feed the AI manager (§14). The engine also shifts risk automatically, e.g. time-wasting when leading late if the instruction allows.

**Outputs:**
- `MatchOutput` = frames (10 Hz positions) + events (SPADL-like) + stats (derived *from events*) + player ratings + **decision traces**.
- Player ratings = baseline 6.0 plus a scaled sum of **possession-value added (xT/VAEP-style)** per action, plus goals/assists, errors and defensive contributions, clamped to 3.0–10.0.

**Calibration from real data (§31):**
- An xG model and pass-completion curves by distance/pressure (StatsBomb open data, Wyscout public dataset)
- An **xT grid** for possession value
- Action-choice frequencies by zone and phase
- Team-level targets: goals/match, shots, passes, completion %, possession splits, set-piece share, cards, home advantage — recomputed from football-data.co.uk and the open event data

**Debug:** every decision stores its top-k candidate actions with utility components, e.g.:

`{player, t, chosen: through_ball→#9, utility: 0.41, parts: {p_success .58, value_gain .22, risk_pen -.05, role_bias +.04, instr_bias +.03, noise +.02}, inputs: {vision 87, passing 84, pressure 0.18, lane_open .72}}`

The viewer overlay can render these.

**Tier 1 Possession-Chain Engine (fast):**
1. Compute **team unit strengths** from the lineup: attributes × role suitability × condition, organised by zone and phase — build-up, progression, chance creation, finishing, aerial, pressing, block solidity, transition.
2. Compute **tactical matchup modifiers**, e.g. high line vs. pace in behind, width vs. narrow block, press vs. press-resistance.
3. Simulate ~180–220 possessions as zone-to-zone Markov transitions with terminal states (shot with sampled xG / turnover / foul / set piece / out).
4. Attribute actions to players by role-weighted involvement.
5. Output events-lite, stats and ratings in ~2–5 ms.

**Tier alignment:** Tier 1's transition parameters are **fitted by regression on thousands of Tier 0 matches** (surrogate modelling). A cross-tier test requires matching distributions of goals, xG, shots and win%, given the same teams, within tolerance.

**Tier 2:** a Dixon-Coles-style Poisson model on team ratings + home advantage. Results only, with lightweight scorer allocation.

## 13. AI Decision System

One framework is shared across the match engine, AI clubs and AI managers. It has four parts:

1. **Utility AI with softmax sampling.** Each decision enumerates candidates and scores them with explicit, logged components. It then samples with a temperature.
2. **Information model.** AI actors see the world through the same imperfect lenses as the user: scouting knowledge for player quality and opponent analysis for tactics. Difficulty improves information quality and reasoning, **not stats**.
3. **Personality and philosophy vectors** from data (`ai_profiles/*.yaml`) bias the weights.
4. **Explainability.** Every non-trivial decision writes `decision_log(reasons_json)`.

**Difficulty = behaviour parameters per domain** (presets Easy/Normal/Hard/Expert/Nightmare + Custom):

| Domain | Knobs |
|---|---|
| Match AI (players) | decision temperature multiplier, re-plan frequency, positional-discipline weight |
| Tactical AI (managers) | opponent analysis depth, in-match re-evaluation interval, counter-tactic library breadth |
| Transfer AI | shortlist breadth, valuation accuracy, needs analysis horizon, bidding strategy sophistication |
| Scouting AI | knowledge gain rate, estimate noise |
| Negotiation AI | reservation-price estimation error, concession strategy, bluff detection |
| Financial AI | budget discipline, wage-structure adherence |
| Youth AI | intake evaluation accuracy, development planning |

An optional, clearly labelled "assist" toggle exists for hidden bonuses. It is off by default.

## 14. AI Managers

**Manager data:**
- attributes (1–20): tactical knowledge, adaptability, man management, motivating, youth development, judging ability/potential, negotiating, discipline, match management
- philosophy vector: possession↔direct, press↔block, width, risk, youth preference, domestic preference, star preference, rotation tendency, sub timing
- preferred formations list
- tactical flexibility
- reputation, age, career spells, learning state

**Layers:**
1. **Strategic (season):**
   - Picks a *primary* and *secondary* tactic. Candidates come from preferred formations plus flexibility-limited alternatives.
   - Scores each: **squad fit** (Hungarian assignment of players to slots/roles, maximising suitability via `scipy.linear_sum_assignment`) + philosophy match + league context.
   - Feeds squad needs into the club's recruitment (§17).
2. **Match prep:**
   - Lineup selection weighs quality, condition, match importance, rotation tendency, promises and development minutes.
   - Opponent adjustment (depth scales with difficulty): e.g. vs. a pacey front three → lower line / deeper block.
3. **In-match controller:**
   - Every N sim-minutes (5–10, faster on higher difficulty) and on triggers (goal, red card, injury, 60/70/80'), it scores options: subs for fatigue/cards/performance, mentality shifts, formation switches, time-wasting, "throw on a striker".
   - The rule set is utility-scored, not scripted, so behaviour differs by personality.
4. **Learning:**
   - Keeps Bayesian running estimates of xG-difference per (formation, opponent style) and per player-in-role.
   - These posteriors bias future choices. It's cheap, explainable, and not ML.
5. **Career:**
   - **Job market:** boards shortlist candidates by reputation, philosophy fit, availability, age and cost.
   - Managers accept or decline based on club prestige, budget and ambition.
   - **Sacking model:** a hazard function of board confidence (results vs. expectation over rolling windows, relegation zone, cup humiliations, fan unrest, finances) × board patience.
   - Resignations happen when unhappy or poached.
   - Retirement is age-based.
   - Reputation moves with results relative to expectation.
   - The pool of unemployed managers is replenished from retired players (high leadership, experience).
   - Calibration target: roughly 4–10 managerial changes per PL season.

## 15. Transfer Market

**Valuation model:**

`value = f(role overall, age curve, potential estimate, contract years left, position scarcity, league/club reputation, form, international status, homegrown status)`

It is fitted against Transfermarkt valuations (CC0 dataset) as a regression. It is re-indexed yearly by league revenue growth, so there's controlled inflation.

**Deal structure:**
- fee
- installments (`transfer_payment`)
- add-ons (appearance/goal/trophy conditions)
- sell-on %
- buy-back
- option or obligation to buy for loans
- signing bonus
- agent fee
- wage and contract length
- release clause (mandatory in Spain, optional elsewhere)
- loyalty bonus

**Two-stage negotiation state machine:**
1. **Club↔club:**
   - The seller's reservation price = value × importance-to-squad × contract-length factor × financial-need factor × rival penalty × deadline-pressure factor × player-wants-out factor.
   - Offers and counters converge by concession rules.
   - Components are valued in expectation: add-ons × trigger probability, installments discounted.
   - Deals can collapse (walk-away thresholds, rival bids, deadline).
2. **Club↔player/agent:**
   - The demand is derived from ability, reputation, current wage, the buying club's wage structure, league, age, ambition, agent greed and **net-of-tax wages** by country.
   - Acceptance weighs wage, squad status/playing time, club prestige, European football, league, location/culture adaptability, and loyalty to the current club.

**Rules enforced from data:**
- transfer windows per association
- registration limits
- non-EU quotas
- work-permit points model (UK GBE-style)
- FIFA loan limits (e.g. international loans, the max-per-club-pair rule)
- the "5-year max contract" rule
- pre-contract rules for players in their final 6 months
- training compensation / solidarity mechanism (5% of fees to training clubs)

## 16. Player Development

Development runs **weekly for playable-league players and monthly for the rest**, vectorised.

`Δattr = rate(age, group) × gap(ceiling_attr − attr) × train(focus, intensity, facilities, coaches) × personality(professionalism, determination, ambition) × minutes(level-adjusted playing time vs. age norm) × injury_penalty + ε`

- **Age curves per attribute group (data):**
  - physical peaks ~24–27 and declines from ~29–30; pace first
  - technical peaks ~26–30
  - mental grows to ~30–32
  - GK curves shifted about +3 years
- **Potential:** a hidden `pa_hidden` (in role-overall units at the best position) plus `pa_profile` (per-group ceilings). Growth slows asymptotically near the ceiling.
  - Small random "late bloomer / early plateau" events move the ceiling ±2–6 at most, with low probability.
- **Competition level:** minutes in stronger leagues give more growth. Minutes-starved youngsters stagnate, so loans matter.
- **Retirement:** a hazard by age × declining ability × injury history × desire. Some retire into staff/manager roles.
- **Explainability:** the monthly dev report lists the factor contributions per player.

## 17. Youth Academy (and AI club recruitment strategy)

**Youth intake:** annual, with a per-country date from data. Count ~ Poisson(λ from youth facilities + recruitment).

**Per youth player:**
- **PA** is drawn from a distribution. Its location and scale are set by nation talent_index × youth_recruitment × facilities × scouting-region quality (from the club's network). The heavy upper tail is **globally rate-limited**: a target count of elite-potential players per year worldwide, calibrated so the world's elite population stays stable over decades.
- **CA at 15–16** is drawn as a fraction of PA.
- **Position** from a nation/club distribution. **Attributes** are shaped by position archetype templates + noise.
- **Physicals** (height/weight) from a nation distribution.
- **Personality** from a distribution, where the academy's youth coaching nudges professionalism.
- **Traits, preferred foot, weak foot, skill moves.**
- **Names** from per-nation name pools (data; user-extendable).

Other youth elements:
- **Youth teams:** U18/U21 squads get simplified Tier 2 youth-league matches to provide minutes and form.
- **Background leagues:** get "regens" generated on the same rules, so the global population stays stable.

**AI club recruitment strategy** comes from data profiles (`ai_profiles/recruitment/*.yaml`):
- `develop_and_sell`, `established_stars`, `domestic_focus`, `attack_investment`, `academy_first`, `data_driven_value`, `loan_network`, `survival_veterans`
- Each profile sets weights on age, price/value ratio, nationality, position and resale.

**Weekly during windows (daily near deadlines), the recruitment loop:**
1. **Needs analysis:** depth chart for the manager's formation → gaps (quality below target for league ambition, depth shortfalls, injuries that last beyond N weeks, expiring contracts, aging starters).
2. **Shortlist** from the club's *own scouting knowledge*.
3. Score each candidate on fit × value × affordability × probability of success.
4. Open negotiations up to a concurrency limit.
5. Handle **outgoing** deals: surplus players, unhappy players, financial needs.

A market-clearing order (by club reputation + randomness) prevents everyone chasing the same player simultaneously without competition. Rival bids *are* modelled.

## 18. Scouting

Each observer club has a `scouting_knowledge` row per player it knows. Knowledge grows with:
- scout assignments (scout judging ability/potential, **familiarity with the league/country**)
- time spent
- matches observed
- data availability (analytics dept, league data coverage level from data)
- player age (younger means noisier)

Estimates:
- **Current-ability band:** `true_ca + scout_bias ± w`, where `w = base × (1 − knowledge) × age_factor × (1 − judging/20)`
- **Potential band:** wider, and shown **verbally** below a knowledge threshold ("Could become an elite player"), then as a range ("84–90"), then narrow ("88").
  - Even at maximum knowledge, the potential uncertainty keeps ±1–2, because the truth itself can drift.

Other scouting rules:
- The same model applies to AI clubs (lazily computed aggregate knowledge per club, so it's cheap).
- **Opponent scouting** (next-opponent reports) feeds the AI's and your tactical prep.

## 19. Training

- **Weekly schedule** of sessions (data-defined types): balanced / attacking / defending / physical / technical / tactical / set pieces / recovery / match prep.
  - Each type has attribute-group weights, a fatigue cost and an injury-risk factor.
- **Intensity** slider (per team and per player).
- **Individual focus:** an attribute group, or a new role/position.
- **Effects:**
  - development multipliers (§16)
  - tactical familiarity with the formation/instructions (a team-level variable that improves cohesion and reduces positional errors in the engine)
  - sharpness and condition
- **No infinite growth:** training only scales the rate toward ceilings, and focus shifts growth between attributes (it doesn't add growth). Soak tests assert attribute distributions stay stable.

## 20. Injuries

**Hazard per minute of exposure:**

`h = base(context: match≈24/1000h, training≈3–4/1000h) × f(age) × f(injury_proneness) × f(fatigue/condition) × f(ACWR acute:chronic workload) × f(recent injury history, recurrence window) × f(match intensity: tackles/sprints) × sandbox_multiplier (default 0.75 "enjoyable")`

- Base rates are anchored to published elite-club injury epidemiology (e.g. the UEFA Elite Club Injury Study) and then tuned for enjoyment.
- **Injury types table (data):** minor knocks (days), muscle strains (grade 1–3), ligament sprains, fractures, ACL (6–9+ months). Each type has a duration lognormal, a recurrence risk window, and a "playing through" possibility.
- A long injury permanently reduces physical attributes a little, with a small probability.
- **Condition model:**
  - daily recovery rate from natural_fitness, age, medical staff/facility, rest days
  - in-match stamina drain from distance × intensity × work rate × press intensity
  - ACWR from rolling 7-day vs 28-day minutes-weighted load
  - playing every 3 days visibly raises fatigue and injury risk

## 21. Club Finances

**Monthly cycle** with a ledger (`finance_tx`).

**Revenue:**
- **Matchday:** attendance model (capacity, reputation, form, opponent, competition, price) × ticket price.
- **Broadcast:** per-league distribution tables in data. E.g. PL: equal share + merit per place + facility fees. EFL: distribution + solidarity + **parachute payments** for relegated PL clubs.
- **Commercial/sponsorship:** reputation- and trophy-driven, with contract renewals.
- **Merchandise:** star players and success.
- **Prize money:** leagues and cups.
- **UEFA distribution:** starting fee + performance + value pillar (data per season).
- **Player sales:** profit on disposal = fee − book value.

**Costs:**
- wages
- **amortisation** (fee spread over contract length, max 5 years)
- staff
- facilities/stadium upkeep
- debt interest
- agent fees
- youth academy

**Budgets:** the board sets the transfer and wage budgets from projected revenue, the financial rules, owner generosity and debt.

**Financial rules (data, per league/competition):**
- PL **Squad Cost Ratio 85%** (wages + amortisation + agent fees ÷ revenue), from 2026-27
- UEFA squad-cost 70%
- EFL P&S / SCMP salary-to-turnover caps
- La Liga squad cost limit (LCPD)
- DNCG (France) administrative sanctions
- Bundesliga licensing
- MLS salary budget/DP rules (post-MVP)

Breaches trigger sanctions from data: fines, transfer embargo, points deductions.

**Initial finances:**
- A curated YAML for PL/Championship clubs (approximate revenue, wage bill, debt), from public accounts (Companies House filings, Deloitte Football Money League, UEFA club finance reports).
- Everyone else is derived from league revenue model × reputation.

## 22. League System

A league is a `competition(type=league)` with a rules file.
- **format:** round-robin (N legs, mirrored or not); split-season (Apertura/Clausura); conference/table-split (e.g. MLS conferences, a Scottish-style split later)
- **points:** 3/1/0 by default, configurable
- **tiebreakers:** ordered list, e.g. PL: pts, GD, GF, H2H pts, H2H away goals, playoff; La Liga: pts, **H2H first**, GD…; Serie A: title/relegation **spareggio**
- **promotion/relegation slots and play-off definitions:** references to other competitions
- **registration/squad rules, window keys, financial rules**
- **reserve-team constraints** (B-teams can't be promoted into their parent's division)
- **sim_level**

**2026-27 rule research (encoded as data, each fact verified again at data-entry time):**

| League | Clubs/Rounds | Down/Up | Notes |
|---|---|---|---|
| Premier League | 20 / 38 | 3 relegated | 25-man squad, ≥8 homegrown (U21 exempt); GBE work permits; SCR 85% |
| Championship | 24 / 46 | 2 auto up + **play-offs 3rd–8th (new 2026-27)**; 3 down | P&S loss limits; parachute payments |
| League One | 24 / 46 | 2 auto + PO 3–6 up; 4 down | SCMP salary cap % turnover |
| League Two | 24 / 46 | 3 auto + PO 4–7 up; 2 down to National League | National League modelled as dormant/simulated |
| La Liga | 20 / 38 | 3 down | H2H tiebreak first; 3 non-EU slots; squad cost limit; mandatory release clauses |
| Segunda | 22 / 42 | 2 auto + PO 3–6 (1 place) up; 4 down | B-team promotion constraint |
| Bundesliga | 18 / 34 | 2 down + 16th vs 2.BL 3rd (two legs) | winter break; 50+1 (flavour only) |
| 2. Bundesliga | 18 / 34 | 2 up + PO; 2 down + 16th vs 3.Liga 3rd | |
| Serie A | 20 / 38 | 3 down | spareggio for title/relegation ties; non-EU signing quotas |
| Serie B | 20 / 38 | 2 up + PO 3–8 (skipped if points gap large); 3 down + playout 16v17 (gap rule) | rule hooks for gap conditions |
| Ligue 1 | 18 / 34 | 2 down + 16th vs L2 PO winner | DNCG |
| Ligue 2 | 18 / 34 | 2 up + PO 3–5; 2 down + 16th barrage | |
| MLS | 30, 2 conferences / 34 | **no pro/rel**; playoffs (Round One best-of-3) | salary budget, DPs, TAM/GAM, draft. Calendar change under discussion; verify |
| Liga MX | 18, **Apertura + Clausura** | relegation suspended (verify status) | two champions/season, play-in + Liguilla |

## 23. Competition System

Generic model: **Competition → CompetitionSeason (rules snapshot) → ordered Stages → Groups → Matches**.

**Stage types:**
- `round_robin`
- `group_round_robin`
- `swiss_league_phase` (the UEFA format: pots, N opponents, constraints)
- `knockout` (single/two legs, seeding, home rule "lower tier hosts", ET, penalties; away goals configurable, default off)
- `playoff_bracket`
- `split_season`

**Slot/allocation DSL** links outputs to inputs:

```yaml
qualification:
  - from: {competition: ENG1, rank: [1,4]}      to: {competition: UCL, stage: league_phase}
  - from: {competition: ENG1, rank: 5}          to: {competition: UEL, stage: league_phase}
  - from: {competition: FA_CUP, winner: true}   to: {competition: UEL, stage: league_phase}
    fallback: {competition: ENG1, next_unqualified_rank: true}
  - from: {competition: EFL_CUP, winner: true}  to: {competition: UECL, stage: playoff}
    fallback: {competition: ENG1, next_unqualified_rank: true}
  - from: {coefficient: association_prev_season, rank: [1,2]}  to: {competition: UCL, stage: league_phase, extra_from: ENG1/next_rank}   # European Performance Spots
```

- An **allocation resolver** handles cascades deterministically: cup winner already qualified → pass the place down.
- **Rule hooks** (named Python functions registered in a plugin registry) cover genuinely procedural quirks. The data only *references* them, e.g. `serie_b_playoff_gap`, `liga_mx_liguilla_seeding`.
- **Draws:** seeded constrained random draws with backtracking (country protection, pot constraints, same-association avoidance, max-2-per-country opponents in the Swiss phase).

**Cups (data):**
- FA Cup: PL/Championship enter R3 proper; no replays from R1 (from 2025-26); lower-league qualifiers are generated/simulated at Tier 2.
- EFL Cup: two-legged semis; UEFA clubs enter later.
- Copa del Rey: single-leg ties with the lower-tier club hosting; two-legged semis.
- DFB-Pokal: 64 teams; lower tier hosts; single leg.
- Coppa Italia: seeded; top clubs enter R16; two-legged semis.
- Coupe de France: amateur rounds simulated at Tier 2; L1 enters R64; lower tier hosts.
- Super cups: Community Shield, Supercopa (4 teams), Supercoppa (4 teams), Trophée des Champions, DFL-Supercup.

## 24. Scheduling

The scheduling engine has three layers:

1. **Season calendar template per association (data):**
   - season start/end
   - FIFA international windows (Sept, Oct, Nov, Mar, and June tournament years)
   - UEFA matchweek slots (Tue/Wed for UCL, Thu for UEL/UECL, and January league-phase dates)
   - cup round weekends/midweeks
   - winter breaks
   - transfer windows
   - youth intake date
   - awards
2. **Fixture generation:**
   - circle-method round-robin with home/away alternation balancing (max 2 consecutive home/away)
   - local derby separation (no same-day home fixtures for clubs sharing a stadium/city if configured)
   - mirrored or randomised second half per league config
   - rounds are assigned to calendar league dates
3. **Kick-off slotting and rescheduling:**
   - constraint pass: minimum rest ≥ 2 full days (≈60 h), with Thu-European → Sun-league
   - cup/Europe conflicts move league fixtures into free midweek slots (greedy with backtracking; OR-Tools CP-SAT if greedy proves insufficient)
   - an "unusual scheduling" flag permits exceptions intentionally

A **validator** asserts that no club has overlapping fixtures or less than the min rest (tests + a runtime assertion). Fatigue (§20) naturally reflects congestion.

## 25. Promotion/Relegation

At the **season rollover** processor:
1. Finalise stages → play-offs (already scheduled in May) → final tables.
2. The allocation resolver computes movements (auto, play-off winners, spareggio/playout outcomes, administrative sanctions like DNCG).
3. Update `club_league_membership` for the next season.
4. Apply finance changes:
   - new broadcast tier
   - **parachute payments** (PL relegation)
   - relegation wage-drop clauses
   - promotion bonuses
5. Reputation adjustments (club, and league reputation from coefficient/strength).
6. Board resets expectations; budgets are recomputed.
7. Player happiness/interest effects: ambitious players may request transfers after relegation; promotion increases attractiveness.
8. Create next-season competition_seasons, stages and fixtures.

## 26. European Competitions

- UCL, UEL and UECL are data files for **the 2024–2028 cycle format**:
  - qualifying rounds (Champions Path / League Path)
  - 36-team Swiss league phase (UCL/UEL 8 matches, UECL 6) with 4 pots by club coefficient
  - 1–8 → R16; 9–24 → two-legged knockout play-offs (9–16 seeded); 25–36 eliminated with no drop-down
  - two-legged R16/QF/SF, single final
  - UCL winner → next UCL; UEL winner → UCL
- **Coefficients:**
  - the association 5-season coefficient determines the access list: slots per association, entry stage, European Performance Spots
  - the club coefficient determines pots and seeding
  - seeded from real 2026-27 values (data), then computed from simulated results
- **Access list** is a data table keyed by association rank → places per competition/stage. When UEFA changes the cycle (2027+), you add a new format file with `valid_from_season`.
- **Non-simulated nations** (the ~40 other associations) are represented by Tier 2 "European entrant" clubs from dormant leagues. Their domestic champions are drawn from a strength-weighted model, so qualifying rounds are populated.
- **Prize money** from a data table (starting fee, per-win/draw, round bonuses, value pillar).

## 27. Career System

**Game clock + event queue:** `advance()` processes day by day, running an **ordered processor pipeline** per day:

`calendar events → matches (Tier by importance) → post-match (stats, ratings, condition, injuries, morale) → training/recovery → dev (weekly) → contracts (expiry/renewal) → transfers (window days) → AI clubs/managers → board (post-match, monthly) → finances (monthly) → news/inbox → season rollover (if due)`

It **stops** when an item has `blocks_advance`:
- the user's match
- a transfer offer received
- a negotiation response
- an injury to a key player (configurable)
- a board meeting
- a scout report
- the start of an international break
- a contract expiring soon
- a player request
- the window deadline

**New career wizard:**
- start date: 1 Jul 2026 for MVP; historical starts post-MVP
- club selection
- manager profile (name, nationality, reputation preset, philosophy, abilities)
- difficulty preset/custom
- sandbox settings (§21/§54)
- world seed
- which leagues are playable vs. simulated vs. dormant (affects performance)

**Board:**
- Pre-season **objectives are derived from a 200× Tier 1 Monte Carlo pre-sim** of the season: expected finish distribution → "finish top 4 / avoid relegation" etc.
- Weighted objectives (league, cups, Europe, youth minutes, finances, style).
- Confidence updates after each match and monthly, with actions: praise, warning, budget increase/decrease, ultimatum, sacking.

**Manager career:** reputation, abilities (improve slowly via experience/coaching courses), spells, trophies, finishes, transfers, player development records, job offers.

**Player relationships:**
- **happiness** = a sum of factors with decay and a visible breakdown: playing time vs. squad status, broken/kept promises, wage vs. teammates (wage envy), club ambition/European football, manager criticism/praise (interactions), team success, homesickness (adaptability), agent pressure
- **requests:** new contract, more playing time, loan, transfer, promise fulfilment
- dressing-room influence via leadership/hierarchy (post-MVP social groups)

## 28. Save System

- **Slots:** 3+ manual slots (configurable count), 1 rotating autosave per slot, pre-season auto-snapshot, and N backups.
- **Working model:**
  - Play happens on a **working DB** (`slot_N/working.sqlite`).
  - **Save** = SQLite **online Backup API** → `career.sqlite.tmp` → `fsync` → `PRAGMA integrity_check` → atomic `os.replace` to `career.sqlite`.
  - The previous version is rotated to `backups/career-YYYYMMDD-HHMM.sqlite` (keep last K).
  - Autosave follows the same flow, triggered by user settings (daily/weekly/monthly/before each match/pre-season).
- **What's saved:** everything is in the DB. `game_meta` holds the date, world seed, **RNG stream states**, schema version, content-data versions (hashes of the config files used), difficulty and sandbox settings. No save during a live match in MVP; saves happen only between days (like FM).
- **Corruption defences:**
  - WAL + synchronous=FULL for saves
  - checksum of the file stored in `slot.json` metadata
  - integrity check on load
  - automatic fallback to the newest valid backup
  - `PRAGMA trusted_schema=OFF` when opening any save (defends against malicious shared saves)
- **Migrations:** `schema_version` + Alembic migrations applied to a copy on load, with the original kept. Migration tests run against fixture saves from each prior version.
- **Content drift:** each save pins its rules snapshot (`competition_season.rules_snapshot_json`), so editing data files later doesn't corrupt running careers. New rules apply from the next season.

## 29. Match Viewer

**Viewing modes** (all consume the same `MatchOutput`):

| Mode | Behaviour |
|---|---|
| 1. Full match | live stream at 1×–16× speed |
| 2. Highlights | the engine tags events with an *excitement score* (xG, danger, cards, goals). The viewer plays windows around them (pre-roll 10–15 s) and fast-forwards between, rendering only the summary. |
| 3. Tactical 2D | top-down pitch with player discs (number, colour, stamina ring), ball with a height shadow, passing arrows, optional formation-shape lines |
| 4. Top-down simulation (debug) | 2D plus overlays: anchors, targets, pitch control heatmap, pass-option utilities, pressing assignments, offside line |
| 5. Text commentary | template-based from events (data phrase banks, variety rules) |
| 6. Instant result | runs Tier 0 headless (same engine, so the same result distribution) |

**Streaming and live control:**
- The engine runs in a worker process and **generates at most ~1 s ahead of playback**.
- Frames are streamed over WebSocket as compact binary (Float32 arrays, delta-coded).
- The client interpolates to 60 fps.
- On **pause**, the engine stops at the displayed tick.
- **Tactical commands** are stamped with the displayed tick. The engine discards any buffered-ahead frames past that tick, restores the snapshot at that tick (state + RNG), applies the command, and continues.
- This keeps "what you saw" and "what happened" consistent, and the command log keeps matches reproducible.

## 30. UI Architecture

- The React SPA uses feature folders: dashboard, squad, player, tactics, training, transfers, scouting, youth, fixtures, competitions, club, finances, staff, manager, inbox, settings, save/load, match, debug.
- **Data layer:** an OpenAPI-generated typed client and TanStack Query caches (invalidated on `advance`). The server provides paged/filterable **read models** (SQL views) for heavy tables (player search across 60k).
- **Dashboard:** next match, league position mini-table, form, upcoming fixtures, injuries, squad morale, transfer news, board confidence gauge, finances summary, inbox.
- **Global:** a date bar with an "Advance/Continue" button (showing the next stop reason), a news ticker, and command palette + keyboard shortcuts.
- **Match day screen:**
  - pitch canvas (centre)
  - score/clock/possession/xG bar (top)
  - event feed + commentary (right)
  - tactics panel (formation board with drag-drop, roles, instructions)
  - bench/subs with condition
  - live stats and player ratings (left)
  - pause/speed controls
- **Player profile:** attributes (grouped, with scouting bands if not your player), role suitability chart, positions map, history (stats, transfers, injuries), happiness breakdown, contract, **development reason log**.
- **Debug pages:** decision_log browser, engine trace viewer, world metrics dashboards (charts of goals/match, age curves, fee inflation over seasons).

## 31. Dataset Research

| Dataset | Contains | Coverage | Update | Quality | Licence/terms | Use for us |
|---|---|---|---|---|---|---|
| **worldfootballR** (+ `worldfootballR_data`) | R wrappers for FBref (match results, season/player stats, lineups, shots, advanced tables), Transfermarkt (values, transfers, squads, injuries), Understat (xG shots, 6 leagues); pre-scraped data releases | FBref: many leagues back to ~2017 for advanced stats; TM: global; Understat: top 5 + RFPL since 2014/15 | **Archived Sep 2025, unmaintained**; FotMob removed; **FBref advanced stats gone Jan 2026** | Good historically | MIT package; underlying site data belongs to the sites (attribution required; scraping subject to their ToS) | **Do not integrate directly** (R, unmaintained, scrapes). Use its `worldfootballR_data` release snapshots as **historical** calibration data (pre-2026 advanced stats) if still downloadable. |
| **transfermarkt-datasets** (dcaribou) | 12 tables: competitions, clubs, players (DOB, position, foot, height, citizenship, contract expiry, agent), games, appearances, lineups, events, valuations, transfers, national teams | 790+ clubs, 65 competitions, ~2012–Jul 2026 | **Paused since mid-Jul 2026 (data to 6 Jul 2026)** | Good; valuations subjective | **CC0** (dataset); original TM content scraped | **Enrichment** (first divisions only): heights, birthplaces, contract expiries, market values, transfer history. Matched to the FC 27 roster by birth date + name. |
| **FC 27 ratings (Kaggle `mikedpad/…fc27…`)** | 19,789 players, 6 face stats + 34 attributes + GK, from EA's ratings API | All FC 27 leagues (incl. EFL, Segunda, 2.BL, Serie B, L2, MLS, Liga MX) | Snapshot 2026-09-12 | High and consistent | **EA-owned**; not redistributable; personal use only; don't commit | **User-provided ratings file** → mapping profile → our attributes. Missing attributes derived (§32). |
| SoFIFA-derived Kaggle sets (FIFA 15–FC 24/25) | Historical ratings incl. potential, wages, work rates | 2015–2025 | Static | Good | Scraped from SoFIFA (EA data); personal use | **Historical start dates**; potential-model calibration (how ratings evolved vs. age). |
| **StatsBomb Open Data** | Event data (freeze frames/360 for some), lineups | Selected competitions/seasons (World Cups, Euros, some league seasons, women's) | Occasional additions | Excellent | Free with **attribution + logo** | **Calibration core**: xG model, pass success vs. distance/pressure, action choice by zone, xT grid, set-piece routines. |
| **Wyscout public dataset** (Pappalardo et al., *Scientific Data* 2019) | ~1,900 matches, ~3.2M events, player/team/competition data | 2017-18 top-5 leagues + WC 2018 + Euro 2016 | Static | Good | CC BY 4.0 | Calibration of league-level action distributions (full seasons! better than StatsBomb for league base rates). |
| **SkillCorner Open Data** | 10 A-League 2024-25 matches of broadcast tracking (10 fps), dynamic events, phases of play, physical aggregates | Small | Occasional | Very good | MIT, credit SkillCorner | **Movement calibration**: speeds, distances, team shape/compactness per phase, off-ball run frequencies. |
| **Gradient Sports (PFF FC) WC 2022** | Broadcast tracking + events for all 64 matches | WC 2022 | Static | Very good | Free on request; terms on download | Tracking-based calibration of shape/line height/pressing distances. |
| **Metrica Sports sample data** | 3 anonymised matches, tracking (25 fps) + events | Tiny | Static | Good | Open (sample) | Engine/viewer prototyping, pitch-control implementation tests. |
| **Understat** | Shot-level xG, match xG | Top 5 + RFPL, 2014/15– | Live (scrape) | Good | Scraping (ToS) | Secondary xG validation for team-level outputs. |
| **football-data.co.uk** | Results + stats (shots, SoT, corners, fouls, cards) + odds | 20+ leagues, 1993– | Weekly | Very good | Free for use; attribution | **Result-distribution targets** (home/draw/away, goals, scorelines, 0-0 rate, cards). |
| **ClubElo** (API/CSV) | Elo ratings for European clubs, daily history | 1940s– | Daily | Good | Free API | Initial club strength priors; sanity-check sim results vs. Elo expectations. |
| **openfootball** | Fixtures/results/clubs in text | Many leagues | Community | OK | Public domain | Fixture/club reference, league membership cross-check. |
| **American Soccer Analysis** (`itscalledsoccer`) | MLS/NWSL/USL xG, g+ | MLS 2013– | Live | Good | Free API; attribution | MLS phase calibration. |
| **soccerdata** (Python) | Scrapers for ClubElo, ESPN, FBref, football-data, Sofascore, SoFIFA, Understat, WhoScored | per source | Active | per source | Apache-2.0 code; each site's ToS applies | Our **Python equivalent to worldfootballR** for any optional refresh scripts (low volume, cached, polite). |
| Deloitte Money League / UEFA club finance reports / Companies House accounts | Revenues, wages, debt | Top clubs, annual | Annual | Good | Public reports; manual curation | Seed club finances. |
| FBref (post-Jan-2026) | Basic stats, results, squads | Many leagues | Live | Good for basics | ToS restricts scraping | Optional basic-stats cross-check only. |

What we are *not* relying on: FotMob, Sofascore or WhoScored scraping, and EA's API. Their ToS restrict it and they're fragile.

## 32. Data Import Pipeline

Stages (each a CLI command, idempotent, with cached outputs):
1. **Acquire** → `data/raw/<source>/<snapshot>/` (gitignored). Download scripts for open datasets; manual drop-in for user-provided files (FC27 CSV).
2. **Stage** → source-specific parsers load into DuckDB staging tables. Supported: CSV, JSON, Parquet, a DuckDB/SQLite dump, and an optional API adapter.
3. **Map** → **mapping profiles** (YAML) translate source columns to our canonical schema. Examples: `ea_fc_ratings_v1.yaml` maps `sprint_speed→sprint_speed`, `defensive_awareness→marking`, etc. `generic_players_csv.yaml` covers a user's own format.
4. **Entity resolution** → match players across sources by normalised name + DOB + nationality + club (fuzzy scoring via `rapidfuzz`). Results go to `external_id`, with `data/overrides/matches.yaml` for manual fixes and a report of unmatched/ambiguous cases.
5. **Derive/fill:**
   - Attributes EA lacks (anticipation, decisions, concentration, work_rate, teamwork, bravery, flair, gk_one_on_ones, gk_command, gk_rushing_out, natural_fitness) come from documented formulas over related attributes + position + noise, e.g. `decisions ≈ .45 reactions + .30 composure + .25 vision`.
   - Players without ratings get the **fallback rating generator**: position template scaled by market value, league strength, age and (if available) stats percentiles.
   - Hidden potential comes from age × overall × dataset potential if present × randomised spread (a **per-career potential variance setting**, so every save differs).
   - Personality comes from a distribution (optional overrides).
   - Wages come from a model (market value, league wage level, club wage structure), because free datasets don't carry reliable wages.
6. **Validate** → Pydantic + SQL constraints:
   - every club has ≥ N players per position group
   - contracts are valid
   - no duplicate persons
   - ratings are within range
   - a report lands in `data/reports/`
7. **Patch layer** → `data/patches/*.yaml`: user-editable transfers, rating tweaks and club changes applied last. This handles post-6-Jul-2026 summer moves, and is how you mod.
8. **Build** → writes `data/worlds/base-2026-27.sqlite` + a manifest (sources, snapshot dates, hashes).

## 33. Licensing/Usage Considerations

- **Personal, local, non-distributed use** is the operating assumption, and it's the main reason real names and data are reasonable here.
- **EA FC ratings:** EA's IP. Never scrape ea.com or its API. Import only files you have obtained yourself, keep them in gitignored folders, and never publish a repo or build containing them. The game must be fully playable with the **generated-ratings path** (Transfermarkt + fallback generator), which is also the fallback if you ever share the code.
- **Transfermarkt-derived CC0 dataset:** the dataset licence is CC0, but the content originates from Transfermarkt. Fine for local use; attribute it anyway.
- **StatsBomb:** attribution and logo required if you publish analysis. We use it only to fit parameters (the params ship, not the data). Keep attribution in `docs/ATTRIBUTION.md`.
- **Wyscout public dataset:** CC BY 4.0, so cite the paper.
- **SkillCorner:** MIT, credit them. **PFF/Gradient:** follow the download terms.
- **Club names, crests, league marks:** use names only; **no crests/logos** (generate simple colour badges).
- **Scraping (if ever):** low-volume, cached, respect robots/ToS, never in the game runtime.
- **Code dependencies:** permissive licences (MIT/BSD/Apache). Avoid GPL-only runtime deps if you might share.

## 34. Testing Strategy

1. **Unit** (pytest): ratings formulas, face stats, standings/tiebreakers (incl. H2H-first, spareggio), fixture generator invariants, schedule validator, allocation resolver cascades, draw constraints, contract expiry, finance ledger balances, amortisation, loan returns, retirement, injury recovery, scouting band convergence.
2. **Property-based** (Hypothesis):
   - any generated schedule has no overlaps or rest violations
   - any league results table sums consistently (Σpts, ΣGF = ΣGA)
   - any negotiation terminates
   - money is conserved across transfers (buyer pays = seller receives + agent)
3. **Scenario/integration:**
   - "reproduce 2025-26 qualification": feed real final tables and assert UEFA allocations match reality (a strong test of the competition DSL)
   - promotion/relegation incl. play-offs
   - a full season advance
   - save → load → continue gives identical results vs. no save (determinism)
4. **Golden-seed regression:** fixed seeds for N matches/seasons. Changes must be intentional; the snapshot diff is reviewed.
5. **Statistical validation harness** (`tools/validate.py`, runs nightly/manually):
   - **Tier 0:** 2,000 matches of mixed-strength pairs → goals/match (target ≈2.7–3.0), 0-0 rate (~7–9%), P(≥7 goals) (<1%), home/draw/away (~44/24/32 %), shots (~25/match), pass completion (~80–85%), possession spread, defender goal share (~10–15%), penalties/cards per match, xG/shot (~0.10–0.12). Targets are recomputed from football-data.co.uk and the open event data.
   - **Strength monotonicity:** a 90-rated team beats a 65-rated team ~85–95% of the time, never 100%.
   - **Tactics matter:** paired tests of the same teams with systematically bad tactics (e.g. high line vs. elite pace with slow CBs) show significant xG swings.
   - **Cross-tier:** Tier 1 vs. Tier 0 distributions within tolerance.
   - **Soak (30 seasons × 5 seeds):** age curves, OVR distribution stability, count of 85+ players, youth talent flow, fee and wage inflation bands, champions' diversity (e.g. no club wins >60% of titles across seeds; Gini of titles within a range), managerial turnover, club bankruptcies/financial breaches, squad sizes within rules.
   - Results are written as HTML reports with charts in `reports/`.
6. **Performance benchmarks** (pytest-benchmark) gate regressions (§35).
7. **UI:** Vitest for components; Playwright smoke tests (create career → advance → play match → save → load).

## 35. Performance Strategy

**Budgets (M-series Mac, single process unless noted):**

| Operation | Budget |
|---|---|
| Tier 0 headless match | **≤ 15 s** (gate, Phase 4); stretch ≤ 3 s |
| Tier 0 live | real time at 1×–16× |
| Tier 1 match | ≤ 5 ms |
| Tier 2 match | ≤ 0.2 ms |
| Advance one normal day | ≤ 250 ms |
| Transfer-deadline day | ≤ 2 s |
| Full season rollover | ≤ 60 s for 5 countries |

**Techniques:**
- **Level of detail (LOD):**
  - Tier 0 only for the user's matches (optionally "featured" matches).
  - Playable leagues use Tier 1.
  - Simulated leagues use Tier 2.
  - Dormant leagues get only yearly aging/dev/transfers.
  - Player updates run weekly for playable leagues and monthly/yearly for others.
- **Vectorisation:** attributes as NumPy matrices (players × attrs) for development, aging, valuation and role-overall recomputation. Movement kinematics vectorised across 22 players per tick.
- **Decision throttling:** off-ball re-plans at 2–5 Hz, carrier decisions only at decision points, candidate pruning (top-k passing targets by lane openness).
- **Parallelism:** multiprocessing for batch Tier 1 matchdays and validation runs (the GIL doesn't matter across processes).
- **DB:** batched writes per day in one transaction, WAL, targeted indexes, precomputed read models. Frames are stored only for the user's matches, compressed.
- **Escape hatch:** if Tier 0 misses the 15 s gate after profiling + Numba, port `match/engine/kernel` (kinematics, intercept times, pitch control) to Rust via PyO3. The decision layer stays in Python.
- **AI throttling:** AI clubs run transfer logic in window weeks only (daily near the deadline), in reputation-ordered batches. Background-league clubs use a simplified market model.

## 36. Security Considerations

- The server binds **127.0.0.1 only**. CORS is restricted to the local UI origin. No auth is needed; a random session token in the UI prevents drive-by requests from other local web pages (CSRF-like attacks on localhost).
- **Mods/data files:** YAML via `safe_load`, JSON Schema validation, no `eval`/pickle, no code execution from data. Rule hooks are referenced only by name from a fixed registry.
- **Imports:** path restrictions (no traversal outside `data/`), size limits, zip-bomb protection, CSV injection irrelevant (no export to spreadsheets by default; if exported, escape leading `=+-@`).
- **Saves from others:** open with `trusted_schema=OFF`, verify the expected schema and triggers (reject unknown triggers/views), integrity check.
- **Dependencies:** `uv.lock` / `package-lock.json`, `pip-audit`/`npm audit` in CI.
- **Scrapers:** never run in-game, rate-limited, identifiable user agent.

## 37. Development Roadmap

Sizes assume one developer working part-time with Claude Code.
- S ≈ 1–2 weeks
- M ≈ 3–5 weeks
- L ≈ 6–10 weeks

| Phase | Deliverable (playable/testable at the end of each) | Size |
|---|---|---|
| **0. Foundations & spikes** | Repo scaffold, tooling, config schemas, **data spike** (TM DuckDB + FC27 CSV → sample PL world) and **engine spike** (22 dots moving by formation anchors with ball shift, shown in the Canvas viewer) | S |
| **1. Core world & import** | Schema v1, importer (TM + ratings profile + fallback generator), base-world build for PL + Championship, entity resolution report | M |
| **2. Player model & ratings** | Attributes, face stats, role/position overalls, suitability, squad and player UI | S |
| **3. League loop (first playable)** | Competition engine v1 (round robin, tables, tiebreakers), fixture generator + calendar, Tier 2 → Tier 1 engine, game clock & advance, dashboard, **save slots v1**. *You can manage nothing yet but can sim seasons.* | M |
| **4. Agent match engine v1 + viewer** | Kinematics, anchors/phases/roles, pass/carry/dribble/shot/tackle/aerial, referee basics, set pieces v1, events/stats/ratings, WebSocket 2D viewer, pause/subs/formation/instruction changes, text commentary, debug overlay. **Performance gate.** | L |
| **5. Calibration & tier alignment** | Fit xG/pass/xT from StatsBomb/Wyscout, validation harness, Tier 1 surrogate fitted to Tier 0, targets met | M |
| **6. Condition, injuries, form, morale** | Fatigue/ACWR, injuries, sharpness, form, basic happiness | S |
| **7. Contracts, transfers, finances v1, board v1** | Valuation, negotiations, windows/registration rules, AI recruitment loop, ledger, budgets, SCR check, board objectives from Monte Carlo pre-sim | L |
| **8. Development, aging, retirement, youth, scouting** | Weekly dev, age curves, retirement, youth intake, scouting knowledge/bands, loans | M |
| **9. AI managers** | Tactic selection, lineups/rotation, in-match controller, learning, sacking/hiring market | M |
| **→ MVP** (end of Phase 9) | — | — |
| 10. England complete | League One/Two, play-offs for all, FA Cup, EFL Cup, Community Shield, National League as dormant feeder | M |
| 11. Europe | Coefficients, access list, qualifying, Swiss draw, UCL/UEL/UECL, prize money | L |
| 12. Big-5 countries | Spain, Germany, Italy, France leagues + cups with rule hooks; windows, non-EU rules | M |
| 13. Depth systems | Staff & attributes, facilities/stadium, training depth, promises/interactions, dressing room | M |
| 14. Americas | MLS (conferences, playoffs, salary budget/DP, draft), Liga MX (Apertura/Clausura, Liguilla) | M |
| 15+ | Media, international football, historical starts, 3D client, etc. (§39) | — |

## 38. MVP Definition (exact scope)

**In:**
- **World:** England Premier League + Championship (44 clubs, playable). Other England tiers + major foreign leagues as **dormant** player pools (players exist, can be scouted and bought, and they age). No cups. No Europe.
- **Data:** base world built from the user-provided FC 27 ratings file (all squads), enriched by transfermarkt-datasets (CC0). League One/Two are included as simulated leagues.
- **Players:** full attribute model, face stats, role overalls, 37 roles (≥25 fully behaviour-implemented), positions and familiarity, personality, traits, hidden potential.
- **Tactics:** 12 formations, team and player instructions, set-piece takers. The live match supports pause, subs, formation/role/instruction changes and specific marking.
- **Match:** Tier 0 agent engine for the user's matches, with 2D viewer, highlights, text commentary, instant result and debug overlay. Tier 1 for all other PL/Championship matches.
- **Season:** fixtures and calendar incl. international breaks (as dates without national teams), tables, **promotion/relegation incl. Championship play-offs (3rd–8th)** and PL→Championship parachute payments.
- **Squad state:** fatigue/condition, injuries, form, morale, happiness (core factors), player requests (contract/playing time/transfer).
- **Transfers:** valuation, club↔club and club↔player negotiations (fee, installments, sell-on, add-ons, wage, bonus, agent fee, length, release clause), loans (fee, wage share, option/obligation), free agents, windows, 25-man squad/homegrown rule, AI recruitment strategies.
- **Development:** weekly development, aging, retirement, youth intake, scouting with uncertainty bands.
- **Finances:** ledger, revenue/costs model, budgets, SCR check (warnings + simple sanctions).
- **Board & AI managers:** board objectives/confidence/sacking (user and AI). AI managers with tactics, lineups, in-match changes, career moves.
- **Career:** new career wizard with difficulty presets and sandbox budget/multipliers; advance-to-next-event; inbox.
- **Saves:** 3 slots, autosave, pre-season snapshot, backups, integrity checks.
- **Tools:** validation harness, decision log browser.

**Out of MVP:** cups, Europe, other playable countries, staff attributes (staff exist only as a single "coaching quality" and "medical quality" per club), media, international football, historical start dates, stadium expansion, detailed training scheduling (team focus + intensity only), dressing-room social groups.

## 39. Post-MVP Roadmap / Backlog

- **Competitions:** international football (national teams, call-ups, fatigue/injury from internationals, World Cup/Euros/Copa/AFCON with qualification), women's football (separate world DB), more leagues (Portugal, Netherlands, Scotland, Brazil, Argentina, Saudi Arabia…), B-teams / Premier League 2 / youth cups.
- **Media & people:** press conferences, player/agent interactions, transfer rumours/media narratives, social media, fan sentiment.
- **Club depth:** detailed staff (coaches, GK coach, fitness, analysts, medical, youth coaches, director of football / sporting director who executes transfer strategy), stadium development and naming rights, sponsorship negotiations, board politics/takeovers (new owners inject money), club culture, dynamic rivalries.
- **Analytics & viewer:** advanced analytics suite (pass networks, xT maps, pressing maps from engine data), 3D viewer (Unity/three.js consumer of the frame stream), richer commentary.
- **Modding & packaging:** mod manager UI + community database packs, **historical start dates** (2015–2025 via SoFIFA-era datasets + TM history), Tauri desktop wrapper.

## 40. Major Risks

| # | Risk | Mitigation |
|---|---|---|
| 1 | **Agent engine produces unrealistic football** (ball-chasing swarms, absurd scores, no chances) | Engine spike in Phase 0; strict formation-anchor discipline first, freedom later; calibrate against real distributions early (Phase 5); debug overlays; golden seeds; keep v1 action set small, then expand |
| 2 | **Python too slow for Tier 0** | LOD tiers; vectorisation; decision throttling; hard performance gate with a planned Rust/Numba kernel port; engine kernel isolated behind an interface from day one |
| 3 | **Tier 0 vs Tier 1 disagree** (your club's matches "play differently" from the rest of the world) | Tier 1 fitted as a surrogate of Tier 0; cross-tier statistical tests in CI |
| 4 | **Scope creep / never playable** | Vertical phases, each ends playable; MVP scope frozen; backlog for everything else |
| 5 | **Data gaps and churn** (FBref loss, TM dataset paused, EA ToS) | Multi-source; generator fallback; patch layer; `external_id` mapping; world is built offline so the game never depends on live sources |
| 6 | **World drift over decades** (talent inflation/deflation, fee hyperinflation, one-club dynasties, bankruptcies) | Global rate limiters (elite regen rate, value indexing), 30-season soak tests with dashboards, tunable data constants |
| 7 | **Rule complexity** (UEFA access cascades, Swiss draw, tiebreakers, Serie B gap rules, MLS roster rules) | Declarative DSL + named hooks + "reproduce real season" tests; MLS/Liga MX deliberately late |
| 8 | **Save corruption/migrations** | Backup API + atomic rename + integrity checks + backups + migration tests on fixture saves |
| 9 | **Non-determinism** (dict order, float, multiprocessing, time) | Named RNG streams, no wall-clock in sim, sorted iteration, determinism test (save/load vs. continuous run) |
| 10 | **UI volume** | Mantine + TanStack Table + generated client; build screens alongside each phase, not at the end |
| 11 | **AI market degeneracy** (hoarding, fire sales, no-one buys) | Constraints (squad size, wage structure), decision logs, soak metrics on transfer counts/fees |
| 12 | **Live-control sync bugs** | Engine ≤1 s ahead; snapshot + discard on command; command log replay tests |

## 41. Recommended First Implementation

Start with **Phase 0 as two parallel spikes** before committing to schema details:
1. **Data spike:** load the transfermarkt-datasets DuckDB and a user-supplied FC27 CSV. Match players for PL + Championship clubs. Measure the match rate and missing fields. This validates the whole import approach in days.
2. **Engine spike:** a standalone Python module simulating 22 players with formation anchors, ball-relative block shift and simple possession (random passes to open teammates), streamed to a minimal Canvas page. Measure the tick cost. This validates the hardest technical risk (movement plausibility + Python performance) before anything depends on it.

Then proceed with Phase 1–3 so that a full PL season can be simulated from the UI as early as possible.

## 42. Proposed Project Folder Structure

```
Soccer-Game/
├─ README.md  justfile  .gitignore  .pre-commit-config.yaml
├─ docs/                      # this design doc, ADRs (docs/adr/0001-sqlite-per-save.md …), ATTRIBUTION.md, data dictionary
├─ data/
│  ├─ config/                 # COMMITTED game-definition data (moddable)
│  │  ├─ formations/*.yaml    roles/*.yaml    instructions.yaml   set_pieces/*.yaml
│  │  ├─ competitions/{eng,esp,ger,ita,fra,uefa,usa,mex}/*.yaml   calendars/*.yaml
│  │  ├─ rules/{registration,finance,transfer_windows,work_permits}.yaml
│  │  ├─ nations.yaml  name_pools/*.yaml  injuries.yaml  personalities.yaml
│  │  ├─ ai_profiles/{managers,recruitment,boards}/*.yaml   difficulty_presets.yaml  sandbox_presets.yaml
│  │  ├─ finance/{broadcast_distribution,prize_money,club_finances_seed}.yaml
│  │  └─ calibration/*.json   # fitted params (xG, pass model, xT grid, tier1 surrogate) — generated, committed
│  ├─ import_profiles/*.yaml  # column mappings (ea_fc_ratings_v1, generic_players_csv …)
│  ├─ patches/*.yaml          # user edits applied at world build
│  ├─ raw/  staging/  worlds/  reports/     # GITIGNORED
├─ backend/
│  ├─ pyproject.toml  uv.lock
│  ├─ src/footsim/
│  │  ├─ core/            # ids, money, dates/calendar, rng streams, event bus, errors
│  │  ├─ defs/            # Pydantic schemas + loaders for data/config (and JSON Schema export)
│  │  ├─ domain/          # plain dataclasses: Player, Club, Contract, Tactic…
│  │  ├─ persistence/     # SQLAlchemy models, repositories, migrations/, saves.py (backup/atomic/integrity)
│  │  ├─ ratings/         # attributes, face stats, role/position overall, suitability
│  │  ├─ competitions/    # formats, stages, fixtures, scheduler, standings, tiebreakers, draws, allocation, hooks/
│  │  ├─ match/
│  │  │  ├─ engine/       # state, pitch, ball physics, kinematics (kernel/), phases, movement, decisions, actions, duels, referee, set_pieces
│  │  │  ├─ tier1/  tier2/
│  │  │  ├─ tactics/      # formation/role/instruction → engine params; live commands
│  │  │  └─ output/       # frames codec, SPADL events, stats, ratings, commentary, highlights
│  │  ├─ people/          # condition, injuries, development, aging, retirement, morale/happiness, personality
│  │  ├─ youth/  scouting/  transfers/  finance/  training/  staff/
│  │  ├─ ai/              # utility framework, managers/, clubs/ (recruitment), board/, difficulty
│  │  ├─ world/           # game clock, event queue, daily processor pipeline, season rollover, career creation
│  │  ├─ importers/       # sources/ (transfermarkt, ea_csv, generic), resolve.py, derive.py, validate.py, build_world.py
│  │  ├─ calibration/     # fit_xg.py, fit_pass.py, fit_xt.py, fit_tier1.py (use statsbomb/wyscout/skillcorner)
│  │  ├─ api/             # FastAPI app, routers/, schemas/, ws/match.py, debug.py
│  │  └─ debug/           # decision traces, trace store
│  ├─ tests/{unit,property,integration,simulation,benchmarks}/
│  └─ tools/              # cli.py: build-world, new-career, sim-seasons, validate, calibrate, bench
├─ frontend/
│  ├─ package.json  vite.config.ts  tsconfig.json
│  └─ src/{api(generated),app,routes,features/{dashboard,squad,player,tactics,training,transfers,scouting,youth,fixtures,competitions,club,finances,manager,inbox,saves,debug,match},match-viewer/{renderer,interpolation,overlays,stream},components,state}
├─ notebooks/                 # calibration & world-metrics exploration
└─ saves/                     # GITIGNORED: slot_1/ slot_2/ slot_3/ {working,career}.sqlite, backups/, slot.json
```

---

# Final Summary (A–Q)

**A. Technology stack:**
- Python 3.13 (uv), FastAPI, Pydantic v2, SQLAlchemy 2 + Alembic, **SQLite per save**, NumPy/SciPy/Numba (Rust/PyO3 kernel only if the performance gate fails)
- React + TypeScript + Vite + TanStack + Mantine, Canvas 2D viewer over WebSocket
- DuckDB/pandas/kloppy/socceraction for data and calibration
- pytest/Hypothesis/Playwright

**B. Architecture:** a local web app. Pure-Python simulation core (no I/O) → repositories → per-save SQLite. FastAPI exposes commands/read models/WebSocket match streams. The React UI and viewer are pure presentation. Multi-fidelity match engines (T0 agent / T1 possession-chain surrogate / T2 results-only) share one `MatchOutput` contract. Everything football-specific is data. Deterministic via seeded RNG streams + command logs.

**C. Database schema:** §5. Person-centric (player/manager/staff share `person`), wide attribute tables, contracts/transfers/clauses/loans/payments as normalised history, and Competition → CompetitionSeason (rules snapshot) → Stage → Group → Match. Stats are per match + per season, plus an append-only finance ledger, scouting knowledge per observer, decision_log, external_id, and game_meta.

**D. Player attribute model:** §6–7. ~50 attributes (1–99) in physical/technical/mental/defensive/GK groups; hidden personality (1–20); traits; physical profile. Face stats are derived. **Role overall = weighted attribute sum per role** (position = best role), and effective rating includes familiarity and condition. The engine uses raw attributes, never the overall.

**E. Match simulation approach:** §11–12. A continuous-coordinate 10 Hz agent engine with 3D ball physics. Formation-anchor + role + phase + space-seeking movement. Utility-based decisions with softmax sampling. Physically resolved passes/shots/duels with attribute-driven execution noise. SPADL-aligned events; stats derived from events; decision traces. Calibrated to StatsBomb/Wyscout/SkillCorner/football-data. The Tier 1 possession-chain surrogate is fitted to Tier 0.

**F. Formation/tactical model:** §9–10. Formations are data with per-phase slot positions and relationships. Roles are data with per-phase offsets, run types, on-ball tendencies and defensive behaviours. Instructions map to engine parameters. Live commands swap data at the next tick, so movement genuinely changes.

**G. AI-manager architecture:** §13–14. A utility-AI framework with philosophy vectors. Strategic (Hungarian squad-fit tactic choice), match-prep (lineups/rotation/opponent adjustment) and in-match controller layers, Bayesian "learning", and a career layer (job market, sacking hazard, reputation). Difficulty = information quality + reasoning depth + noise, not stat bonuses.

**H. Transfer-market architecture:** §15, §17. A regression valuation model with yearly indexing. A needs-analysis → shortlist (from the club's own scouting knowledge) → scored bids pipeline. A two-stage negotiation state machine (club↔club, club↔player/agent) with structured deal components. Data-driven recruitment profiles. Windows/registration/work-permit/loan rules from data. Decision logs.

**I. Youth-generation architecture:** §17. An annual per-country intake. PA is drawn from a distribution shaped by nation talent × club recruitment/facilities × scouting region, with a **global elite-rate limiter**. CA is a fraction of PA. Archetype attribute templates, nation name pools and personality distributions. The same generator repopulates background leagues. Soak tests keep the population stable.

**J. Save architecture:** §28. Per-slot SQLite working DB. Save/autosave via the Backup API → integrity check → atomic replace, plus rotating backups, checksums, schema migrations on copies, rules snapshots per season, and RNG states in `game_meta`. No mid-match saves in MVP.

**K. Exact MVP scope:** §38.

**L. Phased roadmap:** §37 (Phases 0–9 = MVP, then 10–15+).

**M. First 10 concrete implementation tasks:**
1. **Scaffold:** monorepo, `backend/` (uv, Python 3.13, FastAPI, SQLAlchemy, Alembic, pytest, ruff, mypy), `frontend/` (Vite React TS, Mantine, TanStack), `justfile`, `.gitignore` for `data/raw|staging|worlds`, `saves/`; install Node/uv; ADR-0001 (SQLite per save) and ADR-0002 (tiered engines).
2. **Data-definition schemas:** Pydantic models + loaders + JSON Schema export for formations, roles, instructions, competitions, calendars, rules. Author 4-3-3, 4-2-3-1 and 4-4-2, the 10 most common roles, and PL/Championship rules + 2026-27 calendar.
3. **Data spike → importer v1:** the transfermarkt-datasets DuckDB → staging; the `ea_fc_ratings_v1` mapping profile; entity resolution with a match report; the derive step for missing attributes; the fallback rating generator; `build-world` producing `base-2026-27.sqlite` for 44 clubs.
4. **Schema v1 + persistence:** tables for person/player/attrs/positions/personality/club/contract/competition/season/stage/match/standing/game_meta/external_id; repositories; the save manager (clone base world, Backup API save, integrity check, atomic replace, 3 slots).
5. **Ratings module:** attribute groups, face stats, role/position overall from role data, suitability/familiarity. Unit tests with archetypes (winger-vs-CB example) and the weight-sum invariant.
6. **Competition engine v1:** round-robin fixture generator, calendar assignment with international windows, schedule validator, standings with configurable tiebreakers. Property tests.
7. **Tier 2 → Tier 1 fast match engine v1:** team unit strengths, possession-chain sim, player stat attribution, seeded RNG streams. The `validate.py` harness measuring goals/results distributions vs. football-data.co.uk targets.
8. **Game clock & career loop:** event queue, daily processor pipeline (matches, standings, basic condition), new-career creation, advance-to-next-event, inbox items; the season rollover skeleton incl. promotion/relegation + Championship play-offs.
9. **API + UI v1:** career creation, dashboard, squad table, player profile, fixtures, league table, advance button with progress over WebSocket, save/load screen. *(First playable: sim a season as a PL club.)*
10. **Tier 0 engine spike → v0:** pitch/ball physics, vectorised kinematics, formation anchors with phase + ball-relative block shift, simple carrier decisions (pass/carry/shoot) with lanes, a frame stream over WebSocket → Canvas viewer with pause and live formation switch (4-3-3 ↔ 4-4-2). Tick-cost benchmark recorded against the performance gate.

**N. Biggest technical risks & avoidance:** §40. Above all:
- (1) engine plausibility → early spike + calibration + debug overlays
- (2) Python performance → LOD + vectorisation + gated Rust kernel
- (3) tier consistency → surrogate fitting + cross-tier tests
- (4) scope → frozen MVP, vertical slices
- (5) data churn/legal → offline world build, multi-source, generator fallback, patches

**O. Folder structure:** §42.

**P. External datasets/repos to research further:**
- `JaseZiv/worldfootballR` + `JaseZiv/worldfootballR_data` (archived; historical snapshots only)
- `dcaribou/transfermarkt-datasets` (CC0; primary skeleton)
- Kaggle `mikedpad/ea-sports-fc27-player-ratings` (user-provided; EA IP)
- SoFIFA-derived Kaggle FIFA 15–FC 25 sets (historical starts)
- `statsbomb/open-data` + `statsbombpy`
- Wyscout public dataset (Pappalardo et al. 2019, figshare)
- `SkillCorner/opendata`
- Gradient Sports/PFF FC WC2022 tracking
- `metrica-sports/sample-data`
- `ML-KULeuven/socceraction` (SPADL, VAEP, xT)
- `PySport/kloppy`
- `probberechts/soccerdata`
- `andrewRowlinson/mplsoccer` (pitch plotting in notebooks)
- `Friends-of-Tracking-Data-FoTD` (pitch control, EPV tutorials — Spearman's pitch-control model)
- Understat
- football-data.co.uk
- ClubElo API
- `openfootball/*`
- American Soccer Analysis (`itscalledsoccer`)
- Deloitte Football Money League, UEFA European Club Finance & Investment Landscape
- UEFA regulations (UCL/UEL/UECL 2024–27 regs; access list 2027–28)
- Premier League Handbook (SCR/SSR, squad rules), EFL regulations, FIFA RSTP (loans, windows, training compensation)

**Q. Things you haven't mentioned that I'd add:**
- **Taxes and net wages** by country (drives where players want to go).
- **Amortisation accounting** (makes SCR/FFP realistic and transfer strategy interesting).
- **Homegrown status tracking over time** (matters for 25-man squads).
- **Home advantage & crowd, referees with strictness, weather/pitch** (small effects, big flavour).
- **National-team call-ups** affecting availability/fatigue even before international football is playable.
- **Pre-season friendlies and tours** (sharpness + revenue).
- **B-teams/U21 leagues** so youngsters get minutes.
- **Loan management:** recall clauses, loan reports, development tracking of loanees.
- **Training compensation & solidarity payments** (makes academies financially meaningful).
- **Sporting director/DoF** as the executor of AI recruitment.
- **Club takeovers** that reshape budgets.
- **Opposition analysis reports** before matches.
- **Captaincy & dressing-room hierarchy.**
- **Set-piece routine designer.**
- **Hall of fame/records book, season awards (PFA-style, Ballon d'Or-style), team of the season.**
- **"Holiday" auto-manage** to fast-forward seasons.
- **Deterministic replay files** attached to bug reports ("this seed + commands reproduces the weird goal").
- **World-metrics dashboard** across seasons (your simulation health monitor).
- **Per-career potential randomisation** so wonderkids differ per save.
- **Retired players becoming coaches/managers/scouts.**
- **League reputation drift** (a league that does well in Europe gains attraction and money).
- **Accessibility:** colour-blind team kits in the viewer, scalable UI.

---

## Answers to the Research Questions (§56)

1. **Stack:** Python/FastAPI + SQLite + React/TS (§2).
2. **Form:** a self-hosted local web app. Not Unity/Unreal; a desktop wrapper can come later (§3).
3. **Database:** SQLite, one file per save; DuckDB for offline data work (§3, §5).
4. **Python or C#:** Python, with a gated Rust kernel fallback. C# is a valid alternative but loses the calibration ecosystem (§3).
5. **Position representation:** continuous metres, 10 Hz, 3D ball (§11).
6. **Grid vs continuous:** continuous for Tier 0. A zone grid (e.g. 12×8) is used only for xT and Tier 1 possession chains (§12).
7. **Decisions:** utility scoring + softmax sampling with logged components; attributes affect both choice and execution (§11–13).
8. **Formation influence:** per-phase slot anchors + role offsets + block shift + space-seeking + defensive assignments (§9, §11).
9. **Calibrating with real data:** fit the xG, pass success, xT and action-choice models from StatsBomb/Wyscout; movement/shape from SkillCorner/PFF/Metrica tracking; results from football-data.co.uk; automated validation harness (§12, §34).
10. **Datasets:** §31.
11. **Ratings:** imported (user file) or generated from position templates × market value × league strength × stats, then derived attributes (§32).
12. **Importing current players:** transfermarkt-datasets + user ratings file + entity resolution + patch layer (§32).
13. **FC-rating limitations:** EA IP/ToS; no potential in the official API dump; no hidden/personality/wage/contract data; lower-league/youth coverage gaps; a game-design scale, not real performance; a one-time snapshot (§31–33).
14. **Transfers:** §15. **15. AI managers:** §14. **16. Youth:** §17. **17. Potential:** §16, §18.
18. **Finances:** §21. **19. Leagues/competitions:** §22–26. **20. Saves:** §28. **21. Performance:** §35.
22. **MVP:** §38. **23. Later:** §39.

## Verification (how we'll know each step works)

- **Phase 0 spikes:**
  - A data report shows ≥95% of PL/Championship squad players matched across TM ↔ FC27, with the unmatched list reviewed.
  - The engine spike renders 22 players holding a recognisable 4-3-3 vs 4-4-2 shape, with the tick cost measured.
- **Per phase:** `just test` (unit + property + integration), `just validate` (statistical report vs. targets), `just bench` (performance gates), and a Playwright smoke run: create career → advance to match → watch 5 minutes → pause → switch formation → finish → save → quit → load → continue.
- **MVP acceptance:**
  - A 10-season soak across 5 seeds passes all distribution checks.
  - A live tactical change produces a visible shape change and a measurable xG/possession shift in paired tests.
  - Save/load determinism test passes.
  - Promotion/relegation incl. play-offs is correct over 10 seasons.


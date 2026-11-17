# W9a: the NCAA men's soccer season (notes)

The user asked for this on 16 Nov 2026: a full US NCAA Division I men's season whose players feed MLS's SuperDraft. It was built on its own branch from 9939c99 (B1) and will be merged into `phase-1-match-believability`. The SuperDraft itself (order, picks, contracts) is B5's, not this branch's.

## What's built
- **Programs** (`data/config/college/ncaa_d1.yaml`): 213 programs in 23 conferences for 2026.
  - Researched 16 Nov 2026 from Wikipedia's "List of NCAA Division I men's soccer programs" and "2026 NCAA Division I men's soccer season", and checked against both.
  - Changes in 2026: the Pac-12 returns (with Gonzaga), the Mountain West starts men's soccer (with Grand Canyon), the WAC dropped it, the MAAC is now the Metro, and UTRGV joined the OVC. There are no independents.
  - Each program has a tier, from 1 (a national power) to 5. The tiers are a judgement call.
  - Tournament sizes are estimates from the 2024-25 formats.
  - All 23 conferences get an automatic bid. West Florida, new to D-I, is really ineligible for the 2026 postseason; the game doesn't model that.
- **Rules:** `data/config/college/rules.yaml`, validated by `defs/college.py` and cross-checked in `defs/loader.py`.
- **The college world** (`world/college/roster.py`):
  - The NCAA is a competition (key `NCAA`, type `college`, `sim_level: simulated`). It is not in `defs.leagues`, so `active_leagues`, the league pages, cups, Europe and the start page's club list never see it.
  - **Programs** are clubs with nation USA and `source_league` `footsim:NCAA`. They have a fixed reputation by tier and a fixed 4-4-2.
  - **Rosters** have 26-28 players in four classes, aged about 18-23.
  - **Generation, the W7 way:** each player's attributes are copied from a professional of his position near the overall wanted, then shifted to it. The templates are the save's own professionals, so this also runs inside a career for recruiting.
  - **Names** come from the save's own people: about 78% American, the rest from 20 countries.
  - Each player holds a `college` contract (no wage) at his program, so squads and the fast engine see him like anyone else.
- **Ratings** (career seed 7, 5,747 players):
  - median 45, 90th percentile 52, 99th percentile 57; the best are about 60-62, after a cap at 2.5 spreads;
  - a team's best eleven averages 44 (10th percentile), 49 (median) and 53 (90th percentile);
  - by tier: 49.7, 48.5, 45.9, 43.1, 39.7. MLS squads average 65.
  - **Potential:** mean room by class is 14, 11.5, 9 and 7, plus a 3% "star" bonus of 6-14. About 50 players have a potential of 75 or more, and about 215 of 70 or more.
- **The season** (`world/college/season.py`, with pure parts in `competitions/college.py` and `competitions/bracket.py`):
  - **Regular season**, 20 Aug to 4 Nov, stage `college`, on 19 match days. Each conference plays a single round robin in its last weeks, and non-conference games fill the rest (the neediest teams first, never the same opponent twice). That gives 15-17 matches a team: 200 of 213 play 17. There's no overtime, so games can end level.
  - **Conference tables** count conference games only: 3-1-0, then head-to-head points, goal difference, goals scored, wins, and lots.
  - **Conference tournaments**, stage `CT:<key>`, 7-15 Nov:
    - The field is the table's top N, in a fixed bracket by seed with byes.
    - Single matches at the higher seed, with overtime then penalties.
    - A conference without a tournament (none in 2026) sends its table champion.
  - **The NCAA tournament**, stage `NCAA`:
    - The field is selected on 16 Nov: 23 conference champions and 25 at-large teams, the best of the rest by the RPI (0.25 WP + 0.50 OWP + 0.25 OOWP, with draws and shoot-outs counted as half).
    - Seeds follow the RPI. Seeds 1-16 get byes into the second round, and seeds 17-48 sit as 17 v 48 ... 32 v 33 in a 64-bracket.
    - Rounds are on 19, 22 and 29 Nov and 5, 11 and 14 Dec.
    - The higher seed hosts until the College Cup, which is at a neutral ground. Overtime, then penalties.
    - Who is where in each bracket is in `college_entry`. A fixture's `round` is the bracket round and its `tie` is the match's index in the round.
  - **Titles** go in `league_title` under the NCAA competition:
    - `<conf> regular season`: kind `award`, or `champion` for a conference with no tournament; phase = the conference key;
    - `<conf> Tournament`: kind `champion`;
    - `NCAA Championship`: kind `champion`, phase `NCAA`.
    - The season review and honours already skip competitions that aren't in `defs.leagues`. A club's history counts the titles.
  - Matches use the fast engine like every other fixture. `decider_for` sends college stages to `college_decider`.
- **The draft pool** (`world/college/draft.py`):
  - After the College Cup final, every senior and the best 8 underclassmen with a potential of 66 or more (`ga`) become prospects (`declared_season`). In the test season that was 1,277 seniors and 8 GA players.
  - Prospects stay on their rosters and out of the market until `turn_pro`.
  - On 15 Feb the undrafted become free agents; one still unsigned a season later retires. The lifecycle's own free-agent retirement also applies at each rollover.
- **The rollover** (`college_turnover`, called from `world/season.py rollover` after `season_turnover`):
  - the last prospects and seniors leave;
  - stale undrafted players retire;
  - the classes move up;
  - each program signs 6-10 freshmen to get back to 27, the positions it lacks first, at its own level (stronger programs recruit better). In the test that was 1,460 freshmen.
- **Kept out of the pro systems:**
  - `market._players`, the market's cache of every player, leaves out enrolled players and prospects. This also covers every AI club's search, loan search, renewals (which use the market), the user's offers ("No such player") and the market overview.
  - `transfers.validate_move` and `loans.validate_loan` refuse college players.
  - `renewals._expiring_rows` skips `college` contracts.
  - `finance.initialize_finances` gives college programs no ledger, so they also get no budgets, monthly settling or wage bills.
  - `lifecycle.youth_intake` skips college clubs, and `trim_squads` skips college contracts.
  - `reputation.drift_reputations` skips college clubs.
  - A turn to pro bumps `players_epoch`, so the market's cache sees the new free agent.
- **Checked and left alone, since they only read leagues, cups or club_finance:** cups (entry by league), Europe, `_league_positions`, settle_month, board targets, the start page (`world_leagues` lists only `defs.leagues`), `refresh_ai_tactics` (league members only), honours and the season review.

## Interface for the SuperDraft (B5)
- `footsim.world.college.draft_pool(conn, world, meta, season_id) -> list[DraftProspect]` returns the prospects of that season's draft still to be picked, best first by overall + potential.
  - Fields: `player_id`, `name`, `college_id`, `college`, `class_year` (Fr/So/Jr/Sr), `age`, `position`, `overall`, `potential` (the hidden one; scouting it is B5's choice) and `ga`.
- `footsim.world.college.turn_pro(conn, meta, player_id, day)`: the player's college contract ends and his status becomes `pro`, so he is a free agent. The draft then signs him (`complete_move` with a free-agent move, or its own contract insert). It raises ValueError if he isn't in college.
- `footsim.world.college.release_undrafted(conn, meta, day)` runs by itself on 15 Feb (`draft.release`). B5 can call it right after the draft instead.
- `world.college.common.in_college(conn, player_id)` and `IN_COLLEGE_SQL` are there for any other exclusion.

## Read API (`api/college.py`, prefix `/api/college`)
- `GET /conferences?season_id=` returns `[{key, name, short_name, tournament, regular_season_champion: ClubRef|null, tournament_champion: ClubRef|null, rows: [{position, club: ClubRef, played, won, drawn, lost, goals_for, goals_against, points, in_tournament}]}]`.
- `GET /rankings?limit=50` returns `[{rank, club, conference (short name), rpi}]`: the season's RPI so far.
- `GET /bracket?event=NCAA|CT:<key>&season_id=` returns `{event, name, season, seeded, entrants: [{seed, club, conference, bid: auto|at_large|null, rank, rpi}], rounds: [{round, name, date, matches: [{index, a: {seed, club}|null, b, bye, fixture_id, date, neutral, home_goals, away_goals, home_pens, away_pens, extra_time, home_club_id, winner: {seed, club}|null}]}], champion}`.
  - Match indices run top to bottom.
  - The matches with indices 2i and 2i+1 feed match i of the next round.
- `GET /draft-pool?season_id=` returns `[{player_id, name, college: ClubRef, class_year, age, position, overall, potential, ga}]`.
- With no college world yet (an old career before its rollover), every endpoint but the draft pool returns 404 "starts next season".

## Schema
- **v24** (`_to_v24`) creates `college_team`, `college_player` and `college_entry` with `checkfirst`, so it also runs on a v22 database.
- **v23 is a no-op placeholder** for the MLS-rules branch. On merge, replace it with theirs and renumber if needed.

## World and careers
- **No world rebuild and no new career needed.** The college world is generated into a career by `ensure_college`, called from `create_season_fixtures`: a new career gets it at its start, and an existing one at its next rollover, as `ensure_leagues` adds leagues.
- **Cost:** a new career starts in 4.5 s with it (measured with the season below).
- **Follow-up:** move the generation into `just build-world` so a new career, on the phone especially, doesn't pay for it. The code takes a connection, so `build_world` could call it after `_write_world` with the world seed.

## Timing
All runs are a watch-only career's first season on the whole base world, with seed 7 (`advance` to the season's end, the rollover included). Two other agents were working on the Mac at the same time.

**The college game's own cost, CPU (`process_time`) in the instrumented run:** about 13.4 s on a season of about 220 s CPU, or 6%.
- the 1,966 college matches (1,804 regular season, 115 conference tournament, 47 NCAA): 10.6 s;
- generating the world (5,747 players) and the fixtures at the career's start: 1.4 s;
- the rollover's recruiting and cycle: 0.9 s;
- the daily progress (tables, brackets, RPI): 0.5 s.

**On top of that, an indirect share:** the monthly development, the season's overall snapshot and the retirement draw now cover about 21% more players (33.5k against 27.8k). The market's cache doesn't grow, because it leaves college players out. This share wasn't isolated; by the size of those steps it's a few seconds a season.

**Whole-season totals were too noisy to compare:**

| Run | Season, wall clock | CPU, career start + season |
|---|---|---|
| With college | 200 s, then 217 s | 221 s |
| Without | 245 s, then 359 s | 291 s |

The run without college was the slower one both times, because the other agents' load changed between runs. A clean comparison needs a quiet machine.

**A new career** starts in about 4.5-5.2 s with the college world, against 3.3-3.6 s without, so generating it adds about 1.4 s.

## Pro results change
- Pro results are not identical to a world without college soccer.
  - **The match engine's RNG is keyed by fixture id.** College fixtures take ids among the cups', play-offs' and Europe's later rounds, which are created as the season goes, and among every later season's league fixtures.
  - **Monthly development and retirement each draw one stream over every player,** and college players are part of it.
- The first season's league fixtures keep their ids, but the matches then diverge.
- Keeping pro results unchanged would need the match RNG keyed by the fixture's content (season, competition, stage, round, clubs) instead of its id, and the development stream split. Both would change the existing careers' futures, so neither is done here.
- **Golden values:** untouched, since the agent engine is unchanged.

## Tests
- `tests/unit/test_college_unit.py`:
  - brackets: seed order, the 48-team field's 16 byes, conference shapes of 4, 6, 8 and 10, played-out brackets;
  - the regular season on 2026's conference sizes;
  - a hand-checked RPI;
  - season dates and the definitions.
- `tests/integration/test_college_season.py`: a watch-only career's whole season on the base world, read after the College Cup and after the rollover. It checks:
  - the regular season and conference tables, titles and tournaments;
  - the 48-team field: auto bids are exactly the champions, at-large teams come by the RPI, seeds 1-16 have byes, the higher seed hosts, the College Cup is neutral, and the champion's title;
  - the draft pool and `turn_pro`;
  - the rollover's classes, freshmen and contracts;
  - no college player in any build of the market's players, no finances, ledger, transfers, youth contracts, league membership or reputation drift for college clubs;
  - the read API on the played season.
- `tests/unit/test_migrations.py`'s v9 finance test now counts only non-college clubs.

## Follow-ups
- B5 (the SuperDraft) uses `draft_pool` and `turn_pro`; it may call `release_undrafted` after its last round.
- The screens: conference tables, the bracket, rankings, the draft pool (B6).
- A college club's page: the club page works but shows no finances or league. Searching for clubs finds college programs.
- Move the college generation into the world build (above).
- West Florida's postseason ineligibility; real conference tournament sizes once 2026's are confirmed; regional scheduling for non-conference games (pairing is by need and conference only).

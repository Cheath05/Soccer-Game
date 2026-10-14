# W6: European competitions (approved scope, 14 Oct)

## What the user asked for
- The Champions League and "other competitions like that" are the next priority, ahead of step 2.1, the market report and the play-test gate.
- **Scope:** all three UEFA club competitions at once: the Champions League (UCL), the Europa League (UEL) and the Conference League (UECL).
- **Qualifying: "realistic-lite":**
  - league finish gives places, in real-style numbers per country;
  - domestic cup winners get Europa League places;
  - clubs from countries without a league in the game enter by reputation;
  - a short summer qualifying stage fills the last places.

## Principles
- **One match engine, as for every other fixture.** AI matches are played by the fast engine; the user's on the agent engine (live or instant). Nothing about Europe changes how a match is played, except home advantage at the venue and the knockout decider.
- **Data in YAML:** formats, the access list (who qualifies), dates, prize money. Code holds the rules that are the same for every competition: the draw, the table, the bracket, places passing down.
- **Determinism:** every draw uses `derive_rng(meta.seed, "europe", season, competition, stage)`.
- **Same machinery as the domestic cups** wherever it fits: `cup_tie` and `fixture` rows, `Decider` for two legs, extra time and penalties, `post()` for prize money, `_clear_way` to move domestic matches.
- **The world we have:**
  - Ten UEFA countries have leagues in the game (ENG, ESP, ITA, GER, FRA, POR, NED, BEL, SCO, TUR). Saudi Arabia is AFC and belongs to W7.
  - Clubs with squads but no league in the game include those of AUT, SUI, DEN, NOR, SWE, POL, IRL, GRE, CZE, UKR, CRO, CYP, HUN, BUL, AZE and FIN. They play only in Europe.

## The competitions

| | League phase | Matches | Pots | Then |
|---|---|---|---|---|
| UCL | 36 clubs | 8 | 4 × 9: two opponents from each pot, one home, one away | 1st–8th to the round of 16; 9th–24th to a knockout play-off; 25th–36th out |
| UEL | 36 clubs | 8 | as UCL | as UCL |
| UECL | 36 clubs | 6 | 6 × 6: one opponent from each pot, 3 home, 3 away | as UCL |

**League phase draw constraints:**
- no opponent from your own country;
- at most two opponents from any one country;
- home and away balanced as above.

**League phase table tie-breakers (simplified UEFA):** points, goal difference, goals scored, away goals scored, wins, away wins, then lots.

**Knockouts:**
- **Play-off:** 9/10 v 23/24, 11/12 v 21/22, 13/14 v 19/20 and 15/16 v 17/18, two legs. The higher-placed club is at home second.
- **Round of 16:** a seeded bracket. 1st and 2nd meet the 15/16–17/18 winners, and so on down the table.
- **Then:** quarter-finals and semi-finals over two legs, then a one-match final at a neutral ground. Extra time and penalties decide the second legs and the final; there's no away-goals rule.
- **Holders:**
  - the UCL winner enters next season's UCL league phase;
  - the UEL winner also enters next season's UCL league phase;
  - the UECL winner enters next season's UEL league phase.
  - A holder's own league place then passes down.

## Qualifying (realistic-lite)
**Access list, per country (`data/config/europe/access.yaml`):**
- League-phase places by league finish, per competition.
- The cup winner's UEL place: `cup: FA_CUP`, the country's main cup.
- For countries without a league in the game, a number of "champions" and "places" per competition.
- The numbers follow the real 2024–27 access list for each country's association ranking. They're approximate, rounded to what the game's countries make up, and noted as approximate in the file.

**Countries without a league:**
- Their "champion" each season is drawn by weighted lottery among the country's clubs, weighted by reputation (`europe.yaml: lottery_power`). So Salzburg usually comes first, but not always.
- Further places go to the next clubs drawn.

**One summer qualifying stage per competition:** a two-legged play-off round in August.
- **UCL play-off:** the access list's qualifiers (lower-ranked champions and league runners-up). The winners join the league phase; the losers drop into the UEL league phase.
- **UEL play-off:** losers drop into the UECL league phase.
- **UECL play-off:** losers are out.
- The count of play-off places per competition is set so that each league phase has exactly 36. If a country's league isn't in the career (an old save), the next club by coefficient fills the gap. The `fill` rule is in the YAML.

**Double qualification:** a club is in the highest competition it has earned. Its lower place goes to the country's next-best finisher not yet placed. A cup winner already in Europe gives its UEL place to the league's next club.

**The first season:** there is no last season, so league "finishes" are by reputation within each league, as the domestic cups already do.

## Club coefficients
- Each club earns points per European match and round, on a simplified UEFA scheme in `europe.yaml`: a win 2, a draw 1, and bonuses for reaching a round.
- A club's coefficient is the sum of its last 5 seasons.
- **Season 1:** a seed from reputation, also in `europe.yaml`, so the first pots look like real ones (Real Madrid and City in pot 1, Qarabağ in pot 4).
- **Pots:** by coefficient. The UCL holders always go in pot 1.

## Calendar (`data/config/europe/calendar-2026-27.yaml`)
- **Pattern:** the 2025-26 pattern moved to 2026-27, avoiding FIFA's 2026 combined window (21 Sep – 6 Oct):

  | Stage | Dates |
  |---|---|
  | Qualifying play-offs | Aug 18/19 and 25/26 (UEL and UECL on the Thursdays) |
  | League phase | eight matchdays, mid-Sep to late Jan |
  | Knockout play-off | mid/late Feb |
  | Round of 16 | March |
  | Quarter-finals | April |
  | Semi-finals | late April / early May |
  | Finals | UEL Wed 19 May, UECL Wed 26 May, UCL Sat 29 May 2027 |

- The UCL plays Tue/Wed and the UEL and UECL Thursdays, split evenly across a matchday's days.
- **Later seasons:** shifted with `shifted_calendar`, as the country calendars are.
- **Clashes:** any domestic match (league or domestic cup tie) within `REST_DAYS` of a club's European match moves to the nearest free day for both clubs.
  - Leagues use the existing `_free_day`.
  - A domestic cup tie gets a new `_free_cup_day` near its date: the same idea, inside the cup round's week.
- **Who gets moved:** domestic fixtures move; European dates never do.

## Money (`finance.yaml: europe_prizes`, the 2024–27 distribution, approximate)

| | Starting fee | Win | Draw | Round of 16 | QF | SF | Final | Winner |
|---|---|---|---|---|---|---|---|---|
| UCL | €18.62M | €2.1M | €0.7M | €11M | €12.5M | €15M | €18.5M | +€6.5M |
| UEL | €4.31M | €0.45M | €0.15M | — | — | — | — | — |
| UECL | €3.17M | €0.4M | €0.133M | — | — | — | — | — |

- **Further prize money in the YAML:** a league-phase ranking bonus, the knockout play-off, and the UEL and UECL rounds, on the same scheme and scaled down.
- **The ledger:** everything goes in as `prize` entries, with `ref_id` set to the competition, so the Finances page and the board see it.
- **Expectations:** a club's expected income and its budget don't assume European money. It's a bonus, as for the domestic cups.

## Data model (schema v18)
- **`competition` rows:**
  - `UCL`, `UEL`, `UECL`;
  - `type = "continental"`;
  - `nation_id` NULL.
- **`continental_entry`:** `season_id`, `competition_id`, `club_id`, `stage` (`league_phase` or `qualifying`), `route` (`league:ENG1:4`, `cup:FA_CUP`, `holder`, `lottery:AUT:1`, `dropped:UCL`, `fill`), and `pot` (set at the draw). It's unique on (season, club), so a club is in one competition a season.
- **League-phase fixtures:** `stage` = the competition key and `round` = the matchday (1–8).
- **Knockout ties:** `cup_tie` rows with rounds after the league phase, and fixtures with `stage` = the competition key and `round` ≥ 100 (100 is the play-off, then 101, 102 and so on). So the matchdays and the knockout rounds never collide, and `decider_for` can tell them apart.
- **Qualifying ties:** `stage` = `UCL_Q` and so on, as one more knockout round.
- **`club_coefficient`:** `club_id`, `season_id`, `points`.

## API and UI
- **`GET /api/europe/{key}?season=`:**
  - the league-phase table;
  - matchdays and results;
  - the knockout bracket, round by round with aggregates;
  - qualifying;
  - who entered by which route.
- **A "Europe" page,** one tab per competition, with the user's competition first:
  - a league-phase table with lines at 8th and 24th;
  - matchday fixtures;
  - the bracket.
  - The phone layout follows the M2 pattern.
- **Elsewhere:**
  - **Dashboard and Fixtures:** European fixtures show with their competition. "Sim to…" gains "Next Champions League match" through the existing `sim_targets`, which already handles any competition that isn't a league.
  - **Season summary:** a "continental_title" headline builder (the hook already exists) and honours.
  - **Club history:** European finishes.
  - **News:** draws, results and eliminations for the user.

## Checkpoints (each a pushed checkpoint, the usual loop)
1. **E1:** definitions and data.
   - **Files:** `defs/europe.py` and `data/config/europe/` (competitions, access, calendar, coefficient and lottery settings), plus prize money in `finance.yaml`.
   - **Checks:** validation, including that each competition's numbers can make 36 from the game's countries.
   - No behaviour change.
2. **E2:** schema v18 and qualification.
   - **Builds:** at each season start (and for the first season at career start), the entrants and the summer play-off ties, with double qualification and places passing down.
   - **Tests:** 36 per league phase after qualifying, one competition per club, the passing-down cases, the first season, an old save without some leagues, determinism.
3. **E3:** the league phase.
   - **Builds:** pots by coefficient, the constrained draw and the 8 or 6 matchdays (a search over matchings with deterministic backtracking), the fixtures, the table.
   - **Tests:** every constraint on many seeds, everyone plays once per matchday, the table's tie-breakers.
4. **E4:** knockouts.
   - **Builds:** the play-off, the bracket, two legs, the final, prize money, the holders' places next season.
   - **Tests:** a full European season in a watch-only career, with everything played, money balancing and a believable winner.
5. **E5:** the calendar.
   - **Builds:** moving domestic league and cup matches around European dates.
   - **Tests:** no club ever has two matches within `REST_DAYS`, over a whole season for every European club, and every league still finishes in its season.
6. **E6:** club coefficients, their seeding from reputation, and pots from coefficients.
7. **E7:** the API and the Europe page, plus the dashboard, season summary, history and news hooks. A Sonnet agent does the UI; I review it.
8. **E8:** measurement.
   - **Runs:** watch-only seasons (`footsim market-report`-style, or a new `footsim europe-report`).
   - **Checks:** winners by club strength, goals per game in Europe against real (about 3.0 in the UCL), fixture congestion and money.

## Open, decided in their checkpoint
- **Home advantage in Europe:** the same `home_advantage.yaml`, until step 2.1 fits it. Travel isn't modelled.
- **AI squad rotation for congestion:** today the AI picks its best fit XI, and condition handles fatigue. Look at it in E8, if European clubs' leagues suffer unrealistically or not at all.
- **The UEFA Super Cup:** later, if wanted.

# W9a B2: the four Americas leagues (notes)

Checkpoint B2 of `w9a-americas.md`: MLS, Liga MX, Argentina's Liga Profesional and Brazil's Série A,
with their calendars, cups and money. No schema change (still v22).

## What was added
- **Leagues** (`data/config/competitions/{usa,mex,arg,bra}/`), all `simulated`:
  - `USA1` MLS: the 2026 Eastern and Western Conferences, 34 matches (`legs: 2, cross_rounds: 6`),
    the full MLS Cup Playoffs (Wild Card, best-of-three Round One, conference semi-finals and
    finals, MLS Cup), `table_title: Supporters' Shield`, MLS's tiebreakers (wins first).
  - `MEX1` Liga MX: Apertura (July to December) and Clausura (January to May), each a single
    round robin with its own Liguilla (two legs, the better seed through on a level aggregate,
    the final with extra time and penalties).
  - `ARG1` LPF: the 2026 zones A and B and each club's interzonal rival (ESPN's report of the
    17 Dec 2025 draw), two tournaments, each a knockout (round of 16 crossing the zones in a fixed
    bracket, single matches at the better seed, level to penalties; a neutral final with extra
    time); `table_title: Campeón de Liga`. **The first tournament is named "Clausura"**: real life
    plays the Clausura July to December and the Apertura January to June, so the game's 2026-27
    is the Clausura 2026 then the Apertura 2027.
  - `BRA1` Série A: 20 clubs, double round robin, wins first; nobody moves.
- **Calendars** `usa`, `mex`, `arg`, `bra` and **`can`-2026-27**: Canada has no league in the
  game, but its cup must be dated on its own country's calendar (an invariant of
  `test_cups.py`), so `can-2026-27.yaml` holds only the Canadian Championship (and MLS's
  windows). Cup dates are Wednesdays clear of each league's rounds, windows and breaks for this
  season and the next three (checked by `test_cups_keep_clear_of_their_countrys_league_days`).
- **Cups**: `US_OPEN_CUP` (the 16 lowest-placed **US** MLS clubs, from the round of 16; the final
  at the better-placed club), `CANADIAN_CHAMPIONSHIP` (MLS's three Canadian clubs; two-legged
  semi-final with a bye for the best), `COPA_ARGENTINA` (30 LPF clubs, neutral grounds, no extra
  time), `COPA_DO_BRASIL` (20 Série A clubs from the fifth phase, twelve byes; two legs to the
  semi-finals; a single neutral final).
- **Code**:
  - `CupEntryDef.nation` (with required `ranks`): an entry of one nation's clubs of a league,
    honoured in `world/cups.py _entrants`; the loader checks the nation and the ranks.
  - `CupRoundDef.host: drawn | higher_ranked` (the U.S. Open Cup final).
  - `world/club_nations.yaml` + `apply_club_nations` (MLS's Canadian clubs get nation CAN), at
    the world build and, with `apply_club_names`, at each season's start in `ensure_leagues`
    (idempotent; fixes existing careers without a migration).
  - `importers/synthetic.py`: `ea_league` may be a list (Botafogo moves from FC 27's "CONMEBOL
    Sudamericana" into "Liga do Brasil", built once); `level` for a country without a UEFA
    coefficient; `club_levels: values` (clubs differ by their squads' market values, as
    Transfermarkt's Brazilian games start only in 2025, too few for an Elo).
  - `competitions/fixtures.phase_round_counts(league)` for the calendar checks of grouped and
    phased leagues.
- **Money**: `league_income` from the built squads' mean wage bills; `cup_prizes`; wage levels
  for the LPF and Brazil (`LPF`, `Liga do Brasil`, `footsim:BRA1`).
- **Names**: Liga MX's four accent-less clubs renamed in `club_names.yaml` (Mexico).

## The rebuilt world (seed 2026)
Level = mean of each club's best sixteen in-game overalls; wage bill = mean yearly bill.

| League | Clubs | Level | Squad | Wage bill |
|---|---|---|---|---|
| Brasileirão | 20 (18 built from Transfermarkt, Bahia and Botafogo from FC 27) | 72.5 | 28 | €18.7m |
| LPF | 30 | 70.6 | 29 | €7.9m |
| Liga MX | 18 | 70.4 | 24 | €17.6m |
| MLS | 30 | 69.7 | 27 | €14.5m |

Brazil runs from Flamengo 77.0 and Palmeiras 75.4 to Chapecoense 69.0 (Bahia 72.7 and Botafogo 72.6
mid-table). The build report has no warnings and no unmatched FC 27 club for BRA1.

## Tests and timing
- `test_cups_season.py` (extended: the four leagues' titles and play-offs, their cups' winners by
  country, no Canadian club in the U.S. Open Cup, the renamed and Canadian clubs) and
  `test_league_formats.py` pass on the rebuilt world; so do the unit tests touched
  (`test_cups`, `test_competitions`, `test_new_clubs`, `test_definitions`, `test_importers`,
  `test_europe_defs`, `test_club_names_and_sim_targets`, `test_league_formats_unit`,
  `test_windows`). `just lint` passes.
- A whole season, no user club, seed 5, alongside two other agents' work: the old world with the
  old leagues 169 s (career start and the season); the rebuilt world with the Americas 189–204 s
  in `test_a_season_of_leagues_and_cups` (which also copies, migrates and checks): about
  +12–20% for 98 more clubs in leagues and four more cups.

## Existing careers
At an existing career's next season, `ensure_leagues` first fixes the Liga MX names and the
Canadian clubs' nation, then adds MLS (with its conferences), Liga MX and the LPF (with its zones),
whose clubs the old world has by source name; their cups (U.S. Open Cup, Canadian Championship,
Copa Argentina) are drawn that season. **Brazil is not added** (an old world has only Bahia under
"Liga do Brasil"), nor the Copa do Brasil: Brazil needs a new career on the rebuilt world. A new
career on an old (not rebuilt) world gets the same three leagues at once.

## Open
- `tests/unit/test_season_views.py` fails three tests on 9939c99 already (B1 moved the season
  review's honours to `league_title`; the test still writes only `league_final`). Not B2's.
- The U.S. Open Cup's and Copa do Brasil's lower-division rounds are left out (byes stand in).
- Clausura 2027 / Apertura 2027 and Brazil's dates are approximate (real Brazil runs Jan–Dec).

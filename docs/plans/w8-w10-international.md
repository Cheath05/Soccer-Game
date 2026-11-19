# W8 and W10: international football, the World Cup and the Club World Cup

**Status: planned 19 Nov, building from I1.** From the user (19 Nov): "start working on the club world cup and world cup", with these choices:
- **International football in full:** national teams, squads from players' nationalities, qualifiers by confederation in FIFA's international windows, then the 48-team finals; call-ups take players from their clubs (fatigue and injuries come back with them). **The user can also manage a national team**, alongside a club or on its own.
- **Squads for every real nation:** a country's best players in the game, filled out with made-up home-based players rated to its real strength.
- **The Club World Cup's entrants:** UEFA's from the Champions League as played and UEFA's coefficients; the rest from the game's leagues and rankings, with **guest clubs** (made-up squads rated to their real strength) for the regions the game has no leagues in (Africa, most of Asia, Oceania).
- **Real years:** the Club World Cup in summer 2029, the World Cup in summer 2030, then every four years. Qualifying starts in the 2027–28 windows.

The rules of the project still apply: determinism (all randomness through `derive_rng`), tunable numbers in YAML (`data/config/international/`), the same engines for every match, one checkpoint per finished step with `progress.md`, What's new and help.

## What's there to build on

- **Nationalities:** every `person` has a `nation_id`. 174 nationalities appear in the base world. 85 have 40+ players, but many World Cup nations have only a few (Egypt 15, Iran 7, Qatar 1): their real players play at home, in leagues the game doesn't simulate.
- **International windows:** each calendar has FIFA's windows (`international_windows`: September–October, November, March, June). Leagues pause in them where they really do (`pause_for_international_windows`).
- **Competitions:**
  - W6 and W7's European machinery (`world/europe/`): draws with pots and country constraints, a league phase, two-legged and single knockouts, coefficients;
  - B1's groups and play-offs (`competitions/fixtures.py`, `competitions/playoffs.py`);
  - the cups' scheduling (`world/cups.py` `_free_day`).
- **Generated squads:** W7's `new_leagues` rules (`world_build.yaml`, `match/synthetic.py`) make players rated to a target strength, with names from a country's name pool.
- **The season boundary:** a season ends on 30 June and rolls over only when every fixture of the season has been played (`season.season_complete`). Both tournaments run into July, so international and Club World Cup fixtures must be left out of that check (they keep the season they were drawn in).

## The model

- **A national team is a `club` row** (its nation, no league) plus a `national_team` row: confederation, Elo, FIFA-style ranking points, its manager (AI, or the user). The engines, team sheets, tactics, fixtures and match pages then work unchanged.
- **Squads:**
  - **Pool:** a national team's players are a pool of its nationality: the game's players with that `nation_id`, plus its made-up home-based players.
  - **Squad:** a squad (`national_squad`: the window or tournament, up to 26 players) is picked from the pool before each window: the best by position for an AI manager, the user's choice for the user. `squads.load_squad` loads the called-up squad for a national team's club id.
- **Made-up home-based players** (`national_pool`):
  - generated per nation, enough to field a squad whatever the game's own players;
  - rated so the nation's best XI matches its real strength (Elo to a target level, as W7 maps club Elo);
  - kept out of the market, loans, development draws and youth intake, like college players; they age, and the pool is topped up every four years.
  - A nation with enough strong players in the game gets few or none.
- **Call-ups:**
  - a called-up player is away from his club for the window's days: unavailable to it, and back with the condition and any injury he picked up;
  - leagues that play through the windows (England's League One and Two) lose him.
- **Elo:** each national team starts from its real World Football Elo (mid-2026, `data/config/international/teams.yaml`) and moves with every result, using Elo's own weights by match type. It seeds the draws and gives the rankings shown.
- **Fixtures:** a competition type `international` (qualifiers, the finals, friendlies) and `club_world_cup`. Neither counts towards `season_complete`.

## The World Cup 2030 (and every four years)

- **Hosts:** Spain, Portugal and Morocco qualify automatically. FIFA's centenary matches in South America are not modelled.
- **Slots** (`data/config/international/world_cup.yaml`): UEFA 16, CAF 9, AFC 8, CONMEBOL 6, CONCACAF 6, OFC 1, with the hosts counted in their confederation's slots, plus the intercontinental play-off. The 2026 allocation is the default; any 2030 change is YAML.
- **Qualifiers: realistic-lite, in the windows from September 2027** (CONMEBOL from September 2027 too; UEFA from March 2029):
  - **UEFA:** 12 groups of 4–5 in 2029, drawn from Elo pots; the winners qualify; the runners-up and four play-in teams go to play-off paths in March 2030.
  - **CONMEBOL:** one round robin of 10, home and away, over 18 matchdays.
  - **CAF:** groups of 6; the winners qualify, and the best runners-up go to a play-off.
  - **AFC, CONCACAF and OFC:** the stronger teams start in the late rounds, as the real formats seed them. The weakest teams' early rounds are settled on paper by Elo, so every nation in a live round has a squad.
  - **Intercontinental play-off:** six teams for two places, in March 2030.
  - **Friendlies** fill the windows with no qualifier, between nations of similar Elo, so call-ups and Elo keep moving.
- **Finals, 11 June – 19 July 2030:**
  - **Draw:** 48 teams in 12 groups of 4. Pots come from the ranking, with the hosts in pot 1. No group has two teams from one confederation, except UEFA (at most two).
  - **Knockouts:** the top two and the eight best third-placed teams go to the round of 32, then on to the final. Single matches, with extra time and penalties.
  - **Fixtures** are spread over the real dates.
- **Screens:** an International page (the ranking, qualifying groups and tables, the finals' groups and bracket); national team pages (squad, results, Elo); players' caps and international goals.

## Managing a national team (the user's choice)

- **Taking the job:** at a new career (a national team instead of a club, or both), or later from the International page.
  - This first version: any nation's job, as a sandbox choice.
  - A reputation-based offer system is a follow-up.
- **The job:**
  - pick the squad for each window and tournament from the nation's pool (the scouts' view of each player, his club form and minutes);
  - set the team's tactics (the Tactics page switches between the club and the country);
  - play its matches as the user's own: Match day, the live viewer, Instant.
- **Only a country, no club:** Continue moves from window to window; the club screens are hidden, as for a watch-only career.

## The Club World Cup 2029 (and every four years)

- **32 clubs, as FIFA's format:**
  - **UEFA 12:** the Champions League winners of 2026-27, 2027-28 and 2028-29, then the best by UEFA's four-season club coefficient, at most two a country unless more won the Champions League.
  - **CONMEBOL 6:** the game has Brazil and Argentina, whose clubs were all six CONMEBOL entrants in 2025. Entrants come from their league champions and a four-season ranking of their clubs' league finishes, standing in for the Libertadores until W9b builds it.
  - **CONCACAF 4:** MLS and Liga MX, by champions and a four-season ranking (the Concacaf Champions Cup stands in the same way until W9b).
  - **AFC 4:** Saudi clubs by the Saudi league's champions and ranking, plus guest clubs from Japan, Korea, the UAE and Qatar.
  - **CAF 4 and OFC 1:** guest clubs.
  - **Host 1:** a host country in YAML, and its best club.
- **Guest clubs** (`data/config/international/guest_clubs.yaml`): real clubs with their country, stadium and a strength from their real standing, made like W7's generated squads. They have no league; they play only the Club World Cup and are kept out of the market. Their squads are refreshed before each tournament. They are listed per confederation with a ranking, so the entrants change between editions.
- **Tournament, 15 June – 13 July 2029:** 8 groups of 4, drawn from 4 pots by ranking, with no two clubs of one confederation in a group (UEFA's, at most two). Then the round of 16, quarter-finals, semi-finals and the final, single matches. Prize money from FIFA's 2025 figures, as club income.
- **Screens:** a Club World Cup page (groups, bracket, the entrants and how they qualified); honours and club history.

## Checkpoints (each committed and pushed, with tests)

1. **I1, national teams and squads:**
   - `teams.yaml` (every FIFA member: confederation, Elo, names);
   - the `club` and `national_team` rows;
   - made-up pools;
   - the AI's squad picking;
   - a migration for running saves (made on first use, as `ensure_college`);
   - tests: every nation can field a squad, and the best XIs follow Elo.
2. **I2, the windows:**
   - call-ups and players away;
   - friendlies in every window;
   - Elo updates;
   - fixtures not blocking the rollover;
   - players' caps and goals;
   - a first International page (the ranking, a national team's page).
3. **I3, the qualifiers** for 2030, by confederation, with the play-offs, and their screens.
4. **C1, guest clubs and the Club World Cup's entrants:** the guest clubs, the UEFA and per-region rankings, and the host.
5. **C2, the Club World Cup 2029:** the draw, groups, knockouts and prize money; its page and honours.
6. **I4, the World Cup finals 2030:** the draw, groups, best thirds and the bracket; its page and honours; summer fatigue.
7. **I5, the user as a national manager:** taking a job, squad selection, tactics, playing; a country-only career.
8. **Check:** a career simulated from 2026 to 2030, and its timings.

## Open, to settle while building

- Real 2026 Elo values and the 2030 slot allocation and draws need checking against sources (eloratings.net, FIFA). Values go in YAML with their source and date.
- The Club World Cup 2029's host isn't decided by FIFA. YAML picks one, and it's easy to change.
- Players' fatigue after a summer tournament (a later rest at their clubs) is a follow-up.

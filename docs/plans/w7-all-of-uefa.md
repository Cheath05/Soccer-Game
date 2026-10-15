# W7: All of UEFA. Every country's league and cup, country coefficients, and the real qualifying rounds

**Asked for by the user on 15 Oct 2026:**
- a country coefficient ranking that changes each season which countries are strongest, and how many clubs each one sends to the Champions League;
- every league that can qualify for Europe;
- the real qualifying rounds;
- a league picker where the big leagues stay easiest to find, smaller ones are still findable, and a second filter sorts by continent (ready for the MLS later).

This plan supersedes W6's "realistic-lite" qualifying: the fixed per-country list in `europe/access.yaml` and its single summer play-off round.

## What exists (W6, v1.58–1.61)
- **The competitions:** UCL, UEL and UECL, each with a 36-club league phase, knockouts and a final (`world/europe/`).
- **Qualifying:** `europe/access.yaml` lists each country's places by hand, and a single two-legged play-off round runs per competition.
- **Coefficients:** club coefficients exist in a simplified form (`club_coefficient`, `europe/settings.yaml`). Country coefficients don't exist.
- **Leagues:** 27, in 19 countries.
  - FC 27 has 1–4 clubs each from Greece, Czechia, Ukraine, Croatia, Cyprus, Hungary, Bulgaria and Azerbaijan. They sit in the world outside any league and are picked for Europe by a reputation lottery.
  - The other 28 UEFA countries have no clubs at all.

## Data sources
| Source | What it gives | Where it lives |
|---|---|---|
| EA FC 27 (existing) | real squads with ratings | `data/raw/ea_fc27`, never committed |
| Transfermarkt (existing duckdb, games to Jul 2026, values to Jun 2026) | **full 2025-26 squads** for Greece (GR1), Croatia (KR1), Czechia (TS1), Serbia (SER1) and Ukraine (UKR1): names, birth dates, positions, nationality, height, foot, market value, contract expiry. **UEFA qualifying lineups** for 2025-26: 194 clubs and about 4,900 players, among them the champions and cup winners of the small countries. **Every game since 2012** in 31 leagues and all UEFA competitions. | `data/raw/transfermarkt`, never committed |
| kassiesa.net (UEFA's published figures) | country coefficients for each season 2020/21–2025/26, all 55 associations | committed as config: they are public facts |
| UEFA access list 2024–27 (via Wikipedia's 2026-27 pages; the defaults reconstructed and checked, below) | who enters which round | committed as config |
| Web research (league pages) | each new top division's 2026-27 (or 2026) clubs, size, format and cup | committed as config: names and facts only |
| Generated (seeded) | players for clubs no source covers | built into the world, from name pools taken from the raw data at build time |

**Real players where a source has them, generated where none does.** Looking up about 9,000 players club by club isn't reliable, and would still leave ratings to invent. So:
- the 5 Transfermarkt leagues get their real squads;
- small-country clubs that played in Europe in 2025-26 get the real players from their qualifying lineups;
- the rest are generated, with realistic names for each country, rated to the club's measured strength (below).
- **A later option (A6b):** take real names for the remaining clubs from Wikipedia squad lists, kept in `data/raw`. Ages and ratings would still be estimates.

## How ratings are set (measured, not guessed)
1. **Transfermarkt players:** overall comes from the market value, the player's age and position, and the club. The model is fitted on the thousands of players who are in both FC 27 and Transfermarkt, which includes low-value leagues (League Two, Ireland, Scotland, Scandinavia) and covers the small-league range.
   - **Check:** fit on half the leagues and predict the other half; each league's mean error should be under about 2 points.
2. **Club strength:** an Elo rating for every club, computed from Transfermarkt's games since 2012 (31 domestic leagues plus all UEFA rounds). Small-country clubs get theirs from their European results. An Elo → squad-overall curve is fitted on the FC 27 clubs, and generated squads are drawn around it.
3. **Clubs with no games in the data** (never in Europe and not in a covered league) get the league's baseline from the country coefficient (a log fit of league strength on coefficient over the leagues we know), less a bottom-half offset.
4. **Generated squads:** 22–26 players per club, built from a position template, with ages from the real age distribution. Overall is spread around the club's target, using the spread seen in FC 27 squads of similar level. Attributes come from overall and position by the same derivation the importer already uses.

## Country coefficients (A2)
- **Points, UEFA 2024–27:**
  - **Matches:** a win is 2 and a draw 1. In qualifying and play-off rounds both are halved, to 1 and 0.5.
  - **League-phase bonuses:**
    - **UCL:** 6 for taking part, plus a ranking bonus of 0.25 a place from 24th up to 1st, so 1st gets 12 in all.
    - **UEL:** the same 0.25 a place, so 1st gets 6.
    - **UECL:** 0.125 a place from 24th up to 9th, then 0.25 a place to 1st, so 1st gets 4.
  - **Knockouts:** each round reached from the round of 16 on is worth 1.5 in the UCL, 1 in the UEL and 0.5 in the UECL. The knockout play-off has no bonus.
  - **One set of points:** these same points are the club's season points (they replace the simplified `coefficient` in settings.yaml).
- **A country's season coefficient** = its clubs' points ÷ the number of its clubs that entered. Its **ranking** = the sum of the last five seasons; ties go to the later seasons.
- **A club's coefficient** = the higher of its own five-season sum and 20% of its country's five-season coefficient (UEFA's floor). Before the career, its reputation seed still applies.
- **Seeds:** the real season coefficients for 2020/21–2025/26 (`data/config/europe/association_coefficients.yaml`), so:
  - **season 1 (2026-27)** uses the real 2025 ranking (seasons 2020/21–2024/25), as UEFA does: the ranking from two seasons back sets the access list;
  - **season 2** uses the real 2026 ranking;
  - **from season 3**, in-game seasons enter the window.
- **European Performance Spots:** the two countries with the best coefficient in the season just ended each get one extra UCL league-phase place, which goes to the next club in their table. For 2026-27 that's England and Spain, from 2025-26, as in real life.
- **Russia** is suspended and has no clubs, so it's left out: **54 associations**. Liechtenstein has a cup but no league.
- **Storage (schema v19):**
  - new table `association_coefficient(season_id, nation_id, points, clubs, coefficient)`; seeds go in season ids ≤ 0 (season 0 is 2025-26);
  - `continental_entry` gains `entry_round` and `path`;
  - `cup_tie` gains `path`.
- **UI:** the Europe page gets a "Rankings" tab with the country ranking (five seasons, total, places next season) and the club coefficient ranking.

## The access list (A3)
The fixed per-country list is replaced by UEFA's 2024–27 access list **by ranking position**, in `europe/access_list.yaml`. Positions are renumbered with Russia removed, so the old positions 27–55 become 26–54.

**Champions League**
| Round | Path | Enters |
|---|---|---|
| League phase | – | the title holders (TH); the Europa League holders; positions 1–4: champions, runners-up, 3rd and 4th; position 5: champions, runners-up and 3rd; position 6: champions and runners-up; positions 7–10: champions; 2 EPS |
| Play-off (PO) | Champions | champions 11–14, plus 6 Q3 winners → 5 to the league phase |
| PO | League | 4 Q3 winners → 2 to the league phase |
| Q3 | Champions | 12 Q2 winners |
| Q3 | League | 4th of 5, 3rd of 6, runners-up 7–9, plus 3 Q2 winners |
| Q2 | Champions | champions 15–23, plus 15 Q1 winners (24) |
| Q2 | League | runners-up 10–15 |
| Q1 | Champions | champions 24–54 (not Liechtenstein): 30 clubs |

**Where the UCL's losers go:**
- Q1 → UECL Q2 (champions path);
- Q2 champions → UEL Q3 (champions path);
- Q2 league → UEL Q3 (main path);
- Q3 champions → UEL PO;
- Q3 league, PO champions and PO league → UEL league phase.

**Europa League**
| Round | Path | Enters |
|---|---|---|
| League phase | – | the Conference League holders; cup winners 1–7; 5th of 1–5; 12 PO winners; and the UCL drop-ins |
| PO | – | cup winners 8–12, Q3 winners, and UCL Q3 champions-path losers |
| Q3 | Champions | UCL Q2 champions-path losers |
| Q3 | Main | cup winners 13–15, Q2 winners, and UCL Q2 league-path losers |
| Q2 | Main | the cup winners of 16, 3rd of 7–12, 4th of 6, and 8 Q1 winners (16) |
| Q1 | Main | cup winners 17–32 (16) |

**Where the UEL's losers go:**
- Q1 → UECL Q2 main;
- Q2 → UECL Q3 main;
- Q3 champions → UECL PO champions;
- Q3 main → UECL PO main;
- PO → UECL league phase.

**Conference League**
| Round | Path | Enters |
|---|---|---|
| League phase | – | 5 PO champions-path winners, 19 PO main-path winners, and 12 UEL PO losers |
| PO | Champions | Q3 champions-path winners and UEL Q3 champions-path losers |
| PO | Main | 6th of 1–5 (England: the EFL Cup winners), Q3 main winners, and UEL Q3 main losers |
| Q3 | Champions | Q2 champions-path winners |
| Q3 | Main | Q2 main winners and UEL Q2 losers |
| Q2 | Champions | UCL Q1 losers |
| Q2 | Main | cup winners 33–43, runners-up 16–32, 3rd of 13–28, 4th of 7–15, 5th of 6, Q1 winners, and UEL Q1 losers |
| Q1 | Main | cup winners 44–54, runners-up 33–54 (not Liechtenstein), 3rd of 29–49 (not Liechtenstein) |

These are UEFA's 2026-27 numbers, with Russia's suspension already absorbed: the Ukrainian champions in UCL Q2 and the Danish cup winners in UEL Q2, as UEFA moved them. The counts: UCL Q1 30 → Q2 24 → Q3 12 + 8 → PO 10 + 4 → 5 + 2. UEL Q1 16 → Q2 16 → Q3 12 + 14 → PO 24 → 12. UECL Q1 52 → Q2 88 main + 15 champions (one bye) → Q3 52 + 8 → PO 38 + 10 → 19 + 5, and 12 more from the UEL play-off. **Checked:** every round's count adds up, and the 2026-27 UEL adjustments rebuild exactly from the reconstructed defaults.

**Filling places:**
- **Domestic places** pass down the table as now: a club with two places takes the higher one, and the other goes to the next club not yet in Europe.
- **Title holders (UEFA 2024+, by club coefficient):** if the UCL holders already qualify through their league, their place goes to the highest-coefficient champion anywhere in the champions-path qualifying.
  - The UEL holders' place works the same way, from the league path.
  - The UECL holders' UEL place is filled from the UEL qualifying.
- **Re-balancing:** a vacancy in a round is filled by the best-coefficient direct entrant from the rounds below, in the same path. Then each round's size is worked out bottom-up from its entrants, the winners coming up and the losers dropping in.
  - A round with an odd number of clubs gives its top-coefficient club a bye, as UEFA does when it has to.
  - Each league phase is then topped up to exactly 36 by promoting the best direct entrant from the play-off.
  - The process is deterministic, and repeats until it is stable.

## The qualifying rounds (A4)
- **Rounds are numbered** −3 (Q1), −2 (Q2), −1 (Q3) and 0 (PO), with the league phase at 1–8 and the knockouts at 100 and up. A tie's path is in `cup_tie.path`.
- **Each round is drawn once every round that feeds it is decided:** its own competition's previous round, plus any drop-in rounds. The dates come from the UEFA calendar:

  | Round | UCL | UEL and UECL |
  |---|---|---|
  | Q1 | 7–8 and 14–15 July | 9 and 16 July |
  | Q2 | 21–22 and 28–29 July | 23 and 30 July |
  | Q3 | 4–5 and 11 August | 6 and 13 August |
  | PO | 18–19 and 25–26 August | 20 and 27 August |

  Q1 is drawn on 1 July, at the season start, and the league phases on 28 August, as now.
- **Draws:**
  - **Seeding:** the top half by club coefficient is seeded against the unseeded half.
  - **Pairing constraints:** clubs from the same country can't meet, and neither can prohibited pairs (Armenia–Azerbaijan, Gibraltar–Spain, Kosovo–Bosnia, Kosovo–Serbia, Ukraine–Belarus; in `europe/settings.yaml`). The pairing is a matching with these constraints.
  - **Home leg:** the unseeded club is at home first.
- **Money:** each qualifying round reached pays a small amount (in finance.yaml), and each tie won earns coefficient points.
- **Room:** domestic matches are moved around qualifying ties by the existing `make_room`. Domestic seasons mostly start in August, so July ties rarely clash.
- **News:** the user's draws and results, and when their club drops into another competition.
- **The Europe page (Sonnet):** qualifying by round and path, entrants with how they got in (league place, cup, title holder, EPS, or dropped from the UCL Q2…), and the country ranking.

## The leagues (A5–A6)
- **36 more associations get their top division and cup:**
  - **From Transfermarkt:** GRE, CZE, UKR, CRO, SRB.
  - **Partly from FC 27:** CYP, HUN, BUL, AZE.
  - **Generated:** ISR, SVK, SVN, KAZ, MDA, BIH, MKD, ALB, KOS, MNE, GEO, ARM, BLR, LTU, LVA, EST, FIN, ISL, FRO, NIR, WAL, LUX, MLT, GIB, AND, SMR.
  - **Cup only:** LIE.
- **Config, as for the eight leagues of v1.61:**
  - a competition, a calendar and a cup for each;
  - league income from the league's mean wage bill;
  - cup prizes;
  - nation codes and names (backend `nations.yaml` and frontend `format.ts`).
- **Seasons:** spring-to-autumn leagues play August to May, like the rest, and split leagues play a plain round robin.
- **World build:** `footsim build-world` gains three steps:
  - a Transfermarkt league import;
  - partial squads from the qualifying lineups;
  - generated clubs and players.
  It is deterministic for a world seed.
  - **New careers** get everything. **Existing saves** don't have the new clubs, so they keep W6 behaviour with only the countries they have. An importer for old saves is out of scope.
  - **The base world is rebuilt on the Mac.** The user then copies it to Cardinal once, as `deploy/README.md` says.
- **Liechtenstein:**
  - **The cup:** FC Vaduz (in the Swiss league) plus 6 generated amateur clubs.
  - **Eligibility:** Vaduz is a Liechtenstein club, so it can't take Swiss places.
  - A club takes a country's league places only if it belongs to that country; Welsh clubs in the English pyramid stay eligible for England, as in real life.
- **Performance:** about 400 more clubs. The A7 check measures a season's simulation time and the market's cost with them. If either grows by more than about half, small leagues get a lighter level (for example, players outside the top N associations leave the AI market's buyer pool).

## The league picker (A1, Sonnet)
- **API:** competitions gain `confederation` and `country_rank`. UEFA countries are ordered by their coefficient ranking; other confederations come after, ordered by their clubs' reputation.
- **The picker:**
  - **always visible:** the user's own country and the big five, as quick buttons;
  - **"All countries":** a searchable list by country or league name, accents ignored, grouped by continent and in ranking order within each group;
  - **a continent filter** (Europe / Asia / North America / South America / Africa / Oceania), shown only for continents the game has;
  - then the league within the country, as now.
- **Used by** the League and Cups pages, the start page's club picker and the transfer search. Phone layout as in M2.

## Checkpoints (each one: tests, full suite, reviewer, progress.md, commit, push)
| # | What | Who |
|---|---|---|
| A1 | League picker and its API fields | Sonnet (UI), main (API) |
| A2 | Country coefficients (UEFA points, seeds, ranking, club floor), schema v19, API, Rankings tab | main; Sonnet for the tab |
| A3 | Access list by ranking, EPS, holders' rules, re-balancing; fixed list retired | main (Max) |
| A4 | The qualifying rounds, paths, drop-downs, draws with constraints, calendar, money, news; Europe page qualifying view | main (Max); Sonnet for the page |
| A5 | League facts and club lists for 36 associations (web research, sourced YAML) | research agents |
| A6 | World build: TM leagues, qualifying-lineup squads, Elo, rating models, generated squads, name pools, Liechtenstein; configs | main, with Sonnet for configs |
| A6b | (Optional) real names from Wikipedia squads for generated clubs | research agents |
| A7 | Measurement: `europe-report` over 3+ seasons (round sizes, flows, coefficient evolution, places per country, small-country champions' runs); performance with all leagues | main |
| A8 | Help, What's new, e2e on :8765 | main |

A1 and A5 start at once, alongside A2–A4.

## Out of scope for now
- The UEFA Super Cup.
- Winter and travel restrictions in draws.
- Russia.
- Real club coefficients as seeds (reputation plus the 20% floor stand in).
- Leagues outside UEFA (the picker is ready for them).
- An importer for old saves.

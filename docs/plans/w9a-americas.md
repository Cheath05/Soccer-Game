# W9a: the Americas. MLS, Liga MX, Argentina and Brazil, their formats, cups and MLS's roster rules

**Asked for by the user on 16 Nov 2026:** "add and implement the Americas leagues and systems (MLS, etc)". Their choices:
- **Leagues:** the big four with real squads: MLS, Liga MX, Argentina's Liga Profesional and Brazil's Série A. The other CONMEBOL countries' clubs stay outside any league for now.
- **Season dates:** autumn to spring, inside the game's shared July–June season. For MLS this is real from 2027-28: it switches to a fall-to-spring calendar (July to May, with a winter break from mid-December to early February), after a 14-game "Sprint Season" in spring 2027. The game's 2026-27 MLS season plays the 2027-28 shape a year early.
- **Continental competitions** (the Concacaf Champions Cup, the Libertadores, the Sudamericana, the Leagues Cup) come in the next round (W9b), reusing W6/W7's machinery.
- **MLS's rules in full**, including the SuperDraft.

This is roadmap item W9's first part, with W2c's formats (conferences, zones, Apertura and Clausura) that it needs.

## What exists
- **Leagues:** round robins of 1–4 legs; promotion, relegation and play-offs keyed on league rank (`defs/competitions.py`, `world/season.py`); single or two-legged play-off ties with extra time and penalties.
- **Cups:** knockout rounds with byes, legs, neutral grounds and entry by league rank (`defs/cups.py`, `world/cups.py`).
- **Clubs:** FC 27 has MLS (30 clubs), Liga MX (18) and the LPF (30), all in the base world outside any league, so `ensure_leagues` gives them to a career at its next season. Brazil has Bahia (FC 27's "Liga do Brasil") and Botafogo (under "CONMEBOL Sudamericana"); Transfermarkt has the whole Série A (706 players with values), so Brazil goes through W7's `importers/synthetic.py` and needs a world rebuild (a new career).
- **Money** is kept in euros; currencies are display only.

## The formats (researched 16 Nov 2026)
| League | Clubs | Season | Play-offs and titles | Down |
|---|---|---|---|---|
| **MLS** | 30, East and West conferences of 15 | 34 matches: each conference opponent twice (28) and 6 from the other conference once | **MLS Cup Playoffs:** seeds 1–7 of each conference straight into Round One, 8 v 9 a Wild Card match (no extra time, penalties); **Round One best of three** (1 v WC, 2 v 7, 3 v 6, 4 v 5; the higher seed hosts games 1 and 3; every game goes to penalties after 90 minutes); conference semi-finals and finals single matches at the higher seed with extra time; **MLS Cup** at the finalist higher in the Supporters' Shield table. The **Supporters' Shield** goes to the best regular season. | none |
| **Liga MX** | 18 | **Apertura** (July–Dec) and **Clausura** (Jan–May), each a single round robin of 17 (the Clausura with venues reversed) | Each tournament: the top 8 go to the **Liguilla** (no play-in since the Clausura 2026). Quarter-finals 1 v 8, 2 v 7, 3 v 6, 4 v 5; semi-finals reseeded, best v worst; all two legs, the higher seed hosting the second; **a level aggregate goes to the better-placed club** (no extra time or penalties) until the final, which has extra time and penalties. Two champions a season. | suspended |
| **Argentina (LPF)** | 30, zones A and B of 15 | **Apertura** and **Clausura**, each: a single round robin within the zone (14), plus two interzonal matches: the club's rival from the other zone and one drawn | Each tournament: the top 8 of each zone to a single-match knockout (round of 16 crossing the zones, A1 v B8 … A8 v B1), higher seed at home, level after 90 minutes → penalties; final at a neutral ground with extra time. The **annual table** (both tournaments' zone stages) crowns the "Campeón de Liga". | last in the annual table and the worst average (the Primera Nacional isn't in the data: nobody moves) |
| **Brasileirão** | 20 | Double round robin, 38 rounds | The table's winner | 4 (Série B isn't in the data: nobody moves) |

Tiebreakers: MLS wins, goal difference, goals for, intraconference head-to-head (points, goal difference), away goals, drawing of lots (disciplinary points aren't kept). Liga MX points, goal difference, goals for, head-to-head. Argentina points, goal difference, goals for, head-to-head. Brazil wins, goal difference, goals for, head-to-head.

Argentina's league approved a single table without zones for 2027 (late October 2026 reports), but its details aren't settled; the game plays the 2026 format, the last one confirmed.

**The cups:**
- **U.S. Open Cup:** 16 MLS clubs from the round of 32 (in 2026 those not in the Leagues Cup or the Champions Cup, ranked by the Supporters' Shield). Without the Leagues Cup, the game enters the 16 lowest-placed **US** MLS clubs of last season, single matches with extra time and penalties, the final at the higher-placed club.
- **Canadian Championship:** the three Canadian MLS clubs (the CPL isn't in the data): a two-legged semi-final (the best-placed has a bye), then the final.
- **Copa Argentina:** the 30 LPF clubs (the lower divisions aren't in the data), single matches at neutral grounds, level → penalties.
- **Copa do Brasil:** the 20 Série A clubs enter at the fifth phase (with 12 lower-division clubs who aren't in the data: so 4 ties and 12 byes); two legs through the semi-finals, a single final at a neutral ground; level → penalties.
- Liga MX has no cup (the Copa MX ended in 2020).

## MLS's roster rules (2026 figures, MLS Roster Rules and Regulations, 3 Feb 2026)
Money in USD, converted at `currencies.USD.per_euro`. All figures go in `data/config/rules/mls.yaml`.
- **Salary budget** $6,425,000 for the Senior Roster (slots 1–20). **Maximum budget charge** $803,125 for one player. Senior minimum $113,400, reserve minimum $88,025. An empty senior slot below 18 is charged the senior minimum.
- **Roster:** 30 players: 20 senior (counted against the budget) and 10 supplemental (21–24 senior minimum, Generation adidas and Homegrown; 25–30 reserve minimum, 24 or younger).
- **Designated Players:** up to 3 (Model 1) or 2 (Model 2). Charge $803,125, or $150,000 at 20 or younger and $200,000 at 21–23; a DP signed after the secondary window opens is charged half. A club with two DPs pays $150,000 to the league for a third (waived for a young DP).
- **U22 Initiative:** 3 (Model 1) or 4 (Model 2) players aged 22 or younger when signed, eligible to 25; charge $150,000 (20 or younger) or $200,000.
- **TAM:** $2,125,000 a season (2027: $2,025,000), not tradeable, for players paid between $803,125 and $1,803,125, bought down to as little as $150,000.
- **GAM:** $3,280,000 a season, plus $2,000,000 under Model 2; tradeable, never expires (Model 2's does). Buys a charge down by up to half (floor $150,000). Earned by selling players outside MLS (up to $3,000,000 a season; the rest is cash), and by missing the play-offs.
- **International slots:** 8 per club, tradeable. US clubs: Americans are domestic. Canadian clubs: Americans and Canadians are domestic (at least three Canadians). Homegrown players are domestic.
- **Homegrown players:** from the academy, any number, senior or supplemental.
- **SuperDraft:** 3 rounds in January; order is the reverse of the standings, adjusted for the play-offs; college players (generated). Generation adidas players sit on the supplemental roster for up to three years.
- **Trades:** MLS clubs move players to each other for GAM (or cash, at least $50,000, converted to GAM for the seller); transfer fees from outside MLS: 95% to the club.

**How the game models them:**
- Every player at an MLS club has a **roster designation**: senior, supplemental, DP, U22, homegrown or Generation adidas. **Budget charges** follow from the wage (yearly) and the designation. **TAM, then GAM, buy down** the charges of the players paid above the maximum, as a club would.
- **Compliance:** a club is compliant when its senior charges after buy-downs fit the budget, its rosters fit their slots, and its internationals fit its slots. The user's moves are refused with the rule that blocks them, and the roster page shows where the club stands. AI clubs choose designations and stay compliant.
- **Moves between MLS clubs are trades for GAM;** moves out of MLS pay a fee, part of it as GAM.
- **The SuperDraft** runs in January on the user's say (they pick when on the clock, or let it auto-pick); the AI drafts by need and potential.
- **Not modelled (follow-ups):** Discovery and allocation rankings, the Re-Entry Draft, free agency, the player's percentage, off-roster Homegrown call-ups, loans to MLS NEXT Pro, Special Discovery amortisation, the mid-season roster-model switch.

## Checkpoints
Each is its own commit with progress.md, the changelog (for what a player sees), lint, tests, and the engine-reviewer's read.
1. **B1, formats:** conferences and zones (group tables, cross-group matches, rivals), Apertura and Clausura (phases, each with its own table, play-offs and champion; the annual table), play-off series (best of N), the higher seed going through on a level aggregate, reseeded picks, play-offs that crown the champion, a `league_title` table for titles (schema v22) and honours from it. Unit tests per format, plus a whole season of a test league of each kind.
2. **B2, the four leagues:** nations, calendars, league, cup and finance files; Brazil in `new_clubs.yaml`; cup entry by club nation; wage levels; the world rebuild; the whole-season test with every league.
3. **B3, MLS rules, the model:** `rules/mls.yaml`, roster designations and allocation money (schema v23), budget charges and buy-downs, compliance, the starting wages and designations of MLS squads.
4. **B4, MLS rules in the market:** the user's and the AI's signings, sales, loans and renewals checked against the rules; trades for GAM; the season's allocations; AI compliance.
5. **B5, the SuperDraft and Homegrown players.**
6. **B6, the screens:** conference and zone tables, Apertura/Clausura and annual tables, the play-off brackets and series, the MLS roster page, the draft, the continent filter, help, What's new and e2e on :8765.

## Sources
- MLS 2026 Competition Guidelines and Roster Rules and Regulations (mlssoccer.com, as of 3 Feb 2026); MLS's 2027 Sprint Season and 2027-28 calendar announcements.
- Liga MX: the end of the play-in (Clausura 2026); the Liguilla's tiebreak on table position.
- 2026 Argentine Primera División and Copa Argentina (Wikipedia, AFA reports); the 2027 format reports of late October 2026.
- 2026 Campeonato Brasileiro Série A and Copa do Brasil 2026 (Wikipedia, CBF reports).
- 2026 U.S. Open Cup (U.S. Soccer, Dec 2025).

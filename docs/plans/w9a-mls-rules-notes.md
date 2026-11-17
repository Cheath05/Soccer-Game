# W9a B3-B4: MLS's roster rules, notes

The model and the market of MLS's roster rules (docs/plans/w9a-americas.md, "MLS's roster rules"). The figures are MLS's 2026 Roster Rules and Regulations, in `data/config/rules/mls.yaml` (dollars a year, converted at `finance.yaml` `currencies.USD.per_euro`; the game keeps euro cents).

## Where it lives
- `data/config/rules/mls.yaml`, validated by `defs/mls.py` (`MlsRulesDef`, `GameDefinitions.mls`).
- `world/mls.py`: the rules and the model.
  - Pure, no database: `Figures` (the rules in euro cents), `Member`, `ClubRules`, `base_charge`, `buy_downs`, `assess` (a `Report` with charges, budget used and left, TAM and GAM used, slot counts and `Problem`s), `choose_designations` (the AI's), `place_newcomer` (the user's newcomers), `not_allowed`, `tiers_fit`, `new_problems`.
  - The save: `mls_club_ids`, `club_report` (an AI club's designations chosen afresh, the user's as stored), `save_report`, `sync_clubs` (after any change), `start_mls` (career start, or the first season a save has MLS), `new_mls_season` (the rollover's allocations), `mls_month` (the 1st of each month), `fix_club` (AI compliance), `charge_dp_fees`, and the user's `set_designation`, `set_roster_model`, `buy_international_slot`.
- `world/mls_market.py`: the market's side: `addition_problem` (a signing or loan into an MLS club), `wage_problem` (a renewal), `fee_split` and `apply_fee_gam` (trades for GAM, sales out of MLS), `filter_renewals` (AI renewals).
- Hooks: `world/transfers.py` (`validate_move`, `complete_move`), `world/loans.py`, `world/renewals.py` (`renew`, `settle_expiring`), `world/market.py` (MLS clubs' wage floor, bids for the user's players), `world/season.py` (`after_day` on the 1st, `rollover`), `world/career.py` (`initialize_career`).
- `api/mls.py`: the roster page's endpoints.

## Schema v23 (`_to_v23`, idempotent: `metadata.create_all`)
- `mls_club_season` (club, season): `roster_model`, `gam_cents` and `gam_expiring_cents` (Model 2's), `gam_committed_cents` (what this season's buy-downs take; spent at the rollover), `tam_cents`, `international_slots`, `gam_from_sales_cents` (toward the $3M cap), `dp_fee_paid`.
- `mls_roster` (season, player): `club_id`, `designation` (senior, supplemental, dp, u22, homegrown, generation_adidas), `slot` (senior or supplemental).
- `mls_player` (player): `homegrown_club_id`, `green_card`, `ga_until_season` (Generation adidas through that season), `since_season` (his first MLS season).
- `mls_rights` (player, kind): a club's rights to an unsigned player (`draft`, `homegrown`, `discovery`), won in a season, held until one. Empty until B5.
- `mls_gam`: every GAM change (allocation, model, trade, sale, slot, spent, expired), with the transfer or the other club as `ref_id`.

The NCAA agent uses v24; the main session renumbers on merge.

## How the rules are modelled
- **Who is MLS:** members of `USA1` this season; before a save has `USA1`, the clubs whose `source_league` is `MLS`. A club plays under the rules once it has an `mls_club_season` row for the season. A club's country comes from `club.nation_id`, plus `canadian_clubs` in the YAML (Toronto FC, CF Montréal, Whitecaps FC) until the world's club nations say so.
- **The roster:** the club's players of contract age, including those it has lent out (they keep their slots and are charged what the club still pays), plus those it has borrowed (charged the share it pays). Academy players below the contract age are off the roster.
- **Charges:** a senior player's charge is his yearly wage; a DP's is $803,125, $200,000 at 21-23 or $150,000 at 20 or younger, halved when he joined after the secondary window opened (the second transfer window of his club's calendar), never more than his wage; a U22 Initiative player's is $150,000 at 20 or younger, else $200,000. The Supplemental Roster isn't charged. Each empty senior slot below 18 costs the senior minimum.
- **Buy-downs, as a club would:** first, each non-DP senior paid above the maximum comes down to it, with TAM if he's paid up to $1,803,125, then GAM (at most half his charge, never below $150,000); a player GAM can't bring to the maximum must be a DP. Then, while the club is over the budget, TAM buys TAM-eligible players down to $150,000, then GAM buys the dearest charges down by up to half. Only what's needed is spent. GAM spent is worked out from the roster at each change and charged at the season's end (`gam_committed_cents`).
- **Compliance:** the budget after allocation money; 20 senior and 10 supplemental slots, the supplemental tiers (slots 21-24: senior minimum, Generation adidas, Homegrown; 25-30: 24 or younger on the reserve minimum); DPs and U22 players by roster model (3 and 3, or 2 and 4); internationals within the club's slots; MLS's minimums (senior roster $113,400, supplemental $88,025); a Canadian club's three Canadians; each designation's eligibility (a U22 player signed at 22 or younger, under 26, paid at most the maximum charge).
- **Domestic players:** Americans at US clubs, Americans and Canadians at Canadian clubs, Homegrown players, and green-card holders.
- **The roster model:** the AI picks Model 1 unless its third-best player is below 70 overall. The user may change it until their club's first league match of the season. Model 2's $2M of GAM is kept apart and expires with the season.
- **The third DP's fee:** $150,000 to the league (a ledger `adjustment`), once a season, unless one of the club's DPs is a young DP (23 or younger).

## The starting squads
Done at career start (`initialize_career`, before finances are worked out from the wages), or for a save under way on the first 1st of a month after the upgrade (`mls_month`), or at the first rollover with `USA1`. **No world rebuild is needed.** A new career is the clean way: an existing career takes the rules up mid-season, with its wages changed then.
For each club, deterministically:
1. A roster above 30 releases its weakest (a young player counting half his remaining potential; three keepers kept).
2. Model 1 or 2 from its third-best player.
3. Green cards for the internationals beyond 8, the oldest first (FC 27 doesn't know who holds one: Inter Miami had 16 internationals). Domestic players 22 or younger are Homegrown (`start.homegrown_max_age`).
4. The best players (3 or 2) get DP wages: $5M at 80 overall, times 1.24 a point, at least $1.2M, never less than they earn (Messi about $18M, Son and Lewandowski about $7.7M, De Paul and Griezmann about $11.8M).
5. The depth beyond 20 goes on the minimum, chosen so it fits the supplemental tiers.
6. Every other wage is cut by one factor, the largest that leaves the club compliant with $250,000 of the budget free and 25% of its GAM unspent.
7. `fix_club` releases whatever still doesn't fit (senior slots, mostly). Rosters end at 23-30 players. At the career's start these releases are part of building the world (no transfer history, as `trim_squads`); later ones are recorded as releases.
8. A third DP's fee is charged once the clubs have finances, and those clubs' budgets are planned again from the cash left.

Effect: MLS's non-DP wages fall a lot (FC 27's MLS wages are flat: Columbus paid about $15M outside its top three; it now pays about $4M), so MLS clubs' own income (derived from their wage bills) and budgets fall too.

## The market
- **The user's moves** into an MLS club (a transfer, a free agent, a loan in), and their renewals, are refused with the rule: "No international slot free.", "All 3 Designated Player slots are full.", "Over the salary budget by $612K after allocation money." (amounts in the user's currency). The newcomer takes the cheapest place that complies (supplemental, senior, U22, then DP). A club that isn't compliant can't add anyone until it is, unless the move itself makes it compliant; matches are never blocked.
- **AI MLS clubs** check the same rules on every signing, loan and renewal, choosing all their designations afresh and keeping 25% of their GAM out of buy-downs (for trades). Their wages are at least the senior minimum. They bid for the user's players only if they could take them.
- **Trades between MLS clubs** are paid in GAM: the buyer's GAM first, any rest in cash (at least $50,000), and the seller gets all of it as GAM. No cash reaches the seller.
- **Sales out of MLS:** the club gets 95% of the fee, as GAM up to $3M a season (`gam_from_sales_cents`), the rest in cash; its budget gets back `reinvest` of the cash only.
- **The season's allocations** at the rollover: GAM carried in (less last season's buy-downs, Model 2's expiring GAM gone), plus $3,280,000 (and Model 2's $2M); TAM $2,125,000 for a season starting in 2026, $2,025,000 from 2027; slots back to 8; green cards after 4 MLS seasons.
- **Compliance:** AI clubs fix themselves at the season's start and on the 1st of each month (designations afresh, minimum wages, an international slot bought from the club with most to spare at $175,000 of GAM, then releases); the user's club gets news at the season's start and is blocked from adding players.
- **Homegrown:** youth intake players at MLS clubs are Homegrown there (they had a youth contract with the club), so domestic, and eligible for the Supplemental Roster.
- **Clubs outside MLS** are untouched: their moves' money is the fee both ways, and nothing is checked. But MLS's lower wages, budgets and releases at the start change who the AI market buys, so a career's non-MLS outcomes differ from before this change (expected; not measured). One test showed it: in `test_finance.py`'s season (seed 5) Zimbru Chișinău now has five months whose money comes to exactly nothing, which post no ledger row; the test now allows that. `test_market.py`'s fee invariant now leaves MLS's GAM moves to `test_mls_season.py`.

## The API (`api/mls.py`)
- `GET /api/mls/roster?club_id=` (the user's club by default; 404 for a club not under the rules):
  `{club {id, name}, yours, season_id, roster_model, model_choosable, usd_per_euro, budget_eur, budget_used_eur, budget_left_eur, max_charge_eur, empty_senior_slots_charged, allocation {tam_eur, tam_used_eur, tam_left_eur, gam_eur, gam_expiring_eur, gam_used_eur, gam_left_eur}, slots {senior, senior_slots, supplemental, supplemental_slots, designated_players, designated_slots, u22, u22_slots, internationals, international_slots}, compliant, problems [text], adding_blocked, players [{id, name, age, position, overall, salary_eur, designation, roster, international, canadian, homegrown, generation_adidas, loan ("in" | "out" | null), charge {base_eur, tam_eur, gam_eur, charge_eur}, options ["designation:roster"]}]}`.
  Euros a year; the client shows them in the user's currency (`usd_per_euro` for MLS's own dollar figures).
- `PUT /api/mls/designation` `{player_id, designation, roster?}`: dp, u22, senior (for a player paid above the maximum, that's a TAM buy-down instead of a DP slot), homegrown (with `roster` senior or supplemental), supplemental, generation_adidas. Returns the roster; 409 with the rule that blocks it ("All 3 Designated Player slots are full.").
- `PUT /api/mls/roster-model` `{model}`: 1 or 2, before the club's first league match. 409 otherwise, or when the club wouldn't comply.
- `POST /api/mls/international-slot` `{from_club_id}`: buy a slot for the season from an MLS club with more than one to spare, for $175,000 of GAM.

## What's simplified
- Buy-down amounts are the game's choice (the least needed, TAM before GAM), not the user's; the user's choice is a player's designation.
- GAM can't buy a DP's charge down (to free a DP slot), and allocation money can't pay transfer fees.
- A trade's cash part is the buyer's choice in real life; here it's the rest beyond its GAM. Trades of players for players, and of draft picks, aren't modelled.
- International slots are traded for the season only, and only the AI sells them.
- Loans: a lent player keeps his slot at his club, charged what it still pays; a borrowed player is charged the borrower's share. MLS NEXT Pro loans aren't modelled.
- Green cards come after 4 seasons on MLS rosters, and at the start for internationals beyond the slots (oldest first).
- Homegrown at the start: domestic players 22 or younger (FC 27 has no academy history).
- The supplemental Homegrown wage limit is the game's ($250,000), standing in for MLS's Homegrown subsidies.
- U22 eligibility uses his age when his current contract began.
- The GAM for missing the play-offs is in the YAML at 0: MLS doesn't publish an amount (an open question).
- The AI's GAM reserve (25%), slot price ($175,000), DP wage curve, and start headroom are the game's numbers, in the YAML.
- `end_loans` doesn't re-sync the clubs at once; the next 1st of the month does.

## Follow-ups
- **B5:** the SuperDraft (3 rounds in January, reverse standings adjusted for the play-offs) into `mls_rights` (draft) and Generation adidas (`mls_player.ga_until_season`, the Supplemental Roster for up to three years; `GA` is already a designation, charged nothing, always supplemental). Homegrown rights for academy players (`mls_rights` kind homegrown).
- Discovery and allocation rankings, the Re-Entry Draft, MLS free agency (the player's percentage), off-roster Homegrown call-ups, loans to MLS NEXT Pro, Special Discovery amortisation, the mid-season roster-model switch, player-for-player trades, the user selling international slots.
- B6: the roster page in the client.
- Canada: once club nations are fixed (the other agent), drop `canadian_clubs` from the YAML.

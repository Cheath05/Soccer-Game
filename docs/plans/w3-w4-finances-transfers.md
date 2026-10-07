# W3 finances and W4 transfers: the design

**Approved order:**
1. W3, finances;
2. W4, transfers;
3. the user's play-test.

**Written 7 Oct** from three read-only explorations of the code (schema and persistence, the world loop, the API, frontend and tests) and the user's decisions:
- **Currency:** stored in euros, shown in the user's choice of currency (a display setting).
- **Bids for the user's players** stop sim-to-date.
- **W3** includes a basic board: an expectation and a confidence, shown only.
- **W4** includes free agents, expiring contracts and loans, in their simplest safe forms.

Installments, add-ons, sell-ons, buy-backs, agents, persisted multi-day haggling, work permits and quotas (design §15) come later.

## What exists, and what it means

| Area | Today | For W3/W4 |
|---|---|---|
| Contracts | `contract(person_id, club_id, kind, start_date, end_date, wage_weekly_cents, release_clause_cents, is_active)`; one row per player at build; a youth contract for intakes | Wages and dates exist. One active contract per player is assumed by about a dozen queries (`_SQUAD_SQL`, `_PLAYER_SQL`, `lifecycle._players`, `record_result`, …) but not enforced |
| Wages | Set once at build: `WageLevel.wage_for(overall)` by league (`wage_levels.yaml`, EUR/week), then never move | Wage bills give believable club sizes: Premier League €99.5m a year on average, Bundesliga €60m, Championship €17m, League Two €2.4m |
| Values | `player.value_eur_cents`, Transfermarkt's, static (69% of players); else `transfers/valuation.estimate_value_eur` (hand-set) | W4 fits a model on those values and uses it for everyone, every day |
| Club money | None. The club page guesses a budget (`queries.BUDGET_SHARE_*`) | W3 replaces the guess |
| Contract end | `season._renew_contracts` extends every expiring contract 1–3 years at the same wage | W4 replaces it with renewal decisions and free agency |
| Free agents | Players with no active contract (released, trimmed); half leave the game each season | W4 lets clubs sign them |
| Windows | `SeasonCalendarDef.transfer_windows`: only England's calendar sets it, and nothing reads it. England's summer window opens 15 June, before the 1 July rollover | W4 adds every country's, and checks the next season's calendar too |
| Squads | Read live from active contracts (no caches); `LineupPicker.pick` skips missing ids | A move takes effect at the next match |
| Transactions | `session.write()` and every sim step are one SQLite transaction (lock, `engine.begin()`); foreign keys on; no savepoints | Validate first, then write: a failure rolls back the whole step |

## W3: finances

### State, and who owns it

- **`club_finance`**, one row per club:
  - `balance_cents`: the cash, the source of truth;
  - `club_income_cents`: the club's own annual income (commercial and matchday);
  - `transfer_budget_cents` and `wage_budget_cents` (weekly);
  - `budget_season_id`;
  - the board's `board_target` (a league position) and `board_confidence` (0–100).
- **`finance_ledger`**, append-only: `(id, club_id, date, season_id, kind, amount_cents, ref_id)`.
  - `kind` is opening, broadcast, club_income, wages, operating, month (an AI club's net month, one row), prize, parachute, transfer, or adjustment. The user's club gets its month itemised; every other club gets one `month` row.
  - **Invariant:** a club's balance is always the sum of its ledger. The opening balance is a ledger row, and every balance change writes its row in the same statement group.
- **The wage bill is never stored:** it's always the sum of the active contracts.

### The money model (`data/config/finance/finance.yaml`)

- **League income per club per season,** by competition key: an equal share (`base`) plus merit (`merit` for the champion, falling linearly to nothing for last). These are approximate round figures, documented as such.
- **Club income** (commercial and matchday) is derived once, when finances are created: `max(club_income_floor × expected league income, wage_bill_year / wage_ratio_start − expected league income)`. A club's real size is already in its wage bill, which comes from its players. It's fixed afterwards; reputation-driven growth is later.
- **Revenue** = league income (by the club's league that season) + club income. Clubs outside the played leagues have club income only.
- **Monthly, on the 1st** (`after_day`, beside development; one query per kind, not per club):
  - + revenue / 12;
  - − the wage bill × 52 / 12;
  - − `operating_costs` × revenue / 12 (staff, facilities, matchday costs).
- **At a league's end** (`_finalize_league`), merit is paid by final position.
- **Promotion and relegation:** next season's revenue follows the new league. A relegated club gets a one-off `parachute` share of the income it lost.
- **Budgets at each season's start,** after rollover's movements, turnover and renewals:
  - wage budget = revenue × `wage_budget_ratio` / 52;
  - transfer budget = revenue × `budget_share` + max(0, balance) × `cash_share`;
  - nothing if the balance is negative.

  In W4, a purchase takes its fee from both the balance and the transfer budget, and a sale adds the fee to the balance and `reinvest` × fee to the budget.
- **The board (basic, display only):**
  - its target is the club's rank by squad strength within its league at the season's start;
  - its confidence starts at 60 and moves monthly with position against target.

  No sackings yet.
- **The user's sandbox:** a new career can set its club's starting transfer budget, up to €10bn.

### W3 checkpoints

1. **W3-1: foundation.**
   - Schema v10 (`club_finance`, `finance_ledger`), `finance.yaml` and `defs/finance.py`.
   - `world/finance.py`: `initialize_finances` at career start and in `_to_v10` for saves already under way.
   - Budgets for the season.
   - **Tests:** plausible ordering (elite > mid > promoted > lower league); balance = Σ ledger; the migration; determinism (no randomness).
2. **W3-2: the money moves.**
   - Monthly settlement, merit, parachutes, budgets at rollover, the board.
   - **Tests:**
     - a season of a watch-only career keeps every balance equal to its ledger;
     - promoted clubs' revenue rises and relegated clubs' falls;
     - no balance explodes or collapses (bounds per league).
3. **W3-3: what the user sees.**
   - `GET /api/finances` (own club: balance, budgets, wage bill, income and expenses this season by kind, recent ledger, board).
   - The club overview shows other clubs' real figures, rounded.
   - A Finances page, a dashboard card, and the currency display setting.
   - The sandbox budget at career start.
   - **Tests:** the API, plus the e2e smoke run.

### What W3 leaves for W4 to absorb

From the W3-2 review, which put `finance.yaml` against the base world's wage bills. Each season a typical club nets about +20% of its revenue. W4's market is the sink.

- **Relegated big clubs bleed.**
  - A Premier League club with a €56–92m bill loses €27–39m a season in the Championship. Its parachute is €36m, once.
  - W4 must react:
    - the wage budget drives shedding: sales, and letting contracts run down;
    - no transfer budget while in debt (`set_budgets` does this already);
    - possibly an owner injection (ledger kind `adjustment`) as a last resort.
- **Promoted clubs get a windfall,** because their wages don't rise. A promoted Championship club with a €10–28m bill nets about +€61–67m a year in the Premier League. Yo-yo clubs keep accumulating. W4's buying and the higher wages its signings demand must spend that.
- **Clubs outside the 19 leagues** (302 in the base world) net +20% of their own revenue a year. The AI market must include them as buyers and sellers, or their cash just piles up.
- **The board's target** is set on 1 July. Decide whether a window's transfers refresh it.

### W3-4: simpler money (the user's requests, 8 Oct)

The user asked for:
- one budget for fees and wages;
- dollars by default;
- recurring money shown once, as the month's profit, rather than as repeated transactions;
- an optional board.

**Decided 8 Oct (Opus):**

- **One budget** (`club_finance.transfer_budget_cents`, called "budget" everywhere it's shown) is the money a club may commit this season to transfer fees and new wages.
  - A signing costs **its fee + its weekly wage × the weeks left in the season**.
  - A sale gives back `reinvest` × the fee, plus the wage the club no longer pays for the rest of the season.
  - A release gives back nothing (no severance yet, and no free money from dumping wages).
  - The players already under contract are paid from income, so they aren't charged to the budget.
  - `validate_move` refuses a signing whose cost is beyond the budget. The separate weekly wage-budget limit goes.
- **Wage capacity** (`club_finance.wage_budget_cents`, weekly) = revenue × `wage_budget_ratio` ÷ 52: the wage bill the club's income supports.
  - It's shown ("wages €Y a week, your income supports €Z") and used by the AI's own prudence, but it isn't a hard rule.
  - Going over it costs next season's budget instead (below).
- **Each season's budget, at the rollover:**
  - **Board on** (every AI club, and the user unless they turn the board off): `budget_share` × revenue + `cash_share` × max(0, balance) − the wage overshoot. The overshoot is max(0, wage bill × 52 − capacity × 52): what the club already pays beyond its means comes out of the budget first.
  - **Board off** (the user's choice): the budget is all of the club's cash, max(0, balance).
  - Monthly profits go to the balance, and reach the budget at the next season's start.
- **The sandbox:** a new career's budget of X (up to $/€10bn) is X to spend on fees and wages. The owner puts in whatever cash the balance lacks.
- **The board is optional** (`board_enabled` in the career's meta, chosen at career start and switchable on the Finances page).
  - When it's off, there are no expectations, no confidence and (later) no sacking, and the budget is the club's cash.
  - Switching it recomputes the user's budget at once.
  - AI clubs always have one.
- **Dollars by default:** the display currency defaults to $ (money is still kept in euros).
- **Recurring money is shown once:**
  - the Finances page shows **this month's profit**, with its parts (TV, commercial and matchday, wages, running costs) at current rates;
  - a short list of **changes** to them (e.g. "Jul 2027: league TV money $5.2M → $0.8M a month", after relegation) is derived from consecutive monthly settlements;
  - **transactions** lists only one-off money: the opening balance, transfers, prize money, parachutes, and owner investment.
- **Cup prize money:** a cup tie's winner earns that round's prize (`cup_prizes` in finance.yaml: by cup, rising each round, with the final the biggest). It's a one-off `prize` transaction.

## W4: transfers

### Valuation (W4-1)

- **Done (W4-1):** see `docs/calibration/value-model.md`. Two deviations: the terms are overall (with a knee), age, a young-star term, keeper and club reputation, with no potential term (it added nothing); and a stored per-player premium (W4-3) keeps the stars' fame.
- `transfers/valuation.py` is fitted on the base world's Transfermarkt values (`footsim fit-values`, log-linear).
  - **Its terms:** overall, age (young premium, decline after the late 20s), the public potential estimate for players up to 23, position (keepers cheaper), and the league's market level.
  - The fitted coefficients go in `valuation.yaml`, with the fit recorded in `docs/calibration/`.
- It's computed on demand, vectorised, for any player. It replaces the static value and `estimate_value_eur` everywhere.
- Contract time left isn't part of the value. It's part of the asking price.

### Windows (W4-2)

- Every country's calendar gets its own summer and winter windows (data, approximate dates).
- `transfer_window_open(world, meta, nation, day)` checks the current season's and the next season's calendars, so the June days of next season's summer window count.
- A move is allowed when the **buying** club's country is in a window. Signing a free agent follows the same rule.

### The contract invariant and the domain (W4-3)

- **Schema v11:**
  - `transfer` holds the history: player, from club (null for a free agent), to club, date, season, fee, wage, contract end, kind (`transfer` | `free` | `loan` | `loan_return`), and who started it (user or AI);
  - `transfer_offer` holds offers that outlive a click: AI bids for the user's players, and the user's offers awaiting a reply. Its fields are status, fee, wage, years, counter fee, and the created and expires dates;
  - `contract.listed` marks a player transfer-listed.
- **A partial unique index:** one active permanent contract per player, `UNIQUE(person_id) WHERE is_active = 1 AND kind != 'loan'`. The migration checks for duplicates first.
- **`world/transfers.py`:**
  - `validate_move(…)` raises a reason, before any write;
  - `complete_move(…)` does everything in the caller's transaction:
    1. ends the old contract;
    2. opens the new one;
    3. moves the money both ways in the ledger and budgets;
    4. writes the history row;
    5. clears the player from the old club's saved lineup;
    6. returns the news.

  The same functions serve AI and user moves.

### Decisions (W4-4: pure functions, tested alone; detailed 8 Oct)

All numbers live in `data/config/transfers/market.yaml`. The functions are in `transfers/decisions.py`, which has no database.

- **A player's role at his club:** found from his rank in his position group against the formation's demand. The demand is the number of formation slots in that group (`depth_per_slot` × the slots counts as cover).
  - The first `demand` players are **starters**. A starter more than `key_margin` above the club's level is **key**.
  - The next `demand` players are **rotation**.
  - The rest are **surplus**.
- **The seller's asking price** = value × role multiplier (key 1.8, starter 1.4, rotation 1.1, surplus 0.85) × contract multiplier (under 1 year left 0.6, under 2 years 0.85, under 3 years 1.0, more 1.15) × 0.8 if listed × 0.85 if the seller is in debt. It's quoted in market steps.
- **The seller's answer** to a bid: it accepts at or above the asking price, counters at the asking price from `counter_from` (75%) of it, and otherwise rejects. The squad and keeper floors are `validate_move`'s, so they apply to everyone.
- **The buyer:**
  - it opens at value × a keyed eagerness in `bid_eagerness` (0.85–1.05);
  - it pays a counter up to value × (`max_premium` + `urgent_premium` × urgency);
  - it never spends more than `max_deal_share` of its budget on one signing, and always within the budget (cost = fee + wage × weeks left: W3-4).
- **The wage he asks** = max(his new league's going rate for his overall (`wage_levels`), his current wage × `move_raise`). A free agent asks the going rate × `free_agent_discount`.
  - A club pays one player at most `max_wage_share` of its weekly wage capacity.
  - It keeps its bill within capacity × (1 + `wage_slack`). (Prudence is the AI's; the hard rule is the budget.)
- **Contract length** comes from age: up to 23 five years, 27 four, 30 three, 32 two, then one.
- **The player's answer:** he accepts when this is at least 0:
  - `reputation` × (the buyer's reputation − his club's);
  - plus `wage` × ln(the offered wage ÷ his current one);
  - plus `starting` × (he'd start there − he starts now);
  - plus `listed` if his club lists him;
  - plus keyed noise (sd `noise`).

  A free agent accepts the asked wage from any club within `reach` reputation of his own level.

### The AI market (W4-5; detailed 8 Oct)

- **Who acts:**
  - every club except the user's, including the 302 outside the leagues (they act at `outside_league_activity`, so their cash circulates);
  - each in its own country's window.
- **When:** a club looks at the market every `interval_days` of its window, on its own phase ((days since the window opened + club id) mod interval), and with `deadline_activity` chance on each of the last `deadline_days`.
  - Clubs act in reputation order, then by id.
  - `after_day` runs the market at most once a day (the day is recorded in game_meta).
- **Snapshot:** one set of numpy arrays per market day over every player under contract or free. It holds:
  - owner, position group, overall, age, value (with premium), wage, contract years left, listed;
  - whether he has moved this window (a player moves at most once a window).

  It's updated in place after each deal.
- **Needs** come from the club's formation (its tactic; `best_formation` for clubs without one), by position group:
  - **short:** fewer than demand × `depth_per_slot` (keepers: `keepers_wanted`); urgent below demand;
  - **weak:** the weakest starter is more than `weak_gap` below the club's level (the mean of its starters);
  - **ageing:** a starter aged `ageing_from` or more with no younger cover within 3.

  A club acts on at most `needs_per_day`, most urgent first.
- **Targets for a need:**
  - in the group, overall in the need's band around the club's level (upgrade `upgrade_band` with at least `min_improvement` over the starter he'd replace; depth `depth_band`);
  - not his own club's, not the user's (W4-6 adds bids for the user's players), not moved this window;
  - an unlisted player at a club more than `reach` above the buyer in reputation isn't approached;
  - affordable at an estimated cost.

  They're scored by improvement + youth − cost share, and the best `candidates_per_need` are tried in order: the seller's answer, then the player's, then `validate_move` and `complete_move`. Depth needs prefer free agents.
- **Selling:**
  - on a club's first market day in a window, it lists its surplus beyond `squad_max` seniors and its old non-starters well below its level;
  - a club in trouble (in debt, or wages over capacity × 1.2) also lists its best-paid non-key players and takes counters down to `counter_from`.

  Listed players are cheaper and readier to go.
- **Limits:** `max_in_summer` and `max_in_winter` signings a window, and `max_out` sales.
- **Tool:** `footsim market-report` runs a watch-only career through a window (or a season) and prints:
  - deals and fees by league;
  - the top deals;
  - who moved (age, overall);
  - squad sizes (no club below the floors);
  - budgets and balances;
  - free agents;
  - the change in total value.

  **The first targets** are approximate real ones:
  - a Premier League club makes 3–8 senior signings in a summer;
  - most clubs sign someone;
  - fees concentrate at the top;
  - no squad shortages after a window;
  - money flows down the leagues.

### Reputation that moves (proposed 8 Oct, after W4-5)

Today a club's reputation (1–99) is set once, at the world build: 10 + 2.8 × (the mean overall of its best 18 − 55). It never changes.

Since W4 it matters more:
- it is the market level in every player's value;
- it decides which players will come;
- it sets the size and quality of youth intake;
- it seeds the cups.

**Proposal:**
- At each rollover, reputation moves `reputation_drift` (about 0.25) of the way towards a target, plus small one-off steps for honours.
- The target is the same build formula on the club's squad now, blended with its league's standing (the mean reputation of the league's clubs).
- So a club that builds a better squad and climbs gains stature over a few seasons, and a club that sells its best players and drops loses it, without one good season making a giant.

Its numbers would go in YAML, with a test that reputation follows a sustained change of squad and division.

### The user (W4-6)

- **API:**
  - a search (position, age, overall, value, league, free agents);
  - an offer, answered at once: accepted, countered or rejected, then the player's answer, then done;
  - list and unlist;
  - offers received (accept, reject or counter);
  - history.
- **Sim-to-date stops** when an AI club bids for one of the user's players.
- **UI:** a Transfers page (search, my offers, offers received, history), "Make an offer" on player pages, and listing on the squad page. Budgets show on the Finances page.

### Contracts and loans (W4-7, W4-8)

- **W4-7: renewals replace `_renew_contracts`.**
  - **AI clubs** renew players still in their plans (by importance and age) at a new wage. Others run down and leave free on 30 June.
  - **The user** gets a list of expiring players to renew or release.
  - Free agents are signed by W4-5's market. The yearly "half leave the game" rule stays for the unsigned.
- **W4-8: loans keep the invariant.**
  - The permanent contract stays with the parent club.
  - A `loan` row (player, parent, borrower, start, end, wage share, fee) changes where he plays: squad reads go through one helper/view, the club he plays for = the borrower if a loan is active, else his contract's club.
  - Every squad query moves to that helper, with tests that no player appears in two squads.

## Performance and determinism

- No per-day work outside windows except the monthly settlement, which is one aggregate query per kind. Market days do one snapshot and a bounded number of club evaluations.
- All randomness uses `derive_rng(seed, purpose, keys)`; iteration is sorted. A watch-only career run twice from one seed must give identical transfers and balances (a test).
- `after_day` stays idempotent: the settlement and market steps record the day they ran.

## Saves

- `_to_v10` (W3) and `_to_v11` (W4) follow the existing pattern: `create_all`, then backfill from the current state, idempotent.
- They are checked on copies of the three real careers: migrate, load, simulate, save, reload. The real saves are never touched.

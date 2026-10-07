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
  - `kind` is opening, broadcast, club_income, wages, operating, prize, parachute, transfer, or adjustment.
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

## W4: transfers

### Valuation (W4-1)

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

### Decisions (W4-4: pure functions, tested alone)

- **The seller's asking price** = value × importance (a starter, rotation, surplus, or listed; depth left after the sale) × contract time left × the seller's money need.
  - It accepts at or above the asking price;
  - it counters at the asking price from 75% of it;
  - otherwise it rejects.
  - It never sells below its own squad floor or its last keeper.
- **The buyer's bid:** value × eagerness, up to what it can afford.
- **The player's answer** depends on the buyer's reputation and league level against his club's, the wage against his current one, whether he'd start, and his age. There's a small, keyed random factor.
- **His wage demand:** the buying league's `wage_for(overall)` and his current wage, whichever is higher, within the buyer's wage room.
- **His contract length** depends on age.

### The AI market (W4-5)

- **Cadence:** market days only inside a window, every few days, and daily in the last week. Each club acts on a deterministic subset of those days (`derive_rng(seed, "market", day, club)`). Clubs act in a fixed order (reputation, then id).
- **Needs** come from `LineupPicker` on the club's formation:
  - depth per position group;
  - weak starters (slot rating below the club's own level);
  - ageing starters;
  - squad size against limits;
  - the club's budget and wage room.
- **Targets** come from one market snapshot per market day (numpy over every player under contract and every free agent): the position, an overall band around the club's level, an affordable value, a wage within room, and a reachable club (reputation).
  - At most one bid per need, and a few deals per club per window.
- **Selling:** clubs over their limit, or with surplus (old, low-rated, behind two in their position), list players. Listed players are cheaper and are offered to smaller clubs first. Clubs short of money sell more readily.
- **Free agents** fill gaps cheaply.
- **Tools:** `footsim market-report` runs a watch-only window or season. It reports:
  - deals, fees and spending by league;
  - the top deals;
  - age and overall distributions;
  - squad sizes and budgets;
  - any shortages.

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

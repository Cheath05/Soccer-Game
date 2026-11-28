# Academy recruits' wages: investigation (27 Nov 2026)

Backlog item (progress.md, "Backlog from the user (12 Oct)"): the user thinks youth intake players
can arrive on £200k+ a week. Investigation only; nothing was changed, and the user's saves weren't
opened. **Slot 1 itself was not inspected**, so what the user saw there is unconfirmed (see the end).

## What sets the wage

1. **At intake: a flat floor.** `youth_intake` (`backend/src/footsim/world/lifecycle.py`, line ~228)
   writes every new youngster a `kind='youth'` contract at
   `wage_levels.minimum_weekly_wage` (`data/config/finance/wage_levels.yaml`: €400 a week).
   Club reputation, overall and potential never touch it. The 15-17-year-olds' contracts run to
   the end of the season they turn 19 (`lifecycle.yaml` `youth.contract_age`).
2. **At 19: a renewal at the league's going rate.** The contract ending at 19 goes through
   `settle_expiring` (`world/renewals.py`). An AI club that keeps him renews *in place*: the row
   stays `kind='youth'`, and the wage becomes `wage_demand(going_rate, current_wage, False, rules)`
   (`transfers/decisions.py`) = `max(going_rate, 1.15 × current wage)`, rounded to steps. The
   `going_rate` is `reference_wage × per_point ** (overall − reference_overall)` for the *club's*
   league (`wage_levels.yaml`, `WageLevel.wage_for`). It uses **overall only**: no age discount, no
   "first contract" scale, no cap. The user's own club gets the same terms as the price to
   re-sign a youngster whose contract is expiring (`_terms`).
3. The same going rate prices any player who changes club (market `candidates`/`attempt`,
   `player_terms`), so a young player with a high overall costs a lot in wages wherever he goes.

## Measurement

A temporary career from `data/worlds/base-2026-27.sqlite` in a temp folder (never `saves/`), as
Grimsby, with five rollovers (the season's table written as in `tests/integration/test_season_review.py`,
no matches played), so intakes in Jul 2027-Jul 2031, 13,533 youngsters in all. Wages are in €/week.
The probe script was `wages.py` in the session scratchpad, not committed.

| | result |
|---|---|
| Wage at intake (all 13,533, all clubs, all leagues) | **€400**, exactly, every time |
| Aged 15-18 now (8,056 on contracts) | **€400** each, none above |
| Aged 19 (first renewal, 1,737 on a renewed contract) | median €800, p99 €9,000, **max €19,000** |
| Aged 20-21 | median €700, p99 €7,000-8,500, max €13,000 |
| Renewed youngsters over €5K / €20K / €50K / €200K | 97 / 0 / 0 / **0** |
| Left the game unrenewed at 19-21 | 2,179 of the 13,533 |

By league, the renewed 19-21s (median / p90 / max): GER1 3,500 / 7,000 / 19,000; ITA1 4,100 / 9,000 /
18,000; ESP1 2,900 / 7,000 / 14,500; ENG1 3,700 / 9,000 / 13,000; ENG2 1,250 / 4,800 / 13,000;
FRA1 2,450 / 5,000 / 12,500; ENG3 650 / 6,000 / 10,500; ENG4 700 / 2,450 / 4,800. Grimsby's own 11
intake players over the run: seven at €400 and the rest at €600-1,250 after renewal.

The wage tracks overall: median €400 up to overall 50, €850 at 55-59, €2,300 at 60-64, €3,650 at 65-69,
and €9,000-18,000 at 70+. The best renewed youngster in five years was overall 68-70.

## How big is the problem

- **At arrival, there isn't one**: €400 a week is a believable academy/scholar figure (real ones are
  roughly £100-£1,000), and nothing in the intake can produce £200k.
- **The jump at 19 is the soft spot.** About 30% of the 19-21s sit above €400 after renewal, and the
  best are on €10-19K a week: a 19-year-old of 66-70 overall at a big club earns what a mid-table
  Premier League first-teamer does. Real first pro contracts for the best 18-19-year-olds at big
  clubs run about £5-30K, so the top end is high but not absurd. Low-reputation clubs are fine.
- **£200k+ needs overall about 88 in the Premier League's curve** (50,000 × 1.12^(88−75) ≈ 218K).
  No intake player gets near that by 19 (the best I saw was 70), so a £200k+ wage on an *academy
  recruit* isn't reproducible from the base world. The formula is unbounded above, though: a
  genuine wonderkid who reaches 85+ at 21-22 will be paid £150-300K on his next renewal, as any
  star is, with no scale for his age.

## Likely explanations for what the user saw (unverified)

1. They looked at a *later* wage: a developed academy product on a renewal, a transfer-market
   wage, or an asking price in contract talks, not the intake wage.
2. A save made before the current rules (the €400 floor and the renewal-in-place code) may differ.
3. A display or currency issue: the default currency is dollars with `per_euro` near 1, so
   conversion does not explain a 10× gap.
To settle it, someone should read slot 1 *read-only* (or the user can tell us the player's name):
`SELECT … FROM contract WHERE kind='youth' ORDER BY wage_weekly_cents DESC`.

## Recommended fix (when the user says go)

**Add a young-player scale to the going rate**, in YAML (`wage_levels.yaml` or `market.yaml`):

- `young_wage_factor`: a list of (age up to, multiplier) e.g. `[[19, 0.35], [21, 0.55], [23, 0.8]]`,
  applied in `wage_demand` / `going_rate` when the player is under a limit; **plus** a
  `youth_first_contract_cap` (a share of the league's `reference_wage`, e.g. 0.5) for the renewal of a
  `kind='youth'` contract.
- Optionally an absolute ceiling per league (`max_wage` as a multiple of `reference_wage`, e.g. 6×)
  so extrapolating the exponential never produces >£300K in a small league.

Trade-offs:
- Keeps one rule for every league, set in YAML; touches `transfers/decisions.py` and the wage
  levels' definition model only, so no engine/calibration change (no golden values).
- It lowers young wages everywhere, so a young star is cheaper to buy: it interacts with transfer
  budgets (`market_report`) and the AI's affordability (`max_wage_share`). Re-run the market
  report before and after; expect more young signings.
- A cap makes a rising wonderkid underpaid until 23, so he may be more willing to leave: keep the
  scale below 1 only for the *first* renewal, or raise it by overall.
- Changing nothing but the 19+ renewal leaves the mid-career formula as it is. That is the smallest
  fix; the intake wage (€400) needs no change.

Not recommended: tying the intake wage to the club's reputation or the player's potential. It adds
a number that doesn't match real academies, and the intake wage was never the problem.

# Ratings, draws and home advantage in the agent engine (17-18 Oct 2026)

The user's report: watched matches end level too often. The investigation found three causes,
fixed by finishing two of the plan's own steps (2.3e's control by rating, section J's fatigue)
and adding home advantage's second mechanism, then refitting Step 2.1 on the result.

**Candidate values** (one set for every league; **not yet the defaults**: League Two failed the
confirmation, see the end):

| | Before (shipped) | Candidate |
|---|---|---|
| `passing.yaml` `control.touch_skill` | 0.1 | **0.5** |
| `passing.yaml` `control.receiver` | 0.95 | **0.99** |
| `passing.yaml` `execution.skill` | 0.10 | **0.15** |
| `shooting.yaml` `finishing.slope` | 0.35 | **3.0** |
| `shooting.yaml` `keeping.slope` | 0.6 | **0.8** |
| `shape.yaml` `fatigue.press` / `fatigue.gap` | (none) | **1.0 / 3.0** |
| `tactics.yaml` `transition.reaction_fatigue` | (none) | **1.0** |
| `home_advantage.yaml` `crowd` (decisions, execution) | 0.85 | **0.45** |
| `home_advantage.yaml` `familiarity` (execution, control) | (none) | **0.06 / 0.015** |

## Real references

From football-data E0-E3 (2023/24-2025/26, every match), and FC 27's starting elevens (as the
batch harness picks them) against 2025-26's real results:

- **Draws** match an independent Poisson at each league's mean goals (PL .245 against .242).
  Home and away goals correlate -0.13 (PL) to -0.01 (League Two): the mark of strength.
- **Half time to full time:** level at half time ends level 33-38% of the time; a one-goal
  half-time lead ends drawn 22-24%. Second halves have 19-29% more goals than first halves.
  By 15 minutes the last carries 26.3% of goals and the 61-75 period 17.3%
  (premierleague.com); the first ten minutes 7.5% (StatsUltra, 2023/24-2024/25).
- **Rating response,** per point of XI advantage: goal difference +0.176 ±0.040 (PL), +0.199
  ±0.052 (Championship); shot gap +1.14 and shots on target +0.39 (PL). Per club, its own
  conversion +0.28 points a point of XI rating, its opponents' -0.15.

## What the engine did

ENG1 and ENG4, real squads, 400 mirrored matches a seed, Step 2.1's values:

- Draws .286-.318, though an independent Poisson at each match's own xG predicted .245 (ENG1):
  the chances implied the real draw rate; the scoring didn't.
- **Not the in-match managers.** Off, draws fell to .250, but a one-goal half-time lead then
  ended drawn only 13% (real 22-24%); on, 24%.
- **Level half-times stayed level** 50-53% of the time (real 33-38%), and second halves scored
  no more than first halves (1.07 / 0.97 against 1.19-1.29).
- **Ratings drove results half as much as in real football:** goal difference +0.10 a point of
  XI advantage in ENG1 (1,200 matches) and +0.01 in ENG4; synthetic sides +0.09 and +0.11.
  Shots (+0.49 a side a point, real +0.57) and shots on target (+0.19, real +0.20) were right;
  **possession, passes, pass accuracy, xG per shot and conversion were flat** against quality.
  A first touch of 60 or 80 moved a reception by 2 points, and League Two completed more of its
  passes (.907) than the Premier League (.884).

## The levers, at fixed rating gaps

Synthetic sides, every fixture one quality against the other both ways (`--qualities`), 200
matches a pair, seed 61. Goals per side per point of XI advantage (real +0.088):

| | 62 v 70 | 76 v 84 |
|---|---|---|
| baseline | +0.047 | +0.032 |
| A1, control by rating | +0.059 | +0.069 |
| B1, finishing and keeping by rating | +0.056 | +0.040 |
| **A1 + B1** | **+0.065** | **+0.079** |

Control by rating also makes possession follow quality (+0.23-0.26 points a point, from about
0) and pass accuracy twice as much. xG per shot stays flat in every variant: better sides now
make more chances, not better ones (a follow-up: chance quality by rating).

## Fatigue (section J), on top of A1 + B1

ENG1, 400 mirrored, seed 33, managers on:

| | A1 + B1 | F1 (press 0.6, gap 1.5, reaction 1.0) | **F2 (press 1.0, gap 3.0, reaction 1.0)** | Real PL |
|---|---|---|---|---|
| Draws | .292 | .268 | **.260** | .245 |
| Goals, 1st / 2nd half | 1.60 / 1.70 | 1.51 / 1.73 | 1.60 / 1.76 | 1.30 / 1.68 |
| Level at half time → ends level | .418 | .489 | **.357** | .350 |

The second half's goals are about real already; the excess is the first half's (a follow-up:
the opening minutes convert at 1.5-1.7 x xG, and a pass can roll into the net with no shot).
League Two with F2: draws .307 → .290, goals per minute of ball in play 0.042 (range
0.045-0.053).

## Home advantage refitted (Step 2.1 again)

With ratings weighing more in execution, the crowd's pass-error effect grew: home goal
difference +0.43 / +0.48 at 2.1's values. And 2.1 had recorded a conflict: with the crowd
carrying all of home advantage, its effect was concentrated under pressure. Familiarity (the
home side knows its ground: at any pressure, a little less pass error and a surer first touch)
takes the share real home advantage keeps without crowds.

| ENG1 / ENG4, seed 33 | H1: crowd 0.45 | H2: + familiarity 0.2 / 0.05 | Real |
|---|---|---|---|
| Home xG edge | +0.17 / +0.09 | +0.43 / +0.23 | goals +0.23 to +0.30 |
| Home goal difference | +0.12 / +0.20 | +0.33 / +0.41 | |
| Home share of shots | 5.3% / 4.6% | 13.7% / 11.2% | 8.1-11.7% |
| Away extra fouls | 1.1% / 1.7% | 6.9% / 7.6% | 2.2-3.8% |
| Home pass completion | +0.4 / +0.9 points | +2.3 / +2.7 | about +0.7 |

Every trace moves together (the away side's extra fouls come from the territory it gives up);
about 30% of H2's familiarity puts each in its real range: **crowd 0.45, familiarity 0.06 /
0.015**.

## Confirmation (batches of 19 Oct, read 10 Nov): not confirmed for League Two

The whole candidate set at once (AB1, F2, crowd 0.45, familiarity 0.06 / 0.015), ENG1 and ENG4,
400 mirrored a batch, seeds 33 and 34 (`reports/engine/draws/hc-*`; measure worktree at 7692943,
config copy `cfg-hc`, fingerprint 31364e1c63). The copy no longer exists, but rebuilding it from
7692943 with these values gives the same fingerprint byte for byte (as do AB1's and H1's), so the
batches measured exactly this set. Familiarity's two numbers are execution 0.06 and control
0.015, **one set for both leagues** (both ran the same config): the one-engine rule holds.

Two seeds pooled (800 mirrored matches a league; ± the two intervals combined):

| | ENG1 | ENG4 | Real |
|---|---|---|---|
| Home xG edge | +0.24 ±0.05 | **+0.17 ±0.04** | goals +0.23 to +0.30 |
| Home goal difference | +0.25 ±0.12 | +0.18 ±0.11 | +0.24 (PL), +0.23 ±0.08 (League Two) |
| Home share of shots | 8.5% ±1.4 | **6.7% ±1.3** | 8.1-11.7% (League Two 8.1%) |
| Away extra fouls | 3.3% ±1.8 | 2.8% ±1.9 | 2.2-3.8% |
| Home pass completion | **+1.1 ±0.2 points** | **+1.5 ±0.2** | about +0.7 (indicative) |
| Draws | .286 ±.030 | **.330 ±.032** | .245 (PL), .257 (League Two); ranges .22-.29 / .23-.29 |
| Home / away wins | .405 / .309 | **.357 / .312** | .432 / .324, .430 / .313 |

By seed: draws .273 / .300 (ENG1) and .333 / .328 (ENG4); home xG edge +0.27 / +0.20 and
+0.13 / +0.21. Goals per point of XI advantage +0.084 / +0.050 (ENG1, real +0.088) and +0.031 /
+0.031 ±0.054 (ENG4: League Two's elevens are too close together to read it).

- **ENG1 confirms**, but for pass completion: xG edge, shots, fouls and goal difference in range,
  draws .286 (from .318 at the shipped values on seed 33), inside the target range though real
  .245 sits just below the interval.
- **ENG4 misses on four of the five:** draws above range on both seeds (the interval .30-.36
  clears .29), so home wins fall short (.36 against .41-.47; home minus away wins +0.045 against
  real +0.117); the home share of shots and the xG edge are short of real (the intervals end at
  8.1% and +0.21); and the pass-completion gap is twice the indicative real one, at the top of
  the harness's reference range (0-1.5 points). Away fouls are in range.
- **League Two is where the user plays,** and its draws were the report that started this: at
  the shipped values (seed 33, `2.1/final-ENG4-s33`) draws were .318, home share of shots 9.8%,
  xG edge +0.19. The candidate set leaves the draws where they were (.333 on the same seed) and
  takes some of home advantage's territory away.

**Not patched, and why one value can't fix it** (a conflict, recorded): in League Two the
candidate set's home advantage is short in territory (shots, xG) but already long in pass
completion, and familiarity moves pass completion faster than territory (H1 → candidate: +0.6
points of completion for +2.1 points of shot share; the crowd alone, H1, bought 4.6 points of
shot share for +0.9 points of completion). Raising familiarity for League Two would also
overshoot the Premier League (H2: shots 13.7%, fouls 6.9%). And League Two's draws aren't home advantage's to fix: they
were high at every home-advantage setting except H2's oversized one (.253 with a +0.41 goal
difference), the mark of results that follow strength too little (+0.03 goals a point here).

**Proposed re-run** (`calibrate-engine` skill, from `.worktrees/measure` at 7692943, one batch at
a time, nothing else heavy alongside):

1. The shipped values on League Two, seed 34, to pair with `hc-ENG4-s34` (seed 33's pair is
   `2.1/final-ENG4-s33`): does the candidate set leave League Two worse than today's game?
   ```bash
   cd /Users/alexbenton/Developer/Soccer-Game/.worktrees/measure/backend
   caffeinate -i uv run --frozen footsim calibrate-engine --division ENG4 --n 400 --mirror \
     --seed 34 --workers 7 --out /Users/alexbenton/Developer/Soccer-Game/reports/engine/draws/shipped-ENG4-s34
   ```
2. Then the user's choice: switch the set on with League Two's draws and territory recorded as
   follow-ups (if 1 shows no loss against today), or first a split sweep that gives more of home
   advantage to the crowd and less to familiarity (for example crowd 0.6, familiarity 0.04 /
   0.01) on ENG4 seeds 33 and 34, then ENG1, each against the real ranges above.

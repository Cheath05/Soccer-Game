# The AI transfer market (W4-5): the first measurements

Each run: `footsim market-report --until 2026-09-03`, a watch-only career with seed 5, through the first summer window (1 Jul to 3 Sep 2026), run in the measurement worktree.

**The targets** are approximate real ones (`w3-w4-finances-transfers.md`, "The AI market"):
- a Premier League club makes 3–8 senior signings in a summer;
- most clubs sign someone;
- fees concentrate at the top, with a few €50M+ deals;
- no squad runs short;
- money flows down the leagues;
- the market's total value doesn't inflate.

| Run (8 Oct) | Change | Deals | Fees | PL signings per club | 50M+ deals | Biggest |
|---|---|---|---|---|---|---|
| v1 (to 25 Jul) | first settings | 653 | €1.08B | 0.5 | 0 | €41M |
| v2 | starter ask 1.25×, key 1.6×, contract >3y 1.1×; buyer ceiling 1.45× (+0.35 urgent) | 1,665 | €3.3B | 1.1 | 0 | €39.5M |
| v3 | "improve" need: a club with money improves its weakest starter; one signing may take 80% of the budget; key 1.5× | 1,717 | €4.1B | 1.9 | 0 | €41M |
| **v4** | board budget share 20% → **35%** of revenue | 1,534 | **€5.9B** | **2.0** | **10** | **€109M** (Valverde to Man City) |

**What each step found:**
- **v1:** a starter's asking price (1.4 × 1.15 = 1.61× value) was above every buyer's limit (1.3×). So only spare players moved, and 65% of deals were under €1M.
- **v2:** deep squads rarely "need" anyone, so the big clubs barely bought.
- **v3:** the "improve" need raised the Premier League's activity. Stars were still out of reach: values are on Transfermarkt's real scale, but club incomes are on the game's wage scale, about 45% of real (W3). The Premier League's average budget was about €50M and Man City's €78M.
- **v4:** a 35% budget share makes the market the sink the W3 review asked for. Clubs net about 20% of revenue a season, and now spend about that on players, not hoarding it.

**v4 in detail:**
- **Spending:** the Premier League spends €1.04B gross (about €52M a club, about 40% of real, in line with the game's money scale), net €141M. Saudi Arabia (net +€227M) and the Bundesliga (+€295M) spend most. Portugal, the Netherlands, Turkey and the clubs outside the leagues are net sellers.
- **Who signs:** 83–100% of each league's clubs sign someone.
- **Movers' ages:** quartiles 22.9, 27.3 and 29.9.
- **Squads:** none fell below the floors. The clubs short of players were short before the window, mostly Segunda División and outside-league squads in the data. With no free agents in the first summer, they had no one cheap to sign.
- **Checks:** no player with two clubs, every balance equal to its ledger, total value flat (€48.04B → €48.15B).
- **Speed:** 21 s for the whole window, matches included.

**Still to judge with more seasons:**
- free agents (from the first rollover's releases);
- the winter window;
- relegated big clubs shedding wages;
- whether the 35% share keeps balances steady over several seasons, with no runaway and no collapse.

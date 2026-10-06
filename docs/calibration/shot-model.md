# The shot model, fitted to real shots (6 Oct)

`uv run footsim fit-shots` (`backend/src/footsim/calibration/shot_fit.py`) reproduces this. The data is StatsBomb's open data, free for research with attribution: [github.com/statsbomb/open-data](https://github.com/statsbomb/open-data), cached under `data/raw/statsbomb` and never committed.

## Why

Before this, a shot's chance in the agent engine was `expected_goal(place)` × 0.55 for each defender in the cone × (1 − block chance) × finishing × keeper.

The place model was fitted to real *average* xG by place (penalty spot .3, edge of the box .08, 25 m .03), so it already included the defenders usually in the way. Stacking the cone and the blocks on top counted them twice, and the finishing-and-keeper factor averaged 0.82.

A typical crowded shot from the edge of the box came out at about .01, against a real .03–.05. Once the decision saw that (engine review fixes, 70b9171), edge-of-box shots were almost never worth taking. Players walked the ball into close range instead: 4% of shots from outside the box against a real 30–42%, xG per shot .17 against .09–.12, and goals up 35%.

## The data and the measurements

The 2015/16 Premier League gave 9,415 open-play shots, each with a freeze frame (where every visible player stood). Each is measured as the engine measures its own shots (`actions.shot_chance`):
- the distance to the goal's centre, and the angle the posts make;
- a header or not;
- outfield defenders in the triangle between the ball and the posts, +0.5 m (`cone`, capped at 3);
- the nearest outfield defender's closeness: (5 − distance) / 5, from 0 to 1.

StatsBomb's 120 × 80 yard pitch is converted keeping true distances from the goal.

## The fit

P(goal) is a logistic regression, by maximum likelihood. It's the shot's xG, blocks included, for an average Premier League shooter against an average Premier League keeper:

| Term | Coefficient | SE |
|---|---|---|
| intercept | −0.0645 | 0.2417 |
| angle (radians) | +1.1768 | 0.1744 |
| distance (m) | −0.1195 | 0.0104 |
| header | −0.8934 | 0.1062 |
| cone (defenders) | −0.3975 | 0.0463 |
| closeness | −1.0379 | 0.1565 |

Each defender in the cone multiplies the odds by 0.67. A defender on top of the shooter multiplies them by 0.35.

| Distance | Share | Scored | Fitted | StatsBomb xG | Blocked | Model blocks | Mean cone | Mean closeness |
|---|---|---|---|---|---|---|---|---|
| 0–8 m | .117 | .260 | .268 | .258 | .118 | .136 | 0.84 | 0.70 |
| 8–12 m | .177 | .134 | .137 | .129 | .208 | .226 | 0.94 | 0.66 |
| 12–16.5 m | .191 | .117 | .099 | .109 | .297 | .290 | 0.87 | 0.56 |
| 16.5–20 m | .153 | .058 | .061 | .063 | .374 | .351 | 1.06 | 0.51 |
| 20–25 m | .204 | .033 | .036 | .035 | .386 | .369 | 1.22 | 0.45 |
| 25–40 m | .155 | .016 | .020 | .019 | .310 | .328 | 1.21 | 0.35 |

- The fitted mean is .094, the same as the scoring rate and StatsBomb's own xG. It's right in every distance band to about .02.
- Half the shots come from 16.5 m or more, at xG .039; closer ones are .154.
- Fitted xG percentiles: 5% .014, 10% .019, 25% .031, median .060. Real players often shoot at under .03.

## Blocks

The engine's geometric block model applies to the same freeze frames:
- outfield defenders 0.8–14 m along the shot's line and within 0.9 m of it;
- each blocks with one chance, independently, at most 0.65 in all.

It matches the real blocked share (29.2%) with a per-blocker chance of **0.48** (it was 0.28), and then matches it in every distance band (the "Model blocks" column). Its shape was right; its level was too low.

## In the engine

- **The settings:**
  - the fitted terms: `shooting.yaml` `chance`;
  - the per-blocker chance at a Premier League-average defender: `defending.yaml` `blocks.chance` 0.48, `reference` 75;
  - the pressure term's centring: `defending.yaml` `shot_pressure`, with reference 75 for the closing defender and composure 74.
- **One number for the decision and the record:** the shot's xG is the fitted chance. The decision to shoot, a header's choice to go for goal and the recorded xG all use it, so the recorded xG means what a real xG model means.
- **Ratings decide execution around it:**
  - finishing, long shots or heading, and the keeper's reflexes, diving and positioning, each against the Premier League average the fit stands for (`shooting.yaml` `reference`: 73, 69, 70 and 81);
  - League Two's averages are about 58, 55, 59 and 62.
- **Blocks only split the outcome:** the block roll decides whether a non-goal ends blocked, and a shot that gets through scores at xG ÷ (1 − block chance), so the overall chance stays the fitted one.
- **Free kicks and penalties** keep their own models.

## Shot selection

The decision's old gates excluded most real long shots: xG of at least .05, or from 18–30 m with 3 m of room and at least .02. Real long shots are struck with a defender about 2.7 m away.

A shot is now an option from xG .015 (the 5th percentile), and the player chooses among his options with the shot worth its xG × `shooting.yaml` `value` against keeping the ball. `value` is calibrated against the real distribution of shot distances; see `docs/plans/progress.md`.

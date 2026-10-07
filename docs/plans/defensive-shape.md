# Phase D: defensive shape, pressing and transitions

This plan continues `continuation-plan.md`'s Phase D. It records:
- the diagnosis;
- the model;
- the gates;
- the order of work.

It was written on 6 Oct, after the engine review fixes, when the user asked for believable matches before W3 and W4.

## The diagnosis, measured

Before Phase D the agent engine played about 40 shots a match in the Premier League, against a real 23–27.5. The suspicion was that attacks reach dangerous areas too easily, because the side without the ball doesn't defend in a compact block.

`probe.ShapeSampler` (commit 44bdfe9) tests that. Once a second of live play it records the defending side's shape, measured on its outfield players in the attacking side's frame, and split by where the ball is:
- `length`: deepest to highest player;
- `width`;
- `line`: the back line's distance from goal;
- `behind_ball`: players goal-side of the ball;
- `near_ball`: players within 10 m of it;
- `lines_gap`: defence to midfield;
- `ball_side`: the shift towards the ball;
- `free_options`: attackers within 30 m of the ball with nobody within 5 m.

For every box entry it records how the ball got in (carry, pass, through ball, cross, …) and how many defenders were goal-side and in the box. Batches report all of it.

**The cause, in the code.** The defending side's shape had one moving part. The back line stood `min(line height, ball − 9 m)` from goal, and the rest of the team stood a fixed span (26–34 m) upfield of it.

So in a 4-4-2 with a normal line and the ball 30 m from our goal:
- the back four are at 21–23 m;
- the centre midfielders are at about 34 m, and the wide ones at 36 m;
- the forwards are at about 40 m.

The midfield is upfield of the ball wherever it is in our third. One match (golden seed 12) measured **3.7 outfield players goal-side of the ball** with the ball in the attackers' final third, against 7.9 in the middle third and 9.6 in their build-up.

Box entries came from carries, ground passes and through balls; crosses were rare. The 200-match figures are in "Measured" below.

## The model (D2): three lines placed from the ball

Out of possession a side stands in three lines, each placed from the ball (`data/config/match/shape.yaml`; `behaviours._defending_lines`):

| Line | Where | Bounds |
|---|---|---|
| Back line | `back_buffer` (9 m) goal-side of the ball | no deeper than `back_floor` (6 m); no higher than the line instruction's height (24/33/42 m), plus 4 m when pressing high with the ball in their third |
| Midfield | `mid_buffer` (2 m) goal-side of the ball | `mid_gap` 6–15 m in front of the back line, and within the span |
| Forwards | `front_ahead` (10 m) upfield of the ball: the outlet | `front_gap` 6–18 m in front of the midfield, and within the span (26/30/34 m) |

- Each player's formation x is mapped onto the lines piecewise: X_BACK (0.18) on the back line, X_MID (0.42) on the midfield, X_FRONT (0.70) on the forwards, and straight in between. So a holding midfielder (0.30) screens halfway between the back line and the midfield.
- Phase and role offsets still apply in formation units.
- Width and the ball-side shift are unchanged in this first step (0.72 × the width instruction; 42% of the ball's offset). They're measured, and are the next lever if the shape data asks for it.
- The same model for every league and every side. Tactics move it:
  - the line instruction sets the back line's height and the span;
  - pressing high lifts it in the opponent's third.

  Ratings decide how fast a player gets there (pace, acceleration, stamina), how soon he reacts after a turnover (anticipation, work rate: `_react`), and how tightly he marks.
- Pressing, marking and recovery are unchanged in this step. They act on the new zone targets:
  - the nearest players press;
  - markers blend from their zone towards their man;
  - anyone out of position sprints back.

## Gates (D2)

**Shape:**
- **With the ball in the attackers' final third**, 7 or more of the defending side's 10 outfield players are goal-side of the ball.
  - Approximate: real sides defending their third keep 8–9 outfield players behind the ball.
- **Lines** 10–15 m apart (the plan's D2 gate).
- **Length** about 25–35 m out of possession.
- **Width** about 35–45 m (the plan's gate is 40–45 m).

**Outcomes** (200 paired matches per division, seed 21, against the measured baseline):
- shots per minute of ball in play fall towards the real range, without forcing it;
- box entries per team fall, with fewer through balls and carries among them;
- xG per shot holds or rises;
- goals stay in or move towards range;
- fouls, cards and the ball-in-play time don't drift beyond their CIs without a reason;
- the rating response holds: equal synthetic sides at qualities 58/70/82 keep goals within about 15% of each other, as after 2.3f;
- the in-match manager's readings of an opponent's line and press are re-measured, since the shape moves them;
- tactics keep their costs: a high line and a high press still leave space behind.

**Speed:** a match stays within the budget (≤ 8 s).

## Then

1. **D6, defending.**
   - **Cover and handover:** a cover man behind the presser, the far full-back tucking in and the holding midfielder screening.
   - **Pressing:** curved pressing runs that cut the passing lane.
   - **Runners:** tracking runners in behind, which lets the through-ball stopgap in `_pass_options` go.
2. **D2b, lateral compactness** (if the shape data asks): the block's width and ball-side shift.
3. **Phase E, transitions:**
   - counter-pressing on a turnover, then a recovery run into the shape;
   - the side that wins the ball breaking forward before the shape closes;
   - fast-break shots are 2% against a real 6–12%.
4. **Recalibration** of the rating terms (2.3e) and switching 2.3c's honest pass estimate on, both waiting on this shape.

## Measured

All figures are 200 matches per division, seed 21. The tables are in `progress.md`.

| Step | Premier League goals | Premier League shots | League Two goals | League Two shots | What changed |
|---|---|---|---|---|---|
| Before D2 (S1+S2) | 5.30 | 47.2 | 4.54 | 35.5 | |
| D2 | 4.63 | 41.6 | 3.71 | 30.6 | goal-side, ball in the final third: 4.3 → 6 |
| D6 | **2.85** | **27.4** | **2.48** | 20.0 | take-ons 82% → 65%, interceptions 17 → 25 |
| E | 2.88 | 28.2 | 2.42 | 20.8 | fast breaks 2% → 7% / 6% of shots |

Real: Premier League 2.65–3.05 goals and 23–27.5 shots; EFL 2.45–2.85 goals and 22–26 shots.

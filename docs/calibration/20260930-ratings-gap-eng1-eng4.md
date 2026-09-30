# Ratings gap between the divisions (Step 2.3a part 4)

Measured 30 Sep 2026 on the built world (`data/worlds/base-2026-27.sqlite`, FC 27 ratings).

**Method.**
- For every club in each division, the calibration harness picks the starting XI it plays in batches (`engine_batch._sheet`: the club's best formation and lineup on 22 Aug 2026).
- Each attribute is averaged over the outfield starters of all clubs in the division.
- The starting XI rating is the mean slot rating (OVR in the slot) of all eleven starters.
- Only these aggregates are recorded; no player's ratings are.

| Attribute (outfield starters, mean) | ENG1 | ENG2 | ENG3 | ENG4 | ENG1 − ENG4 |
|---|---|---|---|---|---|
| clubs | 20 | 24 | 24 | 24 | |
| starting XI rating (slot OVR) | 78.9 | 70.8 | 65.9 | 62.9 | +15.9 |
| short_passing | 77.1 | 68.7 | 61.8 | 58.0 | +19.1 |
| long_passing | 71.9 | 63.4 | 56.9 | 52.6 | +19.3 |
| vision | 72.7 | 63.1 | 57.3 | 53.9 | +18.8 |
| crossing | 69.7 | 60.6 | 55.1 | 52.3 | +17.3 |
| first_touch | 77.4 | 69.0 | 62.5 | 58.5 | +18.9 |
| dribbling | 75.8 | 67.6 | 61.5 | 57.8 | +18.0 |
| anticipation | 79.2 | 70.0 | 63.6 | 60.6 | +18.6 |
| interceptions | 65.0 | 57.6 | 53.6 | 50.1 | +14.9 |
| decisions | 76.7 | 67.5 | 61.3 | 58.2 | +18.5 |
| composure | 78.0 | 68.0 | 61.8 | 59.0 | +18.9 |
| standing_tackle | 66.3 | 58.8 | 55.1 | 51.8 | +14.5 |
| aggression | 73.3 | 66.6 | 63.8 | 61.5 | +11.9 |
| heading_accuracy | 68.3 | 61.3 | 57.1 | 55.2 | +13.1 |
| jumping | 77.9 | 73.4 | 70.5 | 68.2 | +9.7 |
| strength | 72.2 | 69.8 | 67.8 | 66.7 | +5.5 |
| sprint_speed | 73.6 | 70.5 | 70.5 | 68.2 | +5.5 |
| acceleration | 72.8 | 70.2 | 70.5 | 68.7 | +4.1 |
| agility | 70.8 | 69.1 | 69.7 | 67.7 | +3.1 |
| stamina | 76.6 | 73.8 | 73.6 | 71.7 | +4.9 |
| finishing | 63.3 | 57.0 | 52.6 | 49.1 | +14.1 |

## What it means for calibration

**The ratings are not compressed.**
- League Two's starters sit about 19 points below the Premier League's on every technical and mental attribute the passing mechanics read: short and long passing, vision, first touch, anticipation, decisions and composure.
- They're only 3–6 points below on pace, agility, stamina and strength.

**So the missing gradient is the engine's, not the data's.**
- In round 5 and the 30 Sep diagnostic, League Two sides passed as accurately as Premier League sides.
- The data gives the mechanics a large rating gap to work with; the mechanics barely respond to it. See `docs/plans/continuation-plan.md`, status sections 4 and 5: the receiver always knows the ball's path, a heavy touch comes straight back, and execution error depends weakly on skill.
- Steps 2.3b–2.3e fix that through the ratings (the principles: ratings first, one engine for every league).

**Rough size of the response needed.**
- The real gap in pass accuracy between the Premier League and League Two is several points (PL 82.6% in 2025/26; the EFL range is 74–81%, and League Two sits at its low end; The Analyst).
- Over a ~19-point gap in passing and first touch, that's roughly 0.3–0.5 accuracy points per rating point at team level.
- It's a plausibility check for 2.3e's sweep, not a target to fit directly: the rating responses are judged on the synthetic quality sweep, and the league figures are validated after.

**The physical gap is small,** so leagues shouldn't differ much in distance, sprints or stamina through the ratings alone. Any league difference there has to come from how the game is played (tempo, style, long balls), not from a league label.

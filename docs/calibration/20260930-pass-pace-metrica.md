# Pass pace: a real reference from Metrica's open data (Step 2.3a part 4)

Measured 30 Sep 2026, for Step 2.3b's "pass pace" question.
- The design review found engine passes slow: 4 m/s² rolling friction (`engine.py` `ROLL_FRICTION`), weighted to arrive at 5 m/s.
- That could be part of the interception excess that `intercept_scale` 0.2 covers for.

**Source:** [Metrica Sports sample data](https://github.com/metrica-sports/sample-data), `Sample_Game_1` and `Sample_Game_2`, `RawEventsData.csv`. That's two professional matches, tagged at 25 Hz. Only the aggregates below are recorded here; the data itself isn't committed.

**Method.**
- Completed passes only: events of type `PASS` (Metrica logs failed passes as `BALL LOST`).
- Travel time is `End Time − Start Time`, from the kick to the reception.
- Distance is the straight line from the start to the end position, on a 105 × 68 m pitch (Metrica's normalised coordinates).
- The bands match the probe: short <14 m, medium 14–32 m, long ≥32 m.
- The subtypes are mostly plain passes (1,671), plus headers (47), goal kicks (25), crosses (10) and a few others.

| Band | Completed passes | Mean distance (m) | Mean travel time (s) | Median (s) | Mean speed (m/s) |
|---|---|---|---|---|---|
| short <14 m | 910 | 9.5 | 0.99 | 0.92 | 11.0 |
| medium 14–32 m | 747 | 20.2 | 1.60 | 1.52 | 13.7 |
| long ≥32 m | 104 | 42.2 | 2.76 | 2.70 | 16.2 |

**The engine, for comparison.**
- One synthetic match on the committed settings (30 Sep; indicative only), with `pass_time_*` from the probe:
  - short 1.39 s;
  - medium 2.05 s;
  - long 3.08 s.
- On those figures, engine passes take about 40% longer than real ones over short distances, about 28% over medium ones and about 12% over long ones.
- The engine's mean distance within each band isn't measured yet, so compare speeds before deciding. The 2.3a reference batch reports `pass_time_*` over 400 matches.

**Caveats.**
- Two matches, one data provider, event tagging rather than ball tracking.
- Headers and goal kicks are mixed in.
- Good enough to size the question (whether passes are too slow, and by roughly how much), not to fit a friction value to the decimal.
- Step 2.3b decides from the engine's own speeds per band against these: the physics stays the same for everyone.

# W9e: NCAA Divisions II and III, and the transfer portal

**Asked by the user (20 Nov):** integrate D2 and D3, "with some hidden gems from those divisions
being able to transfer schools to D1".

**The user's choices (20 Nov):**
- Real D2 and D3 schools in their conferences, with rosters, tables, champions and national
  tournaments, played with the quick results engine (no full match simulation).
- The user stays a D1 coach: D2 and D3 are where hidden gems develop, not a job to take.
- The transfer portal runs one way: D2/D3 standouts to D1. D1 players don't transfer, the
  user's included.

## Design

- **Data:** `data/config/college/ncaa_d2.yaml` (202 programs, 21 conferences, from Wikipedia's
  "List of NCAA Division II men's soccer programs") and `ncaa_d3.yaml` (406 programs, 44
  conferences, from Wikipedia's "List of NCAA Division III institutions": its primary
  conference, women's colleges left out; nearly every D-III member sponsors men's soccer).
  Tiers there are generated for spread, not judged from results.
- **Rules:** `data/config/college/lower.yaml`: each division's levels by tier, roster size,
  season dates and national tournament (D-II 36 teams, D-III 64).
- **Tables (schema v30):** `lower_team` (club, division, conference, tier, level) and
  `lower_player` (player, club, class year, entered season), apart from D1's `college_team` and
  `college_player` so no D1 system (recruiting, RPI, draft, program builder) picks them up.
  `IN_COLLEGE_SQL` and `COLLEGE_CLUBS_SQL` include them, so the professional game leaves them
  out as it does D1. `recruit.source` marks a portal entrant (`player_id` is his player).
- **Seasons:** each division is a competition (`NCAA2`, `NCAA3`, type `college_lower`), always
  fast-simulated: a conference schedule (non-conference games to fill), the table's champion
  takes the automatic bid, the best of the rest by the RPI (points a game until 22 Nov) fill the national
  tournament's field (seeded by the same), single-match knockout rounds with extra time and
  penalties.
- **Players:** generated at a division's level; each rollover seniors leave the game (retire),
  everyone else moves up a class, and rosters refill with freshmen: first the high-school
  seniors who went unsigned when the D1 class closed (the hidden gems: their true potential is
  kept), the better ones to D-II, then generated walk-ons.
- **The portal:** when the lower divisions' national tournaments end (December), their best
  non-seniors by overall and potential against D1's level enter: each becomes a recruit of the
  next class (`source = portal`), so the D1 board, offers, decisions, scouting estimates, "Your
  chances", game-day visits and the recruiting assistant all work for him. Signed, he moves to
  his D1 program at the rollover a class on (a D-II sophomore arrives a junior); unsigned, he
  stays where he is.

- **Only a college coach's career** has the divisions (they're created at its start, or on the
  first day a save from before plays); a professional career would pay their cost for nothing.

## Checkpoints

- **E1** data files and defs; schema v30; the lower divisions' programs and rosters created.
- **E2** fixtures, quick results, tables, champions, national tournaments, rollover.
- **E3** unsigned recruits join D2/D3 as freshmen (hidden gems).
- **E4** the transfer portal (recruit rows, AI offers, enrolment as a transfer).
- **E5** screens: the College page's division switch, school pages, Recruiting's Portal filter
  and badge; help, changelog; measure speed and save size, deploy.

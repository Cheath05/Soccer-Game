# W9c: an NCAA coach's career with high-school recruiting (notes)

The user asked for this on 19 Nov 2026. The plan and their choices are in `docs/plans/w9c-college-coach.md`:
- no coaching job moves;
- light recruiting effort;
- the 2025 roster-limit rules;
- new careers only.

It was built on branch `w9c-college-coach` (worktree `.worktrees/college`) from a39a252, and merged into `phase-1-match-believability`.

## A college coach's career
- **Start:** the start page's "Your club" has a Professional club / NCAA program switch. NCAA program lists the 213 programs by conference (`GET /api/world/college-programs`, from the defs, so no career is needed), each with its tier as stars and its state.
  - `POST /api/saves/{slot}/new` takes `college_program` (the club's name, "Wake Forest Demon Deacons") instead of `club_id`.
  - `initialize_career(college_program=...)` sets `meta.user_club_id` right after `create_season_fixtures`, which made the program's club (`ensure_college`), and turns the board off.
- **What's different for a coach:**
  - **Menu:** no Transfers, Finances, professional League, Cups or Europe (`Layout.tsx` `COLLEGE_HIDES`). Recruiting is added. The phone bar is Home, Squad, Tactics, Recruiting.
  - **Squad and player page:** class, scholarship and the season he leaves after (`SquadPlayerOut.college`), and a Draft mark once he has declared. Players have no value, wage or contract.
  - **Dashboard:** the conference table, the program card (prestige, RPI rank, place in the conference) and a recruiting card.
  - **College page:** opens on the coach's conference.
- **The whole NCAA is the coach's league.** `fast_sim.user_league` returns `NCAA` for a college club, so all of it is fully simulated even with the NCAA set to fast, as a professional manager's league is.
- **Fixtures** carry a stage name: "Regular season", "<Conference> Tournament", "NCAA <round>".
- **Players leave** by graduating, by declaring for the draft (W9a's `declare_prospects`), or by release. `queries.release_player` calls `college.draft.leave_program`: he becomes a free agent, within the squad rules' floor.
- **Guards:**
  - College programs can't sign professionals (`transfers.validate_move`) or borrow them (`loans.validate_loan`).
  - The market already left college players out (W9a).

## Recruiting (`world/college/recruiting.py`, `world/college/coach.py`, `data/config/college/recruiting.yaml`)
- **The class:**
  - On each season's first day, `ensure_recruiting` (from `create_college_fixtures`) makes the class that enrolls at the next season's start (`recruit.class_season`).
  - It has 2,200 recruits, 15% from abroad (a nation, no state).
  - Positions are weighted. Home states are weighted by youth soccer (`states:` holds population centres, used for distances too).
  - Each has an overall at enrollment and a potential (hidden).
  - The grade is overall plus half the room to grow, plus error (sd 2.5). It sets the national, position and state ranks and the stars (top 25 five-star, next 150 four, next 600 three).
  - Each has priorities (gamma draws for money, prestige, playing time, home and attention; 12% are "local") and a pace.
  - A recruit becomes a player only when he enrolls (`enroll_class` uses W9a's `_Maker` with his own name, nation, birth date and potential), so the ~950 who never sign never reach the player tables.
- **The first time a save recruits:**
  - each program gets a prestige (from its tier ± 3);
  - its players get scholarships (`_assign_scholarships`: the tier's money spread over the roster, the better players more).
- **Programs:**
  - **Money:** counted in full scholarships, by tier (18 / 15 / 12 / 9.5 / 6.5).
  - **Roster limit:** 28 (the 2025 rules); AI programs recruit to 27.
  - **Next season's money and places** are what the returning players (enrolled, Fr to Jr) and the class so far leave.
  - **Prestige** moves at each rollover (`update_prestige`) towards a mix of the tier's prestige and the last 3 seasons' success: the RPI percentile, 6 points per NCAA win, 10 for the title. It moves 30% of the way, and reputation follows by the tiers' anchors.
- **A week** (Mondays from 1 August to the close; `progress_recruiting` from `after_day`):
  - **AI offers** (`_ai_offers`):
    - A program with places tops up its open offers to 2x its need.
    - It chooses recruits whose expected prestige is within its reach (+10) and floor (−30, lifted after signing day).
    - It ranks them by grade plus its own scouting error (by tier), plus a need bonus by position group, minus a crowd penalty (3 grade points for each program at least as strong already offering).
    - Shares are what the recruit hopes for, within its money. It pulls offers once full.
    - Priorities: Top for its best 3 offers, High for the rest.
  - **Effort** (`_effort`):
    - Each program's weekly effort (by tier, 36 to 20) is spread over its targets by priority weight (3 / 2 / 1), at most 8 on one.
    - Interest grows 1.6 per point, 50% faster with an offer out, and decays 6% a week without effort.
    - The user's knowledge grows 0.015 per point.
    - **Campus visits:** a Top target with an offer and 60 interest visits once, for +18; 12 a program a season.
  - **Decisions** (`_decisions`):
    - **Readiness** grows by stars (0.055 to 0.12 a week) × pace × (0.4 + 1.2 × his best offer's prestige score). It's faster for low recruits and slower while his offers are beneath his hopes, and 3x after signing day.
    - **Scoring:** each offer is scored on money (share against hopes, capped at 1), prestige (a logistic of the program's prestige against his expectation, scale 10), playing time (1 among the starters at his position group next season, × 0.7 for each place below), home (exp(−miles/450); 0.5 from abroad) and attention (interest/100). Each is weighted by base weights × his priorities, plus a fixed fit per program (sd 0.25).
    - **Commitment:** at readiness 1 he commits if his best beats the next by 0.08, or at 2 regardless.
    - **Money and places:** a program without either loses him to his next choice. If it's the user's program, the news says so.
    - **Flips:** before signing day, a committed recruit flips to an offer 0.35 better, with a 15% chance a week.
  - **Signing day** (the first Wednesday on or after 4 February): commitments become signings, and open recruits with offers decide.
  - **The close** (1 May): AI programs still short sign the best left (strongest first, as walk-ons once their money is gone), and the rest are gone.
- **The rollover** (`college_turnover`):
  - prestige moves;
  - the signed class enrolls;
  - generated freshmen fill programs still short: to 27 for the AI, to 22 for a coach (`user.min_roster`). A save's first season with no recruited class still gets W9a's full generated classes.
- **News** comes only for a college coach: commitments to or from them, their targets', the top-10 recruits', campus visits, signing day, the close, and a recruit they couldn't take. A professional career sees none.

## The coach's view (`world/college/coach.py`, `api/recruiting.py`)
- **Estimates:** truth + a fixed error (sd 4 for overall, 6 for potential) × (1 − knowledge), in a range `width` × (1 − knowledge) wide (7 and 10), at least 1. The potential range is never below the overall's.
- **Leaders:** who a recruit leans towards (his offers by his score) shows once the staff's knowledge is 0.25, or for the top 100. The card shows his top 5.
- **Offers:**
  - from 1 August to the close, in 5% steps (0 is a walk-on place);
  - open offers worth at most 1.5x the money left, and at most 1.5x the places in number;
  - a recruit who turned an offer down needs a better one.
  - Pulling a committed recruit's offer frees him and costs 10 interest with every other target.
- **API** (prefix `/api/recruiting`):
  - `GET ""`: the summary.
  - `GET /recruits?view=board|targets|offers|class&position=&state=(code|INTL)&stars=&q=&open_only=&offset=&limit=`
  - `GET /recruits/{id}`
  - `PUT /targets/{id}` with `{priority: top|high|watch|null}`
  - `PUT /offers/{id}` with `{share}`, and `DELETE /offers/{id}` (returns news)
  - `GET /classes?limit=`: class points by stars, 30 / 18 / 9 / 4.
- **Screen:** `pages/RecruitingPage.tsx`:
  - the summary cards;
  - Board / My targets / My offers / My class / Class rankings (a select on a phone);
  - the board's filters;
  - a table on desktop, cards on a phone;
  - the recruit card as a right drawer, or a bottom sheet on a phone.

## Schema v26
- Tables: `recruit`, `recruit_offer`, `recruit_interest` (with `fit`).
- Columns: `college_player.scholarship`, `college_team.prestige`.
- `_to_v26` adds the columns if they're missing (W9a's v24 step makes the college tables from the current metadata, so they may already have them).

## Measured
- **A recruiting year without the matches** (seed 11, from the career's start to the close): 2.2 s of recruiting a season (the first week, with the overalls cache, about 0.2 s).
  - 1,260 signed; every program at 27-28; none over its money.
  - All 25 five-stars went to tier 1; four-stars 34 / 104 / 12 to tiers 1 / 2 / 3.
  - Freshmen's mean overall by tier: 46.7 / 45.4 / 43.9 / 40.9 / 37.8, against W9a's generated 47.5 / 45.5 / 43 / 40.5 / 37.5.
- **Tuning that got there:**
  - prestige weight 1.4 → 2.0 and scale 14 → 10 (tier 1 was landing worse classes than tier 2);
  - bench decay 0.55 → 0.7;
  - the crowd penalty (every power chased the same five-stars);
  - the AI floor 18 → 30 and overcommit 1.5 → 2.0 (powers ran out of four-stars before signing day);
  - waiting for better offers;
  - the class's overall 41 → 39.5.

## Tests
- `tests/unit/test_recruiting_decisions.py`: each factor moves the choice; readiness and the margin; a program without money loses him; signing day; dates and curves.
- `tests/integration/test_recruiting.py`: the class's ranks, stars, homes and determinism; a year of AI recruiting (rosters, money, five-stars, the tier order, signing dates, offers); enrollment.
- `tests/integration/test_college_coach.py`: a career at Indiana (no board or finances, the NCAA fully simulated, the career and squad API, release, no professionals).
- `tests/integration/test_coach_recruiting.py`: a coach's year (targets, offers and their limits, effort, knowledge and estimates, the AI leaving the user's program alone, commitments and news, pulling a commitment, signing day, rankings, enrollment).
- `tests/integration/test_college_season.py`: now checks the recruited class enrolls, the next class is made, prestige moves and reputations stay within the tiers'.

## Follow-ups
- **Coaching jobs:** moving to another program or to MLS (the user: not now).
- **More recruiting:**
  - the transfer portal;
  - junior-college transfers;
  - next year's class (juniors) on the board;
  - money in dollars by school (cost of attendance);
  - funding that grows with success;
  - academic eligibility;
  - camps and showcases.
- **Existing careers switching to a college job** (the user: new careers only).
- **Generation in the world build:** the college world is still generated into a career (W9a's follow-up); the recruiting class adds about 0.3 s at a career's start.
- **The draft:** the coach sees where their players go only through the College page's draft pool and the Draft page (MLS clubs only in the menu).

# W9c: managing an NCAA program, with high-school recruiting

**Asked for by the user on 19 Nov 2026:** "give me an option to be an NCAA manager and make up some kind of recruitment system where I see HS recruits and their ranking nationally and try to give offers (Scholarships and such) to recruit them on my team".

This builds on W9a's college season (`docs/plans/w9a-ncaa-notes.md`): 213 real programs in 23 conferences, made-up players, the conference tables and tournaments, the RPI, the 48-team NCAA tournament, and the draft pool that feeds MLS's SuperDraft (`world/draft.py`). The draft must keep working.

The user's choices on the open questions are recorded under **Decisions** below, once made.

## 1. Managing a college program

### Starting a career
- The start page's league picker gets **"NCAA Division I (USA)"**, listing the 213 programs by conference. Each program shows its tier (1–5, as program prestige stars) and its state.
- College clubs don't exist in the base world: `ensure_college` makes them when the career's first season is created. So the new-career request names the program (`college_program: "Indiana Hoosiers"`), and `initialize_career` sets `meta.user_club_id` to its club right after `create_season_fixtures`. Nothing before that step reads the user's club, except `refresh_ai_tactics`, which only covers league members.
- A college career has **no board** (`board_enabled` false): college programs have no ledger.
- The user's program is fully simulated even if the NCAA is set to fast results: `fast_sim.user_league` returns `NCAA` for a college club.

### What a college coach sees
| Screen | For a college coach |
|---|---|
| Dashboard | next match, the conference table (around the user's row), the RPI rank, the recruiting summary (commitments, scholarship money left, this week's effort), news. No finances or board card. |
| Squad | class (Fr/So/Jr/Sr), scholarship (%), the year he leaves, a "declared" mark for the draft. No wages, values, contract ends or transfer buttons. |
| Tactics, Calendar, Fixtures, Match day, the live viewer | unchanged. |
| College (the "League" for a college coach) | W9a's page: conference tables, RPI, brackets, the draft pool. It opens on the user's conference. |
| **Recruiting** (new) | the national board, the target list, offers, scholarship budget, effort (section 2). |
| Player page | for a college player: class, scholarship and draft status instead of contract and value. No offer or loan buttons. |
| Club page | the program's conference, tier and titles. No finances. |
| **Hidden** | Transfers, Finances, the pro League page, Cups, Europe, MLS roster, the SuperDraft page (it's for MLS clubs; the College page's draft pool shows where the user's players go). |

- The phone's tab bar is Home, Squad, Tactics, **Recruiting**. More holds College, Fixtures, Calendar, Club, Settings, Save / Load.
- **Players leave** the way W9a's cycle already handles: seniors graduate, the best underclassmen declare for the draft (Generation adidas-style), and the draft's picks turn pro. The user can't sell or loan, and AI clubs can't bid (the market already leaves college players out).
- **Release:** the user may remove a player from the roster (he leaves college, as a walk-away transfer would). His scholarship is freed next season, not now.

### Program prestige
- Today a program's reputation is fixed by tier. Recruiting needs it to move, or the user's success never helps them recruit.
- **Prestige** (0–100) starts from the tier (`prestige_by_tier`) and moves at each rollover towards a target set by the last three seasons: the RPI rank, NCAA tournament rounds won, and titles. It moves slowly (a tier-5 program needs several deep runs to recruit like a power).
- Prestige applies to every program, so AI powers that slump also fade. The fixed `reputation` then follows prestige.
- The tier stays as the program's history (shown on the start page).

## 2. High-school recruiting

### The recruits
- Each season, on 1 July, the game makes the **national high-school class** that enrolls the August after next season's rollover: about **2,200 recruits** (213 programs sign about 7 each; the rest go to Division II, NAIA or junior college and leave the game).
- **About 85% domestic, 15% international** (international players are about a fifth of D-I rosters; some arrive as transfers, which aren't modelled). An international recruit's "state" is his country.
- Each has:
  - a made-up name from the save's own people (American pools for domestic recruits, his country's for internationals);
  - a position (GK, CB, LB/RB, DM, CM, AM, LW/RW, ST, weighted like rosters);
  - a hometown state, weighted by where US youth soccer players are (California, Texas, Florida, New York, New Jersey, Pennsylvania, Illinois, Ohio, Georgia, Virginia, North Carolina, Washington… down to small states);
  - a club team (made-up MLS NEXT or ECNL-style academy names by region: flavour only);
  - his **true** overall at enrollment and potential (hidden), on the same scale as today's freshmen (about 30–55, potential up to about 85);
  - **a recruiting-service grade** (public): true value plus noise, so rankings are good but not perfect;
  - **stars** from the national rank: 5★ the top ~25, 4★ the next ~150, 3★ the next ~600, 2★ the rest (`stars` in YAML);
  - a **national rank**, a **position rank** and a **state rank**, all by the public grade;
  - **priorities**, drawn per recruit: how much he weighs money, prestige, playing time, staying near home, and the coach's attention. A few are "local" recruits who strongly prefer their home region.
- Recruits aren't players yet: they live in a `recruit` table. Only those who sign become players (made by W9a's `_Maker` with the recruit's own position, overall and potential), at the rollover. So the 1,000+ who never sign never bloat the save.

### Scouting
- The user sees a recruit's **public grade and stars** from the start, and an **estimated** ability and potential as ranges.
- The range starts wide and narrows with the user's scouting of him: each contact adds a little knowledge, a scouting trip (watching him play) adds a lot. At full knowledge the range is a couple of points wide around the truth.
- The estimate's centre carries a fixed per-recruit error that shrinks with knowledge, like `scouting/estimates.py`, so an unscouted 3★ can be a hidden gem or a dud.
- AI programs see the public grade plus their own (seeded) error, larger for weaker programs.

### Scholarships and the roster (the 2025 rules)
- **The user's choice: the rules since the 2025 House settlement** for D-I programs that opted in. A men's soccer roster has at most **28 players**, and there is **no scholarship cap**: a program can give as many scholarships as its money allows, full or partial, and some players are walk-ons (0%).
- **Each program's scholarship money**, counted in full-scholarship equivalents ("full rides"), comes from its tier (`funding_by_tier`): a power funds about 18, a tier-5 program about 6. The user's program gets its tier's funding. (Money in dollars, cost of attendance by school, and a budget that grows with success are follow-ups.)
- Every college player holds a scholarship share (`college_player.scholarship`, 0–1). W9a's existing rosters get shares at generation (better players more; a program's total about its funding).
- **This season's money for recruits** = funding − the scholarships of the players returning next season (this season's freshmen, sophomores and juniors, less any who declare or leave). Seniors' money comes free.
- **Places for recruits** = 28 − the returning players.
- **Offers:** a full scholarship (100%), any share in 5% steps, or a walk-on spot (0%). The user may have offers out worth more than their money or places (as real coaches do), up to `offer_overcommit` (1.5x), but **commitments can't exceed the money or the places**: when a recruit wants to commit to an offer the program can no longer honour, he takes his next-best option. The Recruiting page warns before that happens.
- The user can **change or pull** an offer, but not a commitment's: pulling it ("decommitting him") makes every recruit trust the program a little less for the season.

### Recruiting effort (light, the user's choice)
- The user doesn't spend effort action by action. They put recruits on their **target list**, each with a priority (**Top**, **High** or **Watch**), and **the staff spreads the program's weekly effort** over the list: calls, visits to watch him play, home visits and campus visits happen by themselves, in proportion to the priority.
- The program's weekly effort is fixed by its tier (a power has a bigger staff). The longer the list, the thinner it's spread: ten Top targets get less each than three.
- Effort does two things for each target each week:
  - **Scouting:** the user's knowledge of him grows (the estimate narrows; section above).
  - **Interest:** his interest in the program grows, faster with an offer on the table. Interest fades a little each week when the program stops recruiting him.
- **Campus visits** happen by themselves for a Top target with an offer and real interest: a big interest boost, limited per season (`official_visits`). News reports them.
- AI programs spread their effort the same way over their own targets.

### How a recruit decides
Each week, every recruit with offers scores each offering program:
- **Scholarship share** of his own expectations (a 5★ expects a full ride; a 2★ is glad of 25%), weighted by his money priority.
- **Prestige** against his own level (a 5★ wants a power; a 2★ is flattered by any D-I offer), weighted by his prestige priority.
- **Playing time** at his position next season: the program's returning players of his position ranked by overall, and where he'd stand among them (as the recruit perceives it), weighted by his playing-time priority.
- **Distance** from his home state to the program's state (state centroids in YAML), weighted by his home priority.
- **Coach effort:** the interest the program built up (its staff's weekly effort, campus visits), weighted by his attention priority.
- **A personal fit** for each program (a seeded draw per recruit and program: he grew up a fan, likes the campus).
- **Competing offers:** the scores are compared; he leans to the best.

He **commits** when his readiness (rising week by week; the best recruits take longer) passes a threshold and his best offer beats the next by a margin, or on signing day. A committed recruit can still **flip** before signing day, rarely, if a much better offer arrives. On **Signing Day** (the first Wednesday of February) every commitment becomes a signing. Recruits still unsigned keep deciding, faster, until **1 May**, when the class closes.

### The AI programs' recruiting
- Each AI program has its needs for next season (positions short of the roster shape after its seniors leave), its money and its own effort.
- Each week it offers to the best recruits it can hope to land (a power aims at 4★ and 5★, a tier-5 program at 2★ and 3★), by need first, with seeded noise, until its open offers cover about 1.5x its places. It sizes offers by the recruit's rank and its money, and puts effort into its top targets.
- Offers it no longer needs (position filled, money spent) are pulled.
- **On 1 May** a program still short signs the best unsigned recruits who'll take a walk-on or small scholarship. If it's still short (an old career, or a thin class), W9a's generated freshmen fill the gap, as today.
- **This replaces W9a's generated freshman classes** for every career, watch-only ones included, from the first season that has a recruiting class. A career's first season has none yet (its freshmen came with the generated rosters); its class arrives on its first 1 July… which is the start of a new career: so a **new career generates its recruiting class at the start**.

### Screens
- **Recruiting page** (`/recruiting`), for a college coach:
  - **Header:** scholarship money (funding, committed, offered, left), places next season (returning, committed, of 28), the target list's size and the effort per target, campus visits left, the dates (signing day, class closes).
  - **National board:** the class, by national rank, with filters (position, state or region, stars, "on my list", "offered", "committed elsewhere"). Columns: rank, name, stars, position (and position rank), state (and state rank), the user's estimate, interest in the user's program, the leader (who he leans towards, once known), status. A button adds him to the list.
  - **My targets:** the list, each with its priority (Top / High / Watch), interest, knowledge and the offer box.
  - **Offers and commitments:** the user's offers, each recruit's interest and top schools, commitments and signings.
  - **A recruit's card** (drawer on desktop, sheet on phone): bio, the estimate ranges, his priorities as he tells them ("wants to play right away", "wants to stay near home"), his top schools with the user's place, the history of visits and offers.
  - **The class rankings:** every program's class by its recruits' points (the 247-style composite), the user's place.
- **News:** a recruit commits to (or decommits from) the user's program; a target commits elsewhere; the top-10 recruits' commitments; signing day's summary; the national class rankings after signing day.
- **Help topics:** "Managing a college program", "Recruiting", "Scholarships", "Signing day".

## 3. Determinism and cost
- All randomness through `derive_rng(meta.seed, ...)`, keyed by season, recruit and program, never by order of processing.
- The weekly recruiting step (about 2,200 recruits, 213 programs) runs on Mondays; aim under 0.1 s a week.

## 4. Schema (v26)
- `recruit`: id, class_season (the season whose rollover he enrolls at), names, nation, state, club team, position, birth date, true overall, potential, public grade, stars, national/position/state rank, priorities (JSON), readiness, status (open | committed | signed | enrolled | gone), club_id, committed_on, signed_on, player_id.
- `recruit_offer`: recruit, club, share, made_on, status (open | pulled | accepted | declined).
- `recruit_interest`: recruit, club, interest, priority (Top/High/Watch: the user's list, or an AI program's target), knowledge (the user's program only), last effort day, campus visit day (sparse: a row only once the program targets him).
- `college_player.scholarship` (REAL, default 0) and `college_team.prestige` (REAL).

## 5. Checkpoints
Each is a commit with progress.md, lint and the relevant tests; player-visible ones also add a changelog entry and help.
1. **R1, recruits and the AI programs' recruiting (backend):** the config (`data/config/college/recruiting.yaml`, `defs/college.py`), schema v26, recruit generation and rankings, scholarships on rosters, prestige, AI offers and recruit decisions, signing day and the 1 May close, freshmen from signed recruits at the rollover (W9a's generated freshmen as the fallback). Tests: generation (counts, stars, ranks, states, determinism), decisions (each factor moves the choice the right way), the AI's classes (every program near its target, the best recruits at the powers), a whole season with the draft still working.
2. **R2, the college coach:** the start page's NCAA option, a career for a program, `user_league`, the menu and phone tabs, the squad, dashboard, player and club pages for a college coach, the career API's college fields. Tests: a college career starts, plays its matches fully simulated, has no finances or market, and its season ends normally.
3. **R3, the user's recruiting (backend):** the target list and the staff's weekly effort, scouting knowledge and estimates, offers (money, places, overcommit), the user's program in recruits' decisions, news, the API (`/api/recruiting/...`). Tests: effort spread by priority, a recruit choosing between the user's and an AI's offer by each factor, commitment blocked by money or places, signing day, the user's freshmen on next season's roster.
4. **R4, the screens:** the Recruiting page, the recruit card, class rankings, the dashboard card, help, What's new; checked at :8765 on desktop and phone width.
5. **R5, a season played through:** a college career from August to the next August at :8765 (offers, commitments, signing day, the new freshmen on the roster), timing, the notes file, and the follow-ups.

## 6. Not in this round (follow-ups)
- The transfer portal, junior-college transfers, scholarship money in dollars, academic eligibility, recruiting camps and showcases, and next year's class (juniors) on the board.
- Coaching jobs: moving from a college program to another, or to MLS (the user: not now).
- Women's college soccer.

## Decisions
The user's answers, 19 Nov:
- **Job moves:** not now. A college career stays with its program; a coaching job market (college and MLS) is a follow-up.
- **Effort:** light. Offers plus a priority on each target; the staff spends the effort automatically.
- **Scholarships:** the 2025 roster-limit rules (28 players, no scholarship cap, each program's money), not the classic 9.9 split.
- **Existing careers:** new careers only. Existing saves get recruiting for the AI programs at their next season, and keep their club.

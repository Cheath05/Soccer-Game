# W9d: the NCAA "program builder" mode (money, training facilities, the stadium)

**Asked for by the user on 19 Nov 2026:** "add an option for the NCAA gamemode to be more game like, where I have the seasonal finances, and I can upgrade my facilities to improve the rate the players overall increases or my stadium makes the home games have the overall be a boost and things like this to make it more game like".

Builds on W9c (`docs/plans/w9c-college-coach.md`, `w9c-college-notes.md`).

## The user's choices (19 Nov)
- **Stadium:** a bigger, fuller stadium strengthens the crowd's existing pressure on the away side. The match engine builds home advantage from mechanisms, not rating boosts (`data/config/match/home_advantage.yaml`), so there is no flat overall boost.
- **Money:** a full program budget each season:
  - the athletic department's allocation, by prestige;
  - ticket sales from home attendance;
  - booster donations that grow with winning;
  - NCAA tournament payouts.

  Scholarships and upgrades are paid from it.
- **Upgrades:** training facilities and the stadium.
- **AI programs** earn money and build facilities too.

## The option
- **Setting:** a college coach's new career chooses the mode: **Classic** (W9c as it is) or **Program builder**. It's stored in `CareerMeta.college_mode`, `classic` by default, so every existing save stays classic.
  - Settings can switch an existing college career to the builder; its programs then start at their tiers' starting facilities and money.
  - The builder can't be switched off: money already spent can't be undone.
- **Scope:** the builder runs the whole NCAA economy (every program), since AI programs invest too. Professional clubs and their finances are untouched.

## Money (`data/config/college/program.yaml`; dollars, shown in the career's currency)
- **Each program's season:** the balance carries over, and the season opens on 1 July with the athletic department's allocation (by prestige: about $0.6M for a small program to $3M for a power).
- **Ticket sales:** each home game sells attendance × the price.
  - **Attendance** = the stadium's capacity × a fill rate: base by prestige, up with the team's recent form, the opponent's prestige, and conference, tournament and NCAA games, down when it's losing.
  - It's capped by capacity, with the ticket price by stadium level.
- **Boosters:** a donation after the regular season, by wins and conference titles, and after the NCAA tournament, by rounds won and the title.
- **NCAA tournament payouts:** per round reached.
- **Costs:**
  - scholarships (each full one costs the cost of attendance, about $55,000 a year);
  - coaching staff (fixed by tier);
  - the facilities' upkeep (by level);
  - travel (per away game).
- **Scholarships come out of money:** under the 2025 rules (no cap), a program's funding in full scholarships is what it sets aside.
  - The user sets a **scholarship budget** for next season's class (a slider on the Program page).
  - Funding = (returning players' scholarships, already committed) + the new class's money ÷ the cost of a full one.
  - AI programs set theirs by a rule.
  - Recruiting (W9c) reads the funding from here instead of `funding_by_tier`.
- **Never below zero:** an upgrade or a scholarship budget the balance can't cover is refused.

## Facilities (levels 1–5; costs, build times and effects in `program.yaml`)
- **Training facilities:** each level above 1 adds to the program's players' monthly growth (+6% a level, so +24% at level 5).
  - The growth goes through the development step (`world/season.py develop_players`) as a per-club growth factor, so only college players at that program are affected. Potential stays the ceiling; it just comes sooner.
  - Recruits count it in the program's appeal (below).
- **Stadium:** capacity by level (about 1,500 / 3,500 / 7,000 / 12,000 / 20,000) and a better atmosphere.
  - **The crowd effect:** the home crowd's pressure on the away side (`home_advantage.yaml` `crowd`) is scaled by the crowd's size and how full the ground is, from 0.5 (a few hundred in a big bowl) to 1.0 (a full 20,000).
    - 1.0 is the value calibrated on professional crowds, so a college crowd never exceeds it, and professional matches are unchanged.
    - It applies in both engines: the agent engine (the user's matches) and the fast engine (AI-vs-AI college games), through the same factor.
  - **More seats** sell more tickets when there's demand.
- **Upgrading:** pay the cost; the work takes the build time (a level finishes over the summer: started by 1 March, it's ready by the next season; later, the season after).
  - One project per facility at a time. Upkeep grows with the level.
- **Recruits' appeal:** a program's facilities add a little to its prestige score in recruits' decisions (`facilities_weight`), so building helps recruiting too.

## AI programs
- They set their scholarship budget by rule (the class they need, at the shares their level expects), keep a reserve, and spend the rest on facilities.
- Their priority is training, then the stadium, with seeded variety.
- Over seasons, programs that win get more money (tickets, boosters, NCAA payouts) and build up. Programs that slump fall behind as their rivals build.

## Screens
- **Program** (in a builder coach's menu, the College coach's "Finances"):
  - the balance;
  - this season's income and costs by line;
  - the scholarship budget slider for next season's class (in full scholarships and dollars);
  - the two facilities, with their level, effect, next level's cost, build time and upkeep, an **Upgrade** button, and work in progress;
  - attendance at each home game so far.
- **Dashboard:** a program money card (balance, next upgrade).
- **Recruiting:** the money left comes from the scholarship budget.
- **A match's page:** the attendance.
- **Help:** "Program builder: money and facilities". Plus What's new.

## Schema (v28)
- `college_program`: club, season, balance and the scholarship budget.
- `college_facility`: club, kind, level, building_to, ready_on.
- `college_ledger`: club, season, date, kind, amount, fixture.
- `fixture.attendance`: column.

## Checkpoints
1. **B1, the model:** config and defs, the schema, the economy (allocation, tickets and attendance, boosters, payouts, costs), scholarship funding from money (recruiting reads it), the facilities (upgrades, build times, upkeep), training growth, AI spending. Tests: a season's ledger adds up, upgrades refused without money, growth faster at a higher level, AI programs build, classic careers unchanged.
2. **B2, the stadium in matches:** attendance per home game, the crowd factor in the agent and fast engines (1.0 for professional matches: golden values unchanged), recruits' facilities appeal. Measured: home goal difference by stadium level over college fixtures.
3. **B3, the screens:**
   - the mode at a new career and in Settings;
   - the Program page;
   - the dashboard card;
   - the recruiting money;
   - attendance;
   - help and What's new.

   Checked at :8765, desktop and phone.
4. **B4, seasons played:** a builder career through two rollovers. Do the money, upgrades and AI building look right? Then deploy to the Proxmox server and the phone.

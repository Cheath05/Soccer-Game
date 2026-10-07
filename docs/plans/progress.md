# Match believability: progress

**Start with the "Continuation checkpoint" below, then resume from the first unticked item.**
- Since 30 Sep, the order of work and its details are in `continuation-plan.md`, which also holds the calibration principles.
- It supersedes `recovery-and-continuation.md` from Step 2.3 on.
- The design is in `match-believability.md`; section letters (for example "section S") refer to it.

**Every major completed change is its own checkpoint** (behaviour change or finished sub-step):
1. `engine-reviewer` checks the diff;
2. lint and tests pass, plus the relevant calibration;
3. the golden values are re-captured if behaviour changed on purpose;
4. this file is updated: the checkpoint section below, and the ticks;
5. commit and push to `phase-1-match-believability` before starting the next change.
   - Unfinished work goes into a labelled WIP commit, never only into the working tree.

## Continuation checkpoint (update at every checkpoint)

- **Branch:** `phase-1-match-believability`.
- **7 Oct: B2, the match viewer** (a Sonnet agent's work, reviewed here; the commit that adds this line, after d7fd793):
  - **The goal moment** had three causes:
    - the picture held on the frame before the ball crossed the line;
    - the banner keyed on the server's hold, while the picture eased in about 1.5 s behind it at 8×;
    - at high speed, the frames around a goal were dropped.

    **The fixes:**
    - the playhead runs on at the match's rate to a hold;
    - the viewer carries the ball over the line and into the net (visual only) and holds it there until the kick-off frame;
    - the banner, score and commentary appear when the ball is shown in the net, at every speed;
    - `LiveSession._drain` always sends the frames from 0.35 s before to 0.25 s after a goal. That changes which frames are sent, not the result: the golden values are unchanged.
  - **A modern look:**
    - a mown-stripe pitch with softer lines, arcs and drawn nets;
    - player markers with rings, shadows and name pills;
    - a dark scoreboard with team colour bars and a live clock;
    - rounded controls and glass overlays.
  - **The ball** has a dark outline, panels that turn as it travels, and a shadow that shrinks as it rises, so it stands out on the white lines.
  - **Tests:**
    - the golden and live-session tests, `npm run build` and lint;
    - the full backend suite;
    - `e2e/live.mjs` on :8765: the goal banner shows only once the ball is in, and there are no browser errors.
  - **Not viewed:** light mode. A 1× goal was not watched end to end; the logic doesn't depend on speed.
- **7 Oct: W3-2, the money moves** (d7fd793, after 59277c9).
  - **On each 1st** (`after_day`, after development), `settle_month` runs once per day (`settled_on`). Every club gets its league's equal share ÷ 12, its own income ÷ 12, its wages (bill × 52 ÷ 12) and running costs (`operating_costs` × projected revenue ÷ 12).
    - The user's club gets these itemised; every other club gets one net `month` row.
    - Then the board's confidence moves: (target − position) × `per_place`, capped at `max_step`, once `min_played` league matches are played.
  - **When a league ends** (`_finalize_league`), merit is paid by position, from the full `merit` for the champion falling linearly to none for the last club.
  - **At rollover** (`start_season_finances`, after the fixtures):
    - relegated clubs get `parachute` × the expected league income they lost, once;
    - a club playing in a league for the first time (one the save only now starts) has its own income worked out again, so league income isn't counted twice;
    - the board's confidence goes halfway back to 60;
    - new budgets and targets are set.
  - **Tests:**
    - `test_finance.py`: a watched season and its rollover. It checks balance = ledger, 11 settlements in a 1 July career's first season, the exact merit shares, the parachute amounts and who gets them, the seasons and dates money is booked to, the budgets and targets for season 2, bounds on balances, the user's itemised month booked only once, and which way confidence moves (clamped);
    - the whole-season cups test;
    - `just lint` clean; the full backend suite passes.
  - **Saves:** checked on copies of the user's three careers, a temporary folder each time:
    - Grimsby (Sep 2026), Wrexham (Jan 2028) and Chelsea (Jul 2028) each went through migrate → load → sim past a 1st → save → reload, with balance = ledger every time and the real files unchanged;
    - Chelsea's copy was then simulated through its rollover to 2029-30 (89 steps). The 15 leagues the save hadn't started joined, taking clubs in leagues from 92 to 368, and the joining clubs' own income was re-derived (e.g. La Liga: own income €88m → €39m, revenue €83m, so nothing is counted twice). Merit went to 88 clubs and parachutes to 10, with no ledger mismatches.
  - **Review** (Sonnet): no blockers. Applied:
    - `min_played` moved to YAML;
    - one rounding rule for confidence;
    - the extra tests above.

    Its economic findings are now W4 requirements in the design doc ("What W3 leaves for W4"): relegated big clubs bleed about €30m a season, promoted clubs get a windfall, and clubs outside the leagues keep accumulating cash. A typical club nets about +20% of its revenue a season, and W4's market is the sink.
  - **Next:** W3-3, the finances API and pages, real figures on the club page, the currency setting and the sandbox budget.
- **7 Oct: B1, the user's UI requests, part 1** (a Sonnet agent's work, reviewed here; the commit that adds this line, after cbee86e):
  - **Season summary:**
    - the automatic promotions were always in the data, but the "Promoted" section was collapsed, and play-off winners were listed under Champions;
    - now Champions holds league and cup winners only;
    - Promoted is open, and each club is badged Champions, Automatic or Play-offs.
  - **Other news** leads with headlines built from the database: the champions of every country's top flight where the game has several divisions, and cup upsets (a lower-tier winner, or one ≥ 20 reputation below the 3 favourites). Builders are kept in a list, so continental winners can be added later.
  - **Squad and player pages:** the overall at the start of the season and the change (▲/▼), from `player_season_overall`; "new" when there's no record.
  - **Tactics:** each name tag is as wide as the gap to its nearest neighbour (44–84 px), so centre-back pairs and front twos don't clash.
  - **Tests:** `test_season_views.py` (honours, headlines, the squad's start overall), `npm run build` and lint, and the full backend suite (with W3-2 in the tree) pass. Checked in a browser on :8765 (4-4-2, 5-3-2, 3-5-2).
  - **B2, the match viewer** (goal timing and animation, a modern look, a more visible ball), is with a Sonnet agent.
- **7 Oct: W3-1, the finances foundation** (cbee86e, after 4e1efc8). The design is `docs/plans/w3-w4-finances-transfers.md`, approved with the user's choices (currency a display setting, sim stops on bids, a basic board in W3, loans and expiring contracts in W4).
  - **Schema 10:**
    - `club_finance`: balance, own income, transfer and weekly wage budgets, the board's target and confidence;
    - `finance_ledger`: append-only. **A club's balance is always the sum of its ledger** (`world/finance.post`).
  - **`data/config/finance/finance.yaml`:**
    - each league's income (base plus merit), derived from that league's own mean wage bill, so it's on the game's wage scale;
    - the budget, cost and board parameters.
  - **`world/finance.py`:**
    - `initialize_finances` at career start, and in `_to_v10` for careers already under way (dated the save's game day);
    - a club's own income is derived from its wage bill;
    - an opening balance;
    - `set_budgets`;
    - the board's target: the club's rank by squad strength within its league.
  - **Tests:**
    - `test_finance.py` (new): ordering by league and by club, balance = ledger, budgets, targets, finances begin only once;
    - two migration tests;
    - `just lint` clean; the full backend suite passes.
  - **The review** (a Sonnet reviewer) found no blockers. The fixes made:
    - `post` refuses an unknown club or kind;
    - finances begin "settled" on their first day, so a migrated save isn't billed for months before it;
    - the loader rejects `league_income` for unknown leagues and checks the ratios are solvent;
    - the tests re-run the v10 step, check whole cents and determinism, and test `post`.

    The focused tests and lint pass after the fixes.
  - **Noted for W3-2:** a club that first joins a league mid-career (a league the save activates later) must have its own income re-derived, or it would count its league income twice.
  - **A sanity check on a new career:**

    | League | Mean revenue | Mean wage budget |
    |---|---|---|
    | Premier League | €166m | €116m a year |
    | League Two | €4.0m | €2.8m a year |

    Their wage bills are €99.5m and €2.4m. Man City's transfer budget is €78m; Grimsby's is €1.2m.
  - **Running alongside:** a Sonnet agent is fixing the user's 7 Oct UI requests (track B1: season summary promotions, notable "other news", season-start rating on the squad page, tactics name tags). It works only on its own files, and is reviewed and committed separately.
  - **Next:** W3-2, the money moves (monthly settlement, merit, parachutes, budgets at rollover, the board's confidence). Then W3-3 (the API and pages), then W4-1 to W4-8, then the user's play-test.
  - **Calibration:** none running. **Play-test:** nothing new to see in-game until W3-3.
- **Before that (6 Oct): the engine review fixes**, a behaviour change measured on real squads ("Review of 2.3f, 2.4 and W1" below). The commit before it, ca2447e, holds the review's behaviour-neutral fixes.
  - **Since 1 Oct, in the approved order** ("The approved order (1 Oct)" below), each its own commit:
    - the plan: aea59dc;
    - 2.3f, attack against defence by rating: 8170f0e and 24265b2 (WIP), 77b4cd2;
    - 2.4, fouls and cards: 88c7cf1 and 484c1ad (WIP), 0488313;
    - B2, the fast engine against the agent engine: dc6d5ee (tooling), 5a70414;
    - W1, retirement and youth intake: e4fdb5f;
    - nation pickers for the start and League pages: beb267c (a Sonnet agent's patch);
    - W2, La Liga, Serie A, the Bundesliga, Ligue 1 and their lower divisions: 131da6f.
  - **Tests:** `just lint` is clean, and the backend suite passes, with the Mac's golden values re-recorded and a History note.
  - **:8000 still runs 77b4cd2 (2.3f),** from 17:53 on 1 Oct. Restart it on this checkpoint once `lsof -nP -iTCP:8000 -sTCP:ESTABLISHED` shows no connections and `GET /api/career/sim` shows no sim running. Loading a save then migrates its working copy to schema 8 (retirements). The user's careers: slot 1 Grimsby, slot 2 Wrexham, slot 3 Chelsea.
  - **The user's own server (6 Oct):** the user hosts the game on a Proxmox Ubuntu VM on their tailnet, reached at `https://<vm>.<tailnet>.ts.net` through `tailscale serve`.
    - `deploy/install.sh` sets it up as systemd user services, and `deploy/update.sh` deploys every push to this branch within ten minutes, unless a match or a sim is running (`deploy/README.md`).
    - **Every push is a deploy:** keep each pushed commit playable.
    - **The version tag** (bottom of the menu, top of the start page) shows the build. It turns orange when the page and the server are on different commits.
  - **Production on the VM (6 Oct, the user's spec):**
    - footsim runs on `127.0.0.1:8001` as the systemd **user** service `footsim.service`, reached at `https://cardinal.tailaf3b0c.ts.net:8443` (Tailscale Serve to 8001). Cardinal, another app, owns `127.0.0.1:8000` and HTTPS 443, and is never touched.
    - The VM's settings are in `~/.config/footsim/deploy.env` (`FOOTSIM_PORT=8001`), read by the service, the updater and `deploy/status.sh`.
    - `deploy/install.sh` retires the user's hand-made `/etc/systemd/system/footsim.service`:
      - it checks the unit runs footsim, and keeps its saves;
      - it backs the unit up, then removes it;
      - it rolls back by itself if the new service doesn't answer.
    - Development and tests keep port 8000 and 8765.
    - Exercised in a stubbed sandbox: migration, rollback, refusal of a non-footsim port, re-run, and the updater (new commit, nothing new, busy, `--force`). It hasn't been run on the VM itself yet.
  - **Versions:** `v<major>.<minor>`, with the minor counting commits since the latest `v<major>.0` tag. `v1.0` is the commit that brought the deployment fix. The next major (`v2.0`) is for a big change to the simulation (Phase D accepted).
  - **Each country's cups** (a Sonnet agent's patch, reviewed and tested here):
    - Copa del Rey, Coppa Italia, DFB-Pokal, Coupe de France, Taça de Portugal and Taça da Liga, KNVB Beker, Scottish Cup and League Cup, Türkiye Kupası, Belgian Cup and King's Cup;
    - each on its own country's calendar, with only clubs in the data (byes for the top-ranked where a bracket doesn't fill).
    - The Cups page picks a country, defaulting to the user's.
    - The whole-season test checks every cup finishes.
  - **Season-end views** (the user's requests, 6 Oct, after a full-season sim; a Sonnet agent's patch, reviewed and tested here):
    - **Schema 9:** `player_season_overall` holds every player's overall as each season begins (recorded at career start and each rollover), so the next season's row is also the last one's end.
      - A save already under way starts the record on the day it's upgraded, and the summary says so.
    - **The season summary is built from the database,** in sections:
      - the user's finish and cup runs;
      - by country (defaulting to the user's): champions (leagues, play-offs, cups), promoted and relegated;
      - **your squad's development:** start → now, with the squad page's green and red arrows and the change;
      - retirements, youth intake and other news.

      The season-end lists no longer flood the news.
    - **League:** shows last season's final table until the new season's first match, with a note; "(now)" switches.
    - **Fixtures:** a season picker (`GET /clubs/{id}/fixtures?season=`).
    - **Player:** a "Seasons" table, a row per competition with a total per season (`GET /players/{id}/seasons`, from `player_match`). It's the base for the Ballon d'Or and players of the year later.
    - The rollover itself is unchanged.
  - **Engine step one done (7 Oct):** D6 (43675a4) and E (2a0b606) are measured and pushed. **Next:** W3, finances, then W4, transfers, designed first at the top model level. Open engine items are listed under Phase E below.
  - **Calibration:** nothing running once this checkpoint's measurement is in.
- **Before that (1 Oct, 14:55):** P17, the cups: d5c1d9d, with the follow-up 7376d17. Round 4 of the user's play-test ("Play-test round 4" below):
  - P15, the up/down arrows by a player's overall: e959fe4;
  - P16, club histories and past final tables: 3630131;
  - 2.3c iteration 4, crosses and long balls estimated as the physics plays them, still behind the switch: 09b1242. It was measured on real squads, which recorded the conflict that keeps the switch off and also found P14's side effect on goals;
  - P17, the FA Cup and the Carabao Cup: d5c1d9d. Follow-up 7376d17: a save from before the cups starts them this season if their first round is ahead.
  - **:8000 runs 77b4cd2 (2.3f),** restarted at 17:53 on 1 Oct, with no connections and no sim running. The user had been playing in between (a sim to 28 Nov 2028 finished and autosaved). Before that it ran 7376d17 from 14:54 (log `demo-server-7376d17-build.log`).
  - **Earlier, :8000 ran 7376d17,** restarted at 14:54 on 1 Oct. It had been restarted on d5c1d9d at 14:49, and on e91f9ca at 10:59. Each time there were no connections and no sim running. Logs: `demo-server-e91f9ca-build.log` and `demo-server-d5c1d9d-build.log`.
    - **The user's careers:**
      - slot 1: Grimsby, 2026;
      - slot 2: Wrexham, manual save 22 Jan 2028;
      - slot 3: Chelsea, a new career started today, saved on 1 Jul 2028.
    - Loading migrates the working copy: schema 7, potentials moved with P14's overall, the trend column, cup ties.
    - Chelsea's cups start on its first day played; Wrexham's from 2028-29.
  - **Next task:** the approved order (1 Oct), section "The approved order (1 Oct)" below. It starts with 2.3f.
  - **Note:** during P17's first full test run, `test_live_safety` hung for over 10 minutes right after `test_clubs` had failed. It passed on its own (23 s), and the whole suite passed once that failure was fixed. If it hangs again, run it with `-o faulthandler_timeout=60` to see where.
- **Before that, the same day:** P14 at e91f9ca, the overall closer to the six headline ratings; P13 at 578342d, development by age and traits. :8000 ran e91f9ca from 10:59.
- **Before that:** 4b779e9 (code at e8701a0, P12). The user's play-test fixes are done, each its own commit:
  - **Round 1** ("Play-test fixes" below):
    - P1, 99 ratings: 85a20ce;
    - P2, set-piece taker: 36fbd4f;
    - P3, viewer skipping: d981315;
    - P4, goal pause: 17635e6;
    - P5, sim to date: 66a92c7.
  - **Round 2** ("Play-test round 2" below):
    - P6, receivers: 9b3635a;
    - P7, calm passes and composure: 235a772;
    - P8, season summary: e407939, follow-up 2e2c05f;
    - P9, formations: 494ab06;
    - P10, development: c0db47a;
    - P11, losses costed where they happen: 82cbeb6;
    - P12, offsides, P11 softened, manager re-measured: e8701a0.
  - **Measurements** in `reports/engine/step2.3/`: `ref-p7`, `ref-p11` and `ref-p12`, each recorded under its item below. P13 and P14 change no match mechanics (P14 changes lineup picks and synthetic sides slightly), so `ref-p12` still describes the engine.
  - **:8000** ran e8701a0 from 03:45 on 1 Oct. Since then the user started a Wrexham career in slot 2 (manual save 1 Jul 2026, autosave 1 Jul 2027). The Chelsea career it replaced survives only in `saves/slot_2/backups` (the rotating backups up to 01:58 on 1 Oct). Restarted on P14: see above.
    - Saves from before are schema 3. Loading runs the v4 (development table) and v5 (potential moves with the new overall) migrations on the working copy.
  - **Next task**, in the order chosen with the user ("Play-test round 2"):
    1. 2.3c's honest estimate. It's the real fix for the inverted long-ball response (Premier League sides go longer than League Two's) and for the over-clean passing.
    2. 2.3f, attack against defence by rating, for the Premier League shot excess.
    3. 2.3e: control by rating, for the heavy touches.
    4. 2.4, fouls and cards.
    5. Phase D (defending against long balls and runners lets the through-ball stopgap go).
    6. Then transfers and the academy as phases of their own.
  - Check `lsof -nP -iTCP:8000 -sTCP:ESTABLISHED` before any batch: a batch slows a match the user is watching (use `--workers 3` then).
- **Earlier on 1 Oct:** :8000 was restarted on 17635e6 (P1–P4) at 01:28 and on 66a92c7 (P1–P5) at 01:40, each time with no connections and nothing unsaved.
- **Checkpoint commit:** 1de6591, the play-test build (30 Sep): round 5's measured passing values are now the committed defaults. The commit right after it only filled in this hash and recorded the :8000 restart.
  - The values are `intercept_scale` 0.2, `per_metre` 0.008 and `length_per_metre` 0.022, called "f020e2".
  - Earlier: Step 2.3c WIP iteration 2 0f96176 (iteration 1 eeb5239); 2.3b complete at d7ccf17; 2.3a a9a8ced.
- **Engine:** behaviour changed on purpose. The Mac's golden values were re-recorded, with a History note. 2.3c is still behind `estimate.honest` (off).
  - **Why:** every Step 2.3 measurement used f020e2 through a variant config, while the committed defaults stayed at the original values.
    - Nobody had measured those since round 5, where they gave 64–74 interceptions a match (real 14–26), 13–15 throw-ins and 69–77 minutes of ball in play.
    - So a play-test of the latest commit showed a state no step was working on.
  - **Measured:** `ref-2.3b2-p40` (200 matches per division, seed 21) is this exact build. Everything since d7ccf17 is behind the switch, and the golden values didn't move until this commit. Figures are in "The play-test build" below.
  - **Still provisional:** 2.3e sets the final values.
    - Conflict, already flagged in the continuation plan: e2's length spread is wider than real long passes plausibly are, and distance terms can't make weaker passers less accurate.
    - It stays until 2.3e's rating terms take over part of it.
- **2.3c, WIP, unchanged by this commit. Done in iteration 2** (from the reviewer's notes on iteration 1):
  - `_run_distance`: receivers and chasers move as `_move_players` runs an urgent player (top speed from stamina, own acceleration), replacing a flat 0.9 share.
  - The receiver runs for the intended point during his read delay, and only the ground beyond that is slack for a pass that's off.
  - A keeper in his own box reaches 2.4 m and gathers about 95%.
  - Only defenders already at a dropping ball, plus the one quickest to it, contest it.
  - Short throws are estimated with skill 85, as `start_pass` plays them.
- **Quick check with the switch on, iteration 2** (`scratchpad/honesty_check.py`: 6 synthetic matches, f020e2 settings; indicative):
  - throw-ins are honest (estimate gaps −0.03 to −0.01);
  - long balls are now slightly overrated (+0.05);
  - medium passes are still overrated (+0.10; the 0.8–0.9 decile completes 69%);
  - short passes are overrated (+0.06);
  - crosses are underrated (−0.13).
- **Key finding, which changes 2.3c's scope:** with honest estimates, long balls vanish (0.2% of passes, against Opta's 11.7%).
  - Their estimate is now about right (~0.5), but the decision values (`threat`, `RETAIN`, `loss_cost`) never make a 50% long ball worth playing.
  - Real teams go long mostly under pressure in their own half, against a high press, or when the short options are covered: situations where losing a short pass is costly.
  - The old estimate's +0.10–0.16 optimism about long balls had been standing in for that.
  - **So 2.3c needs a second half: calibrate the decision values with honest estimates.** Candidates:
    - the loss cost of a short pass under pressure deep in our own half, which also covers the high-regain leak;
    - the territorial value of a long ball;
    - the passing-direction instruction's weight.
  - The acceptance check must include the pass mix (long-ball share and cross share in range), not only the reliability table.
- **Iteration 3 (1 Oct, behind the switch), with `.claude/skills/calibrate-engine/estimate_parts.py`:**
  - That diagnostic splits the estimate into its parts (`EstimateParts`: path, reach, arrive, secure) and compares each with what happened to the passes played.
  - **What it found:**
    - The overrating of ground passes was almost all balls that never reached the receiver: medium passes predicted .032, actual .115.
    - Mostly that was physics: receivers overran the ball's line (fixed as P6), and e2's length error applies to ground passes too (P7).
  - **The estimate now follows ground passes through their errors** (`_ground_arrival`):
    - a 5×5 Gauss-Hermite grid over the angle and length errors;
    - meeting points 0, 3, 6 or 10 m on along the path;
    - soft balls stopping short;
    - the arrival pace feeding the first touch.
  - **Also:**
    - first-touch pressure uses the marker's distance at the ball's arrival;
    - the path counts an opponent from the ball's first metre (blocks) and one just beyond the receiver.
    - Two fitted shares in `passing.yaml`: `estimate.adjust` 1.0 (a receiver's running after his read delay goes into getting to a pass that's off) and `estimate.closing` 0.25 (how much opponents close a pass's path and the receiver).
  - **Result** (12 synthetic matches, qualities 62 and 78, P6 in; estimate against completed):

    | Band | Estimate | Completed |
    |---|---|---|
    | Short | .942 | .926 |
    | Medium | .906 | .876 |
    | Throws | .842 | .829 |

    - The 0.8–0.9 deciles are within +4.
    - Medium's 0.6 decile is −9: interceptions and pressured touches are still over-predicted for risky passes.
    - These move again with P7, so re-run the diagnostic after it.
- **What remains for 2.3c, in order:**
  1. Ground passes: re-check after P7, and tune `adjust` and `closing` if the deciles moved.
  2. Crosses underrated (estimate .03 against .15–.20 completed). Make `_landing_chance` and the arrival for crosses follow `_aerial`:
     - any attacker within 3 m of where it drops can win it;
     - with no defender there, he wins it outright, without a first-touch roll.
  3. Calibrate the decision values, as above.
  4. Then the reliability table within ±5 points per decile **and** the pass mix in range. Then the slow honesty test, switch it on, a 200-match measurement, golden values, delete `_heuristic_success`, and commit.
- **Tests:**
  - `just lint` is clean;
  - all 139 backend tests pass, with the golden values re-recorded for the new defaults;
  - `just e2e` (smoke and live) passes against a fresh :8765 with no browser errors;
  - copies of both save slots load on a :8765 server and play their next match (about 6 s each):
    - slot 1, Grimsby: the manual save and the autosave;
    - slot 2, Chelsea: the autosave.
  - The saves are schema 3, the same as the old :8000 build, so no migration runs.
- **Next task:** 2.3c remaining items 1–4 above. The quick check recipe:
  - `cfg-dev` = the checkout's `data/config` with `honest: true` (f020e2 is now the default);
  - then `FOOTSIM_CONFIG_DIR=/private/tmp/claude-502/cfg-dev uv run python <scratchpad>/honesty_check.py`;
  - the script is also described in this checkpoint, if the scratchpad is gone: 6 synthetic matches (3 at q62, 3 at q78), then `probe.aggregate` and `probe.reliability`.
- **Calibration:** nothing is running. Pin the worktree first for any batch.
- **Unresolved:** 2.3c (WIP), 2.3d–2.3f, C1, 2.4, 2.1 and 2.6. The verified engine bugs still open:
  - onside through balls are dropped;
  - offside awareness re-rolls every decision;
  - slow tempo gets an accuracy bonus;
  - the card rules;
  - stale duel engagements (2.4);
  - counter holds after the side already in possession gains a loose ball (E).
- **Measured on 1 Oct (`ref-p7`), with the step that owns each:**
  - **ENG1 shot excess** (37.5 a match):
    - Its sides get into the box 27 times per team per match, against ENG4's 17, and each box entry yields 0.6–0.7 shots.
    - The shots are mostly inside the box (16–22% from outside, real 30–42%) and weak (0.06–0.07 xG, real 0.09–0.12).
    - Stronger attacks beat stronger defences too easily: 2.3f (attack against defence by rating). Then shot selection under pressure in the box.
  - **Heavy touches:** 94 a match in ENG4 and 66 in ENG1, about 9% of receptions against roughly 3% in real football.
    - `control.receiver` 0.95, with `touch_skill` 0.1, gives an ordinary player about 92% clean control before any pressure.
    - 2.3e: control by rating.
  - **Pass accuracy falls as quality rises** in ENG1 (.927 for sides rated 70–75, .895 for 80–85). Real football is the other way round.
    - Weaker sides played safe, sideways and backwards; P11's long-ball value should change that. Check in `ref-p11`, then in 2.3e.
- **Play-testing on :8000, the user's game.** It runs 66a92c7 (play-test fixes P1–P5), restarted at 01:40 on 1 Oct after a check showed no connections. Earlier: 17635e6 from 01:28, and 1de6591 from 21:37 on 30 Sep.
  - The log is `/private/tmp/claude-502/demo-server.log`. Earlier builds' logs are kept next to it as `demo-server-20260928-build.log`, `demo-server-1de6591-build.log` and `demo-server-17635e6-build.log`.
  - A restart clears the loaded career, so the user loads it again from the start page. Both slots were listed unchanged after the restart.
  - Until 30 Sep its backend dated from 28 Sep (Phase A), while it served the 30 Sep frontend from `frontend/dist`. The frontend is read from disk; the backend isn't.
  - To update it later: `cd frontend && npm run build`, then restart :8000 with the `run-footsim` skill, once `lsof -nP -iTCP:8000 -sTCP:ESTABLISHED` shows no connections.
  - Automated checks use a throwaway :8765 with a temporary `FOOTSIM_SAVES_DIR`; none is running now.
  - **Note:** this is an intermediate calibration state; see "The play-test build" below.
- **Housekeeping:** `stash@{0}` (local 2.1/2.2/2.5 work from before the cloud merge) is superseded by the cloud versions and can be dropped.

## The play-test build (what to expect)

**Measured:** `ref-2.3b2-p40`, real squads, seed 21, 200 matches per division. Per match:

| | League Two (ENG4) | Premier League (ENG1) | Real |
|---|---|---|---|
| Goals | 2.92 | 3.67 | PL 2.65–3.05; EFL 2.45–2.85 |
| Shots | 30.0 | 37.1 | PL 23–27.5; EFL 22–26 |
| Pass accuracy | .817 | .812 | PL .80–.85; EFL .74–.81 |
| Long-ball share | .039 | .103 | PL .095–.14 |
| Interceptions | 15.7 | 15.7 | 14–26 |
| High regains | 41.8 | 31.2 | 10–17 |
| Throw-ins | 37.8 | 52.2 | PL 32–42; EFL 32–44 |
| Ball in play (min) | 65.3 | 58.1 | PL 54–60; EFL 52–60 |
| Offsides | 6.4 | 4.9 | 2.5–4.5 |
| Fouls | 8.4 | 14.1 | 20–24.5 |

**Known issues, and the step that addresses each,** so play-test notes can focus on anything new:
- **Too many shots, and too many goals in the Premier League.** One striker can take 10 or more shots: 13 in both 30 Sep test matches.
  - No step owns shot selection yet.
  - 2.3c's honest estimates should cut the overrated crosses and long balls that feed it.
  - Re-measure after 2.3c, and add a step if it's still high.
- **Too many turnovers high up the pitch** (high regains): 2.3c's decision values, then 2.3e.
- **Few fouls, so few cards:** 2.4.
- **Too many offsides:** 2.3d.
- **Too many Premier League throw-ins:** 2.3e.
- **League Two:** too much ball in play, and it goes long too rarely. 2.3e's rating terms, then C2's styles.
- **Static shape:** players hold a fixed shape, and team phases flicker. Phase D.
- **Tactics:** aggressive and direct are too strong, and slow tempo gets an accuracy bonus. C1.

## Play-test fixes (the user's play-test of 1de6591, 30 Sep; each is its own checkpoint)

The user also said save files may be deleted if they ever get in the way of the new engine. Not needed so far: both slots load on the current build.

- [x] P1 **Hand-picked starters showed as 99.** `LineupPicker.pick` forces a fixed player into his slot with a score of 1e6, and reported that score, capped at 99, as his rating.
  - It reached the tactics screen, the live subs panel's OVR and the tie-break in a mid-match formation change.
  - Results were never inflated: the user's matches run on the agent engine, which plays from attributes.
  - Saves store only slot → player, so nothing stored was wrong.
  - Fixed: fixed players keep their real slot rating. `test_lineup.py` fails without the fix. Golden values unchanged.
- [x] P2 **The set-piece taker ran back and forth before the restart.**
  - **Cause:** the taker was an urgent player, and urgent players run at full speed with no braking, so he ran past the spot and back until the restart was due.
  - **Traced** in 2 synthetic matches: 6–19 turns a restart (corners 19, throw-ins 9) at up to 8 m/s, overshooting by 3–6 m.
  - **Fixed:** a `settle` flag gives the taker the arrival braking that forward runners already have. He jogs to the ball and runs only if jogging would make him late (`restarts.yaml` `taker_hurry_margin` 2 s).
  - **After:** 0 turns, at most about 1 m of overshoot.
  - **Restart waits are unchanged** on 4 seeds: throw-ins 15.6 s (before 16.3), goal kicks 27.1 (28.0), corners 31.7 (32.1). Ball in play 62.4 minutes (61.8).
  - **Tests:** `test_a_taker_waits_on_the_ball_instead_of_running_past_it` fails without the fix. Mac golden values re-recorded with a History note.
- [x] P3 **The live viewer skipped actions:** a pass reached a player, then the picture jumped to the other side in possession.
  - **Cause:** the server runs the engine a little ahead of the screen (`lookahead_seconds`), and pausing, resuming and changing speed or mode restarted its clock from the engine's time, not the screen's.
    - So the screen fell behind by up to `lookahead × rate` with each change: 18 match seconds when slowing from 8×.
    - The viewer then jumped ahead once it was too far behind.
  - **Simulated** with the real LiveSession and the viewer's playback ported line for line (scratch `viewer_sync.py`, a typical watch with speed changes and pauses): jumps of 12.9, 14.9 and 18.3 match seconds, each on slowing to 1×.
  - **Fixed:**
    - `LiveSession.shown(now)` is the one timeline. Pause, resume, speed and mode carry on from the moment on screen, and `pause()` is also used on connect and disconnect.
    - Every message carries `shown` and `play_rate`, and the viewer steers its playhead to them, snapping only when far out (a highlight, a hidden tab).
    - Highlights replay at `presentation.yaml` `highlight_rate` (18) on both ends, and the next skip waits until the viewer has seen the whole highlight.
    - At high speeds every frame where the ball changes hands is kept, so a pass is seen from foot to foot.
  - **After:** the same simulation shows no jumps and no frame step faster than 1.6× the rate.
    - In Chromium (`e2e/live.mjs`, which now samples the time the pitch draws via `canvas.dataset.t`): the largest step in about 100 ms after slowing from 8× to 1× is 2.7 match seconds, a smooth catch-up.
  - **Tests:** `test_the_picture_carries_on_through_speed_changes_and_pauses`; the frame-limit test now also checks that every touch is sent. Golden values unchanged (presentation only).
  - **Also:** `e2e/smoke.mjs` no longer reports the 409 a fresh server's start page gets for `/api/career` (no career loaded yet, as intended).
- [x] P4 **Goals: a 3-second pause and a banner with the scorer and any assist.**
  - **The hold:** `LiveSession` collects each goal from the engine's log, which now carries `scorer_id` and `assist_id`; a substitution can follow at the kick-off in the same tick, so slots won't do.
    - It adds a `Hold` to the timeline, and `shown` stops there for `presentation.yaml` `goal_pause` (3) real seconds at any speed, highlights included.
    - The engine runs ahead of the screen, so the hold is in place before the picture gets there.
    - Pausing or changing speed during a hold keeps only the time it has left.
  - **Messages:** each one carries `holding` (scorer, assist, own goal, penalty, clock, score), `hold_at` and `server_time`.
  - **The viewer:**
    - its playhead stops on `hold_at`;
    - it puts the server's `shown` at the moment the server meant, using the smallest clock offset seen. This removes the lag from message delivery: about 2 match seconds at 8×.
    - `GoalBanner` shows once the picture reaches the goal.
    - The scoreboard counts a goal only once it has been seen; the commentary already did.
  - **Tests:**
    - `test_a_goal_holds_the_picture_while_the_scorer_is_shown` and `test_goal_pauses_never_change_the_result`;
    - `e2e/live.mjs` watches for the banner at 8× (into the second half if need be) and checks the picture holds still, as it did for "GOAL! Evanilson, Assist: Ryan Christie";
    - after slowing from 8× to 1×, the largest step in about 100 ms is 1.3 match seconds;
    - golden values unchanged.
- [x] P5 **Sim to date** (Phase I, basic).
  - **Where:** a "Sim to…" menu beside Continue: one week, one month, end of season, or a chosen date.
  - **The step:** `world/career.py` `sim_step` either plays the user's match of the day as Instant does, or advances to his next match day or the target, whichever comes first.
    - The target day itself is left to the user, so its match can still be watched.
    - The season's end (rollover after the play-offs) stops it too.
  - **The job** (`api/sim.py`): `POST /api/career/sim {until}`, `GET` for progress, `POST /api/career/sim/stop`.
    - A background thread takes the write lock per step only.
    - It autosaves after each of the user's matches and at the end, and is abandoned if another career is loaded.
    - Continue, instant play and live matches are refused while it runs, and it won't start during a live match.
  - **The page:** a progress window (bar, current day, results as they come, Stop), then a summary with the results and the news. `CareerOut` gained `season_end`.
  - **Stop conditions:** the date, the season's end, Stop. More can follow (injuries, offers) once those systems exist.
  - **Tests:**
    - `tests/integration/test_sim_to_date.py`: plays every user match before the date and none after; refuses Continue meanwhile; autosaves; stops on request; refuses a date not ahead.
    - `e2e/smoke.mjs` sims a week from the browser.
- Later (the user agrees): transfers and the other management systems.

## Play-test round 2 (the user, 1 Oct; each is its own checkpoint)

The user asked whether the engine or the management features (transfers, academy) should come first, and to do whatever makes the game a finished product most effectively.

**The order chosen:**
1. **First, the engine problems the user can see in a match:** misplaced passes in build-up (P6, P7).
2. **Then the cheap, visible fixes:**
   - the sim summary covering the season summary (P8);
   - more formations (P9);
   - players developing during the season (P10).
3. **Then 2.3c's remaining calibration and the rest of the plan.** The invisible parts are time-boxed.
4. **Transfers and the academy come later,** each as its own phase once matches feel right. They are big systems, and half-built ones help nobody.

- [x] P6 **Receivers ran through the ball's line.**
  - A pass receiver is an urgent player, and urgent players never brake, so after reading a pass he sprinted at the nearest point of its path and overran it. The physics then had him miss passes he should take.
  - **Found by 2.3c's honesty diagnostics:** safe-looking short passes (estimated 0.96) failed 8.0%. Two thirds of the failures were balls the receiver never got within 1.3 m of.
  - **Fixed:** the receiver gets the arrival braking from P2 (`settle`), and stops on the line.
  - **After:** those passes fail 4.1%, matching the estimate. Medium passes complete .92 against .84 in the same synthetic matches.
  - Overall pass accuracy will rise, likely above the real ranges. P7 and 2.3e bring it back through mechanisms (execution by ratings, composure, pressure), not by undoing this.
  - **Tests:** `test_a_receiver_stops_on_the_balls_line_instead_of_running_through_it` (4.8 m/s at the ball without the fix). Mac golden values re-recorded with a History note.
- [x] P7 **Misplaced passes from the back without pressure** (the user: real teams rarely do it; suggested composure or pressure).
  - **Cause, measured:** e2's length error (`length_per_metre` 0.022) applies to ground passes too. A 20 m ground pass has a 44% length spread, so 48% are mis-hit by more than 30%, and soft back passes stop short.
  - **Done:**
    - `execution` splits each distance term: `per_metre` 0.0015 and `length_per_metre` 0.008 for any pass (the original values), plus `lofted_per_metre` 0.0065 and `lofted_length_per_metre` 0.014 for a ball in the air. Lofted balls keep e2 exactly (0.008 / 0.022).
    - `execution.composure` 0.5: pressure costs (1 − w) + w · 2 · (1 − composure/100), so 1 at composure 50, 0.7 at 80 and 1.2 at 30. With no opponent near, composure makes no difference.
    - The estimate uses the same `pass_error`.
  - **Tests:** `test_a_ball_in_the_air_goes_astray_more_than_one_on_the_ground` and `test_composure_decides_what_pressure_costs`. Mac golden values re-recorded with a History note.
  - **Measured** (P6 and P7 together, real squads, seed 21, 200 matches per division, `reports/engine/step2.3/ref-p7`; before → after):

    | | ENG4 | ENG1 | Real |
    |---|---|---|---|
    | Pass accuracy | .817 → .922 | .812 → .905 | PL .80–.85; EFL .74–.81 |
    | Medium completed | .810 → .938 | .829 → .946 | ~.83–.87 |
    | High regains | 41.8 → 19.5 | 31.2 → 15.8 | 10–17 |
    | Throw-ins | 37.8 → 19.8 | 52.2 → 31.5 | PL 32–42; EFL 32–44 |
    | Ball in play (min) | 65.3 → 75.3 | 58.1 → 65.8 | 52–60 |
    | Goals | 2.92 → 1.61 | 3.67 → 3.11 | PL 2.65–3.05; EFL 2.45–2.85 |
    | Shots | 30.0 → 20.7 | 37.1 → 37.5 | PL 23–27.5; EFL 22–26 |
    | Long-ball share | .039 → .034 | .103 → .094 | PL .095–.14 |

    - **Better:** the build-up leak is gone (high regains in range for ENG1, near it for ENG4), and ENG1's throw-in conflict is resolved.
    - **Worse:** passing is too clean, so the ball is in play too long and ENG4 scores too little.
    - **Not undone:** both fixes removed unrealistic mechanics, and undoing them would bring back the user's complaint.
    - **The missing realism is the pass mix:** ENG4 plays fewer long balls than ENG1, the reverse of real football. See P11.
- [x] P11 **Decision values: a failed pass is lost where it fails** (2.3c item 3, brought forward).
  - `_pass_options` charged every option the loss cost of the passer's own position, so a 40 m ball out of trouble was costed as if lost at the centre-back's feet. Long balls were almost never worth it.
  - **Done:**
    - a pass's failure is costed where it's lost: a lofted ball where it lands, a ground pass midway (`pitch.loss_cost` takes arrays now);
    - a shot is charged the possession it gives up when it doesn't go in, (1 − xG) × the loss cost where it's taken. Shots had ignored that, so players shot too readily.
  - **Indicative** (4 synthetic matches at quality 62, before → after):

    | | Before | After |
    |---|---|---|
    | Pass accuracy | .913 | .836 |
    | Long-ball share | .052 | .163 |
    | Throw-ins | 24 | 38 |
    | Ball in play (min) | 73 | 61.5 |
    | High regains | 19 | 14 |
    | Shots | 22 | 31.5 |
    | xG per shot | .073 | .075 |

    - Without the shot term, shots were 35 at .056 xG each.
  - **Shots stay too many.** Attacks reach the box too easily against static defensive shapes: Phase D.
  - **Tests:** `test_a_long_ball_risks_the_ball_where_it_lands_not_at_the_passers_feet`. Mac golden values re-recorded with a History note.
  - **Measured** (`reports/engine/step2.3/ref-p11`, 200 matches per division, P7 → P11):

    | | ENG4 | ENG1 | Real |
    |---|---|---|---|
    | Pass accuracy | .922 → .869 | .905 → .824 | PL .80–.85; EFL .74–.81 |
    | Long-ball share | .034 → .106 | .094 → .239 | PL ~.12 |
    | Goals | 1.61 → 2.29 | 3.11 → 4.35 | PL 2.65–3.05; EFL 2.45–2.85 |
    | Shots | 20.7 → 28.4 | 37.5 → 48.4 | PL 23–27.5; EFL 22–26 |
    | Ball in play (min) | 75.3 → 67.6 | 65.8 → 54.4 | 52–60 |
    | High regains | 19.5 → 15.8 | 15.8 → 12.7 | 10–17 |
    | Offsides | 7.3 → 12.5 | 5.9 → 8.1 | 2.5–4.5 |
    | Shots from outside the box | .22 → .12 | .16 → .08 | .30–.42 |

    - **Right for ENG4.** For ENG1 it's too much: Premier League sides pass long well, so with territory valued they went long a quarter of the time. Defences can't deal with long balls yet (Phase D), so box entries, shots and goals ran away.
    - **More offsides:** long balls met the per-decision offside re-roll (P12).
    - **Long shots almost vanished:** the shot term weighs most on low-xG shots. Known; revisit with shot selection.
    - **Not shipped to :8000** in this form; P12 below adjusts it.
- [x] P12 **Offsides, and P11 softened.**
  - **Offside awareness:** the passer re-rolled whether he noticed an offside at every decision, so sooner or later he played it.
    - Now he notices any receiver beyond his blind spot (`passing.yaml` `offside_blind_spot` 1.0 m × (1 − decisions/100), about 0.3 m at decisions 70), judged on the receiver's position as the law has it.
    - No offside filter at throw-ins, goal kicks or corners.
    - Indicative (4 matches, quality 62): offsides 14.5 → 4.25.
  - **Through balls in behind stay rare** through the old random filter: a stopgap until defenders track runners (Phase D).
    - Without it, through balls jumped from 103 to 154 a match and goals to 5.75 (4 matches): defences can't deal with balls in behind yet.
  - **P11 softened:** `passing.yaml` `loss_where_lost` 0.5 costs a failed pass halfway between the passer's feet and where it's lost.
    - Indicative (4 matches each), quality 78: long balls .09, shots 32, accuracy .91, ball in play 68.5 min. Quality 62: .086, 24 shots, accuracy .88, 68 min.
    - The 200-match batch decides between 0.5 and 1.0.
  - **The in-match manager's press reading,** re-measured over 8 seeds now that sides go long out of the back:
    - a high press reads 1.38–1.58 and a normal one 1.02–1.51;
    - so `tactics.yaml` `high_press` 1.02 → 1.33, and `min_samples` 50 → 30 (sides spend less time on the ball near their own goal).
  - **Tests:** `test_a_passer_sees_a_clear_offside_but_may_miss_a_marginal_one`. The long-ball test now checks the configured share. Mac golden values re-recorded.
  - **Measured** (`reports/engine/step2.3/ref-p12`, 200 matches per division; p40 is what :8000 ran before, P11 is at full strength):

    | | ENG4 p40 → P11 → P12 | ENG1 p40 → P11 → P12 | Real |
    |---|---|---|---|
    | Goals | 2.92 → 2.29 → 1.85 | 3.67 → 4.35 → 3.75 | PL 2.65–3.05; EFL 2.45–2.85 |
    | Shots | 30.0 → 28.4 → 22.8 | 37.1 → 48.4 → 42.0 | PL 23–27.5; EFL 22–26 |
    | Pass accuracy | .817 → .869 → .907 | .812 → .824 → .874 | PL .80–.85; EFL .74–.81 |
    | Long-ball share | .039 → .106 → .059 | .103 → .239 → .154 | PL ~.12 |
    | High regains | 41.8 → 15.8 → 18.6 | 31.2 → 12.7 → 14.5 | 10–17 |
    | Throw-ins | 37.8 → 27.7 → 22.5 | 52.2 → 49.5 → 41.0 | PL 32–42; EFL 32–44 |
    | Ball in play (min) | 65.3 → 67.6 → 74.0 | 58.1 → 54.4 → 61.3 | 52–60 |
    | Offsides | 6.4 → 12.5 → 2.9 | 4.9 → 8.1 → 1.6 | 2.5–4.5 |
    | Fouls | 8.4 → 13.5 → 13.1 | 14.1 → 19.6 → 20.0 | 20–24.5 |

  - **Shipped to :8000:** P12 fixes what the user raised (misplaced calm passes, the high-turnover leak) and offsides, with ENG1 throw-ins and fouls now in range.
  - **Left over:**
    - passing a little too clean;
    - League Two scoring too little (1.85);
    - Premier League shots too many (42).
  - **No single `loss_where_lost` fixes both divisions.**
    - Premier League sides go long more than League Two ones at any value, the reverse of real football, because the heuristic estimate overrates long balls most for good long passers.
    - So the real fix is 2.3c's honest estimate, then Phase D's defending against long balls and runners (2.3f for the shots).
- [x] P8 **Sim to the season's end:** its summary sat over the season summary, and closing it closed both.
  - The results now come first, in their own window. Its button opens a separate "Season summary" (or "News") window with every item, where only the last 12 were shown before. That window stays until it's closed.
  - At the season's end the summary leads with the user's finish: position, record, goals, points and outcome. The job reads `league_final` and reports it as `SimStatusOut.season_final`.
  - **Checked:**
    - `e2e/smoke.mjs`: one week, no news that week.
    - The new `e2e/season.mjs`: a whole Arsenal season simmed from the browser. "The season is over. Now Thu, 1 Jul 2027", then a separate Season summary: "4th in the Premier League · Won 18, drawn 9, lost 11 · goals 88–72 · 63 points". No browser errors.
  - **Follow-up fix:** "End of season" asked for the season's end + 60 days. From 1 July that is over the job's 400-day limit, so it was refused (400) from a season's start; it worked mid-season. It now asks for the day after the calendar's end, and the rollover stops it.
- [x] P9 **Only 3 formations:** eight more, as data: 3-5-2, 3-4-3, 3-4-2-1, 5-3-2, 5-4-1, 4-1-4-1, 4-4-1-1 and 4-1-2-1-2 (diamond), 11 in all.
  - Wing-backs take their attacking width from the `wing_back` role. The slots only drop them into a back five without the ball.
  - The user picks them on the tactics screen and during matches.
  - **AI clubs still choose from 4-3-3, 4-2-3-1 and 4-4-2** (`world/context.py` `AI_FORMATIONS`), so calibration is unchanged. Widen that once Phase D gives formations real phase shapes.
  - `test_formations.py` plays five minutes in each. One synthetic match each against a 4-4-2 ran clean.
- [x] P10 **Players develop as the season goes,** not only at its end.
  - The yearly model (`people/development.py`) now runs a twelfth at a time on the first of each month (`season.after_day` → `develop_players`), and the rollover no longer develops.
    - Growth is compounded so twelve months add up to the year's.
    - Decline is spread evenly, and the noise is scaled by √(1/12).
    - Minutes count over the past twelve months.
  - **News for the user:** a monthly "Player development." item names his players whose overall moved ("Improved: Harvey Cartwright 61→62 …").
  - **Cost:** about 1 s per month on the full world (17,849 players).
  - **Tests:** `test_development.py` (twelve months make a year; decline evenly). A year of monthly steps on a fresh Grimsby career changed 99% of players.

## Play-test round 3 (the user, 1 Oct: development and the overall)

The user asked for:
- **Development:** ratings rise through the season; in their prime (about 20–28) players reach their ceiling, with chances to go above it; decline from the early to mid thirties; a rare few, only "wonder players", keep their prime until they retire.
- **Monthly upgrades** go to specific stats, and when the overall goes up, every stat goes up with it.
- **The overall** sits too far above the six headline ratings: "a player with only 2/5 general ratings at 70 and the rest lower and their rating is like 76". Make them closer.

- [x] P13 **Development as the user described** (`people/development.py`, `data/config/rules/development.yaml`).
  - **Traits**, drawn once per player and kept in the new `player_development` table (schema 4, migrated on load):
    - his peak age (26–29);
    - the age his decline starts (31–33);
    - how far his ceiling sits above his potential (30% of players: +1–2, +3–4 or +5–7);
    - agelessness: 0.2% of ordinary players, 10% of those with potential 88+. His decline starts 4 years later and runs at half pace.
  - **Each month:**
    - before his peak age, a player closes a share of the gap to his ceiling (30–55% a year by age, scaled by minutes played in the past twelve months), so a regular reaches it by his peak;
    - he holds it, closing what's left slowly;
    - from his decline age he loses 0.5, 1.0, 1.6, 2.3, 3.0, then 3.8 overall a year, physical attributes first;
    - noise of 1 point a year (sd).
  - **The month's change is split:**
    - 40% lands on a few individual attributes, picked by how much his position values them; in decline, physical ones first;
    - 60% builds up as `progress` until it makes a whole point of overall. Then every attribute moves by one: every outfield attribute for outfield players, every one but the mental ones on the way down.
  - **News:** "Player development. Improved: Iwan Morgan 62→63, Alex Graham 54→55 (every attribute up). Declined: …"
  - **Measured on the full world** (a fresh career, a year of monthly steps, no matches played):
    - 0.73 s a month;
    - 62 ageless players (0.35%);
    - average overall change over the year: ages 15–21 +1.7, 21–25 +0.9, 25–29 +0.3, 29–32 0.0, 32–35 −1.0, 35+ −2.7. Young regulars grow about twice that, since minutes count.
  - **Tests:**
    - `test_development.py`: a regular reaches his ceiling by his peak and holds it; decline from his decline age, matching the table; ageless rare and mostly the best; a whole-point move lifts every attribute; individual moves touch a handful;
    - `test_migrations.py`: a schema-3 save gains the table.
  - **Not yet:** retirement doesn't exist, so "until they retire" waits for it (youth and academy phase).
- [x] P14 **The overall closer to the six headline ratings** (`ratings/overall.py`, new `data/config/overall.yaml`).
  - **Before**, measured on the base world: on average the overall wasn't above the headline ratings (within 0 to −3.6 of each group's top three). Specialists, though, sat well above most of theirs: Calvin Stengs, AM 77 (PAS 77, DRI 76, the rest 52–68); Dan Burn, CB 78 (DEF 77, PHY 81, PAC 43, SHO 38). The roles put almost all the weight on the position's 2–3 key attributes, as EA FC's overall does.
  - **Now** each role's weights are blended with the position's weights over all six headline ratings: `face_blend` 0.7, with per-group weights (a CB: DEF .38, PHY .25, PAC .15, PAS .12, DRI .05, SHO .05).
  - **Scaling:** `footsim calibrate-overall` now matches each group's mean and spread to EA FC 27's overall instead of a least-squares fit, which would have shrunk the spread and pulled the best players down. `overall_scaling.yaml` was refitted.
  - **Measured on the EA FC 27 players** (`scratchpad/p14_check.py`), against the roles alone:
    - one-dimensional players are 2–5 points lower: Burn 78→75, a CB with PAC 30 78→73, a CM with PAC 35 78→73, a ST with DEF 31 78→74;
    - rounded ones move within a point;
    - every group keeps its average and spread (change −0.05 on average, sd 1.5);
    - the top 30 are 1 point lower on average (−3 to +2): Mbappé 91, Haaland 89, Kane 86, Saliba 86;
    - correlation with EA's overall is 0.95–0.99 by group (r² 0.90–0.98).
    - CBs are still mostly above their third-best headline rating, as their SHO and DRI barely count.
  - **Potential stays consistent.** It was drawn relative to the old overall, so schema 5's migration moves each player's hidden potential by however much his overall changed, at his current attributes. His room to grow is unchanged. The pre-P14 scaling is kept in the migration for this.
    - On a copy of the user's Wrexham autosave: 0.6 s, potentials −0.6 on average (sd 1.4, −9 to +5).
    - New careers copy the base world (schema 2) and migrate the same way, so the base world needn't be rebuilt.
  - **The player page** outlines the three headline ratings that count most for his position, with a note that every one counts for something (`face_key` in the API).
  - **Development follow-ups:**
    - each attribute point now moves the overall less, so a month's individual moves touch more attributes (about 11 a month for a fast-growing 18-year-old when all of it is individual, 4–6 before);
    - the monthly news names a player only when his overall moved at least `news_min_change` (0.5) in the month. Before, someone sitting on x.5 flickered "80→81" then "81→80" in consecutive months.
    - The smoke and live e2e scripts close the monthly news window, which since P13 can open after "Continue".
  - **Golden values:** re-recorded for the Mac, with a History note. Synthetic players are drawn to hit a target overall, so their attributes change with it, and so do lineup picks.
  - **Tests:**
    - `test_ratings.py`: a one-dimensional CB falls at least 3 points further behind a rounded one; the key ratings still weigh most; the scaling keeps the source's mean and spread;
    - `test_migrations.py`: a schema-4 world's potentials move with the new overall, about 0 on average, and only once.
    - all 173 backend tests pass and `just lint` is clean;
    - smoke and live e2e pass on a fresh :8765 with no browser errors; a centre-back's page outlines PAC, DEF and PHY (Saliba 86).

## Play-test round 4 (the user, 1 Oct: arrows, history, cups, 2.3c)

The user asked to "continue with step 2.3c", and also for:
- **cup games** like the FA Cup and the Carabao Cup;
- **history:** where their club, and other clubs, finished in previous years;
- **an up (green) or down (red) indicator** by a player's overall, for "their latest overall form".

Order of work: the arrows (P15) and the history (P16) first, as they're small. Then 2.3c, with the cups (P17) written while 2.3c's batches run and checked between them.

- [x] P15 **Up/down arrows by a player's overall.**
  - Each month's development also updates a per-player `trend`: his monthly change in overall, smoothed (`trend_memory` 0.7 of last month's trend kept). It's stored in `player_development` (schema 6, migrated on load).
  - The squad, any club's squad and the player page show a green ▲ when the trend is at least `trend_shown` (0.12 overall a month, about 1.5 a year), and a red ▼ at −0.12 or below. The player page says "Rising lately" or "Falling lately".
  - **Measured on a fresh career** with no matches played (`scratchpad/trend_check.py`), share showing ▲/▼ after 11 months:
    - 15–21: 54%/0%;
    - 21–25: 33%/1%;
    - 25–29: 15%/3%;
    - 29–32: 6%/5%;
    - 32–35: 2%/21%;
    - 35+: 0%/71%.
  - A whole-point move (every attribute up) shows the arrow for about three months.
  - **Tests:** `tests/integration/test_development_trend.py` checks the sign by age; `test_migrations.py` checks that a schema-5 save gains the column. All backend tests pass and `just lint` is clean.

- [x] P16 **History: where every club finished.**
  - `GET /api/clubs/{id}/history`: a club's league seasons in this career, newest first. Final positions and outcomes come from `league_final`; the season in progress shows its position so far. It also counts titles, promotions (a lower league's champions included) and relegations.
  - `GET /api/seasons` and `?season=` on the table: past seasons' final tables, with each club's outcome (champions, promoted, play-off winners, play-offs, relegated).
  - **UI:**
    - a History card on every club page;
    - a "Club & history" link in the sidebar to the user's own club;
    - a season picker on the League page.
  - The career starts in 2026–27, so there's no history from before it: the real past isn't in the data.
  - `managed` is true for every season of the user's club, as a career has one club so far. Job changes would need a manager-history table.
  - **Checked** on a copy of the user's Wrexham save (now 22 Jan 2028), on a throwaway :8765: it loads in 0.35 s, running migrations v4–v6. History shows 2026–27 21st (42 pts) and 2027–28 19th so far. The 2026–27 Championship final table shows West Ham champions, Swansea play-off winners, three relegated.
  - **Tests:** `tests/integration/test_history.py`. All backend tests pass, lint is clean and the smoke e2e passes.

- [ ] **2.3c iteration 4** (behind `estimate.honest`, still off; the golden values are unchanged).
  - **Crosses** follow `_aerial`: `_cross_landing` averages over the cross's angle and length errors (5×5 Gauss-Hermite). At each landing point:
    - out of play loses it;
    - the keeper may claim it;
    - any attacker who gets within 3 m can win the header, outright if no defender is there, else against the best one.
  - **Long balls** follow the physics too: `_long_landing` over the same grid.
    - The receiver runs for the intended point until he reads the ball, then for where it's dropping; the nearest opponents go from the kick.
    - Both there: a header (`_long_ball_contest`). Him alone: his first touch. Otherwise a race for the loose ball (`reach_scale`).
  - **Quick check** (6 synthetic matches, qualities 62 and 78, honest on), estimate minus completed:
    - crosses −0.32 → −0.03 (estimate .197, completed .213);
    - long balls −0.33 → −0.12;
    - short +0.01, medium +0.02.
  - **The conflict this exposes:** with honest estimates, long balls all but vanish and shots explode. Synthetic sides take 70 shots a match and score 6.7–8.3, against 40 shots and 4.2 goals with the switch off.
  - **Measured on real squads** (200 matches per arm, seed 21, worktree at 09b1242; `reports/engine/step2.3/c4-off-*` and `c4-on-*`):

    | | ENG1 off | ENG1 on | ENG4 off | ENG4 on |
    |---|---|---|---|---|
    | Goals | 4.18 | 8.03 | 2.19 | 4.54 |
    | Shots | 41.6 | 75.9 | 23.7 | 52.7 |
    | Pass accuracy | .876 | .915 | .905 | .902 |
    | Long-ball share | .150 | .005 | .065 | .005 |
    | Throw-ins | 39.7 | 13.0 | 24.5 | 11.6 |
    | Interceptions | 18.8 | 31.1 | 20.2 | 29.1 |
    | Shots per box entry | .63 | .81 | .56 | .74 |
    - **Why** (`scratchpad/long_options.py`, 3,382 decisions with a long option): the best long option scores 0.04–0.05 utility below the best pass everywhere from x 0 to 70, even under pressure, because a safe short option (estimate .86–.96) is always there.
    - Real sides go long when the press has covered the short options and the build-up is risky. Our pressing doesn't cover them, and passes into and around the box complete about 90%.
    - The old estimate's pessimism about short passes (−0.10 to −0.15) was hiding this weak defending.
    - Neither `loss_where_lost` 1.0 nor `RETAIN` 0.005 brings long balls back (0.5–0.7%).
    - So the decision values can't be calibrated until defending covers options and the box (2.3f, Phase D6). **The switch stays off;** 2.3f comes before switching it on.
  - **Tests:** `test_passing.py` gains a cross being anyone's who gets to it, and a long ball being whoever's gets to where it drops.

- **P14's side effect on matches, found in this measurement.** The "off" arms against `ref-p12` (the same seed and engine, before P14):
  - Premier League goals 3.75 → 4.18; conversion .089 → .100; save rate .725 → .691; draws .275 → .200. Shots are unchanged at 42.
  - League Two goals 1.84 → 2.19; conversion .081 → .092. That's nearer the real 2.45–2.85, while the Premier League's is further from its 2.65–3.05.
  - **Cause:** the overall picks lineups and AI formations, and it now counts every headline rating. 6 of 20 Premier League clubs and 4 of 24 League Two clubs choose a different formation (mostly 4-3-3 → 4-2-3-1), and about one starter per club changes (`scratchpad/pick_diff.py`). Keepers aren't the cause: one club changes keeper, with the same shot-stopping (`scratchpad/gk_pick.py`).
  - **Kept**, as the user asked for the overall. Goal levels belong to 2.3f. If they should come back, the option is to pick lineups by role ratings without the headline blend, at the cost of slot ratings that differ from the overall shown.
- [x] P17 **Cups: the FA Cup and the Carabao Cup** (`world/cups.py`, `data/config/cups/`, calendar `cups:`).
  - **Formats** (`defs/cups.py`, validated in the loader):
    - **FA Cup:** single matches with extra time and penalties (no replays since 2024-25), semi-finals and final at Wembley. League One and Two start in the first round. The real cup's 32 non-league qualifiers aren't in the game, so the highest-ranked clubs are exempt in rounds 1 and 2 (48 → 32 → 20). The Premier League and Championship join in round 3, which has its 64.
    - **Carabao Cup:** the EFL's 72 in round 1, Premier League 9th–20th in round 2, the top 8 (no Europe yet) in round 3. No extra time (straight to penalties) except in the final; two-legged semi-finals.
  - **Ranks** for entry and exemptions come from last season's finish within the league, with promoted clubs below those who stayed up. A first season uses reputation.
  - **Dates** are in the season calendar (Carabao Cup on Tuesdays with a Sunday final in the March break; FA Cup on Saturdays), shifted to later seasons like everything else.
    - A round's `blocks` keep leagues off its date: FA Cup round 1 for Leagues One and Two, round 3 for the Premier League and Championship, and rounds 4 to the final for the Premier League.
    - Any other clash is rearranged at the draw: a club's league match within two days of its cup match moves to the nearest day both clubs are free. It prefers a midweek and a later date, stays within the league's dates, and keeps clear of cup dates.
  - **Each round** is drawn when the one before it ends (`cup_tie`, schema 7). Knockout rules come through `Decider`, so the live engine plays extra time and penalties as it does for play-offs.
  - **News:** your draw, exemption or exit, and every cup winner.
  - **UI:**
    - a Cups page: each round's ties and results, your tie highlighted, the rounds still to come, and a season picker;
    - round names on fixtures, the dashboard and the match day;
    - cup runs on club histories and in the season summary.
  - **A career already under way** starts its cups this season if their first round is still ahead: the first day played draws it, and league matches move around the ties as usual. Otherwise it starts them next season.
    - The user's Chelsea career (slot 3, saved on 1 Jul 2028, a new season's first day) gets them this season.
    - The Wrexham career (slot 2, 22 Jan 2028) gets them from 2028-29. On a copy simmed past the season's end, the rollover drew "Carabao Cup first round draw: Colchester v Wrexham (Tue 8 Aug)".
  - **Measured:** a whole watch-only season (`scratchpad/cup_season.py`, seed 5) takes about 20 s of quick-engine matches.
    - Arsenal won the FA Cup (3–1 against Spurs) and Aston Villa the Carabao Cup.
    - FA Cup: 91 matches, 18 went to extra time and 11 to penalties. Carabao Cup: 93 matches, 0 to extra time, 16 to penalties.
    - 78 of 2,036 league matches were moved for cup ties.
    - A new Wrexham career on :8765 plays its Carabao Cup first round on 11 Aug, before the league, and gets the draw news for every round.
  - **Bug found and fixed:** a rearranged match could land before its league had started (`test_clubs` caught Arsenal with two games played by matchday one).
  - **Tests:**
    - `test_cups.py`: the formats add up, and leagues keep clear of the rounds that block them;
    - `tests/integration/test_cups_season.py`, a whole season: every round has the clubs it should, both cups reach a winner, every match is played, no club plays twice within two days, league matches stay within their league's dates, and the next season's first round is drawn.
    - a save from before the cups starts them on its first day if the first round is ahead, once only.

## The approved order (1 Oct)

The user asked when other leagues (with their differences in quality), transfers and academies should come. The recommendation was approved ("Start the plan"); the reasoning is in the addendum at the top of `continuation-plan.md`.

The order, each its own checkpoint (or several):

1. **Believable matches:**
   - [x] 2.3f, attack against defence by rating (the rating symmetry; box defending's level goes to Phase D, below).
     - **Measured first** (`reports/engine/step2.3f/sweep0-q*`: equal synthetic sides, 120 matches each, seed 31, honest off):

       | Quality | Goals | Shots | Final-third entries | Box entries | Shots per box entry | xG per shot | Heavy touches |
       |---|---|---|---|---|---|---|---|
       | 58 | 3.0 | 31.3 | 62.0 | 34.5 | .454 | .068 | 71 |
       | 70 | 3.5 | 37.2 | 61.3 | 36.2 | .514 | .073 | 63 |
       | 82 | 4.7 | 49.3 | 63.3 | 39.5 | .624 | .082 | 51 |

       Entries into the final third are flat and into the box nearly so. Once there, better sides take far more and better shots. The finishing-against-keeper term already balances with quality, so creation in the box is what outgrows defending.
     - **Why:** no defender rating changed where a defender stood. `marking`, `concentration` and `positioning` were never read, and `def_positioning` only in the tackle score. Markers stood 1.8 m goal-side, going 45% of the way from zone to man for every defender alike.
     - **Iteration 1, WIP:** `data/config/match/defending.yaml`.
       - A marker stands closer goal-side and commits further to his man the better his `marking`: 1.8 m and 45% at marking 60, as before; about 1.4 m and 68% at 80.
       - Blockers reach further from the shot's line with `def_positioning`, and block more often with `bravery`. One blocker blocks at 0.28 at the reference; several combine to at most 0.65.
       - **Measured** (`sweep1`): worse. At quality 82, shots were unchanged (49.6) while goals rose 4.70 → 5.44 and xG per shot .082 → .090. Committing markers further to their man pulled them out of their zones and gave others better chances.
     - **Diagnosis** (`scratchpad/box_diag.py`): at quality 82, 37% of shots came straight after a carry in the box (5% at 58), taken with a defender about 2 m away. Two asymmetries:
       - a carrier judged his chance of keeping the ball from his own dribbling against a fixed 70, never against the defender in front;
       - the shooter's composure softened pressure, but the closing defender's quality never added to it. The same was true of a first touch, which only the receiver's own first touch decided (71 heavy touches a match at quality 58, 51 at 82).
     - **Iteration 2, WIP:**
       - a carrier weighs up the defender in his way with the duel's own scores (`duels.tackle_score` and `dribble_score`);
       - shot pressure grows with the closing defender's positioning and tackling (`shot_pressure`), the same model for the shot and the decision to take it;
       - first-touch pressure grows with the marker's marking (`touch_pressure`), in the physics and in the pass estimate;
       - iteration 1's commitment slope goes back to 0; its goal-side slope and the blocks stay.
       - On 2 matches per quality, carries in the box fell to 13% of shot sources at quality 82, but the shots came from passes, headers and through balls instead.
       - **Measured** (`sweep2`, the same 120 matches per quality as `sweep0`):

         | Quality | Goals before → now | Shots before → now | Shots per box entry | Tackles |
         |---|---|---|---|---|
         | 58 | 2.98 → 3.85 | 31.3 → 36.1 | .454 → .496 | 17 → 34 |
         | 70 | 3.53 → 3.86 | 37.2 → 39.2 | .514 → .532 | 24 → 38 |
         | 82 | 4.70 → 4.27 | 49.3 → 44.7 | .624 → .592 | 42 → 40 |

       - **The slope is largely fixed:** goals rise 11% from quality 58 to 82 (58% before), and shots 24% (58% before).
       - **The level rose at low quality:** weaker sides now run at defenders more, since the decision compares them with a defender of their own level instead of a fixed 70. Hence twice the tackles at 58.
       - **What remains is the level at every quality:** 36–45 shots a match against the real 23–27.5, 8% of them from outside the box against 30–42%, about 36 box entries per team, and xG per shot about .075 against .09–.12. Attacks reach the box too easily and end in weak shots there. That's the defensive shape: a compact block covering passing options and the box (Phase D2 TeamShape and D6 defending). It's also what keeps 2.3c off.
     - **On real squads** (200 matches per division, seed 21, `step2.3f/it2-*`, 4 workers), against `c4-off` at 09b1242:

       | | ENG1 before | ENG1 now | ENG4 before | ENG4 now | Real (PL / EFL) |
       |---|---|---|---|---|---|
       | Goals | 4.18 | 3.76 | 2.19 | 3.05 | 2.65–3.05 / 2.45–2.85 |
       | Shots | 41.6 | 40.3 | 23.7 | 31.4 | 23–27.5 / 22–26 |
       | xG per shot | .077 | .071 | .064 | .081 | .09–.12 |
       | Shots outside the box | .077 | .105 | .104 | .076 | .30–.42 |
       | Fouls | 20.0 | 25.0 | 12.0 | 19.9 | 20–24 / 20.5–24.5 |
       | Yellows | 3.9 | 4.4 | 2.2 | 3.5 | 3.4–4.3 / 3.3–4.2 |
       | Tackles | 42 | 55 | 29 | 56 | about 30–40 (duels.yaml's reference) |
       | Ball in play (min) | 61.6 | 61.7 | 73.5 | 70.1 | 54–60 / 48–54 |

       The two divisions now play much more alike (3.76 against 3.05 goals, where it was 4.18 against 2.19), as real leagues do. League Two's fouls and cards are near the real figures for the first time.
     - **Still off:** shots in both divisions; the share from outside the box; tackles; and the Premier League's fouls and yellows, now a little high. League Two's goals and shots went above range: its sides attack as boldly as stronger ones now, against defending that doesn't hold its shape.
     - **The memory note on 1 Oct:** the machine swapped hard during the first attempt (load 105, 2.8 GB of 4 GB swap), and the batch was stopped at the 1-hour limit. Re-run with 4 workers, one division at a time.
     - **The in-match manager re-measured:** `test_reads_a_high_press_from_the_pitch` failed. Pressed sides spend shorter spells near their goal now, so most high-press matches never collected the 30 looks a reading needs. On 12 seeds (`scratchpad/press_window.py`), `min_samples` 25 reads high presses at 1.46 on average against 0.97 for normal ones, with 64% of high presses read and no false alarms. Over each match he went direct in 8 of 12 pressed matches and 1 of 12 normal ones.
   - **Re-sequenced by this measurement:** switching 2.3c on, and 2.3e, wait for Phase D's shape and defending (D2, D6). Both need defending that covers passing options and the box: 2.3c's honest estimates find the safe short option otherwise, and 2.3e's better control would keep that possession longer. D2 and D6 run alongside the main track, as planned. The main track goes on: 2.4, then B2, then the world.
   - [x] 2.4, fouls and cards.
     - **Rules:**
       - a booked player's caution is applied once, to his chance of fouling in any duel. It used to scale his tackle rate and his foul chance, so second yellows almost never happened;
       - the card risk from aggression grows smoothly from 60 to 100, where it was a step at 80;
       - a foul that denies an obvious goal-scoring chance (Law 12: within 30 m, nobody covering in a 9 m corridor) is a red card, or a yellow for a challenge for the ball in the area, which is a penalty already. It carries a one-match ban;
       - an engagement a defender let lapse is sized up afresh instead of carried over.
     - **The probe:** fouls by source (tackle, take-on, tactical, aerial); second yellows, straight reds and DOGSO counted apart; take-ons as the carrier's duels only (it counted every duel).
     - **Measured** (200 per division, seed 21, `reports/engine/step2.4/`):
       - `cards1`: the caution on the tackle rate alone gave 0.33 second yellows a match, because booked defenders kept fouling attackers who ran at them;
       - `cards2`: caution 0.15 on the foul chance;
       - `cards3`, the values kept: caution 0.07 and straight reds 0.0007 a foul.

       | cards3 | Premier League | League Two | Real (PL / EFL) |
       |---|---|---|---|
       | Fouls | 23.8 | 18.8 | 20–24 / 20.5–24.5 |
       | Yellows | 4.20 | 3.34 | 3.4–4.3 / 3.3–4.2 |
       | Reds | 0.185 ±0.06 | 0.085 ±0.05 | 0.08–0.18 |
       | of which second yellows | 0.08 | 0.02 | |
       | Penalties | 0.215 | 0.12 | 0.15–0.30 / 0.15–0.32 |
       | Fouls by tackle / take-on / aerial | 13.8 / 10.9 / 0.8 (`cards1`) | 11.6 / 7.7 / 0.4 | |
       | Take-ons, success | 28, 81% | 26, 82% | success about 45–60% |

     - **Still off, recorded:**
       - League Two's fouls and penalties are a little low;
       - tackles are about 57 a match against roughly 28–45;
       - take-ons succeed 81% of the time against about half: the attacker usually runs at whoever is nearest, often a forward or midfielder with poor tackling, and `take_on_edge` favours him.
       - These belong to the duel volume and choice of opponent: Phase D's defending (D6) and transitions.
   - [ ] 2.3c switched on, with the decision values calibrated (long-ball and cross shares in range): after D2 and D6.
   - [ ] 2.3e, control by rating: after D2 and D6.
2. - [x] **B2, the fast engine** as a surrogate of the agent engine. Moved up from Step 5.
     - **Tooling** (dc6d5ee):
       - batch reports keep a row per match;
       - `--division ENG1+ENG4` pools divisions, for fixtures across them as cup ties are;
       - `footsim cross-engine REPORT` replays a report's fixtures 20 times each with the fast engine and compares the two.
     - **Measured** (agent engine at 0488313, seed 41, 200 matches per sample, `reports/engine/b2/`):

       | Sample | Goals agent / fast | Home–draw–away agent | fast | Home edge agent / fast | GD per rating point agent / fast |
       |---|---|---|---|---|---|
       | Premier League | 3.71 / 2.74 | .435 .240 .325 | .432 .238 .330 | +0.38 / +0.39 | +0.18 / +0.23 |
       | League Two | 3.08 / 2.76 | .385 .285 .330 | .454 .253 .292 | +0.27 / +0.38 | −0.06 / +0.23 |
       | Both pooled (gaps up to 15 points) | 4.13 / 3.44 | .445 .165 .390 | .457 .145 .398 | +0.20 / +0.35 | +0.24 / +0.22 |

     - **Reading:**
       - Where rating gaps are big enough to measure (the pooled fixtures), the engines respond to quality alike: +0.24 against +0.22 goal difference a point.
       - Within League Two, gaps are too small for 200 matches to give a slope.
       - Home and draw rates agree within a few points. The fast engine's home edge is a little stronger, at the real level (about +0.3 to +0.4).
       - The goal level differs, and the fast engine is the one at the real level (2.65–3.05 / 2.45–2.85). The agent engine's excess is Phase D's defending. So **no fast-engine values changed:** surrogate the agent engine's rating response, not its known excess.
       - Re-run `cross-engine` after D2 and D6 bring the agent's goals down.
     - **Test:** `test_cross_engine.py` pins the fast engine's behaviour on 600 synthetic fixtures: +0.23 a point, home edge +0.36, 3.3 goals at those quality spreads (bounds 0.12–0.35, 0.15–0.6, 2.4–3.6).
3. - [x] **W1, retirement and a yearly youth intake** (academies, part one). `world/lifecycle.py`, `data/config/rules/lifecycle.yaml`, run at each season's end before the new fixtures.
     - **Retirement:** chances by age, from 3% at 32 to 95% at 40. Keepers retire two years later; the ageless, and players still 78+, later still; players under 55 sooner. Free agents nobody has signed leave the professional game: at least half of them each season, at any age, until transfers can sign them. Retired players keep their history (`player.retired_on`, schema 8) and drop out of development.
     - **Youth intake:** every club takes in 2–5 youngsters a year by reputation (standing in for its academy until W5), aged 15–17.
       - Attributes come from the position-fitted synthetic model at a low quality (mean overall 40–52 by reputation).
       - Potential is drawn on top (mean 58–72, sd 8, at least 6 above his overall, at most 94).
       - Most are from the club's own country, the rest from its players' countries, named from the save's own players of that country.
       - Each gets a youth contract to the end of the season he turns 19, at the minimum wage.
     - **Squads:** computer-run clubs with more than 34 senior players release their weakest down to 31: worst overall first, young players counting half their remaining potential, three keepers kept. Youngsters on youth contracts under 19 are in the youth squad and don't count. The user's squad is never trimmed: a Release button on their own players ends a contract (`POST /api/players/{id}/release`).
     - **News:** your retirements and youth intake (with the coaches' pick of it), and notable retirements elsewhere (80+).
     - **Balance over ten season-ends** on a fresh career (no matches or development, `scratchpad/turnover_balance.py`):
       - the world goes from 17.9k players to 26.2k and levels off (+100 in the tenth year);
       - about 950 free agents;
       - average squads 37.7 including youth squads, about 30 senior;
       - the share of 32+ rises from 12% to 21% here, where nobody declines; in a career, decline retires the old sooner.
     - **Tests:** `test_lifecycle.py` (retirement chances); `tests/integration/test_lifecycle_season.py` (a season-end on the real world: retirements mostly from 33+, every club's intake ready to play, computer-run senior squads within the limit, the user's squad untrimmed, the youth news; and Release: own players only).
4. - [x] **W2, other leagues** (the first four countries; the rest come later in W2b):
     - **Leagues** (`data/config/competitions/{esp,ita,ger,fra}/`), each on its own country's calendar (`calendars/{esp,ita,ger,fra}-2026-27.yaml`, approximate dates, winter breaks as `blackout`, the same international windows and season boundaries as England):
       - Spain: La Liga (20) and Segunda (22), with play-offs for 3rd–6th, two legs each round;
       - Italy: Serie A (20) and Serie B (20), with play-offs for 3rd–8th (single-leg preliminaries, then two legs);
       - Germany: Bundesliga, 2. Bundesliga (18 each) and 3. Liga (20);
       - France: Ligue 1 and Ligue 2 (18 each).
     - **Movements:** three up and down in Spain and Italy, two in Germany (both levels) and France.
       - Play-offs between leagues (Bundesliga 16th against 2. Bundesliga 3rd, and so on) aren't supported yet, so those countries move two each way.
       - The lowest league in each country has no relegation, as its next level isn't in the data.
     - **Their quality comes from their players' ratings:** no league setting (best XI: Premier League 79.7, La Liga 78.0, Serie A 77.0, Bundesliga 76.8, Ligue 1 75.5).
     - **How a save gets them:** `LeagueDef.source_leagues` names the ratings source's league. `ensure_leagues` (in `create_season_fixtures`) adds a missing league's competition and its clubs for the season, found by that name, and skips a league whose clubs don't add up.
       - A new career has them from the start; a career under way from its next season (with news).
       - `league_calendar` schedules each league, and its play-offs, on its own country's dates.
     - **UI:** the start page and the League page pick a country, then its league. Built by a Sonnet agent, as a patch from a scratch copy (beb267c).
       - The start page lists the new leagues from the base world by their source names, so a career can start abroad.
       - Checked in the browser: a Real Madrid career starts in La Liga, with the La Liga table at 1440 px and at phone width.
       - The API's competitions and leagues carry `nation`.
     - **Measured:** a whole season of all 13 leagues on the fast engine is 5,242 league matches in 71 s (`footsim sim-season`), with 2.76 goals a match, 45% home wins and 24% draws.
     - **Tests:**
       - every league fits its own calendar, clear of its breaks;
       - `test_cups_season.py` now plays a season of every league and both cups: every league finishes and starts the next season at its size, with clubs moving in every country (it takes about a minute).
   - [x] **W2b, more leagues:** the Liga Portugal, the Eredivisie, the Scottish Premiership, the Saudi Pro League, the Süper Lig and the Belgian Pro League.
     - Each is on its own country's calendar (`calendars/{por,ned,sco,ksa,tur,bel}-2026-27.yaml`; approximate dates, sharing the season's boundaries):
       - the Netherlands, Turkey and Belgium with winter breaks;
       - Saudi Arabia paused for the AFC Asian Cup it hosts in January 2027, which leaves it five midweek rounds.
     - **Their own rules where the engine supports them:**
       - **tiebreakers:** head-to-head first in Portugal, Turkey and Saudi Arabia; wins first in Belgium; goal difference first in the Netherlands and Scotland;
       - **Scotland:** 12 clubs playing each other three times (33 rounds).
     - **Simplified, recorded in each file:**
       - Scotland's split after 33 rounds (5 more within each half) and Belgium's play-offs aren't supported yet (W2c);
       - nobody moves, as their second divisions aren't in the data.
     - **The clubs** are the data's 2026-27 line-ups: Belgium's league grows to 18, and this season's promoted sides are in.
     - **Tests:**
       - every league fits its own calendar, with Saudi Arabia's midweeks and the others on weekends;
       - the whole-season test (`test_cups_season.py`) plays every league, now 19 of them, and rolls the season over;
       - all 203 backend tests pass.
   - [ ] **W2c, other formats:** splits (Scotland), play-offs within a league (Belgium), conferences (MLS), Apertura and Clausura (Mexico, Argentina), where they fit around the core.
5. - [ ] **W3, finances:** TV money, wages, budgets and the board, by league. Most of the gap between leagues that a manager feels is here.
6. - [ ] **W4, transfers:** valuations, AI buying and selling, bids and negotiation (fee, wage, length), loans, free agents and expiring contracts, and the windows (already in the calendar). Most big transfers cross borders, so this comes after W2.
7. - [ ] **W5, academies in full:** facilities, youth squads, loaning young players out.
8. - [ ] **W6, European competitions:** the Champions League (league phase), the Europa League and the Conference League, where the leagues meet on the pitch.

**Added by the user on 6 Oct:**
- **The play-test gate** comes after the engine's defending (D6, E as needed), W3 and W4: believable matches, more leagues, finances and a working transfer market. Stop there for a substantial play-test by the user before investing in W5–W8.
- [ ] **W7, other continental competitions:** the Libertadores, the AFC Champions League and the rest, reusing W6's machinery.
- [ ] **W8, international football:** national teams, call-ups, qualifiers and the World Cup.
- [ ] **Integration and polish** of those systems.
- [ ] **Phase P, simulation performance:** a late phase, planned in `docs/plans/performance.md` and not to be implemented before its turn.
  - P1 profiles first (`footsim bench`, on the M3 and the VM);
  - P2 makes behaviour-neutral single-core improvements;
  - P3 adds multi-core, only if the measurements show it pays: per day, workers compute the AI matches and the user's match, and the parent records them in fixture-id order.
  - Results must stay identical for a seed (a new career-level determinism test).
  - D-pre, vectorising `update_targets`, stays in Phase D as its own gate (the 8 s budget per agent match).

**Findings from the performance study (6 Oct), to check separately (not fixed):**
- Nothing asserts that a club plays at most once a day. `cups._free_day` can fail to find a date and leave a clash. Add a check, and decide what to do when it happens.
- One sim-to-date step can span many days in one transaction (`advance` until the user's next match), so a cancel waits for it.
- `player_match` grows without bound (about 28 rows a match), so `develop_players`' monthly minutes query slows as a career lengthens. The season-stats views (queued) read the same table.

**Alongside, in the time the management phases leave the CPU:** Phase D (D-pre to D7), Phase E, and the remaining engine steps: 2.3d, C1, 2.1, 2.6, C2, F2, G, J and K. Their measurement batches run while management code is written, as the cups were written during 2.3c's batches.

## Review of 2.3f, 2.4 and W1 (6 Oct, a Sonnet reviewer agent)

The user allowed agents for work that doesn't need the CPU. A reviewer read the 2.3f, 2.4 and W1 commits against the project's rules.

- [x] **Fixed, behaviour-neutral:**
  - **Release had no floor:** a squad released below 11 couldn't play its next match ("needs 11 starters"), and no transfers could replace them. Now the user can't go below 16 senior players or 2 keepers (`lifecycle.yaml` `user_min_players`, `user_min_keepers`; 409 with the reason).
  - **Squad trimming protected keepers only when a club had three or fewer;** with four or more it protected none. It now keeps the best three.
  - **Red-card reasons** were matched by text between the engines and the ban rules; they're now shared constants (`match/report.py`).
  - **Lifecycle tunables moved to YAML:** the intake's spread, left-footedness, weak foot and skill moves, and trimming's young-player age, potential weight and keepers kept.
  - **Nits:**
    - `aggression_cards` validated low < high;
    - `test_restarts.py` updated for 3-tuple engagements;
    - the blocks comment corrected (combined chances, two at 0.48 where 0.56 added up before).
  - **New tests:**
    - `test_defending.py` pins 2.3f's rating responses: a better marker puts a receiver off more, a better defender a shooter, and a carrier expects less against a better tackler;
    - the v8 migration;
    - Release's floor.
- [x] **Behaviour changes, measured as one engine checkpoint** (the review's list):
  1. **The decision to shoot saw only the pressure.** The shot then paid 0.55 for each defender in the cone and a block chance on top, so a shooter overrated his chance by up to two-thirds.
     - **Fixed:** one model, `actions.shot_chance` (`ShotChance`: pressure, the place's xG with the cone, blockers, block chance). `decide` weighs `xg × (1 − block)`, and `start_shot` plays the same numbers.
     - **Headers too:** a header went for goal on the place's xG alone, then the shot applied the pressure, cone and blocks. It now goes for goal on `shot_chance(header=True)` (found by the second review).
  2. **Keepers as the nearest opponent were read with outfield ratings** (positioning and tackling about 14), so a rushing keeper put a shooter off half as much as before 2.3f.
     - **Fixed:** keepers are left out of shot pressure, the cone (already), blocks, first-touch pressure, the pass estimate's marker and the carry estimate, as they already were from duels (`MatchEngine.outfield_indices`).
     - A keeper's part is his own: the save, his claims in his box, his gathering.
     - **Also:** a block is credited to the nearest outfield player, never the keeper (`shot_tick`).
     - **Not yet:** a keeper never challenges a carrier (no smother or one-on-one). That belongs with Phase D6 or E.
  3. **The lapse test was a coin flip:** `t - last > 2 * DT` with floating-point times. Replaying the clock, one missed tick lapsed 45% of the time. It's now 2.5 DT.
  4. **The pass estimate's regather term could go negative** for a marker of 90+ (`close` × quality above 1). It's now clipped to [0, 1].
     - This and item 2's estimate marker sit behind 2.3c's switch (`estimate.honest`, off), so neither the golden values nor the batches see them yet.
  5. **Tunables moved to YAML:**
     - the blocks' reach floor and chance cap, their own reference, and the shot-line geometry (0.8–14 m): `defending.yaml` blocks;
     - the shot thresholds (`min_xg` 0.05, `long_range_xg` 0.02, `header_xg` 0.04) and the cone (0.55 a defender, at most 3): a new `shooting.yaml`.
     - **The same numbers are now stricter:** they're compared with the chance after the cone and the block chance.
  - **Found by the taker test on the new build:** a restart's taker already on the ball was flagged to hurry as the restart came due, and ran onto it at 1.2 m/s (P2's bug, in an edge case: a quick free kick taken by the fouled player standing on the spot). He now stays put once within reach (`behaviours._taker`; `TAKER_REACH` moved to `state.py`).
  - **Tests:**
    - keepers are no marker, shooter pressure, blocker or tackler;
    - the choice to shoot sees the bodies in the way (`decide`'s own utility);
    - the estimate reads markers as the physics does, and the regather never goes below the first touch alone;
    - one missed tick keeps an engagement and two lapse it, on the engine's own clock.
    - Each new test fails on the old code.
  - **Reviewed:** a Sonnet `engine-reviewer` agent, statically. Its findings are all in this commit:
    - the block credit;
    - the header gate;
    - the decision-level and estimate tests;
    - the thresholds and geometry in YAML;
    - the comments.
  - **Measured** (200 matches per division, seed 21, 4 workers, `reports/engine/review-fixes/`):
    - Run at 44bdfe9: 70b9171 plus the read-only `ShapeSampler`, so the same matches.
    - Compared with `step2.4/cards3` (0488313), the previous engine.

    | | PL before | PL now | L2 before | L2 now | Real (PL / EFL) |
    |---|---|---|---|---|---|
    | Shots | 41.9 | **25.7** | 32.4 | **22.3** | 23–27.5 / 22–26 |
    | Shots on target | 12.5 | 12.1 | 9.1 | 8.9 | |
    | Goals | 3.79 | **5.19** | 3.19 | **4.25** | 2.65–3.05 / 2.45–2.85 |
    | xG per shot | .071 | **.168** | .081 | **.183** | .09–.12 |
    | Conversion | .090 | .202 | .098 | .190 | .095–.12 |
    | Shots from outside the box | .104 | **.037** | .080 | **.021** | .30–.42 |
    | Box entries per team | 32.3 | 32.1 | 25.3 | 24.8 | |
    | Shots per box entry | .65 | .40 | .64 | .45 | |
    | Corners | 7.7 | **3.7** | 5.5 | 2.8 | about 10–11 |
    | Set-piece share of goals | .21 | .13 | .18 | .12 | .20–.32 |
    | Offsides | 2.2 | 3.3 | 2.8 | 3.7 | 2.5–4.5 |
    | Fouls / yellows | 23.8 / 4.2 | 24.3 / 4.7 | 18.8 / 3.3 | 19.2 / 3.3 | |
    | Interceptions | 19.3 | 23.4 | 18.8 | 20.9 | 14–26 |
    | Ball in play (min) | 62.0 | 64.3 | 70.0 | 71.5 | 54–60 |
    | Home / draw / away | .385 .215 .400 | .495 .195 .310 | .400 .250 .350 | .450 .240 .310 | |

    - **What it means:** the shot count is now in range, for the wrong reason, and goals went **up** 35%.
      - Seeing the bodies in the way, players stopped taking hopeful shots, and kept the ball instead.
      - Against defending that leaves about 4 outfield players goal-side of the ball in its own third, keeping it pays: they walk the ball into close-range chances (mean shot about 10 m out, against a real 16–17).
      - Corners fell with the blocked and deflected long shots that used to make them.
    - **Shape, measured** (the same batches; the defending side, ball in the attackers' final third):
      - 4.2 outfield players goal-side of the ball (middle third 7.5–7.9, build-up 9.6);
      - length 27.8 m, width 30.7 m, lines 9 m apart;
      - box entries by pass .35, carry .23, through ball .21, cross .11.

      The cause is in `behaviours._team`: the defending midfield and forwards stood a fixed span upfield of a back line only 9 m behind the ball, so they were upfield of the ball whenever it was in their third. Phase D2 (`docs/plans/defensive-shape.md`) answers that.
    - **The chance model double-counts defenders** (found tracing every shot in 16 matches, `scratchpad/chance_diag.py`).
      - `expected_goal` is fitted to real *average* xG by place (penalty spot .3, edge of box .08, 25 m .03), which already includes the defenders usually in the way.
      - The shot then multiplied that by 0.55 for each defender in the cone, took a block chance off for the same defenders, and applied a finishing-and-keeper factor averaging about 0.82.
      - So a typical crowded shot from the edge of the box came out at about .01, against a real .03–.05.
      - Before the review fixes the decision didn't see that, so players took the shots and the recorded xG came out low (.071). Now the decision sees it too, so edge-of-box shots are almost never worth it.
      - **The fix is to fit the chance model to real shots,** not to retune thresholds: StatsBomb's open data records where every defender stood at each shot (`calibration/shot_fit.py`; step S1 below).
    - **Next, in order:**
      1. **S1, the shot model fitted to real freeze frames:**
         - place, header, the cone and pressure as one fitted logistic: the shot's xG, blocks included;
         - the per-blocker chance fitted to real blocked shots;
         - finishing and keeping centred on average players, so they decide execution without biasing the level;
         - the decision and the recorded xG are the same number.
      2. **D2, the three-line shape:** coded and set aside as `scratchpad/d2/d2.patch`. Three matches showed 5.4 goal-side, with box entries unchanged; measure on 200.
      3. **S2, if the long-shot share is still off:** calibrate the shooting decision's values against real shot locations.
- [x] **S1 and S2: the shot model fitted to real shots, and real shot selection** (d53262f; `docs/calibration/shot-model.md`).
  - **S1:**
    - A shot's xG is a logistic on the place, a header, the outfield defenders in the cone and the nearest one's pressure. It's fitted to 9,415 Premier League 2015/16 open-play shots with StatsBomb freeze frames (`footsim fit-shots`), and matches the real scoring rate in every distance band.
    - The per-blocker chance is fitted to the real 29% of blocked shots (0.48), and also matches in every band.
    - Finishing, long shots, heading and keeping are centred on Premier League averages (73, 69, 70, 81), so ratings move execution around the xG without biasing its level.
    - The decision, a header's choice and the recorded xG are one number.
  - **S2:**
    - The old gates (xG .05, or 18–30 m with 3 m of room and .02) excluded most real long shots. A shot is now an option from xG .015, the 5th percentile of real shots.
    - It's worth 2.0 × xG against keeping the ball. That's calibrated on 16-match sweeps on where shots come from: 0.95 gave 14% from 16.5 m+, 2.0 gave 53% (real 51%, every band within a few points), and 3.0 gave 74%.
  - **Measured** (200 per division, seed 21, `reports/engine/s1s2/`, against `review-fixes/`):

    | | PL before | PL S1+S2 | L2 before | L2 S1+S2 | Real (PL / EFL) |
    |---|---|---|---|---|---|
    | xG per shot | .168 | **.101** | .183 | **.107** | .09–.12 |
    | Conversion | .202 | **.112** | .190 | **.128** | .095–.12 |
    | Shots from outside the box | .037 | **.428** | .021 | **.349** | .30–.42 |
    | Ball in play (min) | 64.3 | **59.6** | 71.5 | 68.3 | 54–60 |
    | Corners | 3.7 | 6.2 | 2.8 | 4.5 | about 10–11 |
    | Shots | 25.7 | **47.2** | 22.3 | **35.5** | 23–27.5 / 22–26 |
    | Goals | 5.19 | 5.30 | 4.25 | 4.54 | 2.65–3.05 / 2.45–2.85 |
    | Possessions ending in a shot | .147 | .268 | .147 | .234 | |

    - **Each shot is now real:** its quality, where it's taken from, how often it scores.
    - **What's wrong is how many chances get made:** 27% of possessions end in a shot, and the defending shape is unchanged (4.3 goal-side of the ball in the final third). That's D2.
    - Not pushed on its own: 47 shots a match would have looked worse in the user's game than the build deployed. It goes out with D2.
- [ ] **D2, the defending shape** (84e044c, `docs/plans/defensive-shape.md`). On 16 identical synthetic matches at quality 78, against S1+S2:

  | | Before | After |
  |---|---|---|
  | Goals | 4.13 | 2.94 |
  | Shots | 36.1 | 27.8 |
  | Box entries per team | 25.4 | 20.0 |
  | Goal-side, ball in the final third | 4.5 | 6.0 |

  xG per shot and the long-shot share were unchanged. Three single-value variants (midfield 4 m goal-side; wide players deeper; forwards 6 m ahead) each raised the goal-side count a little but didn't beat it, within 16-match noise.
  - **Measured** (200 per division, seed 21, `reports/engine/d2/`, against `s1s2/`):

    | | PL S1+S2 | PL D2 | L2 S1+S2 | L2 D2 | Real (PL / EFL) |
    |---|---|---|---|---|---|
    | Goals | 5.30 | **4.63** | 4.54 | **3.71** | 2.65–3.05 / 2.45–2.85 |
    | Shots | 47.2 | **41.6** | 35.5 | **30.6** | 23–27.5 / 22–26 |
    | xG per shot | .101 | .095 | .107 | .103 | .09–.12 |
    | Shots from outside the box | .428 | .415 | .349 | .322 | .30–.42 |
    | Box entries per team | 32.4 | 29.1 | 25.5 | 22.8 | |
    | Shots per box entry | .72 | .71 | .69 | .67 | |
    | Goal-side, ball in the final third | 4.3 | **6.0** | 4.3 | **6.1** | about 8 |
    | Final-third length (m) | 27.9 | 18.7 | | | |
    | Ball in play (min) | 59.6 | 61.4 | 68.3 | 70.5 | 54–60 |
    | Take-on success | .83 | .82 | .83 | .83 | .45–.60 |

  - **Reading:**
    - D2 does what it was built for: 6 outfield players goal-side instead of 4, fewer box entries, and goals down 13–18% with the shot model's quality unchanged.
    - The volume is still about 1.6 times real: once inside the box, a possession still ends in a shot 70% of the time.
    - The final-third block is very short (19 m): the lines close up, but nobody closes the man on the ball.
    - **Next is D6, engagement:** pressure on the ball carrier in and around the box, cover, the take-on duel (82% success against about half), and markers staying on their man in the box.
- [x] **D6, turnovers at real rates** (43675a4, 7 Oct).
  - **Real references measured first** (StatsBomb Premier League 2015/16, 380 matches, `scratchpad/sb_possessions.py` and `sb_defense.py`):
    - 18.5 open-play possessions per team reach the box, and 38% of those end in a shot;
    - 95 possessions per team;
    - take-ons: 32 a match, 61% succeed;
    - per team: 11.7 interceptions, 20.3 tackles (60% won), 28.5 clearances (14.7 in their own box), 19.5 blocks.
  - **The diagnosis** (`scratchpad/box_diag2.py`):
    - an attack that reached the box kept the ball for a median 28 s;
    - the defence made about 1.5 duels a match in its own box;
    - possessions averaged about 47 s against a real ~18 s.

    The ball rarely changed hands, so every possession had time to make a chance.
  - **The changes, each calibrated to a real rate:**
    - **take-ons:** the defender's edge in the duel 1.75 (was −0.25, 86% success), with carriers' appetite 1.0 (was 0.35) so they still try as often as real ones;
    - **interceptions:** `intercept_scale` 0.3 (was 0.2);
    - **first-time clearances:** a defender reaching the ball in his danger zone under pressure clears it (`defending.yaml clearances`). These are starting values: most real clearances are crosses headed away, and the engine plays a third of the real crosses.
  - **Measured** (200 per division, seed 21, `reports/engine/d6/`; League Two re-run on 3 workers after the Mac swapped at load 40):

    | | PL D2 | PL D6 | L2 D2 | L2 D6 | Real (PL / EFL) |
    |---|---|---|---|---|---|
    | Goals | 4.63 | **2.85** | 3.71 | **2.48** | 2.65–3.05 / 2.45–2.85 |
    | Shots | 41.6 | **27.4** | 30.6 | **20.0** | 23–27.5 / 22–26 |
    | Shots on target | 12.2 | 7.8 | 8.3 | 5.3 | |
    | xG per shot | .095 | .087 | .103 | .097 | .09–.12 |
    | Shots from outside the box | .415 | .481 | .322 | .399 | .30–.42 |
    | Box entries per team | 29.1 | 21.6 | 22.8 | 16.4 | 18.5 (PL 15/16) |
    | Shots per box entry | .71 | .62 | .67 | .61 | .38 |
    | Take-on success | .82 | **.65** | .83 | **.63** | .61 |
    | Interceptions | 16.6 | **24.5** | 17.5 | **25.0** | 23 (PL 15/16) |
    | Fouls / yellows | 23.8 / 4.2 | 20.0 / 3.9 | 18.2 / 3.3 | 15.5 / 2.7 | 20–24 / 3.4–4.3 |
    | Ball in play (min) | 61.4 | 66.9 | 70.5 | 74.2 | 54–60 |
    | Home / draw / away | .40 .21 .39 | .325 .34 .335 | .415 .235 .35 | .365 .34 .295 | .41–.47 / .22–.29 |

  - **Reading:** goals are in range in both divisions, and shots in the Premier League (League Two a little under).
  - **Still off:**
    - **home wins too few and draws too many:** with real scoring, the provisional home-advantage values show. That's step 2.1's fit;
    - **League Two's fouls and yellows a little low** (fewer duels now);
    - **ball in play too long;**
    - **corners and penalties low:** fewer crosses and blocked shots;
    - **shots per box entry still high;**
    - **fast breaks 2% of shots** (real 5–10%). That's Phase E.
- [x] **Phase E, counter-attacks** (2a0b606, 7 Oct).
  - **The diagnosis:**
    - A settled-play stopgap held back balls in behind 76–85% of the time, including on counters.
    - "Unset" can't mean fewer than 6 opponents goal-side: at an open-play regain in a side's own half the opponents usually have 7–10 there (`scratchpad/regain_diag.py`), so 6 applied to 0.6% of regains.
  - **The change:** a side that wins the ball in open play in its own half is on a counter for the counter window, while at least two opponents are caught upfield of the ball (`tactics.yaml transition`: `counter_unset` 9, `counter_forward` 0.05). It plays balls in behind, and values forward passes more.
  - **Calibrated** on 32-match sweeps at quality 78: unset 6 gave 2.0%, 8 gave 5.3%, 9 gave 6.0%, with goals and shots unchanged.
  - **Measured** (200 per division, seed 21, 3 workers, `reports/engine/e/`): fast breaks **2.2% → 7.2%** of shots in the Premier League and **2.4% → 6.2%** in League Two (real 5–10%). Every other figure stayed within its CI of D6: PL goals 2.88 and shots 28.2; L2 goals 2.42 and shots 20.8.
  - **Tests:** the counter state (on, set, too late, from a restart, won in their half); all 240 backend tests pass.
- **Step one (D6, then E) is done.** The engine is in or near range for goals, shots, shot quality, take-ons, interceptions, cards and fast breaks.
  - **Open engine items, for later rounds:**
    - home advantage: home wins .36 against .41–.47, and draws .31–.34 against .22–.29 (step 2.1's fit);
    - ball in play long: 66–74 minutes against 54–60;
    - corners low: 4.3 against about 10. Crosses are a third of real, which is 2.3c's decision values;
    - League Two's fouls a little low;
    - shots per box entry .62 against .38;
    - runner-tracking, which would let the settled-play through-ball stopgap go.
  - **Still open for D6:**
    - shots per box entry .69–.72;
    - take-ons succeeding about 82% (real 45–60%), mostly against whoever is nearest;
    - close-range shooters under less pressure than real ones (closeness .44–.50 against .56–.70).

## Quick fixes (do first; each is its own checkpoint)

- [x] 0a `just e2e` defaults to :8765. The e2e scripts refuse :8000, and any server whose `/api/health` doesn't confirm `default_saves: false`; `FOOTSIM_E2E_ALLOW_REAL_SAVES=1` overrides. Also fixed the start page staying on screen after starting a career from `/start`. Verified with `just e2e` on a fresh :8765 server; the user's saves are unchanged
- [x] 0b A substitute starts with no yellow card: `_load` resets the slot's `yellows` and `tackle_ready` (`engine.py:183-202`). Tested by `test_a_substitute_starts_unbooked`, which fails without the fix. The golden values are unchanged: no golden match makes such a substitution
- [x] 0c Two more per-slot carry-overs on a substitution, found by the reviewer. Done: `_load` drops the slot's `engaged` and `take_on_ready` entries, and `_bring_on` re-picks a restart taker who goes off. Two tests; Mac golden values re-recorded with a History note
  - Clear the slot's `engaged` state (`engine.py:93`; `duels.py:56-59`); this moves the seed-12 golden, so re-record it with a History note.
  - Re-pick a pending restart's taker in `_bring_on` when the slot it named has been substituted (`restarts.py:58-60`, `engine.py:763-764`).
  - Both with tests.

## Cloud session (29 Sep, claude.ai/code)

The local session reached its usage limit, and a cloud session carried on from 8a5d319.
- **Start here: `docs/plans/cloud-handoff.md`.** It says how to bring the cloud work in, check it on the Mac (including the one golden-value command), and carry on.
- **Branch.** Cloud sessions can push only to their own branch, `claude/eloquent-ramanujan-ho29ch`. It is `phase-1-match-believability` plus the cloud commits, so to pick up locally: `git switch phase-1-match-believability && git fetch origin && git merge --ff-only origin/claude/eloquent-ramanujan-ho29ch && git push`.
- **No EA data or built world in the cloud,** so batches there use synthetic teams. `--synthetic --division ENG4 --quality 58-66 --equal` stands in for Grimsby in League Two: equal sides, as section S asks, in a League Two-like band. Re-run a result on Grimsby locally before treating it as accepted.
- **Speed.** The cloud machine has 4 cores and takes about 17.8 s per match (the Mac: 6.7 s), so the 8 s budget can only be checked on the Mac.
- **Golden values are pinned per platform** in `backend/tests/unit/engine_golden.json`. The Mac and Linux round some floating-point operations differently, and a match amplifies the difference. A cloud commit that changes behaviour can record only the Linux values, and deletes the Mac's, so the golden tests skip on the Mac. **The only local follow-up:** `cd backend && FOOTSIM_UPDATE_GOLDEN=1 uv run pytest tests/unit/test_engine_golden.py`, then commit `engine_golden.json`.
- **Tests must hold on both platforms.** The same seed plays out differently on the Mac and on Linux, so a test must never depend on one match's chaotic outcome (as `test_reads_a_high_press_from_the_pitch` did: it now judges the manager's average reading over four seeds).

## Before the 29 Sep crash (checkpoint commit 24207eb)

- [x] Phase 0: measurement and safety (probe, harness, targets, synthetic teams, golden and determinism tests, live-match safety, migrations)
- [x] Phase A: MM:SS clock, 5-minute halves, LiveSession, protocol v2, half-time, speeds, OVR beside the live rating in the subs panel, player card
- [x] Phase F1: restart state machine (setup times, set-piece layouts, 5 attackers at corners, substitutions at stoppages)
- [ ] Phase B1: calibration pass 1. **Partial**; the rest is in Step 2
- [ ] Phase C1: tactical guardrails. `tactics.yaml` costs and the turnover reaction delay are written; the rest is in Step 1

## Step 0: secure and tool up

- [x] 0a Branch `phase-1-match-believability`; golden values re-captured; checkpoint committed and pushed (24207eb)
- [x] 0b Tooling: plugins (`pyright-lsp`, `typescript-lsp`, `context7`), the `chrome-devtools` MCP, project agents and skills, `CLAUDE.md`, `pyrightconfig.json`, and the plans in `docs/plans/`

## Step 1: finish C1

- [x] 1.1 Harness CIs: a ±95% CI column, and paired CIs for A/B differences
- [x] 1.2 `ManagerAI`: reads the opponent from observed behaviour; an assistant toggle; events and commentary; tests
- [ ] 1.3 C1 A/B at 200 paired fixtures per arm, against section S (costs tuned if needed). **Measured in the cloud (synthetic equal sides, 94d5de3): fails section S.** Aggressive +1.07 goal difference and +23 points of win rate; direct passing alone +0.91; fast, press and high line now too costly (−0.44 to −0.62). The report and its verdict are in `docs/calibration/20260929T195539-synthetic-n200-q58-66-equal-ab.md`. Much of direct play's edge comes from the opponent's leaky build-up, so **fix 2.3 first**, then re-run C1 on Grimsby at the head and tune costs from there. Check `reports/engine/` for the Grimsby runs from before the limit
  - **Grimsby on real squads agrees (local, b6dce71, ENG4, seed 11, 200 paired per arm, opponents' managers on).**
    - All-aggressive: +0.89 goal difference, +21.5 win points. Its costs pass: xG against +12%, fast-break shots against ×3.3, stamina −5.7.
    - Direct: +0.79 / +23.5. High line −0.57, press −0.40, fast −0.35. Attacking, wide and all six cautious settings are within limits.
    - With every manager off, aggressive was +1.59 / +36.5: the opponent going long against the press halves the exploit.
    - Reports: `reports/engine/20260929T171031-ENG4-n200-ab-nomanager`, `…T181944-ENG4-n200-ab` (bold), `…T221425-ENG4-n200-ab` (cautious), local only.
  - **Next for 1.3:** after 2.3, re-run both sets of Grimsby arms at the new head. Remove slow tempo's `hurry: -0.1` accuracy bonus, then tune costs mechanism-first (`continuation-plan.md`, "C1").
    - Direct's edge today is almost all defensive: shots against −4.65, xG against −0.40.
- [ ] 1.4 Golden values re-captured; commit and push; restart the :8000 game

## Step 2: close the B1 gaps

- [ ] 2.1 Home advantage (referee and crowd mechanisms), fitted to the real home, draw and away split. **Now done after 2.4:**
  - one set of values for every league;
  - 400 matches each in ENG4 and ENG1, seed 31, pooled for `home_goal_diff`. **Mechanisms in (cloud), values provisional:** `home_advantage.yaml` (referee foul and card bias, crowd decision noise and pass error under pressure, each split evenly between the sides so totals stay put), `MatchEngine.venue_bias`, and the `home_goal_diff` and `away_card_gap` metrics and targets. (The earlier cloud idea of fitting on unequal synthetic sides is replaced by the real-squad fit above.) The manager still reads a press correctly with it on: 15/15 high presses spotted and 1/18 false alarms (20 seeds, 25-minute reads)
- [x] 2.2 Interceptions separated from recoveries in stats, ratings and commentary (cloud). **Finding:** the counting was only a small part of the problem. Two full 64 v 64 matches had 82 interceptions, 4.5 recoveries and 5 clearances a match (real interceptions: 14–26). The engine really does cut out about 80 passes a match, so the excess is behaviour, not labels, and goes to 2.3 and D
- Fixed (cloud): `duels._counter_on` and `gain_possession` read `eng.possessions` (rule 7). They now read `eng.possession_start`, simulation state set at the same moment. Behaviour is unchanged (the golden values hold)
- [ ] 2.3 Build-up leak: high regains broken down by cause; decision-level causes fixed. **Diagnosed and measured (cloud):** it's physics, not decisions. Passers' estimates are honest, but opponents cut out about 8% of passes (real about 2%). `passing.yaml` `intercept_scale` 0.35 against 1.0 (synthetic sides, 200 paired matches): interceptions 68→29, high regains 57→36, throw-ins 19→26, ball in play 73→69 min, fast-break shots 1.4→3.5%, but goals 2.43→2.14 and offsides 19→39. Not applied: tune it on real squads from about 0.3, then long-pass execution error. See `docs/calibration/20260929T202538-step2.3-intercept0.35-synthetic-n200.md`
  - **Real squads at 0.3 (local, b548f33, seed 21, 200 each).**
    - ENG4: interceptions 74→34, high regains 58→36, goals 2.00→2.13, but offsides 6→21.
    - ENG1: interceptions 65→30, high regains 47→25, goals 3.92→3.15, shots 40→30, throw-ins 13→22, but offsides 8→27 and fouls 22→16.5.
  - **Why offsides exploded:** all 107 calls in three diagnostic matches were sprinting forward runners, a median 2.0 m past the line. A sprinting player never slowed down, so runners overshot their mark (line − 1 m).
  - **Fixed:** runners holding the line now ease off to stop on their mark. Chasers and the ball carrier keep full speed. Offsides went from about 36 to 5 a match on synthetic sides at 0.3.
  - **With the fix, at 65b3b8f (seed 21, 200 each).**
    - 0.3 → ENG4: interceptions 36, high regains 37, offsides 6.0, goals 2.26, shots 24.4. ENG1: 32, 26, 4.6, 3.55, 40.
    - 0.2 cut interceptions only about 3 more (33 and 30), while ENG1 goals rose to 3.97.
  - **Why 0.2 barely helps:** an opponent near a pass took it with probability max(0.05, p), and intercept_scale never touched that 5% floor. Now it scales the floor for opponents too (inert at 1.0: golden values unchanged).
  - **Rounds 4–5** (local, 50e3cf1, seed 21, 200 each, both divisions). The variants:
    - f030: 0.3 with the floor fix;
    - f030e1: plus per_metre 0.004 and length_per_metre 0.014;
    - f020e2: 0.2 with 0.008 / 0.022;
    - f020e3: 0.2 with 0.012 / 0.032.
  - **What they show:**
    - 0.2 lands interceptions in both divisions (about 20 ±0.7).
    - Long-ball error lands ENG1's accuracy and throw-ins only by overshooting its goal kicks (24–26), and it needs implausible length spreads.
    - It can't make weaker passers less accurate: synthetic 62- and 78-rated sides both complete 94% of short passes.
    - The table and its reading are in `continuation-plan.md`, status section 5.
  - **Why (30 Sep diagnostics and design review): the passing physics hides the ratings.**
    - The receiver is sent to the true landing point at the kick.
    - Heavy touches are re-gathered at once and count as complete.
    - Passes are slow, and the estimate misjudges their timing.
    - The estimates ignore `passing.yaml`, and at 0.2 they overrate crosses (45–48% estimated against 20–23% completed).
    - So 2.3 continues as 2.3a–2.3e, as the plan describes.
  - [x] **2.3a Measure (behaviour-neutral).** Split into four checkpoints. Summary: `docs/calibration/20260930-step2.3a-summary.md`:
    - [x] Part 1, probe metrics: pass bands and outcomes, the reliability table, failure causes, travel times, heavy touches, offside kinds, rates per minute of ball in play, and possessions ending in a shot
    - [x] Part 2, targets and report: `kind` rate / volume / reference; volumes judged per minute of ball in play; references listed separately; the reliability table in the report; the synthetic quality sweep
    - [x] Part 3, refactors: the `pass_error()` helper, one aerial-score helper, `control.touch_skill` (bit-identical), and the no-league-names guard test
    - [x] Part 4, measurements: the ENG1–ENG4 ratings gap, the Metrica pass-pace reference, and the 2.3a reference batch
  - The original 2.3a list:
    - pass bands, the reliability table, failure causes, travel times, heavy touches, offside tags;
    - rates per minute of ball in play, and rating responses (a synthetic quality sweep, 58/66/74/82);
    - the ENG1–ENG4 ratings gap, and a pass-pace reference from Metrica's open data;
    - `match_targets.yaml` tagged rate / volume / reference;
    - the refactors, and the no-league-names guard test (it checks keys, values and code, not comments citing real-world sources).
    - The f020e2 re-run must reproduce round 5 exactly.
  - [x] **2.3b Physics shortcuts,** in two checkpoints:
    - [x] Part 1, reception (code): the read delay from anticipation, the re-touch lockout, crosses landing clear, and no completion for a passer's own re-gather. Tests pass; golden values re-recorded. Measured: accuracy ENG4 .819 / ENG1 .815; quality gradient 0.5 → 2.1 points; high regains up to 47 / 36. See `docs/calibration/20260930-step2.3b1-reception.md`
    - [x] Part 2, pass pace: `pace.arrive` 6.0 + 0.17 m/s per metre (friction 4.0), matching Metrica's travel times. Interceptions 16 / 16 (in range); high regains 42 / 31; ENG1 throw-ins too many (a recorded conflict). See `docs/calibration/20260930-step2.3b2-pace.md`
  - [ ] **2.3c Honest pass estimates** (WIP, behind `estimate.honest`, off; see the checkpoint for what remains): P_path × p_reach × P_arrive × P_secure, a landing grid for lofted balls and crosses, and a slow honesty test.
  - [ ] **2.3d Offside decisions:**
    - through balls judged at the runner's position;
    - awareness as a risk, not a per-decision re-roll;
    - free-kick positions, if measured.
  - [ ] **2.3e Ratings that matter:**
    - sweep the rating terms (the same values for every league) and check the rating responses first;
    - then measure the league residual. Only if it's justified and bounded, add the league-environment layer with its guard tests;
    - league references are validated last, and conflicts are flagged.
  - [ ] **2.3f Attack against defence, by rating** (new, from 2.3a's quality sweep):
    - equal sides' goals (3.1 to 4.5) and shots (28.5 to 41.2) grow with quality from q58 to q82, where real goals and shots are similar across leagues;
    - trace which creation or finishing mechanic outgrows defending (shot selection, pressure on the shooter, blocks, keepers), then fix it through ratings;
    - behind ENG1's shot excess;
    - do it after 2.3e, measured with the quality sweep.
- [ ] **2.4 Discipline, now done before 2.1** (the card-gap fit depends on foul volume):
  - measure fouls by source, and fix `take_ons`;
  - duels come from situations, adding the missing foul sources (holding a runner, 50-50s, fouls on a shielding carrier, every contested header);
  - DOGSO reds;
  - `booked_caution` applied once, not twice;
  - the aggression > 80 red-card cliff made smooth;
  - fit to fouls per minute of ball in play, and cards per foul;
  - **stale duel engagements** (from 0c's review): `engaged` entries survive between engagements, so a defender meeting the same carrier again skips the sizing-up delay (`duels.py:50-59`). Decide it here, measured, since fixing it changes duel volume.
- [x] 2.5 Teleports down to zero (keeper-catch snaps) (cloud). A saved shot is placed where the keeper can reach it (the same random draw, mapped into his dive window); a keeper with no shot on target in reach is beaten; and he keeps going for the shot until it resolves. Four full matches: 1 of 22 saves needed any correction, and it was 0.4 m (a teleport is over 1.5 m). **Confirmed:** 0 teleports in 400 synthetic matches (0.09 a match before)
- [ ] 2.6 Pre-D baseline reports (ENG1 and ENG4, 200 each) in `docs/calibration/`
- [x] Synthetic players fitted to real ones (handoff section 5, item 7; done early, while batches ran).
  - `footsim fit-synthetic` fits each position's attributes to real players: attribute = a + b × overall, plus the spread, over 17,847 players.
  - It writes only those aggregates to `data/config/calibration/synthetic_attributes.yaml`.
  - A synthetic centre-back is now as aggressive as a real one (it was 10 below its overall), and a striker tackles like one.
  - Golden values: Mac re-recorded, Linux deleted.

## Step 3: Phase D, dynamic movement

- [x] D0 Debug overlay (`?debug=1`): team phase and lines, offside line, targets (red when sprinting), pressers, the ball carrier's five best options with scores, and a text panel. Built early, while the Step 2.3 batches ran; `frontend/e2e/debug.mjs` checks it
- [ ] D-pre Vectorise `update_targets` in two behaviour-neutral commits (golden values unchanged). Today it takes 3.3 s of a 6.6 s match; the target is 1.5 s or less
- [ ] D1 `phases.py`: team phases with hysteresis. D1a is behaviour-neutral: `PhaseState` and `movement.yaml` with today's thresholds, plus flicker metrics. D1b adds the margin, dwell and blending
- [ ] D2 `shape.py`: TeamShape (line heights, compactness, width, ball-side shift, cover depth)
- [ ] D3 `intents.py`: MovementIntent; role runs; `press_bias`, `hold_line`, `track_runners`
- [ ] D4 Structural jobs in possession (width, depth, support, rest defence, box occupation)
- [ ] D5 Positional discipline
- [ ] D6 Defending: runner handover, curved pressing runs, cover man, far full-back tuck, holding midfielder screen
- [ ] D7 Movement speed bands, turning, stamina drain by band
- [ ] D gates (section S), an acceptance report, and a restart of the :8000 game

## Step 4: Phase E, transitions

- [ ] E Counter-press, rest-defence delay, recovery sprints, the ball-winner's first action, runners and support
- [ ] E gates: fast breaks give 6–12% of shots; the aggressive setup concedes at least 30% more fast-break shots

## Step 5: the remaining phases, in the approved order

- [ ] C2 Full TacticalState, a utility-based manager, and the A/B suite at 400+ paired matches
- [ ] F2 Set-piece routines, marking schemes, long throws, goal-kick patterns, and set-piece UI
- [ ] B2 1,000-match acceptance, the fast engine as a surrogate, cross-engine tests
- [ ] G Substitution windows and the queued-substitution UI
- [x] H Other-club pages (done early, while the C1 batches used the CPU)
- [ ] I Sim-to-date
- [ ] J Match analytics
- [ ] K Full validation (10,000 matches); then reassess before transfers and other management systems

## Acceptance checks

The user's 12 questions, answered at the end of each phase:

1. A believable normal match?
2. Aggressive tactics have downsides?
3. A formation change is visible?
4. Natural movement?
5. Transitions look different?
6. Corners set up?
7. Goal kicks and throw-ins are real restarts?
8. The best substitute can be picked from the ratings?
9. Another club's squad can be viewed?
10. Sim to a date?
11. About 5 minutes per half?
12. Plausible statistics?

| Phase | Date | Answers and notes |
|---|---|---|

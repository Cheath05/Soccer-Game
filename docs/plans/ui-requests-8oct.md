# The user's UI requests of 8 Oct: specs for the agents

**Status:**
- **Already given to agents (8 Oct):**
  - **F**, finance: one budget, $ by default, the month's profit and its changes, one-off transactions, the optional board, cup prize money (`w3-w4-finances-transfers.md` "W3-4");
  - **D**, development: bench credit, the academy potential boost, schema 12.
- **Queued here:** U1 and U2. Launch them after F is committed, one after the other, because they share API files with F and with each other.
- **Rules for each agent:**
  - work in the real checkout, on its scope only, editing existing files with Edit, with no git state changes;
  - run focused tests, `uv run mypy`, ruff, `npx tsc -p tsconfig.app.json --noEmit`, `npm run lint`;
  - build into a temporary folder only (`npx vite build --outDir /private/tmp/<name> --emptyOutDir`);
  - browser checks only on a throwaway server on port 8765 or 8766 with a temporary `FOOTSIM_SAVES_DIR`; never port 8000, never `saves/`.

## U1: squad, player, tactics and in-match changes (done 9 Oct)

The user's words: "having the arrow and then a number next to it is fine, I don't need a separate season start overall. I want to have a back button when I click on a player in squad, and an option to go from that player's information to another player. In tactics I want the position of the player to be more clear as I find myself wondering why a player's overall rating is one number, but their shown rating is lower, make it more clear. I would also like to be able to drag players from different positions on the squad formation in tactics and between the bench. I'd like to be able to choose who is on the bench vs the reserves too. When it comes to subs in a game, I would also like the option to see the formation and the players' positions and drag the player to another position or a bench player to replace them to make subs easier."

1. **The squad's overall.**
   - Drop the separate "Season start" column added in B1 (59277c9).
   - Show the change since the season began as the arrow and number beside the overall: "78 ▲+3", or "▼−2" in red.
   - Keep the player page's line.
   - `SeasonStart.tsx` can shrink to `SeasonChange`.
2. **Player page navigation.**
   - A back button, to the page he came from (browser history; the squad by default).
   - Previous and next player buttons that walk the squad list in the order it was shown. Pass the ordered ids in router state or a query param, or fall back to the club's squad order. Keyboard ← and → as well.
3. **Tactics, clarity.**
   - Each slot shows his rating there and why it differs from his overall. The rating is `LineupPicker.slot_rating` = role overall × `familiarity_factor(familiarity with the slot's position)` × `condition_factor(condition)`; read `match/teams.py`.
   - The tactics API returns, per starter: his overall (best position), his position familiarity at the slot, his condition, and the slot rating. The pitch and the side list show something like "ST 72 · OVR 78 (CM) · out of position −5 · tired −1".
   - An out-of-position player gets an amber or red marker.
4. **Tactics, drag and drop.**
   - Drag a player from one slot to another (swap), from the bench or reserves onto a slot (in), or from a slot to the bench or reserves (out).
   - Saved through the existing `PUT /api/tactics` lineup: `{slot id: player id}`.
5. **Bench and reserves.**
   - The user picks the substitutes, `match/teams.py` `BENCH_SIZE` of them; everyone else is a reserve.
   - Store them in the tactic's lineup JSON under slot ids `SUB1..SUBn`, so no schema change is needed.
   - `LineupPicker.pick` honours them (bench = the chosen available ones, filled automatically if short, still making sure a keeper is on the bench when one is available).
   - The squad and tactics screens show the starters, the bench and the reserves.
   - The golden test must not change: AI clubs keep the automatic bench.
6. **In-match substitutions on a pitch view.**
   - In the live match's subs panel (`frontend/src/match-viewer/SubsPanel.tsx`, `LivePage.tsx`; the server side in `match/live/session.py`), a formation view of the user's side shows its players in their slots.
   - Drag a bench player onto a player to substitute him (the existing sub API).
   - Drag two players to swap positions. If the live session can't swap positions yet, add that as an input to the engine (a tactical change at a stoppage, like a sub). Matches without it must stay identical (golden test), and determinism holds (the user's inputs are part of the run).

## U2: finding clubs, simming to cups, league order, Italian names (done 9 Oct)

The user's words: "Let me also just have an option to look up a team so I can see their squad, and their results without having to click league and then the country and then look for them. When simming, I want to have an option to sim to a cup game without needing to know the date, and when champions league etc is added, an option for that too, and if I just sim an entire season, let me know the competition the game was like (La Liga) or (Copa Del Rey). When I click leagues and countries, make the big five leagues be the default first options to choose from. Also, for the Italian league, just change the names of the clubs to their real ones, like Milano should be AC Milan etc."

1. **Club search.**
   - A search box in the header that finds any club by name (accents ignored, a few letters enough), via `GET /api/clubs/search?q=` returning the club, its league and its country.
   - Choosing one opens the club page (squad and results already there).
2. **Sim to the next cup match.**
   - The "Sim to…" menu gains "Next cup match", the user's next fixture in a cup (any cup). It's computed on the server so the client needn't know the date.
   - It's built so continental competitions (later) are just another entry, e.g. a list of "next match in <competition>" choices from the user's upcoming fixtures.
3. **Competition names in sim results.**
   - The sim summary dialog's results list, and the season summary's results, show each match's competition, e.g. "(La Liga)" or "(Copa del Rey)".
4. **The big five first.**
   - Wherever a country or league is picked (the start page, the League page, the Cups page: `NationPicker`, `LeaguePicker`), list England, Spain, Italy, Germany and France first, in that order, then the rest.
   - The default is the user's own country, as now.
5. **Real Italian club names.**
   - FC 27 has several Serie A and Serie B clubs under made-up names: "Milano FC" (AC Milan), "Lombardia FC" (Inter), "Bergamo Calcio" (Atalanta), "Latium" (Lazio), and so on.
   - A data file `data/config/world/club_names.yaml` maps the data's name to the real one (look up the full list from the base world's Italian clubs; only real, well-known names).
   - It's applied at world build (`importers/build_world.py`) and, for saves already made, by a migration step at the next free schema version. The step is idempotent and renames by the old name.
   - Real club names are facts, not EA data. The mapping is fine to commit.
   - Check other leagues for the same problem: list any made-up names in the report, but rename only where sure.

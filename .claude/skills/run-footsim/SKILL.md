---
name: run-footsim
description: Launch, restart and browser-test the footsim game. Covers rebuilding the frontend, restarting the user's game on port 8000 safely, running a throwaway test server on port 8765 with a temporary saves folder, running the Playwright e2e scripts, and driving the match viewer with the chrome-devtools MCP (screenshots, clicks, console, WebSocket, performance traces). Use whenever the app needs to be run, restarted, screenshotted or checked in a browser.
---

# Running footsim

The backend is FastAPI (`footsim.api.app:app`). It serves the built frontend (`frontend/dist`) and the API under `/api`, with the live match on a WebSocket at `/api/fixtures/{id}/live`. Saves go to `FOOTSIM_SAVES_DIR` (default `saves/`).

## The user's game (port 8000): be careful

The user plays their career here (slot 1: Grimsby, League Two). Restart it only at the end of a phase, so they get the latest version.

1. **Check nobody is using it.** Run `lsof -nP -iTCP:8000 -sTCP:ESTABLISHED`. An open connection (a browser WebSocket) may mean a match is being watched. In that case don't restart: tell the user instead.
2. **Nothing needs saving.** The app autosaves after every advance and every match (`/api/career/advance`, `/api/fixtures/{id}/play`, and the end of a live match). Never call `POST /api/saves/save` on the user's behalf, because it would overwrite their manual save.
3. **Rebuild and restart:**
   ```bash
   cd /Users/alexbenton/Developer/Soccer-Game/frontend && npm run build
   kill $(lsof -ti tcp:8000 -sTCP:LISTEN)        # the old server
   cd /Users/alexbenton/Developer/Soccer-Game/backend && (nohup uv run --frozen uvicorn footsim.api.app:app --host 127.0.0.1 --port 8000 > /private/tmp/claude-502/demo-server.log 2>&1 &)
   ```
   - The subshell and `nohup` detach the server, so it outlives the Claude session.
   - Don't start it as a background task: that ties the server to the session.
   - Copy the old log aside first if it might explain a problem the user hit.
4. **Confirm it's the new build.** `curl -s http://127.0.0.1:8000/api/health` answers, and `curl -s http://127.0.0.1:8000/ | grep -o 'assets/index-[^"]*'` names the bundle you just built. Tell the user to load their save again.

**Rebuild and restart together.** The server reads `frontend/dist` from disk on every request, but loads its Python code only at start. So a rebuild alone, even one for a :8765 test, gives the user's game a new frontend over an old API. That happened between 28 and 30 Sep. Note in `progress.md` which commit :8000 runs.

## Throwaway test server (port 8765): for all automated checks

```bash
cd /Users/alexbenton/Developer/Soccer-Game/frontend && npm run build
SAVES=$(mktemp -d /private/tmp/footsim-saves.XXXX)
cd /Users/alexbenton/Developer/Soccer-Game/backend && FOOTSIM_SAVES_DIR=$SAVES uv run --frozen uvicorn footsim.api.app:app --host 127.0.0.1 --port 8765
```

- Run the server in the background.
- The scripts start from `/start`, so one server can run them back to back. Restart it only for a clean slate; it keeps the last career in memory.
- Kill it when you're done: `kill $(lsof -ti tcp:8765 -sTCP:LISTEN)`.

## Automated browser tests (Playwright, already installed)

```bash
cd /Users/alexbenton/Developer/Soccer-Game/frontend
OUT=$(mktemp -d /private/tmp/footsim-e2e.XXXX)
node e2e/smoke.mjs http://127.0.0.1:8765 $OUT && node e2e/live.mjs http://127.0.0.1:8765 $OUT
```

- `live.mjs` starts a Liverpool career and watches a match, covering speed, half-time, subs, the player card, Instant and the report.
  - It also checks the picture never skips ahead after slowing down, and that a goal holds the picture while its banner shows.
- `smoke.mjs` also sims a week from the header's "Sim to…" menu.
- `season.mjs` (slow: several minutes) sims a whole season from a new Arsenal career. It checks that the results window comes first and the season summary opens separately after it. It isn't part of `just e2e`.
- Screenshots land in `$OUT`. Read them with the Read tool.
- `just e2e` runs `smoke.mjs` and `live.mjs` against :8765 by default.
- Every script starts a new career, which overwrites save slot 1. So `e2e/target.mjs` first asks the server (`GET /api/health`) where it keeps its saves.
  - It refuses unless the server confirms that isn't the default folder.
  - That rules out :8000 (refused outright), the Vite servers that pass /api through to it, and a test server started without `FOOTSIM_SAVES_DIR`.
  - `FOOTSIM_E2E_ALLOW_REAL_SAVES=1` overrides the check. Never set it for the user's game.

## Interactive checks with the chrome-devtools MCP

Use these for the visual gates: shape changes, corner setups, teleports and the debug overlay.

- The server is registered at user scope, runs headless with an isolated profile at 1440×900, and scales screenshots down to 1280 px wide.
- Point it only at the :8765 test server.
- Useful tools:
  - `navigate_page`, `take_snapshot` (accessibility tree, for finding buttons) and `click` or `fill`;
  - `take_screenshot`, for the pitch canvas;
  - `evaluate_script`, for example reading `document.querySelector('[aria-label="Match clock"]').innerText`;
  - `list_console_messages`;
  - `list_network_requests`, including the live WebSocket;
  - `performance_start_trace` and `performance_stop_trace`, for frame rate at 8×.
- For time-based behaviour (for example a corner setting up), pause, step the speed, and take screenshots a few game-seconds apart.
- The debug overlay (Phase D0) opens with `?debug=1`.

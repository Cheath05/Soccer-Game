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
   cd /Users/alexbenton/Developer/Soccer-Game/backend && uv run --frozen uvicorn footsim.api.app:app --host 127.0.0.1 --port 8000
   ```
   Start the last command with `run_in_background: true`.
4. Confirm that `curl -s http://127.0.0.1:8000/api/health` answers. Tell the user they may need to load their save again.

## Throwaway test server (port 8765): for all automated checks

```bash
cd /Users/alexbenton/Developer/Soccer-Game/frontend && npm run build
SAVES=$(mktemp -d /private/tmp/footsim-saves.XXXX)
cd /Users/alexbenton/Developer/Soccer-Game/backend && FOOTSIM_SAVES_DIR=$SAVES uv run --frozen uvicorn footsim.api.app:app --host 127.0.0.1 --port 8765
```

- Run the server in the background.
- Restart it between e2e runs, because it keeps the last career in memory.
- Kill it when you're done: `kill $(lsof -ti tcp:8765 -sTCP:LISTEN)`.

## Automated browser tests (Playwright, already installed)

```bash
cd /Users/alexbenton/Developer/Soccer-Game/frontend
OUT=$(mktemp -d /private/tmp/footsim-e2e.XXXX)
node e2e/smoke.mjs http://127.0.0.1:8765 $OUT && node e2e/live.mjs http://127.0.0.1:8765 $OUT
```

- `live.mjs` starts a Liverpool career and watches a match, covering speed, half-time, subs, the player card, Instant and the report.
- Screenshots land in `$OUT`. Read them with the Read tool.

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

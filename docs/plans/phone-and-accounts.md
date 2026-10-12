# Phone layout and accounts for friends (approved 11 Oct)

## Context
You want to play on your phone, and you want friends to play on their own devices with their own saves. The calibration and roadmap plan is paused until this ships.

What the code does today:
- **Frontend.** It is Mantine 9. It already folds the sidebar into a burger below 48em, and most tables scroll sideways. What breaks on a 390px phone:
  - three fixed-size pitches: Tactics at 340×480, the in-match subs pitch at 330×400, and the half-time panel;
  - the header, which keeps everything on one line;
  - the 12-column squad table;
  - drag and drop, which uses the browser's HTML5 drag events and is unreliable on touch screens. Tap-to-pick already exists as a fallback.
  - Nothing tests a phone-sized screen.
- **Backend.** Each process holds **one career**: `app.state.session` is a single `CareerSession`. It is looked up in only three places: `get_session` in `api/routes.py` and `_session()` in `api/live.py` and `api/sim.py`.
  - When anyone loads a save, everyone's live match and sim are thrown away.
  - There are 3 slots under one `FOOTSIM_SAVES_DIR`, and there is no notion of a user.
  - `get_world()` and the base world are read-only, so all users can share them.
- **Your decisions:**
  - username and password accounts, which you create with one command;
  - friends reach the game privately over Tailscale, through machine sharing, never publicly, since the world holds EA's ratings.

The intended outcome:
- On a phone the same site lays itself out for a phone.
- Each signed-in person has their own career slots.
- About 12 people can play at once on the existing single server.

## How phone vs computer is detected
- The page adapts to the device: **screen width** (Mantine's `sm` breakpoint, 48em) plus **`(pointer: coarse)`** for touch. It does not read the browser's user-agent string, which is unreliable, misreads tablets, and breaks when the phone is rotated.
- This lives in one hook, `useDevice()`, in `frontend/src/lib/device.ts`. It returns `{ phone, touch }` and is built on Mantine's `useMediaQuery`.
- A **web-app manifest** and Apple meta tags let you "Add to Home Screen". The game then opens full-screen like an app.

## Why this setup handles about a dozen people
- **One server process, with one `CareerSession` per signed-in user.** The world definitions are shared. Each user's saves live in their own folder.
  - SQLite with one file per save, the approach in ADR 0001, already isolates users. There's no need for Postgres or Docker.
- **CPU.** A live match costs roughly 7 s of CPU spread over the minutes you watch it, so about 1% of a core.
  - Each match's engine runs off the server's main loop, via `asyncio.to_thread`, so simultaneous matches don't stutter.
  - Sim-to-date, Continue and Instant play are the heavy work. They move into a pool of 3 worker processes (U2b), so different people's sims run on different cores.
- **Memory.** A session is just a database connection pool. Sessions idle for 30 minutes are closed and reopened on the next request.
- **Disk.** Each slot takes 80–150 MB including backups.
  - Friends keep 2 backups instead of 5, which is configurable.
  - The worst case is about 5 GB for 12 people with 3 slots each.
- **Moving later to a small rented server** (from your sharing plan) is the same app plus Tailscale. Nothing here is specific to Cardinal.

## Track U: accounts (main session, Opus High). Each step is a pushed checkpoint.

### U1. The account store and CLI
- **New `backend/src/footsim/accounts/`:**
  - `store.py` keeps users and sessions in `FOOTSIM_SAVES_DIR/accounts.sqlite`, using SQLAlchemy Core:
    - `user` holds id, name, password_hash, is_owner, created and disabled;
    - `login_session` holds token_hash, user_id, created, last_seen and expires.
    - Passwords are hashed with the standard library's `hashlib.scrypt`, so there's no new dependency.
    - Session tokens come from `secrets.token_urlsafe(32)`, and only their sha256 is stored.
  - It has its own small schema version and migrations, kept apart from career saves.
- **CLI (`cli.py`):** `footsim users add NAME [--owner]`, `list`, `reset-password NAME`, `disable NAME` and `remove NAME`.
  - Passwords are read with `getpass`. `remove` keeps the user's save folder unless `--delete-saves` is given.
- **Where saves live:**
  - **Owner:** your account uses the existing saves root, so your Grimsby career and slots stay exactly where they are. No files are moved.
  - **Friends:** each friend gets `FOOTSIM_SAVES_DIR/users/<user_id>/slot_N`.
- **Tests:** hashing round-trip, wrong password, a disabled user, token expiry, owner root vs friend root, and the CLI.

### U2. Per-user sessions
- **`api/session.py`:**
  - A `SessionRegistry` holds the shared base-world path, a dict mapping user_id to `CareerSession`, and a lock.
  - `for_user(user)` builds `CareerSession(SaveManager(root, keep_backups=...), base)` on demand.
  - Sessions idle longer than `idle_close_minutes` are closed, but never during a live match or sim.
  - `app.state.registry` replaces `app.state.session`. `create_app(session=...)` stays available for tests, wrapped as a single-user registry.
- **Auth modes**, chosen by `FOOTSIM_AUTH`:
  - **Off, the default.** One implicit "local" owner user. Behaviour is identical to today, so local play, `just e2e` on :8765 and the test suite are unchanged.
  - **On.** Every `/api/*` route except `/api/health` and `/api/auth/*` needs the session cookie: `footsim_session`, HttpOnly, Secure, SameSite=Strict, valid 30 days and refreshed on use.
    - Without it the route returns 401.
    - The WebSocket checks both the cookie and that the Origin header matches the host.
- **Routes:**
  - `POST /api/auth/login` and `POST /api/auth/logout`.
  - `GET /api/auth/me` returns name, is_owner and whether auth is on.
  - Login attempts are limited per name and per IP, with a 1 s delay after a failure.
- **Wiring:**
  - Swap the three lookups for one dependency: `get_session` in `routes.py` and `_session()` in `live.py` and `sim.py`.
  - The `generation` and `live_matches` logic stays per session, so loading a career only affects your own matches.
- **Live matches:** in `api/live.py`, the playback loop calls `await asyncio.to_thread(playback.pump, t)`. Commands are still applied in the same coroutine between pumps, so ordering and determinism don't change. A live match is light, about 1% of a core, so threads are enough.

### U2b. Heavy simulation in worker processes, so two people's sims use two cores
- **Why it's needed:** Python runs one thread of Python code at a time per process (the GIL). Today two people's sims would be two threads in one process, sharing **one** core, so each would run at about half speed while the other 3 cores sit idle.
- **New `backend/src/footsim/api/workers.py`:** a `ProcessPoolExecutor` using spawn, with `max_workers = sim_workers` from `server.yaml`. The default is 3 on the 4-core VM, leaving one core for the web server and live matches.
  - The workers stay running and keep `get_world()` cached, so only the first job pays the start-up cost.
- **Changes to `api/sim.py` `_run`:**
  - The job thread still holds `session.lock` for each step, exactly as now, so no other write can interleave.
  - It hands the heavy call to the pool: `pool.submit(sim_step_in_file, working_db_path, until).result()`.
  - The worker opens its own connection to the user's `working.sqlite`, runs `sim_step` in one transaction, commits, and returns the `SimStep`.
  - Autosave, cancel, the generation check and progress all stay in the parent. SQLite in WAL mode handles one writer process with other processes reading.
- **The same treatment for Continue** (`/career/advance`) and Instant play (`/fixtures/{id}/play`), which are the other heavy calls.
- **Queueing:** when all workers are busy, a job waits its turn, and `GET /career/sim` reports `waiting`.
- **What it does and doesn't speed up:**
  - **Separate people:** you and a friend simming at once each get a full core, so neither slows the other, up to 3 at a time.
  - **One person:** a single sim still uses one core, because days are played in order.
  - **Possible follow-up:** run each day's AI matches in parallel across the workers. That would need profiling and a determinism proof first, so it stays out of this plan.
- **Inline mode:** a setting with no pool runs everything in-process, for tests and local dev.
- **Tests:**
  - the same career simulated inline and through the pool gives an **identical** database (fixtures, results, ledger);
  - two users simulating at once both finish;
  - cancel works while a step is running in a worker;
  - loading another career abandons the job.
- **Measuring it on :8765:** start two sims at once, then check with `top` that two Python processes are each near 100%. Time one sim alone, then two at once; the times should be nearly the same.
- **Health:**
  - `in_use` becomes true if any user's session has a live match or a running sim, so the updater still waits.
  - `users_active` is a count only, with no names.
- **Tunables:** `data/config/server.yaml` holds `idle_close_minutes`, `sim_workers`, `friend_keep_backups`, `session_days` and the login rate limits. The Pydantic model goes in `defs/`.
- **Tests (`tests/integration/test_accounts.py`):**
  - two users each start a career in slot 1, and their careers are independent;
  - user A can't load or see B's saves;
  - the API refuses requests without the cookie when auth is on;
  - auth off behaves exactly as before, through the existing API tests;
  - a live match for A survives B loading a save;
  - health aggregates `in_use`;
  - a job queues once all the workers are busy (see U2b).
  - The golden values stay untouched.

### U3. Sign-in screen
This is done by me, after M1 has finished with `Layout.tsx`.
- A new `components/AuthGate.tsx` wraps the router in `main.tsx`.
  - It calls `/api/auth/me`. If auth is on and nobody is signed in, it shows a Mantine sign-in card.
  - The `api/client.ts` handler for 401 responses returns to the sign-in screen.
- A small account menu in the header shows who is signed in and offers Sign out.

### U4. Deployment, and adding a friend
This needs your hands on Cardinal; I can't reach it from here.
- **New `deploy/add-user.sh NAME [--owner]`:** wraps `footsim users add` with the deployment's environment.
- **New `deploy/enable-accounts.sh`:**
  1. It refuses to run until an owner account exists.
  2. It adds `FOOTSIM_AUTH=1` to `~/.config/footsim/deploy.env`.
  3. It restarts footsim the same safe way `update.sh` does: waiting while `in_use` is true, and leaving Cardinal, the ports and Tailscale Serve alone.
- **Updater safety:** `update.sh` keeps working without changes. The code ships with auth off, so pushing changes nothing on Cardinal until you run the script.
- **`deploy/README.md` gains "Add a friend":**
  1. In the Tailscale admin, use Machines → cardinal → Share, and send the friend the invite. Shared users are free and see only that machine.
  2. The friend installs Tailscale, accepts, and opens `https://cardinal.tailaf3b0c.ts.net:8443` on their phone.
  3. You run `deploy/add-user.sh <name>` and send them the password.
  4. Optionally they "Add to Home Screen".
- **`deploy/status.sh`:** adds the auth mode and the number of accounts. It stays read-only.

## Track M: phone layout (Sonnet agents, frontend only, run one at a time alongside Track U)

**Rules for every M agent:**
- They change only their listed files, and make no git changes; I review, commit and push each one.
- They run `npm run build` only.
- Browser checks run on a throwaway :8765 server with a temporary `FOOTSIM_SAVES_DIR`. They use Chrome DevTools `emulate` at 390×844, touch on, plus 1440×900 to confirm the desktop layout is unchanged.
- No backend or engine changes.

### M1. The shell and the device hook
- **Files:** `lib/device.ts` (new), `components/Layout.tsx`, `index.html`, `public/manifest.webmanifest` and icons (new).
- **Header on a phone:** the club name is shortened, Continue / Match day is the one main button, and Save and Sim-to-date move into a "⋯" menu.
- The burger drawer closes after you pick a page. Tap targets are at least 44px.
- The manifest uses `display: standalone` with the theme colour. It adds `apple-mobile-web-app-capable` and `theme-color` meta tags, plus `viewport-fit=cover` with safe-area padding.

### M2. Lists and tables
- **Files:** `SquadPage`, `TransfersPage`, `LeaguePage`, `FixturesPage`, `ClubPage`, `PlayerPage`, `MatchReportPage`, `MarketOverview`, `FinancesPage`.
- **Pattern:** on a phone, keep the table but show only the key columns, chosen through a `phoneHidden` set per table using `visibleFrom="sm"`. Make the name column sticky.
  - Squad keeps Pos, Name, Ovr, Condition and Value.
  - Tapping a row still opens the player.
- `MatchReportPage` gets `Table.ScrollContainer` and lets its header wrap.
- The Transfers filters fold into a "Filters" drawer.

### M3. Tactics and touch
- **Files:** `components/PitchBoard.tsx`, `pages/TacticsPage.tsx`.
- `PitchBoard` scales to the screen width through an SVG `viewBox` with `width: 100%` and a capped `max-width`. The player discs are placed in percentages.
- **Interactions:**
  - **On touch,** tap-to-pick becomes the main interaction: tap a player, then a slot or bench row, and the picked player is clearly highlighted. The HTML5 drag events are off on touch, since they are unreliable there.
  - **On desktop,** drag stays as it is.
- On a phone the side columns stack under the pitch, and the 120px instruction labels go above their controls.

### M4. The live match on a phone
- **Files:** `match-viewer/**`, `pages/LivePage.tsx`.
- **Portrait phone:** the pitch is drawn vertically, filling the width.
  - In `draw.ts`/`PitchView.tsx`, the canvas transform swaps the axes, and click hit-testing goes through the same transform.
  - It is drawing only: protocol and engine are unchanged.
- **Landscape phone:** the pitch fills the screen, with a minimal score bar.
- **Below the pitch:** score bar, then controls, then a bottom tab strip with Commentary, Stats, Tactics and Subs.
- The half-time panel becomes a full-screen sheet.
- `SubsPitch` scales by `viewBox`, uses the same tap-to-pick on touch, and keeps the yellow-card markers.

### M5. A phone check in e2e
- **File:** `frontend/e2e/phone.mjs` (new).
- At 390×844 with touch, it walks: start career, dashboard, squad, tactics (tap a sub into the XI), Continue, a live match (pause, sub, resume), then finances.
- It asserts no horizontal page scroll (`scrollWidth <= innerWidth`) and saves screenshots.
- It runs against :8765 only, like the other e2e scripts.

## Order
1. U1, with M1 running alongside, since they touch different files.
2. U2 then U2b, with M2 then M3 alongside.
3. U3, after M1.
4. M4.
5. U4.
6. M5.
7. Hand-off: you enable accounts on Cardinal, then add a friend.

**Each step follows the usual loop:**
1. focused tests;
2. the full suite;
3. the reviewer;
4. update `progress.md`;
5. commit with explicit paths;
6. push.

Model: Opus High is enough for all of this. Nothing here needs Max.

## Verification
- **Backend:**
  - `just lint` and the full `uv run pytest`;
  - new account and isolation tests;
  - the existing API tests, passing unchanged with auth off;
  - `test_engine_golden.py` untouched.
- **Two people at once on :8765,** with a temporary saves folder and `FOOTSIM_AUTH=1`:
  1. Create two users with the CLI against the temporary folder.
  2. Sign in as each in two separate browser contexts.
  3. Start a career for each.
  4. Run a live match for A while B simulates to a date. Both progress, and neither sees the other's saves.
  5. Without a cookie, requests get 401.
- **Phone:** `npm run build`. Check each M step at 390×844 (touch) and at 1440×900, with screenshots. `frontend/e2e/phone.mjs` passes on :8765.
- **Your saves:** your saves and port 8000 are never touched. The owner account maps onto the existing root without moving files. I can only check that on a copy of your saves in a temporary folder.

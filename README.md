# Soccer-Game (Footsim)

A local football management simulation: a living world of clubs and players, an agent-based match engine you can watch and control in 2D, and the management layer around it. The design is in [docs/design.md](docs/design.md), and architecture decisions are in [docs/adr/](docs/adr/).

## Play the demo

```sh
just demo        # builds the interface and serves the game at http://127.0.0.1:8000
```

Then open http://127.0.0.1:8000, pick a club from any of the four English divisions and start a career. (First time on a new machine: do [Setup](#setup) and [Data](#data) below.)

**What you can do**

- **Manage a club** in the Premier League, Championship, League One or League Two, with the real 2026-27 squads (EA FC 27 ratings).
- **Advance through the season:** press **Continue** to jump to your next match day. Every other match in the four English leagues is simulated as you go.
- **Watch your matches** in a 2D top-down view: pause, speed up (1×–32×), switch to highlights, or skip to the result. Change formation and team instructions mid-match and watch the shape change; make substitutions or let your assistant do it. Live commentary and stats run alongside.
- **Instant result:** plays the same match engine without the viewer.
- **Squad:** sortable list with overall ratings, condition, form, value, wage and contract. Player profiles show attributes, role ratings, face stats, traits and a scouted potential range.
- **Tactics board:** formation, who plays where, each player's role, and team instructions.
- **League tables** with promotion, play-off and relegation zones and form. **Fixtures & results**, and **match reports** with events, team stats and player ratings.
- **Full seasons:** Championship play-offs (the new 3rd–8th format), League One and Two play-offs, promotion and relegation, player development each summer, then the next season.
- **Fitness, injuries, suspensions and form** carry over between matches.
- **Saves:** 3 save slots with autosave after every Continue, plus manual Save.

**Not in yet** (planned next; see the roadmap in [docs/design.md](docs/design.md))

- Transfers, contract negotiations, finances, the board, youth academy and staff. Contracts renew automatically for now.
- Domestic cups and European competitions. Leagues outside England are a player pool only.
- Retirements and newly generated youth players.
- Match-engine calibration is still in progress. Watched matches average ~3.4 goals against a real-world ~2.8, and occasional heavy scorelines happen.

## Requirements

- macOS/Linux with [uv](https://docs.astral.sh/uv/), Node.js and [just](https://github.com/casey/just) (`brew install uv node just`)
- Python 3.13 (uv installs it)

## Setup

```sh
just setup
```

## Data

Third-party datasets live in `data/raw/`, which is gitignored and never committed. See [docs/ATTRIBUTION.md](docs/ATTRIBUTION.md).

1. **Player ratings (EA SPORTS FC 27):** download the Kaggle dataset `mikedpad/ea-sports-fc27-player-ratings` and copy `players.csv` to `data/raw/ea_fc27/`. The data belongs to EA, so keep it local.
2. **Transfermarkt snapshot (CC0, optional enrichment):**
   ```sh
   curl -L -o data/raw/transfermarkt/transfermarkt-datasets.duckdb \
     https://pub-e682421888d945d684bcae8890b0ec20.r2.dev/data/transfermarkt-datasets.duckdb
   ```
3. Build the world:
   ```sh
   just calibrate      # fit our overall formula's scale to the ratings source
   just build-world    # writes data/worlds/base-2026-27.sqlite and a report in data/reports/
   ```

## Development

```sh
just test          # backend tests (the API flow tests run when the world has been built)
just lint          # ruff + mypy
just sim-season    # simulate a whole season of all four divisions and print the tables
just api           # backend only, with auto-reload, on http://127.0.0.1:8000
just web           # frontend dev server on http://127.0.0.1:5173 (proxies /api to the backend)
just e2e           # browser tests against a throwaway server on :8765 with temporary saves (see the run-footsim skill; needs `npx playwright install chromium`)
```

Game rules and content (positions, roles, formations, instructions, leagues, calendars, wage levels, world-building rules, fast-engine parameters) are YAML files in `data/config/`, validated at load time. Import mappings live in `data/import_profiles/`.

Saves are SQLite files in `saves/slot_N/`. If a save was made with an older schema version, the game refuses it with a message: rebuild the world with `just build-world --force` and start a new career.

Troubleshooting: if `import footsim` fails under `uv run` on macOS, run `chflags -R nohidden backend/.venv`. Python 3.13 ignores `.pth` files that carry the macOS hidden flag, which iCloud Drive sync can set, so keep the project outside iCloud-synced folders.

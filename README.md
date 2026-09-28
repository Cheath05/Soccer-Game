# Soccer-Game

A local football management simulation: a living world of clubs and players, an agent-based match engine you can watch and control in 2D, and the full management layer. The design is in [docs/design.md](docs/design.md), and architecture decisions are in [docs/adr/](docs/adr/).

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
just test    # backend tests
just lint    # ruff + mypy
just api     # backend on http://127.0.0.1:8000
just web     # frontend on http://127.0.0.1:5173
```

Game rules and content (positions, roles, formations, leagues, calendars, wage levels, world-building rules) are YAML files in `data/config/`, validated at load time. Import mappings live in `data/import_profiles/`.

Troubleshooting: if `import footsim` fails under `uv run` on macOS, run `chflags -R nohidden backend/.venv`. Python 3.13 ignores `.pth` files that carry the macOS hidden flag.

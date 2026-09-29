# Task runner: `just --list`

backend := "backend"
frontend := "frontend"

# Install backend (incl. data-pipeline tools) and frontend dependencies
setup:
    cd {{backend}} && uv sync --group dev --group data
    cd {{frontend}} && npm install

# Run the backend test suite
test:
    cd {{backend}} && uv run pytest

# Lint and type-check the backend
lint:
    cd {{backend}} && uv run ruff check src tests
    cd {{backend}} && uv run mypy

# Everything CI would run
check: lint test
    cd {{frontend}} && npm run build

# Fit overall-rating scaling to the ratings source (writes data/config/calibration/)
calibrate:
    cd {{backend}} && uv run footsim calibrate-overall

# Build the base world from data/raw (pass --force to rebuild)
build-world *args:
    cd {{backend}} && uv run footsim build-world {{args}}

# Build the interface and play: http://127.0.0.1:8000
demo:
    cd {{frontend}} && npm run build
    @echo "Footsim is running at http://127.0.0.1:8000  (Ctrl+C to stop)"
    cd {{backend}} && uv run uvicorn footsim.api.app:app --host 127.0.0.1 --port 8000

# Play a season of every English league without a user club and print the tables
sim-season *args:
    cd {{backend}} && uv run footsim sim-season {{args}}

# Play a batch of agent-engine matches and compare with real football (reports/engine/)
# e.g. just calibrate-engine --n 200 --division ENG4 --ab aggressive:mentality=attacking
calibrate-engine *args:
    cd {{backend}} && uv run footsim calibrate-engine {{args}}

# Browser smoke test against a running server (default: the demo on port 8000)
e2e url="http://127.0.0.1:8000":
    cd {{frontend}} && node e2e/smoke.mjs {{url}} /tmp && node e2e/live.mjs {{url}} /tmp

# API server on http://127.0.0.1:8000
api:
    cd {{backend}} && uv run uvicorn footsim.api.app:app --host 127.0.0.1 --port 8000 --reload

# Frontend dev server on http://127.0.0.1:5173 (proxies /api to the backend)
web:
    cd {{frontend}} && npm run dev

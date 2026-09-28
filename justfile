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

# API server on http://127.0.0.1:8000
api:
    cd {{backend}} && uv run uvicorn footsim.api.app:app --host 127.0.0.1 --port 8000 --reload

# Frontend dev server on http://127.0.0.1:5173 (proxies /api to the backend)
web:
    cd {{frontend}} && npm run dev

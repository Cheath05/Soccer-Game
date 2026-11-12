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

# Browser tests against a running throwaway server (default :8765; see the run-footsim skill).
# They start a new career, which overwrites save slot 1, so they refuse the user's :8000 game.
e2e url="http://127.0.0.1:8765":
    cd {{frontend}} && node e2e/smoke.mjs {{url}} /tmp && node e2e/live.mjs {{url}} /tmp && node e2e/phone.mjs {{url}} /tmp

# API server on http://127.0.0.1:8000
api:
    cd {{backend}} && uv run uvicorn footsim.api.app:app --host 127.0.0.1 --port 8000 --reload

# Frontend dev server on http://127.0.0.1:5173 (proxies /api to the backend)
web:
    cd {{frontend}} && npm run dev

# iOS app (docs/plans/commercial-ios-release.md, Track I; see ios/README.md).
# Python packages for iOS into ios/wheelhouse and ios/build/site-packages-* (once, or after a
# dependency changes)
ios-wheels:
    ios/scripts/build_wheels.sh
    ios/scripts/install_site_packages.sh device ios/build/site-packages-device
    ios/scripts/install_site_packages.sh simulator ios/build/site-packages-simulator

# Assemble the game for the app (ios/build/app) and generate the Xcode project
ios-bundle profile="personal":
    ios/scripts/assemble_bundle.sh {{profile}}
    cd ios && xcodegen generate

# Build and run in the simulator
ios-sim device="iPhone 17 Pro Max": ios-bundle
    cd ios && xcodebuild -project Footsim.xcodeproj -scheme Footsim -destination 'platform=iOS Simulator,name={{device}}' -derivedDataPath build/dd build | grep -E "error:|BUILD"
    xcrun simctl boot "{{device}}" || true
    xcrun simctl install "{{device}}" ios/build/dd/Build/Products/Debug-iphonesimulator/Footsim.app
    xcrun simctl launch --terminate-running-process "{{device}}" com.alexbenton.footsim.personal

# Build, sign and install on the connected iPhone (Xcode needs your Apple account: Settings > Accounts)
ios-phone: ios-bundle
    cd ios && xcodebuild -project Footsim.xcodeproj -scheme Footsim -destination 'generic/platform=iOS' -derivedDataPath build/dd -allowProvisioningUpdates build | grep -E "error:|BUILD"
    xcrun devicectl device install app --device "$(xcrun devicectl list devices | awk '/iPhone/ && /physical/ {for (i=1;i<=NF;i++) if ($i ~ /^[0-9A-F]{8}-[0-9A-F]{16}$/) print $i}' | head -1)" ios/build/dd/Build/Products/Debug-iphoneos/Footsim.app

#!/bin/bash
# Assemble the game as the app carries it, in ios/build/app, laid out as in the repository so
# the game's own paths hold (core/paths.py's REPO_ROOT is the `app` folder):
#   backend/src/footsim   the game (without the calibration tools, the CLI and the importers
#                         that only build worlds), with bytecode
#   data/config, data/changelog.yaml
#   data/worlds/<world>   one file, checkpointed, no WAL
#   frontend/dist         the pages, built now
#   build.json            the version and commit (there's no git on a phone)
# Usage: ios/scripts/assemble_bundle.sh [personal]   (the store profile comes with PW1/I6)
set -euo pipefail

PROFILE="${1:-personal}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="$ROOT/ios/build/app"
WORLD="base-2026-27.sqlite"
if [ "$PROFILE" != "personal" ]; then
    echo "only the personal profile exists so far" >&2
    exit 1
fi

rm -rf "$OUT"
mkdir -p "$OUT/backend/src" "$OUT/data/worlds" "$OUT/frontend"

rsync -a --exclude '__pycache__' --exclude 'calibration/' --exclude 'cli.py' \
    --exclude 'importers/build_world.py' --exclude 'importers/csv_source.py' \
    --exclude 'importers/transfermarkt.py' --exclude 'importers/profile.py' \
    "$ROOT/backend/src/footsim" "$OUT/backend/src/"

rsync -a "$ROOT/data/config" "$OUT/data/"
cp "$ROOT/data/changelog.yaml" "$OUT/data/"

# One self-contained file: VACUUM INTO checkpoints and leaves no -wal or -shm behind.
/usr/bin/python3 - "$ROOT/data/worlds/$WORLD" "$OUT/data/worlds/$WORLD" <<'PY'
import sqlite3, sys
source = sqlite3.connect(sys.argv[1])
source.execute("VACUUM INTO ?", (sys.argv[2],))
source.close()
copy = sqlite3.connect(sys.argv[2])
copy.execute("PRAGMA journal_mode=DELETE")
copy.close()
PY

(cd "$ROOT/frontend" && npm run build >/dev/null)
rsync -a "$ROOT/frontend/dist" "$OUT/frontend/"

cd "$ROOT"
DESCRIBED="$(git describe --tags --match 'v[0-9]*' --long)"
MAJOR="$(echo "$DESCRIBED" | sed -E 's/^v([0-9]+).*/\1/')"
MINOR="$(echo "$DESCRIBED" | sed -E 's/^v[0-9.]+-([0-9]+)-g.*/\1/')"
cat > "$OUT/build.json" <<JSON
{"FOOTSIM_VERSION": "$MAJOR.$MINOR", "FOOTSIM_COMMIT": "$(git rev-parse --short HEAD)",
 "FOOTSIM_COMMIT_DATE": "$(git log -1 --format=%cI)", "FOOTSIM_BRANCH": "$(git rev-parse --abbrev-ref HEAD)",
 "FOOTSIM_BUILD_PROFILE": "$PROFILE"}
JSON

# Bytecode beside the sources: the bundle is read-only, and importing is twice as fast with it.
(cd "$ROOT/backend" && uv run --frozen python -m compileall -q \
    --invalidation-mode unchecked-hash "$OUT/backend/src/footsim" >/dev/null)

du -sh "$OUT" | sed 's/^/assembled: /'

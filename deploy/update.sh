#!/usr/bin/env bash
# Deploy the newest commit of the checked-out branch, unless the game is in use.
#
# footsim-update.timer runs this every ten minutes (install.sh sets it up). To update now, run
# "systemctl --user start footsim-update", or run this script. In order, it:
#   1. fetches, and stops quietly if nothing is new;
#   2. refuses to touch a checkout with uncommitted changes to tracked files;
#   3. stops quietly, to try again next time, if the game is in use (a connection to the port,
#      or a sim-to-date running);
#   4. fast-forwards the checkout (never a reset, rebase or force), installs the dependencies
#      and builds the frontend beside the live one;
#   5. swaps the new frontend in, restarts the server and checks that it answers.
# A failure before step 5 leaves the running server, and the frontend it serves, as they were.
#
# The commit last deployed is kept in ~/.local/state/footsim, so a build that failed after the
# fast-forward is tried again next time, and so is a checkout that was moved by hand.
set -euo pipefail

port=8000
base="http://127.0.0.1:$port"
unit=footsim.service
state_dir="${XDG_STATE_HOME:-$HOME/.local/state}/footsim"
marker="$state_dir/deployed-commit"

log() { printf 'footsim-update: %s\n' "$*"; }
fail() { printf 'footsim-update: %s\n' "$*" >&2; exit 1; }

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"
trap 'rm -rf "$root/frontend/dist-next"' EXIT

# One update at a time: the timer and a hand-started run could overlap.
mkdir -p "$state_dir"
exec 9>"$state_dir/update.lock"
flock -n 9 || { log "another update is running"; exit 0; }

# Nothing here may wait for a password: the timer has nobody to type it.
export GIT_TERMINAL_PROMPT=0

branch=$(git rev-parse --abbrev-ref HEAD)
[ "$branch" != HEAD ] || fail "the checkout is not on a branch, so there is nothing to follow"
timeout 120 git fetch --quiet origin "$branch" || fail "could not fetch origin/$branch"

head=$(git rev-parse HEAD)
remote=$(git rev-parse "origin/$branch")
deployed=$(cat "$marker" 2>/dev/null || true)

# Is there something to fast-forward to? If origin is behind (a commit made here and not pushed),
# the checkout is deployed as it is; if the two have diverged, a person has to sort it out.
merge=no
if [ "$head" != "$remote" ]; then
  if git merge-base --is-ancestor "$head" "$remote"; then
    merge=yes
  elif ! git merge-base --is-ancestor "$remote" "$head"; then
    fail "HEAD and origin/$branch have diverged; leaving the checkout alone"
  fi
fi
if [ "$merge" = no ] && [ "$head" = "$deployed" ]; then
  exit 0
fi

if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  fail "tracked files have uncommitted changes; not updating (commit or discard them by hand)"
fi

# In use: a browser connected (a match being watched holds a WebSocket open), or a sim-to-date
# running in the background, which needs no connection.
busy() {
  local connections sim
  connections=$(ss -Htn state established "( sport = :$port )") || fail "cannot list connections with ss"
  [ -z "$connections" ] || return 0
  sim=$(curl -sf --max-time 5 "$base/api/career/sim" || true)
  grep -Eq '"running"[[:space:]]*:[[:space:]]*true' <<<"$sim"
}

if busy; then
  log "busy, will try again"
  exit 0
fi

if [ "$merge" = yes ]; then
  git merge --quiet --ff-only "origin/$branch" || fail "cannot fast-forward to origin/$branch"
  log "checkout is now at $(git rev-parse --short HEAD) on $branch"
else
  log "deploying $(git rev-parse --short HEAD), which is checked out but not deployed"
fi

# step <directory> <what> <command...>: run in that directory of the checkout, or give up.
step() {
  local dir=$1 what=$2
  shift 2
  log "$what"
  (cd "$root/$dir" && "$@") || fail "$what failed; the running server is untouched"
}

step backend "installing Python dependencies" uv sync --frozen
step frontend "installing frontend dependencies" npm ci --no-audit --no-fund
rm -rf "$root/frontend/dist-next"
step frontend "building the frontend" npm run build -- --outDir dist-next --emptyOutDir

# The build took a minute or two; somebody may have started playing meanwhile.
if busy; then
  log "busy, will try again"
  exit 0
fi

# The running server reads frontend/dist from disk, so this swap is all it sees before the restart.
rm -rf "$root/frontend/dist-old"
if [ -d "$root/frontend/dist" ]; then
  mv "$root/frontend/dist" "$root/frontend/dist-old"
fi
mv "$root/frontend/dist-next" "$root/frontend/dist"
rm -rf "$root/frontend/dist-old"

expected=$(git rev-parse --short HEAD)
log "restarting $unit"
systemctl --user restart "$unit" || fail "could not restart $unit"

for _ in $(seq 30); do
  if body=$(curl -sf --max-time 2 "$base/api/health"); then
    running=$(sed -n 's/.*"commit"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' <<<"$body")
    [ "$running" = "$expected" ] || fail "the server answers but reports commit '${running:-none}', not $expected"
    git rev-parse HEAD > "$marker"
    log "deployed: the server is up on commit $running"
    exit 0
  fi
  sleep 1
done
fail "the server did not answer on /api/health within 30 s; see: journalctl --user -u footsim"

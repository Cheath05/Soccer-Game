#!/usr/bin/env bash
# Install footsim on an Ubuntu machine as systemd user services, kept up to date automatically:
#   footsim.service        the game, on 127.0.0.1:8000
#   footsim-update.timer   runs deploy/update.sh every ten minutes
# Run it as your normal user (no sudo) from anywhere in the checkout. Running it again is safe:
# it refreshes the dependencies, the build and the unit files, and restarts the game.
set -euo pipefail

port=8000
base="http://127.0.0.1:$port"

say() { printf 'footsim-install: %s\n' "$*"; }
die() { printf 'footsim-install: %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -ne 0 ] || die "run this as your normal user, not root: the services belong to that user"

# The tools. update.sh needs curl and ss as well.
missing=()
for tool in git curl uv node npm ss; do
  command -v "$tool" >/dev/null 2>&1 || missing+=("$tool")
done
if [ "${#missing[@]}" -gt 0 ]; then
  {
    printf 'footsim-install: missing: %s\n' "${missing[*]}"
    for tool in "${missing[@]}"; do
      case $tool in
        uv) hint='curl -LsSf https://astral.sh/uv/install.sh | sh   (then open a new shell, so ~/.local/bin is on the PATH)' ;;
        node | npm) hint='curl -fsSL https://deb.nodesource.com/setup_24.x | sudo -E bash - && sudo apt install -y nodejs' ;;
        ss) hint='sudo apt install -y iproute2' ;;
        *) hint="sudo apt install -y $tool" ;;
      esac
      printf '  %s: %s\n' "$tool" "$hint"
    done
    echo "Install them, then run this again."
  } >&2
  exit 1
fi
if [ "$(node -p 'process.versions.node.split(".")[0]')" -lt 22 ]; then
  die "node $(node -v) is too old to build the frontend (22 or newer). Install Node 24 from NodeSource: curl -fsSL https://deb.nodesource.com/setup_24.x | sudo -E bash - && sudo apt install -y nodejs"
fi

repo=$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel) \
  || die "this script is not inside a git checkout of footsim"
[[ $repo != *[[:space:]%]* ]] || die "the checkout's path ($repo) has a space or a % in it: move it somewhere plainer"
cd "$repo"
uv=$(command -v uv)
node_dir=$(dirname "$(command -v node)")
# What the units can see: uv and node may live outside systemd's default PATH.
unit_path="$HOME/.local/bin:$(dirname "$uv"):$node_dir:/usr/local/bin:/usr/bin:/bin"

say "installing the Python dependencies (uv sync --frozen)"
(cd backend && uv sync --frozen)
say "installing the frontend dependencies (npm ci)"
(cd frontend && npm ci --no-audit --no-fund)
say "building the frontend (npm run build)"
(cd frontend && npm run build)

world=data/worlds/base-2026-27.sqlite
mkdir -p data/worlds
if [ ! -f "$world" ]; then
  say "WARNING: $world is missing, so no career can be started. It is never in git. Copy it"
  say "from the Mac (run this there; use this machine's Tailscale name or address if the"
  say "hostname doesn't resolve):"
  say "  scp ~/Developer/Soccer-Game/data/worlds/base-2026-27.sqlite $USER@$(hostname):$repo/data/worlds/"
fi

say "writing the systemd user units"
units="$HOME/.config/systemd/user"
mkdir -p "$units"

cat > "$units/footsim.service" <<EOF
[Unit]
Description=Footsim, the football manager simulator

[Service]
WorkingDirectory=$repo/backend
Environment=PATH=$unit_path
ExecStart=$uv run --frozen uvicorn footsim.api.app:app --host 127.0.0.1 --port $port
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
EOF

cat > "$units/footsim-update.service" <<EOF
[Unit]
Description=Pull and deploy the newest footsim commit, unless the game is in use

[Service]
Type=oneshot
WorkingDirectory=$repo
Environment=PATH=$unit_path
ExecStart=$repo/deploy/update.sh
EOF

cat > "$units/footsim-update.timer" <<EOF
[Unit]
Description=Look for a new footsim commit every ten minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=10min
Persistent=true

[Install]
WantedBy=timers.target
EOF

[ -x "$repo/deploy/update.sh" ] || chmod +x "$repo/deploy/update.sh"

# Lingering keeps the user's services running after logout and starts them at boot.
if [ "$(loginctl show-user "$USER" --property=Linger --value 2>/dev/null || true)" != yes ]; then
  say "enabling lingering, so the game starts at boot and keeps running when you log out"
  loginctl enable-linger "$USER" 2>/dev/null || {
    say "that needs sudo here:"
    sudo loginctl enable-linger "$USER"
  } || die "could not enable lingering; run: sudo loginctl enable-linger $USER"
fi

# Over ssh the runtime directory is already set; the user manager may take a moment to appear.
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
for _ in $(seq 20); do
  systemctl --user show-environment >/dev/null 2>&1 && break
  sleep 1
done
systemctl --user show-environment >/dev/null 2>&1 \
  || die "cannot reach your systemd user manager. Log in again over ssh (not su or sudo -u) and re-run this."

was_running=no
if systemctl --user is-active --quiet footsim.service; then
  was_running=yes
fi
systemctl --user daemon-reload
systemctl --user enable --now footsim.service footsim-update.timer
if [ "$was_running" = yes ]; then
  say "footsim was already running; restarting it on the new build"
  systemctl --user restart footsim.service
fi

say "waiting for the game to answer"
for _ in $(seq 30); do
  if body=$(curl -sf --max-time 2 "$base/api/health"); then
    commit=$(sed -n 's/.*"commit"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' <<<"$body")
    # What update.sh compares with, so it doesn't redeploy this commit.
    state_dir="${XDG_STATE_HOME:-$HOME/.local/state}/footsim"
    mkdir -p "$state_dir"
    git rev-parse HEAD > "$state_dir/deployed-commit"
    say "up on commit ${commit:-unknown}"
    break
  fi
  sleep 1
done
if [ -z "${commit:-}" ]; then
  say "WARNING: no answer from $base/api/health after 30 s. See: journalctl --user -u footsim"
fi

cat <<EOF

Footsim runs on 127.0.0.1:$port, which only this machine can reach. To use it from your own
devices over Tailscale, run this once:

    sudo tailscale serve --bg $port

then open https://<vm-name>.<tailnet>.ts.net (the address is shown by: tailscale serve status).

Keep it on your tailnet: no "tailscale funnel", no port forwarding. The world holds EA's ratings.
Without HTTPS, you could bind all interfaces instead: change --host 127.0.0.1 to --host 0.0.0.0
in $units/footsim.service, run
"systemctl --user daemon-reload && systemctl --user restart footsim", and open
http://<tailscale-ip>:$port. Then only a firewall that admits just tailscale0 keeps it private.

Updates: every ten minutes the newest commit of this branch is deployed, unless someone is
playing. To update now: systemctl --user start footsim-update

Logs:
    journalctl --user -u footsim -f
    journalctl --user -u footsim-update
EOF

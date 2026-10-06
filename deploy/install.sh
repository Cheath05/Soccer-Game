#!/usr/bin/env bash
# Install footsim for PRODUCTION on an Ubuntu machine: systemd user services, kept up to date.
#   footsim.service        the game, on 127.0.0.1:$FOOTSIM_PORT (default 8001)
#   footsim-update.timer   runs deploy/update.sh shortly after boot and every ten minutes
# Settings: ~/.config/footsim/deploy.env (see deploy/common.sh). Run it as your normal user from
# anywhere in the checkout. Running it again is safe: it refreshes the dependencies, the build
# and the unit files, and restarts the game.
#
#   deploy/install.sh [--port N] [--yes]
#     --port N   listen on 127.0.0.1:N (default: the settings file's, else 8001)
#     --yes      don't ask before replacing an old system-level footsim.service
#
# Before deploy/ existed, footsim may have been set up by hand as a system service
# (/etc/systemd/system/footsim.service). Two services would fight over the port, so the user
# service becomes the only one: the old unit is checked to really be footsim, backed up to
# ~/.config/footsim/, stopped and removed (with sudo), and its saves folder is kept. If the new
# service doesn't answer, the old one is put back as it was.
#
# Nothing else on the machine is touched: no other service, port or Tailscale setting.
set -euo pipefail

say() { printf 'footsim-install: %s\n' "$*"; }
die() { printf 'footsim-install: %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -ne 0 ] || die "run this as your normal user, not root: the services belong to that user"

new_port=""
assume_yes=no
while [ $# -gt 0 ]; do
  case $1 in
    --port) new_port=${2:-}; shift 2 ;;
    --port=*) new_port=${1#--port=}; shift ;;
    --yes | -y) assume_yes=yes; shift ;;
    *) die "unknown option $1 (see the top of this script)" ;;
  esac
done
if [ -n "$new_port" ] && ! [[ $new_port =~ ^[0-9]+$ ]]; then
  die "--port needs a number"
fi

# The tools. update.sh needs curl, ss and flock as well.
missing=()
for tool in git curl uv node npm ss flock; do
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
        flock) hint='sudo apt install -y util-linux' ;;
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
# shellcheck source=deploy/common.sh
. "$repo/deploy/common.sh"
if [ -n "$new_port" ]; then
  FOOTSIM_PORT=$new_port
  port=$new_port
  base="http://127.0.0.1:$port"
fi
uv=$(command -v uv)
node_dir=$(dirname "$(command -v node)")
# What the units can see: uv and node may live outside systemd's default PATH.
unit_path="$HOME/.local/bin:$(dirname "$uv"):$node_dir:/usr/local/bin:/usr/bin:/bin"

# --- 1. Look before touching anything --------------------------------------------------------
old_unit=no
fragment=""
saves_dir="${FOOTSIM_SAVES_DIR:-}"
if system_unit_exists; then
  fragment=$(systemctl show -p FragmentPath --value "$unit")
  say "found a system-level $unit ($fragment):"
  systemctl cat "$unit" 2>/dev/null | sed 's/^/    /'
  if ! systemctl cat "$unit" 2>/dev/null | grep -q 'footsim.api.app'; then
    die "that system $unit doesn't run footsim (no footsim.api.app in it); not touching it"
  fi
  old_unit=yes
  old_dir=$(systemctl show -p WorkingDirectory --value "$unit")
  old_env=$(systemctl show -p Environment --value "$unit")
  old_user=$(systemctl show -p User --value "$unit")
  old_saves=$(grep -o 'FOOTSIM_SAVES_DIR=[^ ]*' <<<"$old_env" | head -1 | cut -d= -f2- || true)
  if [ -z "$saves_dir" ] && [ -n "$old_saves" ]; then
    saves_dir=$old_saves
    say "it kept its careers in $saves_dir: the new service will too"
  elif [ -z "$saves_dir" ] && [ -n "$old_dir" ] && [ "$old_dir" != "$repo/backend" ] \
       && [ -d "$old_dir/../saves" ]; then
    saves_dir=$(cd "$old_dir/.." && pwd)/saves
    say "it ran from another checkout ($old_dir): the new service keeps its careers, $saves_dir"
  fi
  say "it runs as ${old_user:-root}"
fi
[ -n "$saves_dir" ] || saves_dir="$repo/saves"

# Whatever answers on our port must be footsim, or we stop: never take over another app's port.
if [ -n "$(listening "$port")" ]; then
  if ! health "$port" >/dev/null; then
    die "something that isn't footsim listens on port $port; not touching it. Pick another port with --port"
  fi
  if [ "$old_unit" = no ] && ! systemctl --user is-active --quiet "$unit" 2>/dev/null; then
    die "footsim is already running on port $port but not as a service (a terminal running uvicorn?). Stop it (Ctrl+C there), then run this again"
  fi
fi

# --- 2. Build, while whatever is running keeps running ---------------------------------------
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
  say "from the Mac (run this there; use this machine's Tailscale name or address):"
  say "  scp ~/Developer/Soccer-Game/data/worlds/base-2026-27.sqlite $USER@$(hostname):$repo/data/worlds/"
fi

# The careers must be writable by this user. A system service that ran as root may have left
# them owned by root.
mkdir -p "$saves_dir" 2>/dev/null || true
if [ -n "$(find "$saves_dir" ! -user "$USER" -print -quit 2>/dev/null)" ]; then
  say "some of $saves_dir isn't owned by $USER (the old service's files); giving them to $USER"
  sudo chown -R "$USER:" "$saves_dir"
fi

# --- 3. Settings and units -------------------------------------------------------------------
mkdir -p "$config_dir" "$state_dir"
{
  echo "# footsim production settings on this machine (deploy/install.sh; see deploy/common.sh)."
  echo "FOOTSIM_PORT=$port"
  echo "FOOTSIM_SERVE_PORT=$FOOTSIM_SERVE_PORT"
  if [ "$saves_dir" != "$repo/saves" ]; then
    echo "FOOTSIM_SAVES_DIR=$saves_dir"
  fi
} > "$env_file"
say "settings: $env_file (port $port)"

say "writing the systemd user units"
units="$HOME/.config/systemd/user"
mkdir -p "$units"
cat > "$units/footsim.service" <<EOF
[Unit]
Description=Footsim, the football manager simulator (127.0.0.1:\${FOOTSIM_PORT})

[Service]
WorkingDirectory=$repo/backend
Environment=PATH=$unit_path
EnvironmentFile=$env_file
ExecStart=$uv run --frozen uvicorn footsim.api.app:app --host 127.0.0.1 --port \${FOOTSIM_PORT}
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
Description=Look for a new footsim commit shortly after boot and every ten minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=10min

[Install]
WantedBy=timers.target
EOF
chmod +x "$repo/deploy/update.sh" "$repo/deploy/status.sh"

# Lingering keeps the user's services running after logout and starts them at boot.
if [ "$(loginctl show-user "$USER" --property=Linger --value 2>/dev/null || true)" != yes ]; then
  say "enabling lingering, so the game starts at boot and keeps running when you log out"
  loginctl enable-linger "$USER" 2>/dev/null || sudo loginctl enable-linger "$USER" \
    || die "could not enable lingering; run: sudo loginctl enable-linger $USER"
fi
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
for _ in $(seq 20); do
  systemctl --user show-environment >/dev/null 2>&1 && break
  sleep 1
done
systemctl --user show-environment >/dev/null 2>&1 \
  || die "cannot reach your systemd user manager. Log in again over ssh (not su or sudo -u) and re-run this."
systemctl --user daemon-reload

# --- 4. Hand over from the old system service, if there is one -------------------------------
backup=""
if [ "$old_unit" = yes ]; then
  if [ "$assume_yes" != yes ]; then
    printf 'footsim-install: replace the system-level %s with the user service (backed up first)? [y/N] ' "$unit"
    read -r answer
    [[ $answer =~ ^[Yy] ]] || die "left everything as it was: the old system service still runs footsim"
  fi
  backup="$config_dir/footsim.system-service.backup"
  systemctl cat "$unit" > "$backup"
  say "backed up the old unit (with any drop-ins) to $backup"
  say "stopping and removing the old system service (sudo)"
  sudo systemctl disable --now "$unit"
  sudo rm -f "$fragment"
  sudo rm -rf "/etc/systemd/system/$unit.d"
  sudo systemctl daemon-reload
  for _ in $(seq 20); do
    [ -z "$(listening "$port")" ] && break
    sleep 1
  done
fi

restore_old() {
  [ -n "$backup" ] || return 0
  say "putting the old system service back as it was"
  systemctl --user disable --now footsim.service footsim-update.timer || true
  grep -v '^# /' "$backup" | sudo tee "/etc/systemd/system/$unit" >/dev/null
  sudo systemctl daemon-reload
  sudo systemctl enable --now "$unit"
}

# --- 5. Start, and check it answers ----------------------------------------------------------
if systemctl --user is-active --quiet footsim.service; then
  systemctl --user restart footsim.service
fi
systemctl --user enable --now footsim.service footsim-update.timer

say "waiting for the game to answer on $base"
body=""
for _ in $(seq 60); do
  if body=$(health "$port"); then
    break
  fi
  body=""
  sleep 1
done
if [ -z "$body" ]; then
  restore_old
  die "no answer from $base/api/health after 60 s. See: journalctl --user -u footsim -n 50"
fi
commit=$(json_field "$body" commit)
version=$(json_field "$body" version)
git rev-parse HEAD > "$marker"
say "up: version ${version:-unknown}, commit ${commit:-unknown}"
[ -z "$backup" ] || say "the old system service is gone; its unit is kept in $backup"

echo
"$repo/deploy/status.sh" || true
cat <<EOF

To reach it from your devices, Tailscale Serve must forward HTTPS port $FOOTSIM_SERVE_PORT to it.
If the status above doesn't show that, run once (it doesn't touch the normal HTTPS on 443):
    sudo tailscale serve --bg --https=$FOOTSIM_SERVE_PORT http://127.0.0.1:$port
Keep it on your tailnet: no "tailscale funnel", no port forwarding. The world holds EA's ratings.
EOF

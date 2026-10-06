# Shared by deploy/install.sh, deploy/update.sh and deploy/status.sh (sourced, not run).
#
# These scripts are for a PRODUCTION install: the machine where footsim runs as a service, kept
# up to date from git. Its settings live outside the checkout, in this machine's own file:
#     ~/.config/footsim/deploy.env
#   FOOTSIM_PORT          the port footsim listens on, on 127.0.0.1 only (default 8001)
#   FOOTSIM_SERVE_PORT    the HTTPS port Tailscale Serve gives it, for the checks (default 8443)
#   FOOTSIM_SAVES_DIR     where the careers are saved, if not the checkout's saves/ folder
# install.sh writes the file. The game's service reads it too (EnvironmentFile), so the port and
# the saves folder are the same for the service, the updater and the checks.
#
# Development and testing don't use any of this: `just demo`, `just api` and the test servers
# keep their own ports (8000 and 8765).

config_dir="${XDG_CONFIG_HOME:-$HOME/.config}/footsim"
env_file="$config_dir/deploy.env"
state_dir="${XDG_STATE_HOME:-$HOME/.local/state}/footsim"
marker="$state_dir/deployed-commit"
unit=footsim.service

if [ -f "$env_file" ]; then
  # shellcheck disable=SC1090
  . "$env_file"
fi
FOOTSIM_PORT="${FOOTSIM_PORT:-8001}"
FOOTSIM_SERVE_PORT="${FOOTSIM_SERVE_PORT:-8443}"
port=$FOOTSIM_PORT
base="http://127.0.0.1:$port"

# json_field <json> <key>: a string value from footsim's flat health JSON (no jq needed).
json_field() {
  sed -n "s/.*\"$2\"[[:space:]]*:[[:space:]]*\"\\([^\"]*\\)\".*/\\1/p" <<<"$1"
}

# health [port]: footsim's /api/health on the port, or nothing (and a failure) if what answers
# isn't footsim. Only footsim's health has "saves_dir" in it.
health() {
  local body
  body=$(curl -sf --max-time 3 "http://127.0.0.1:${1:-$port}/api/health" 2>/dev/null) || return 1
  grep -q '"saves_dir"' <<<"$body" || return 1
  printf '%s' "$body"
}

# listening <port>: what listens on 127.0.0.1:<port> (or any address), one line each.
listening() {
  ss -Hltn "( sport = :$1 )" 2>/dev/null
}

# system_unit_active / system_unit_exists: the old, hand-made /etc/systemd/system/footsim.service
# that installs before deploy/ used. Reading it needs no sudo.
system_unit_exists() {
  [ -n "$(systemctl show -p FragmentPath --value "$unit" 2>/dev/null)" ]
}
system_unit_active() {
  systemctl is-active --quiet "$unit" 2>/dev/null
}

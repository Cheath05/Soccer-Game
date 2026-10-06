#!/usr/bin/env bash
# Where the production footsim stands on this machine. It only looks, and never changes anything:
#   - the service: exactly one footsim, the user service, answering on 127.0.0.1:$FOOTSIM_PORT;
#   - its version, commit and branch, and the checkout the updater follows;
#   - the update timer, and when it next runs;
#   - lingering (so it keeps running after logout and starts at boot);
#   - Tailscale Serve's HTTPS port for it;
#   - what else listens on the other ports, shown and left alone.
set -uo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck source=deploy/common.sh
. "$root/deploy/common.sh"

ok() { printf '  ok    %s\n' "$*"; }
bad() { printf '  FIX   %s\n' "$*"; problems=$((problems + 1)); }
info() { printf '        %s\n' "$*"; }
problems=0

echo "footsim production status (settings: $env_file)"

# The service: the user unit, and no system-level one beside it.
if systemctl --user is-active --quiet "$unit" 2>/dev/null; then
  ok "user service $unit is active ($(systemctl --user is-enabled "$unit" 2>/dev/null))"
else
  bad "user service $unit is not active: systemctl --user status $unit"
fi
if system_unit_exists; then
  bad "a system-level $unit exists too ($(systemctl show -p FragmentPath --value "$unit")): run deploy/install.sh to retire it"
else
  ok "no system-level $unit (one footsim service only)"
fi

# What answers on the port.
if body=$(health "$port"); then
  ok "footsim answers on 127.0.0.1:$port: version $(json_field "$body" version), commit $(json_field "$body" commit), branch $(json_field "$body" branch)"
  info "saves: $(json_field "$body" saves_dir)"
else
  bad "nothing footsim answers on 127.0.0.1:$port"
fi
listeners=$(listening "$port" | wc -l | tr -d ' ')
[ "$listeners" -le 1 ] && ok "$listeners listener on port $port" || bad "$listeners listeners on port $port"
if [ "$port" != 8000 ]; then
  if [ -n "$(listening 8000)" ]; then
    info "port 8000 is in use by another app (left alone)"
  fi
fi

# The checkout the updater follows.
branch=$(git -C "$root" rev-parse --abbrev-ref HEAD 2>/dev/null)
info "checkout: $root, branch $branch at $(git -C "$root" describe --tags --match 'v[0-9]*' --always 2>/dev/null)"
deployed=$(cat "$marker" 2>/dev/null || true)
if [ -n "$deployed" ]; then
  info "last deployed commit: ${deployed:0:7}"
fi

# The updater.
timer=footsim-update.timer
if [ "$(systemctl --user is-enabled "$timer" 2>/dev/null)" = enabled ] \
   && systemctl --user is-active --quiet "$timer" 2>/dev/null; then
  ok "$timer is enabled and active"
  systemctl --user list-timers "$timer" --no-pager 2>/dev/null | sed -n '2p' | sed 's/^/        next: /'
else
  bad "$timer is not enabled and active: systemctl --user enable --now $timer"
fi
last=$(journalctl --user -u footsim-update -n 1 --no-pager -o cat 2>/dev/null | tail -1)
[ -z "$last" ] || info "last update run: $last"

# Lingering.
if [ "$(loginctl show-user "$USER" --property=Linger --value 2>/dev/null)" = yes ]; then
  ok "lingering is on (runs at boot and after logout)"
else
  bad "lingering is off: sudo loginctl enable-linger $USER"
fi

# Tailscale Serve (read only).
serve=$(tailscale serve status 2>/dev/null || sudo -n tailscale serve status 2>/dev/null || true)
if [ -z "$serve" ]; then
  info "Tailscale Serve: couldn't read it here; check with: sudo tailscale serve status"
elif grep -q ":$FOOTSIM_SERVE_PORT" <<<"$serve" && grep -q "127.0.0.1:$port" <<<"$serve"; then
  ok "Tailscale Serve has HTTPS port $FOOTSIM_SERVE_PORT for 127.0.0.1:$port"
  grep -E "https://|proxy" <<<"$serve" | sed 's/^/        /'
else
  bad "Tailscale Serve has no HTTPS port $FOOTSIM_SERVE_PORT -> 127.0.0.1:$port; run once: sudo tailscale serve --bg --https=$FOOTSIM_SERVE_PORT http://127.0.0.1:$port"
  sed 's/^/        /' <<<"$serve"
fi

if [ "$problems" -eq 0 ]; then
  echo "All good."
else
  echo "$problems thing(s) to fix (marked FIX)."
fi
exit "$problems"

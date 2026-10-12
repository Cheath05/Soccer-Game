#!/usr/bin/env bash
# Switch accounts on or off for this production footsim, or say which it is:
#   deploy/accounts.sh status
#   deploy/accounts.sh on     everyone signs in, and plays their own careers
#   deploy/accounts.sh off    as before: everyone who reaches the server plays the owner's careers
# "on" refuses until an owner account exists (deploy/users.sh add NAME --owner): the owner plays
# the careers already in the saves folder, so nothing moves. Either way it sets FOOTSIM_AUTH in
# ~/.config/footsim/deploy.env and restarts the service the way the updater does: only when no
# match is being watched and no sim is running (it waits up to ten minutes). Nothing else
# changes: not the port, not Tailscale Serve, not the other services on this machine.
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck source=deploy/common.sh
. "$root/deploy/common.sh"

log() { printf 'footsim-accounts: %s\n' "$*"; }
fail() { printf 'footsim-accounts: %s\n' "$*" >&2; exit 1; }

saves="${FOOTSIM_SAVES_DIR:-$root/saves}"
current() { grep -Eq '^FOOTSIM_AUTH=1$' "$env_file" 2>/dev/null && echo on || echo off; }

busy() {
  local body
  body=$(health "$port") || return 1  # not answering: nothing to wait for
  grep -Eq '"in_use"[[:space:]]*:[[:space:]]*true' <<<"$body"
}

restart() {
  for _ in $(seq 120); do
    busy || break
    log "a match or a sim is running; waiting"
    sleep 5
  done
  busy && fail "still in use after ten minutes; try again later (nothing restarted)"
  log "restarting $unit"
  systemctl --user restart "$unit"
  for _ in $(seq 60); do
    if body=$(health "$port"); then
      if grep -Eq '"accounts"[[:space:]]*:[[:space:]]*true' <<<"$body"; then
        log "up on 127.0.0.1:$port with accounts on"
      else
        log "up on 127.0.0.1:$port with accounts off"
      fi
      return
    fi
    sleep 1
  done
  fail "the server did not answer within 60 s; see: journalctl --user -u $unit"
}

set_auth() {  # set_auth 1|"": rewrite deploy.env with or without FOOTSIM_AUTH=1
  mkdir -p "$config_dir"
  local tmp
  tmp=$(mktemp "$config_dir/deploy.env.XXXX")
  grep -v '^FOOTSIM_AUTH=' "$env_file" 2>/dev/null >"$tmp" || true
  [ -z "$1" ] || echo "FOOTSIM_AUTH=$1" >>"$tmp"
  mv "$tmp" "$env_file"
}

case "${1:-status}" in
  status)
    echo "accounts are $(current) (settings: $env_file)"
    if [ -f "$saves/accounts.sqlite" ]; then
      "$root/deploy/users.sh" list
    else
      echo "no accounts yet: deploy/users.sh add NAME --owner"
    fi
    ;;
  on)
    [ "$(current)" = off ] || { log "accounts are already on"; exit 0; }
    [ -f "$saves/accounts.sqlite" ] && "$root/deploy/users.sh" list | grep -q ' owner ' \
      || fail "make the owner's account first: deploy/users.sh add NAME --owner"
    set_auth 1
    log "accounts switched on in $env_file"
    restart
    ;;
  off)
    [ "$(current)" = on ] || { log "accounts are already off"; exit 0; }
    set_auth ""
    log "accounts switched off in $env_file"
    restart
    ;;
  *)
    fail "usage: deploy/accounts.sh status|on|off"
    ;;
esac

#!/usr/bin/env bash
# The accounts that may play on this production footsim: a thin wrapper around "footsim users"
# that uses this machine's saves folder (~/.config/footsim/deploy.env, deploy/common.sh), so
# the accounts land where the service looks for them. Examples:
#   deploy/users.sh add Alex --owner        the owner first: you, playing the careers you have
#   deploy/users.sh add Sam --generate      a friend; prints a password to send them
#   deploy/users.sh list
#   deploy/users.sh reset-password Sam --generate
#   deploy/users.sh rename Sam Samuel      a new name to sign in with; careers unchanged
#   deploy/users.sh disable Sam             (disable Sam --enable to let them back in)
#   deploy/users.sh remove Sam              their careers stay unless --delete-saves
# Accounts only matter once they are switched on: deploy/accounts.sh on.
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck source=deploy/common.sh
. "$root/deploy/common.sh"

saves="${FOOTSIM_SAVES_DIR:-$root/saves}"
cd "$root/backend"
exec uv run --frozen footsim users --saves "$saves" "$@"

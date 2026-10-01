#!/bin/zsh
# make_variant.sh NAME INTERCEPT PER_METRE LENGTH_PER_METRE [SKILL] [LENGTH_SKILL]
# Optional pace (environment): PACE_FRICTION, PACE_ARRIVE, PACE_PER_METRE.
# Copies the measurement worktree's config and sets Step 2.3's passing values.
set -e
NAME=$1 I=$2 PM=$3 LPM=$4 SK=${5:-} LSK=${6:-}
D=/private/tmp/claude-502/cfg-$NAME
rm -rf $D && cp -R /Users/alexbenton/Developer/Soccer-Game/.worktrees/measure/data/config $D
F=$D/match/passing.yaml
sed -i '' -E "s/^intercept_scale: [0-9.]+ /intercept_scale: $I /" $F
sed -i '' -E "s/^  per_metre: [0-9.]+ /  per_metre: $PM /" $F
sed -i '' -E "s/^  length_per_metre: [0-9.]+ /  length_per_metre: $LPM /" $F
[ -n "$SK" ] && sed -i '' -E "s/^  skill: [0-9.]+ /  skill: $SK /" $F
[ -n "$LSK" ] && sed -i '' -E "s/^  length_skill: [0-9.]+ /  length_skill: $LSK /" $F
[ -n "${PACE_FRICTION:-}" ] && sed -i '' -E "s/^  roll_friction: [0-9.]+ /  roll_friction: $PACE_FRICTION /" $F
[ -n "${PACE_ARRIVE:-}" ] && sed -i '' -E "s/^  arrive: [0-9.]+ /  arrive: $PACE_ARRIVE /" $F
[ -n "${PACE_PER_METRE:-}" ] && sed -i '' -E "s/^  arrive_per_metre: [0-9.]+ /  arrive_per_metre: $PACE_PER_METRE /" $F
grep -E "^intercept_scale|^  (per_metre|length_per_metre|skill|length_skill|roll_friction|arrive|arrive_per_metre):" $F

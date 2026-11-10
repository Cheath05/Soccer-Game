#!/usr/bin/env bash
# Install ios/wheelhouse/ into a flat site-packages folder for one platform,
# ready to be copied into the app bundle.
#
#   install_site_packages.sh <device|simulator> <dest>
#
# Run build_wheels.sh first. The install uses only the wheelhouse (--no-index),
# so a missing dependency is an error rather than a silent download.
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

if [[ $# -ne 2 ]]; then
    echo "usage: $(basename "$0") <device|simulator> <dest>" >&2
    exit 2
fi

case "$1" in
    device) sdk="iphoneos" ;;
    simulator) sdk="iphonesimulator" ;;
    *) echo "platform must be 'device' or 'simulator', not '$1'" >&2; exit 2 ;;
esac
dest="$2"

if [[ ! -d "$WHEELHOUSE" ]]; then
    echo "No wheelhouse at $WHEELHOUSE. Run scripts/build_wheels.sh first." >&2
    exit 1
fi

platform_args=()
while IFS= read -r arg; do platform_args+=("$arg"); done < <(ios_platform_args "$sdk")

# Start clean so a stale package from an earlier run can't linger.
rm -rf "$dest"
mkdir -p "$dest"

pip_cmd install \
    --target "$dest" \
    --no-index --find-links "$WHEELHOUSE" \
    --only-binary=:all: \
    --python-version "$PYTHON_VERSION" --implementation cp --abi cp313 \
    "${platform_args[@]}" \
    --no-compile \
    -r "$REQUIREMENTS"

# Console scripts (uvicorn, fastapi, f2py, ...) can't run on iOS: there are no processes.
rm -rf "$dest/bin"

# Every compiled module must be built for the platform asked for.
want="IOS"
[[ "$sdk" == "iphonesimulator" ]] && want="IOSSIMULATOR"
bad=0
count=0
while IFS= read -r -d '' lib; do
    count=$((count + 1))
    got="$(xcrun vtool -show-build "$lib" | awk '$1 == "platform" {print $2}')"
    if [[ "$got" != "$want" ]]; then
        echo "wrong platform ($got, expected $want): $lib" >&2
        bad=1
    fi
done < <(find "$dest" \( -name '*.so' -o -name '*.dylib' \) -print0)
[[ "$bad" == 0 ]] || exit 1

echo "Installed into $dest ($count compiled modules, all $want)"

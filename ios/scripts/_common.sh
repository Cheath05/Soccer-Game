# Shared settings for the iOS dependency scripts. Sourced, not run.

IOS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WHEELHOUSE="$IOS_DIR/wheelhouse"
SUPPORT_DIR="$IOS_DIR/support"
BUILD_DIR="$IOS_DIR/build"
REQUIREMENTS="$IOS_DIR/requirements-phone.txt"

PYTHON_VERSION="3.13"
IOS_MIN_VERSION="17.0"

# Wheel platform tags pip should accept. A wheel built for an older iOS runs on
# a newer one, so every major version from 13 up to the deployment target counts.
ios_platform_args() {  # $1 = iphoneos | iphonesimulator
    local sdk="$1" major
    for major in 17 16 15 14 13; do
        printf -- '--platform\nios_%s_0_arm64_%s\n' "$major" "$sdk"
    done
}

# pip, run through uv so no system Python is needed.
pip_cmd() {
    uv run --quiet --no-project --python "$PYTHON_VERSION" --with pip python -m pip "$@"
}

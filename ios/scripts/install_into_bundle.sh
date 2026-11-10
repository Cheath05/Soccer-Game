#!/bin/bash
# Xcode build phase: copy the assembled game (ios/build/app, from assemble_bundle.sh) and the
# Python packages for this platform into the app, then let the Python support package install
# the standard library and turn every .so into a signed framework (its utils.sh).
set -euo pipefail

if [ "$EFFECTIVE_PLATFORM_NAME" = "-iphonesimulator" ]; then
    PACKAGES="$PROJECT_DIR/build/site-packages-simulator"
else
    PACKAGES="$PROJECT_DIR/build/site-packages-device"
fi
GAME="$PROJECT_DIR/build/app"
for needed in "$PACKAGES" "$GAME/backend/src/footsim" "$GAME/frontend/dist/index.html"; do
    if [ ! -e "$needed" ]; then
        echo "error: $needed is missing: run ios/scripts/build_wheels.sh and ios/scripts/assemble_bundle.sh first"
        exit 1
    fi
done

rsync -a --delete "$GAME/" "$CODESIGNING_FOLDER_PATH/app/"
rsync -a --delete "$PACKAGES/" "$CODESIGNING_FOLDER_PATH/app_packages/"

source "$PROJECT_DIR/support/Python.xcframework/build/utils.sh"
install_python support/Python.xcframework app app_packages

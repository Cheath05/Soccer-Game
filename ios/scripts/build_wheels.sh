#!/usr/bin/env bash
# Fill ios/wheelhouse/ with every Python wheel the phone needs, for the device
# (arm64 iphoneos) and the Apple-silicon simulator (arm64 iphonesimulator), and
# download BeeWare's Python 3.13 iOS support package into ios/support/.
#
# Re-runnable: a step whose output already exists is skipped. Pass --force to
# rebuild pydantic-core and PyYAML.
#
# Needs: Xcode with the iOS SDK, uv, and rustup (brew install rustup). The Rust
# toolchain, its iOS targets and maturin are fetched on first use.
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

SUPPORT_BUILD="b18"
SUPPORT_TARBALL="Python-${PYTHON_VERSION}-iOS-support.${SUPPORT_BUILD}.tar.gz"
SUPPORT_URL="https://github.com/beeware/Python-Apple-support/releases/download/${PYTHON_VERSION}-${SUPPORT_BUILD}/${SUPPORT_TARBALL}"
SUPPORT_SHA256="d06acf2a9c7964a8689566353a0e707402eff822037de5e29ba0e16040f7047d"

BEEWARE_INDEX="https://pypi.anaconda.org/beeware/simple"

PYDANTIC_CORE_VERSION="2.46.5"
PYDANTIC_CORE_SHA256="10416c15b8839ecc4ef4d0885da76da6fd0f67333a0eb8aff6d93c4b8f2910fc"
PYYAML_VERSION="6.0.3"
MATURIN_VERSION="1.16.0"

# Modest by default: the build machine has 8 GB of RAM.
export CARGO_BUILD_JOBS="${CARGO_BUILD_JOBS:-4}"

FORCE=0
[[ "${1:-}" == "--force" ]] && FORCE=1

# Homebrew's rustup is keg-only, so it isn't on PATH by default.
for dir in /opt/homebrew/opt/rustup/bin "$HOME/.cargo/bin"; do
    [[ -d "$dir" ]] && PATH="$dir:$PATH"
done
export PATH

log() { printf '\n==> %s\n' "$*"; }

check_sha256() {  # $1 = file, $2 = expected
    local actual
    actual="$(shasum -a 256 "$1" | awk '{print $1}')"
    if [[ "$actual" != "$2" ]]; then
        echo "sha256 mismatch for $1: expected $2, got $actual" >&2
        exit 1
    fi
}

mkdir -p "$WHEELHOUSE" "$SUPPORT_DIR" "$BUILD_DIR/src"

# --- 1. The support package (Python.xcframework) ----------------------------

fetch_support() {
    if [[ -f "$SUPPORT_DIR/VERSIONS" ]] && grep -q "^Build: ${SUPPORT_BUILD}\$" "$SUPPORT_DIR/VERSIONS"; then
        log "Support package ${PYTHON_VERSION}-${SUPPORT_BUILD} already in place"
        return
    fi
    log "Downloading Python-Apple-support ${PYTHON_VERSION}-${SUPPORT_BUILD}"
    curl -fL --retry 3 -o "$SUPPORT_DIR/$SUPPORT_TARBALL" "$SUPPORT_URL"
    check_sha256 "$SUPPORT_DIR/$SUPPORT_TARBALL" "$SUPPORT_SHA256"
    rm -rf "$SUPPORT_DIR/Python.xcframework" "$SUPPORT_DIR/testbed" "$SUPPORT_DIR/VERSIONS"
    tar -xzf "$SUPPORT_DIR/$SUPPORT_TARBALL" -C "$SUPPORT_DIR"
}

# --- 2. pydantic-core, cross-compiled with maturin --------------------------

ensure_rust() {
    if ! command -v rustup >/dev/null; then
        echo "rustup not found. Install it with: brew install rustup" >&2
        exit 1
    fi
    rustup toolchain list | grep -q '^stable' || rustup default stable
    rustup target add --toolchain stable aarch64-apple-ios aarch64-apple-ios-sim
}

fetch_pydantic_core_source() {
    local tarball="$BUILD_DIR/src/pydantic_core-${PYDANTIC_CORE_VERSION}.tar.gz"
    if [[ ! -f "$tarball" ]]; then
        curl -fL --retry 3 -o "$tarball" \
            "https://files.pythonhosted.org/packages/source/p/pydantic_core/pydantic_core-${PYDANTIC_CORE_VERSION}.tar.gz"
    fi
    check_sha256 "$tarball" "$PYDANTIC_CORE_SHA256"
    if [[ ! -d "$BUILD_DIR/src/pydantic_core-${PYDANTIC_CORE_VERSION}" ]]; then
        tar -xzf "$tarball" -C "$BUILD_DIR/src"
    fi
}

# $1 = Rust target, $2 = SDK (iphoneos | iphonesimulator), $3 = xcframework slice
build_pydantic_core() {
    local rust_target="$1" sdk="$2" slice="$3"
    local wheel="$WHEELHOUSE/pydantic_core-${PYDANTIC_CORE_VERSION}-cp313-cp313-ios_${IOS_MIN_VERSION//./_}_arm64_${sdk}.whl"
    if [[ -f "$wheel" && "$FORCE" == 0 ]]; then
        log "pydantic-core for ${sdk} already built"
        return
    fi
    log "Building pydantic-core ${PYDANTIC_CORE_VERSION} for ${rust_target} (iOS ${IOS_MIN_VERSION})"

    local slice_dir="$SUPPORT_DIR/Python.xcframework/$slice"
    local platform_config="$slice_dir/platform-config/arm64-${sdk}"
    local target_env
    target_env="$(echo "$rust_target" | tr 'a-z-' 'A-Z_')"

    # maturin asks a Python interpreter what it is building for, and an iOS
    # interpreter can't run on the Mac. The support package ships the answer: a
    # script that turns a macOS venv into a "cross venv", whose Python reports
    # the iOS platform, extension suffix and sysconfig data (the same trick
    # Briefcase and mobile-forge use).
    local crossenv="$BUILD_DIR/crossenv-${sdk}"
    rm -rf "$crossenv"
    uv venv --quiet --python "$PYTHON_VERSION" "$crossenv"
    "$crossenv/bin/python" "$platform_config/make_cross_venv.py" "$crossenv" "$platform_config"
    local reported
    reported="$("$crossenv/bin/python" -c 'import sysconfig; print(sysconfig.get_platform())')"
    if [[ "$reported" != ios-*-arm64-"${sdk}" ]]; then
        echo "The cross venv reports '$reported', not an iOS ${sdk} platform" >&2
        exit 1
    fi

    (
        cd "$BUILD_DIR/src/pydantic_core-${PYDANTIC_CORE_VERSION}"
        # Sets the binary's minimum OS and the wheel's platform tag.
        export IPHONEOS_DEPLOYMENT_TARGET="$IOS_MIN_VERSION"
        # Where PyO3 finds the target's _sysconfigdata when cross-compiling.
        export PYO3_CROSS_LIB_DIR="$platform_config"
        export PYO3_CROSS_PYTHON_VERSION="$PYTHON_VERSION"
        export SDKROOT
        SDKROOT="$(xcrun --sdk "$sdk" --show-sdk-path)"
        # On iOS an extension module links against Python itself. PyO3 asks
        # for -lpython3.13; the slice's lib/ has that name as a link to
        # Python.framework, so the module ends up depending on
        # @rpath/Python.framework/Python, as BeeWare's own wheels do.
        export "CARGO_TARGET_${target_env}_RUSTFLAGS=-L native=${slice_dir}/lib"
        export CARGO_TARGET_DIR="$BUILD_DIR/cargo-target"
        uvx --python "$PYTHON_VERSION" "maturin@${MATURIN_VERSION}" build \
            --release \
            --target "$rust_target" \
            --interpreter "$crossenv/bin/python" \
            --out "$WHEELHOUSE"
    )
    [[ -f "$wheel" ]] || { echo "Expected wheel not produced: $wheel" >&2; ls "$WHEELHOUSE" >&2; exit 1; }
}

# --- 3. PyYAML without libyaml ----------------------------------------------

build_pyyaml() {
    local wheel="$WHEELHOUSE/pyyaml-${PYYAML_VERSION}-py3-none-any.whl"
    if [[ -f "$wheel" && "$FORCE" == 0 ]]; then
        log "PyYAML already built"
        return
    fi
    log "Building a pure-Python PyYAML ${PYYAML_VERSION}"
    local work="$BUILD_DIR/pyyaml"
    rm -rf "$work"
    mkdir -p "$work/sdist" "$work/wheel"
    pip_cmd download --no-deps --no-binary=:all: --dest "$work/sdist" "pyyaml==${PYYAML_VERSION}" >/dev/null
    tar -xzf "$work"/sdist/*.tar.gz -C "$work"
    # PYYAML_FORCE_LIBYAML=0 makes setup.py skip the C extension. setuptools
    # still tags the wheel for the build machine, so retag it afterwards.
    PYYAML_FORCE_LIBYAML=0 uv run --quiet --no-project --python "$PYTHON_VERSION" \
        --with build python -m build --wheel --outdir "$work/wheel" "$work"/pyyaml-*/ >/dev/null
    if unzip -l "$work"/wheel/*.whl | grep -Eq '\.(so|dylib)$'; then
        echo "The PyYAML wheel contains a compiled extension; expected pure Python" >&2
        exit 1
    fi
    uv run --quiet --no-project --python "$PYTHON_VERSION" --with wheel python -m wheel tags \
        --python-tag py3 --abi-tag none --platform-tag any --remove "$work"/wheel/*.whl >/dev/null
    rm -f "$wheel"
    cp "$work"/wheel/*-py3-none-any.whl "$wheel"
}

# --- 4. Everything else: PyPI (pure Python) and BeeWare (numpy) -------------

download_wheels() {  # $1 = iphoneos | iphonesimulator
    local sdk="$1"
    log "Resolving and downloading wheels for ${sdk}"
    local platform_args=()
    while IFS= read -r arg; do platform_args+=("$arg"); done < <(ios_platform_args "$sdk")
    # Full dependency resolution, binary wheels only: this fails if any
    # requirement (direct or transitive) has no wheel that installs on iOS.
    pip_cmd download \
        --dest "$WHEELHOUSE" \
        --only-binary=:all: \
        --python-version "$PYTHON_VERSION" --implementation cp --abi cp313 \
        "${platform_args[@]}" \
        --find-links "$WHEELHOUSE" \
        --extra-index-url "$BEEWARE_INDEX" \
        -r "$REQUIREMENTS"
}

fetch_support
ensure_rust
fetch_pydantic_core_source
# One target at a time: the release profile uses fat LTO, which is memory-hungry.
build_pydantic_core aarch64-apple-ios iphoneos ios-arm64
build_pydantic_core aarch64-apple-ios-sim iphonesimulator ios-arm64_x86_64-simulator
build_pyyaml
download_wheels iphoneos
download_wheels iphonesimulator

log "Wheelhouse:"
ls -1 "$WHEELHOUSE"

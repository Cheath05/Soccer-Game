# iOS build

The Python side of the iOS app: the dependency list for the phone and the
scripts that turn it into something an Xcode project can bundle. See
`docs/plans/commercial-ios-release.md` (sections 1.1, 1.2 and I0) for the why.

## What's here

| Path | Committed | What it is |
|---|---|---|
| `requirements-phone.txt` | yes | The phone's runtime dependencies, every one pinned |
| `scripts/build_wheels.sh` | yes | Fills `wheelhouse/` and downloads the support package into `support/` |
| `scripts/install_site_packages.sh` | yes | Installs the wheelhouse into a flat site-packages folder for one platform |
| `scripts/_common.sh` | yes | Settings the two scripts share (Python version, iOS minimum, platform tags) |
| `wheelhouse/` | no | Every wheel, for the device and the simulator |
| `support/` | no | BeeWare's Python-Apple-support package: `Python.xcframework` and its testbed |
| `build/` | no | Sources, cargo's target folder, logs and the installed site-packages |

## Usage

```sh
ios/scripts/build_wheels.sh                # about 5 minutes the first time
ios/scripts/install_site_packages.sh device    ios/build/site-packages-device
ios/scripts/install_site_packages.sh simulator ios/build/site-packages-simulator
```

Both scripts can be re-run. `build_wheels.sh` skips a step whose output exists;
`--force` rebuilds pydantic-core and PyYAML. `install_site_packages.sh` deletes
the destination and installs from the wheelhouse only (`--no-index`), then
checks that every compiled module is built for the platform asked for.

Needs Xcode with the iOS SDK, `uv`, and `rustup` (`brew install rustup`; it's
keg-only, and the script adds `/opt/homebrew/opt/rustup/bin` to its own `PATH`).
The stable Rust toolchain, the two iOS targets and maturin are fetched on first use.

## What `build_wheels.sh` does

1. Downloads the support package and checks its sha256.
2. Builds **pydantic-core** from the PyPI sdist (sha256 checked) with maturin,
   once for `aarch64-apple-ios` and once for `aarch64-apple-ios-sim`:
   - maturin asks a Python interpreter what it's building for, and an iOS
     interpreter can't run on the Mac. So the script makes a venv per platform
     (`build/crossenv-<sdk>`) and converts it with the support package's
     `platform-config/arm64-<sdk>/make_cross_venv.py`. That venv's Python
     reports the iOS platform, extension suffix and sysconfig data. Without
     it maturin stops with "platform.system() in python, darwin, and the rust
     target ... don't match".
   - `PYO3_CROSS_LIB_DIR` points at the same `platform-config` folder, which
     holds the platform's `_sysconfigdata`.
   - PyO3 links with `-lpython3.13`. The xcframework slice's `lib/` has that
     name as a link to `Python.framework/Python`, so the script adds it to the
     linker's search path and the module depends on
     `@rpath/Python.framework/Python`, as BeeWare's numpy does.

   `IPHONEOS_DEPLOYMENT_TARGET=17.0` sets both the binary's minimum OS and the
   wheel's tag. The two targets build one after the other with
   `CARGO_BUILD_JOBS=4`, because the release profile uses fat LTO.
3. Builds **PyYAML** from its sdist with `PYYAML_FORCE_LIBYAML=0`, checks the
   wheel has no compiled extension, and retags it `py3-none-any`.
4. Runs `pip download` with full dependency resolution for each platform,
   wheels only, against PyPI plus BeeWare's index
   (`https://pypi.anaconda.org/beeware/simple`, for numpy). It fails if any
   requirement has no wheel that installs on iOS.

## Versions

| Thing | Version |
|---|---|
| Python | 3.13 (support package 3.13-b18: CPython 3.13.18, OpenSSL 3.5.9) |
| Deployment target | iOS 17.0, arm64 device and arm64 simulator |
| pydantic-core | 2.46.5, built here (`ios_17_0_arm64_iphoneos`, `ios_17_0_arm64_iphonesimulator`) |
| numpy | 2.5.2.post1 from BeeWare (`ios_17_0` wheels); the Mac's lock has 2.5.3 |
| PyYAML | 6.0.3, pure Python, no libyaml |
| Others | fastapi 0.141.1, starlette 1.7.0, pydantic 2.13.5, uvicorn 0.54.0, websockets 17.1, sqlalchemy 2.1.1, anyio 4.15.1, h11 0.16.0, click 8.5.0, idna 3.20, typing-extensions 4.16.0, typing-inspection 0.4.4, annotated-types 0.8.0, annotated-doc 0.0.5 |
| Build tools | maturin 1.16.0, Rust stable (1.99.1 when first built), Xcode 27.1 |

## Left out on purpose

- **scipy**: no iOS wheel; the runtime stops using it (plan steps I0c and I1).
- **alembic, mako, markupsafe**: never imported at runtime.
- **uvicorn's `standard` extras** (uvloop, httptools, watchfiles, python-dotenv):
  the phone runs plain uvicorn on h11 and asyncio. websockets is listed directly.
- **greenlet**: optional for SQLAlchemy (only its asyncio extension needs it),
  and it has no iOS wheel.

## Notes for the Xcode side

- The compiled modules are plain `.so` files here. The App Store needs each one
  as a framework; the support package's `build/build_utils.sh`
  (`install_python`) does that conversion in a build phase.
- The x86_64 simulator isn't built. Add the `x86_64-apple-ios` Rust target and
  a third `build_pydantic_core` call if an Intel Mac ever needs it.

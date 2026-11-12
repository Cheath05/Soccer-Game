"""The embedded entry point. The Swift host sets the FOOTSIM_* variables, starts Python on a
thread of its own and calls ``main()``, which serves the game until the app dies.

- **One career session, no accounts, the sim in this process** (iOS has no processes).
- **The world** ships read-only in the app bundle. It is copied into the app's container the
  first time (and whenever the bundle's changes), because the game opens it read-write.
- **Leaving and returning:** iOS may take a suspended app's listening socket without telling
  it, so the host calls ``pause()`` on the way out (the server stops listening; careers, and
  any match being watched, stay in memory) and ``resume()`` on the way back (a new server on
  the same port).
- **The key:** every request must carry the launch's secret as a cookie, which only the app's
  web view has, so nothing else on the phone can read or change a career. Refusals are 403,
  never 401 (the pages read 401 as "signed out").
"""

import json
import os
import secrets
import shutil
import threading
import time
from pathlib import Path
from typing import Any

import uvicorn
from starlette.types import ASGIApp, Receive, Scope, Send

from footsim.api.app import create_app
from footsim.api.session import CareerSession, default_base_world
from footsim.core.paths import REPO_ROOT, saves_dir

COOKIE = "footsim_key"
OPEN_PATHS = ("/api/health",)  # the host polls it before the web view has loaded

_server: uvicorn.Server | None = None
_awake = threading.Event()
_awake.set()
_lock = threading.Lock()


class LoopbackOnly:
    """Refuse anything that isn't the app's own web view: the Host must be this server's and
    the launch's secret must come as a cookie. HTTP and WebSocket alike."""

    def __init__(self, app: ASGIApp, secret: str, port: int) -> None:
        self.app, self.secret = app, secret
        self.hosts = {f"127.0.0.1:{port}".encode(), f"localhost:{port}".encode()}

    def _allowed(self, scope: Scope) -> bool:
        headers = dict(scope.get("headers") or [])
        if headers.get(b"host") not in self.hosts:
            return False
        if scope["type"] == "http" and scope.get("path") in OPEN_PATHS:
            return True
        cookies = headers.get(b"cookie", b"").decode("latin-1")
        pairs = (c.strip().partition("=") for c in cookies.split(";"))
        key = self.secret.encode()
        return any(name == COOKIE and secrets.compare_digest(value.encode("latin-1"), key)
                   for name, _, value in pairs)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket") or self._allowed(scope):
            await self.app(scope, receive, send)
        elif scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
        else:
            await send({"type": "http.response.start", "status": 403,
                        "headers": [(b"content-type", b"text/plain")]})
            await send({"type": "http.response.body", "body": b"forbidden"})


def _world(bundled: Path, container: Path) -> Path:
    """The world to play from: the bundle's, copied into the container when it's new there or
    the bundle's has changed (by size and time; an app update replaces the bundle)."""
    target = container / "worlds" / bundled.name
    stamp = f"{bundled.stat().st_size}:{int(bundled.stat().st_mtime)}"
    marker = target.with_suffix(".stamp")
    if not target.exists() or not marker.exists() or marker.read_text() != stamp:
        target.parent.mkdir(parents=True, exist_ok=True)
        for sidecar in ("-wal", "-shm"):
            Path(str(target) + sidecar).unlink(missing_ok=True)
        shutil.copyfile(bundled, target)
        marker.write_text(stamp)
    return target


def _build_info() -> None:
    """There's no git on a phone: the bundle step wrote the version and commit to build.json
    (ios/scripts/assemble_bundle.sh), which core/build_info reads from the environment."""
    baked = REPO_ROOT / "build.json"
    if baked.exists():
        for key, value in json.loads(baked.read_text()).items():
            os.environ.setdefault(key, str(value))


def build(port: int, secret: str) -> ASGIApp:
    """The phone's app: one career session on the container's saves, behind the key."""
    _build_info()
    saves = saves_dir()
    saves.mkdir(parents=True, exist_ok=True)
    world = _world(default_base_world(), saves.parent)
    session = CareerSession(saves, world, keep_backups=2)
    app: ASGIApp = create_app(session=session)
    return LoopbackOnly(app, secret, port) if secret else app


def main(port: int | None = None, secret: str | None = None) -> None:
    """Serve until the process ends. Blocks: the host gives it a thread."""
    global _server
    port = port if port is not None else int(os.environ["FOOTSIM_PHONE_PORT"])
    secret = secret if secret is not None else os.environ.get("FOOTSIM_PHONE_SECRET", "")
    if not secret:
        raise RuntimeError("the host gave no key (FOOTSIM_PHONE_SECRET): refusing to serve")
    app = build(port, secret)
    while True:
        _awake.wait()
        config = uvicorn.Config(app, host="127.0.0.1", port=port, http="h11", loop="asyncio",
                                ws="websockets-sansio", lifespan="off", log_level="warning",
                                access_log=False)
        with _lock:
            if not _awake.is_set():  # paused since the wait: don't start listening
                continue
            _server = server = uvicorn.Server(config)
        try:
            server.run()
        except (SystemExit, OSError):  # the port wasn't free yet (uvicorn exits on that)
            time.sleep(0.5)


def pause() -> None:
    """The app is leaving the foreground: stop listening (called from the host's thread)."""
    with _lock:
        _awake.clear()
        if _server is not None:
            _server.should_exit = True


def resume() -> None:
    """The app is back: listen again."""
    _awake.set()


def state() -> dict[str, Any]:
    return {"awake": _awake.is_set(), "serving": _server is not None and _server.started}

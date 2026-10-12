"""Signing in (docs/plans/phone-and-accounts.md, U2).

With FOOTSIM_AUTH=1 every /api route but ``/api/health`` and ``/api/auth/*`` needs a signed-in
account: the browser holds a random token in the ``footsim_session`` cookie, and each request
is served from that account's own careers (``SessionRegistry``). Without it, as before
accounts existed, everyone plays as the owner from the saves folder itself.
"""

import time
from collections import defaultdict, deque
from threading import Lock
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from starlette.requests import HTTPConnection

from footsim.accounts.store import Account
from footsim.api.session import LOCAL, CareerSession, SessionRegistry

COOKIE = "footsim_session"


def is_open(path: str) -> bool:
    """The /api paths served without signing in: health, and signing in itself."""
    return path == "/api/health" or path.startswith("/api/auth/")

router = APIRouter(prefix="/api/auth")


class LoginIn(BaseModel):
    name: str = Field(max_length=64)
    password: str = Field(max_length=1024)


class MeOut(BaseModel):
    auth: bool  # whether this server asks for accounts at all
    name: str | None  # who is signed in (None when nobody is, or accounts are off)
    is_owner: bool


def registry(conn: HTTPConnection) -> SessionRegistry:
    found: SessionRegistry = conn.app.state.registry
    return found


def _account(conn: HTTPConnection) -> Account | None:
    """Who this request is from: the owner when accounts are off, else the cookie's account
    (None when there's no valid sign-in). Reads the accounts file: call off the event loop."""
    reg = registry(conn)
    if reg.accounts is None:
        return LOCAL
    token = conn.cookies.get(COOKIE)
    if not token:
        return None
    return reg.accounts.session_account(token, reg.server.session_days)


async def signed_in(conn: HTTPConnection) -> Account | None:
    return await run_in_threadpool(_account, conn)


def same_origin(conn: HTTPConnection) -> bool:
    """A browser always sends Origin on a WebSocket; it must be this site (the cookie is
    SameSite=Strict as well, so this is a second lock on the same door)."""
    origin = conn.headers.get("origin")
    if origin is None:
        return True  # not a browser
    hosts = {h.lower() for h in (conn.headers.get("host"), conn.headers.get("x-forwarded-host"))
             if h}
    return urlsplit(origin).netloc.lower() in hosts


def account(request: Request) -> Account:
    """The signed-in account, set by the middleware in app.py for every /api request."""
    found: Account | None = getattr(request.state, "account", None)
    if found is None:
        raise HTTPException(401, "sign in first")
    return found


def session_for(request: Request) -> CareerSession:
    return registry(request).for_account(account(request))


Session = Annotated[CareerSession, Depends(session_for)]


class Throttle:
    """Failed sign-ins per key (a name, an address) within a sliding window."""

    def __init__(self) -> None:
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def blocked(self, keys: list[str], limit: int, window: float, now: float) -> bool:
        with self._lock:
            for key in keys:
                failures = self._failures.get(key)
                while failures and failures[0] <= now - window:
                    failures.popleft()
                if failures is not None and not failures:
                    del self._failures[key]
            return any(len(self._failures.get(key, ())) >= limit for key in keys)

    def fail(self, keys: list[str], now: float) -> None:
        with self._lock:
            for key in keys:
                self._failures[key].append(now)

    def clear(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)


def _throttle(request: Request) -> Throttle:
    found: Throttle = request.app.state.login_throttle
    return found


def _address(request: Request) -> str:
    """The player's address. Behind Tailscale Serve every request comes from 127.0.0.1, so
    the proxy's X-Forwarded-For is used there: its last entry, the one the proxy added (the
    ones before it are whatever the browser sent)."""
    host = request.client.host if request.client else "?"
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded and host in ("127.0.0.1", "::1"):
        return forwarded.split(",")[-1].strip()
    return host


def _secure(request: Request) -> bool:
    return (request.url.scheme == "https"
            or request.headers.get("x-forwarded-proto", "").lower() == "https")


def _set_cookie(request: Request, response: Response, token: str, days: int) -> None:
    response.set_cookie(COOKIE, token, max_age=days * 86400, httponly=True,
                        secure=_secure(request), samesite="strict", path="/")


@router.get("/me")
async def me(request: Request, response: Response) -> MeOut:
    """Who is signed in. The page asks on opening, which also renews the cookie, so a sign-in
    in use lasts as long in the browser as on the server."""
    reg = registry(request)
    found = await signed_in(request)
    if reg.accounts is None:
        return MeOut(auth=False, name=None, is_owner=True)
    token = request.cookies.get(COOKIE)
    if found is not None and token:
        _set_cookie(request, response, token, reg.server.session_days)
    return MeOut(auth=True, name=found.name if found else None,
                 is_owner=bool(found and found.is_owner))


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response) -> MeOut:
    reg = registry(request)
    if reg.accounts is None:
        raise HTTPException(400, "this server has no accounts: everyone plays as the owner")
    server = reg.server
    keys = [f"name:{body.name.strip().lower()}", f"addr:{_address(request)}"]
    throttle = _throttle(request)
    if throttle.blocked(keys, server.login_attempts, server.login_window_seconds,
                         time.monotonic()):
        raise HTTPException(429, "too many failed sign-ins: wait a few minutes")
    found = reg.accounts.verify(body.name, body.password)
    if found is None:
        throttle.fail(keys, time.monotonic())
        time.sleep(server.failure_delay_seconds)
        raise HTTPException(401, "wrong name or password")
    throttle.clear(keys[0])
    _set_cookie(request, response, reg.accounts.start_session(found, server.session_days),
                server.session_days)
    return MeOut(auth=True, name=found.name, is_owner=found.is_owner)


@router.post("/logout")
def logout(request: Request, response: Response) -> MeOut:
    reg = registry(request)
    token = request.cookies.get(COOKIE)
    if reg.accounts is not None and token:
        reg.accounts.end_session(token)
    response.delete_cookie(COOKIE, path="/", httponly=True, secure=_secure(request),
                           samesite="strict")
    return MeOut(auth=reg.accounts is not None, name=None, is_owner=False)

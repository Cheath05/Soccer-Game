"""Watching a match live over a WebSocket.

The match is played by match.live.session.LiveSession, which keeps the engine just ahead of
what the viewer sees. This module only moves messages: about 20 times a second it applies
the viewer's commands, lets the session advance the match, and sends the new frames and
state. Matches live in memory until they finish, so a page reload reconnects to the same
match (paused). A match belongs to the career loaded when it started (see CareerSession).

Protocol v2 (JSON).
  Server -> client: init | frames | ack | end | error.
  Client -> server: pause | resume | speed {value} | mode {value: full|highlights} |
    formation {key} | instruction {key, value} | sub {out, in} | auto_subs {value} |
    assistant {value} (the AI manager adjusts the user's tactics) | start_period | finish.
    Any command may carry a cmd_id, echoed back in its ack.
"""

import asyncio
import contextlib
from dataclasses import dataclass
from datetime import date
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from footsim.api.session import CareerSession
from footsim.match.live.session import LiveSession
from footsim.persistence.schema import club, fixture
from footsim.world.career import agent_match
from footsim.world.context import get_world
from footsim.world.meta import read_meta
from footsim.world.results import record_result

router = APIRouter()

LOOP_SECONDS = 0.05  # real seconds between updates while playing
PAUSED_SECONDS = 0.25


@dataclass
class LiveMatch:
    session: LiveSession
    fixture_id: int
    day: date
    names: tuple[str, str]
    generation: int  # the career it belongs to (CareerSession.generation)


def _session(ws: WebSocket) -> CareerSession:
    session: CareerSession = ws.app.state.session
    return session


def _open(session: CareerSession, fixture_id: int) -> LiveMatch:
    live: LiveMatch | None = session.live_matches.get(fixture_id)
    if live is not None:
        return live
    world = get_world()
    generation = session.generation
    with session.read() as conn:
        meta = read_meta(conn)
        fx = conn.execute(select(fixture).where(fixture.c.id == fixture_id)).first()
        if fx is None or fx.status != "scheduled":
            raise ValueError("this match isn't waiting to be played")
        if meta.user_club_id not in (fx.home_club_id, fx.away_club_id):
            raise ValueError("not your match")
        if fx.date != meta.current_date.isoformat():
            raise ValueError("this match isn't today")
        engine = agent_match(conn, world, meta, fx, meta.current_date, record=True)
        names = {r.id: r.name for r in conn.execute(select(club.c.id, club.c.name).where(
            club.c.id.in_([fx.home_club_id, fx.away_club_id])))}
    user_team = 0 if fx.home_club_id == meta.user_club_id else 1
    playback = LiveSession(engine, world, world.defs.presentation, user_team)
    live = LiveMatch(playback, fixture_id, meta.current_date,
                     (names[fx.home_club_id], names[fx.away_club_id]), generation)
    with session.lock:
        if session.generation != generation:
            raise ValueError("the career changed while the match was being set up")
        session.live_matches[fixture_id] = live
    return live


def _belongs(session: CareerSession, live: LiveMatch) -> bool:
    return (session.generation == live.generation
            and session.live_matches.get(live.fixture_id) is live)


def _finish(session: CareerSession, live: LiveMatch) -> bool:
    """Play out the rest, record the result and autosave. False if the career has changed
    since the match started (another save was loaded), in which case nothing is written."""
    live.session.finish()
    report = live.session.engine.report()
    with session.lock:
        if not _belongs(session, live):
            return False
        with session.write() as conn:
            record_result(conn, live.fixture_id, report, live.day, "live")
        session.live_matches.pop(live.fixture_id, None)
        session.autosave()
    return True


@router.websocket("/api/fixtures/{fixture_id}/live")
async def live_match(ws: WebSocket, fixture_id: int) -> None:
    await ws.accept()
    session = _session(ws)
    try:
        live = await asyncio.to_thread(_open, session, fixture_id)
    except Exception as exc:  # noqa: BLE001 - report any setup failure to the client
        await ws.send_json({"type": "error", "message": str(exc)})
        await ws.close()
        return
    playback = live.session
    playback.pause(asyncio.get_running_loop().time())
    playback.debug = playback.engine.debug = False  # a reloaded viewer starts without it
    await ws.send_json(playback.init_message(live.names, asyncio.get_running_loop().time()))

    inbox: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def reader() -> None:
        try:
            while True:
                inbox.put_nowait(await ws.receive_json())
        except (WebSocketDisconnect, RuntimeError):
            inbox.put_nowait({"type": "_disconnected"})

    task = asyncio.create_task(reader())
    loop = asyncio.get_running_loop()
    finishing = False
    pending: list[dict[str, Any]] = []  # a command that arrived while we were waiting
    try:
        while True:
            started = loop.time()
            while pending or not inbox.empty():
                cmd = pending.pop(0) if pending else inbox.get_nowait()
                kind = cmd.get("type")
                if kind == "_disconnected":
                    return
                if kind in ("finish", "instant"):
                    finishing = True
                    continue
                error = playback.apply(cmd, loop.time())
                if error:
                    await ws.send_json({"type": "error", "message": error,
                                        "cmd_id": cmd.get("cmd_id")})
                elif cmd.get("cmd_id") is not None:
                    await ws.send_json({"type": "ack", "cmd_id": cmd["cmd_id"],
                                        "tick": playback.engine.tick_count})
            if not _belongs(session, live):
                await ws.send_json({"type": "error", "message": (
                    "Another career was loaded, so this match was abandoned and not recorded.")})
                return
            if finishing or playback.engine.finished:
                if not await asyncio.to_thread(_finish, session, live):
                    await ws.send_json({"type": "error", "message": (
                        "Another career was loaded, so this match was not recorded.")})
                    return
                engine = playback.engine
                await ws.send_json({"type": "end", "score": list(engine.score),
                                    "stats": engine.live_stats(), "clock": playback.clock(),
                                    "status": playback.status(), "fixture_id": fixture_id})
                return
            update = playback.pump(loop.time())
            await ws.send_json(playback.update_message(update, loop.time()))
            pause = PAUSED_SECONDS if playback.paused else LOOP_SECONDS
            # Wait for the next update, but act on a command the moment it arrives.
            with contextlib.suppress(TimeoutError):
                pending.append(await asyncio.wait_for(
                    inbox.get(), max(0.0, pause - (loop.time() - started))))
    finally:
        playback.pause(loop.time())
        task.cancel()
        with contextlib.suppress(Exception):
            await ws.close()

"""Live matches over a WebSocket.

The server runs the agent engine in step with the viewer: every 100 ms it advances the
match by ``speed`` ticks (1 tick = 0.1 s of match time) and sends the new frames, so a
tactical change the user makes applies from the moment they see. Matches live in memory
until they finish, so a page reload reconnects to the same match (paused).

Protocol (JSON). Server -> client: init | frames | end | error. Client -> server:
pause | resume | speed {value} | mode {value: full|highlights} | formation {key} |
instruction {key, value} | sub {out, in} | auto_subs {value} | finish.
"""

import asyncio
import contextlib
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from footsim.api.session import CareerSession
from footsim.match.engine.engine import MatchEngine
from footsim.persistence.schema import club, fixture
from footsim.world.career import agent_match
from footsim.world.context import get_world
from footsim.world.meta import read_meta
from footsim.world.results import record_result

router = APIRouter()

TICK_INTERVAL = 0.1  # seconds of wall time per loop
MAX_SPEED = 64
HIGHLIGHT_TYPES = {"goal", "shot", "penalty", "red"}
HIGHLIGHT_BEFORE = 150  # frames (15 s) shown before a highlight
HIGHLIGHT_AFTER = 5.0  # match seconds shown after it
SKIP_TICKS = 300  # ticks simulated per loop while skipping between highlights


@dataclass
class LiveMatch:
    engine: MatchEngine
    fixture_id: int
    user_team: int
    day: date
    names: tuple[str, str]
    speed: int = 1
    paused: bool = True
    mode: str = "full"
    replay_until: float = -1.0
    feed_sent: int = 0
    lineup_sent: int = -1
    last_stats: float = -99.0
    commands: list[dict[str, Any]] = field(default_factory=list)


_matches: dict[int, LiveMatch] = {}


def _session(ws: WebSocket) -> CareerSession:
    session: CareerSession = ws.app.state.session
    return session


def _open(session: CareerSession, fixture_id: int) -> LiveMatch:
    live = _matches.get(fixture_id)
    if live is not None:
        return live
    world = get_world()
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
    live = LiveMatch(engine, fixture_id, user_team, meta.current_date,
                     (names[fx.home_club_id], names[fx.away_club_id]))
    _matches[fixture_id] = live
    return live


def _state(live: LiveMatch) -> dict[str, Any]:
    e = live.engine
    return {"score": list(e.score), "minute": e.minute, "period": e.period,
            "paused": live.paused, "speed": live.speed, "mode": live.mode,
            "finished": e.finished, "subs_left": [5 - e.subs_used[0], 5 - e.subs_used[1]]}


def _init_message(live: LiveMatch) -> dict[str, Any]:
    e = live.engine
    defs = e.defs
    live.feed_sent = len(e.feed)
    live.lineup_sent = e.lineup_version
    return {
        "type": "init", **_state(live),
        "teams": [{"name": live.names[0], "club_id": e.sheets[0].club_id},
                  {"name": live.names[1], "club_id": e.sheets[1].club_id}],
        "user_team": live.user_team,
        "lineup": e.lineup(),
        "bench": [e.bench_info(0), e.bench_info(1)],
        "formation": [e.formation[0].key, e.formation[1].key],
        "formations": [{"key": f.key, "name": f.name} for f in defs.formations.values()],
        "instructions": [dict(e.instructions[0]), dict(e.instructions[1])],
        "instruction_options": [{"key": d.key, "label": d.label, "options": d.options}
                                for d in defs.instructions.values()],
        "auto_subs": list(e.auto_subs),
        "stats": e.live_stats(),
        "feed": e.feed[-30:],
        "frames": list(e.frames)[-5:],
    }


def _apply(live: LiveMatch, cmd: dict[str, Any]) -> str | None:
    """Apply a client command; returns an error message or None."""
    e = live.engine
    kind = cmd.get("type")
    team = live.user_team
    try:
        if kind == "pause":
            live.paused = True
        elif kind == "resume":
            live.paused = False
        elif kind == "speed":
            live.speed = max(1, min(MAX_SPEED, int(cmd.get("value", 1))))
        elif kind == "mode":
            live.mode = "highlights" if cmd.get("value") == "highlights" else "full"
            live.replay_until = -1.0
        elif kind == "formation":
            e.set_formation(team, str(cmd["key"]))
        elif kind == "instruction":
            e.set_instruction(team, str(cmd["key"]), str(cmd["value"]))
        elif kind == "sub":
            e.substitute(team, int(cmd["out"]), int(cmd["in"]))
        elif kind == "auto_subs":
            e.auto_subs[team] = bool(cmd.get("value"))
        elif kind == "finish":
            live.mode = "finish"
        else:
            return f"unknown command {kind!r}"
    except (ValueError, KeyError) as exc:
        return str(exc)
    return None


def _advance(live: LiveMatch) -> tuple[list[list[float]], bool]:
    """Step the engine for one loop. Returns frames to show and whether a highlight began."""
    e = live.engine
    if live.mode == "full":
        for _ in range(live.speed):
            e.step()
        frames = list(e.frames)
        e.frames.clear()
        return frames, False
    if live.mode == "highlights":
        if e.t < live.replay_until:  # showing a highlight's aftermath at the chosen speed
            for _ in range(max(1, live.speed)):
                e.step()
            frames = list(e.frames)
            e.frames.clear()
            return frames, False
        start = len(e.feed)
        for _ in range(SKIP_TICKS):
            e.step()
            if e.finished or any(f["type"] in HIGHLIGHT_TYPES for f in e.feed[start:]):
                break
        if any(f["type"] in HIGHLIGHT_TYPES for f in e.feed[start:]):
            live.replay_until = e.t + HIGHLIGHT_AFTER
            frames = list(e.frames)[-HIGHLIGHT_BEFORE:]
            e.frames.clear()
            return frames, True
        return [], False
    return [], False


def _finish(session: CareerSession, live: LiveMatch) -> None:
    if not live.engine.finished:
        live.engine.record = False
        live.engine.run()
    report = live.engine.report()
    with session.write() as conn:
        record_result(conn, live.fixture_id, report, live.day, "live")
    _matches.pop(live.fixture_id, None)


def _update(live: LiveMatch, frames: list[list[float]], highlight: bool) -> dict[str, Any]:
    e = live.engine
    message: dict[str, Any] = {"type": "frames", **_state(live), "frames": frames,
                               "highlight": highlight}
    if len(e.feed) > live.feed_sent:
        message["feed"] = e.feed[live.feed_sent:]
        live.feed_sent = len(e.feed)
    if e.lineup_version != live.lineup_sent:
        live.lineup_sent = e.lineup_version
        message["lineup"] = e.lineup()
        message["bench"] = [e.bench_info(0), e.bench_info(1)]
        message["formation"] = [e.formation[0].key, e.formation[1].key]
    if e.t - live.last_stats >= 1.0 or highlight:
        live.last_stats = e.t
        message["stats"] = e.live_stats()
        message["lineup_stamina"] = [round(float(s) * 100) for s in e.stamina]
    message["instructions"] = [dict(e.instructions[0]), dict(e.instructions[1])]
    message["auto_subs"] = list(e.auto_subs)
    return message


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
    live.paused = True
    await ws.send_json(_init_message(live))

    inbox: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def reader() -> None:
        try:
            while True:
                inbox.put_nowait(await ws.receive_json())
        except (WebSocketDisconnect, RuntimeError):
            inbox.put_nowait({"type": "_disconnected"})

    task = asyncio.create_task(reader())
    loop = asyncio.get_running_loop()
    try:
        while True:
            started = loop.time()
            while not inbox.empty():
                cmd = inbox.get_nowait()
                if cmd.get("type") == "_disconnected":
                    return
                error = _apply(live, cmd)
                if error:
                    await ws.send_json({"type": "error", "message": error})
            if live.mode == "finish" or live.engine.finished:
                await asyncio.to_thread(_finish, session, live)
                await ws.send_json({"type": "end", "score": list(live.engine.score),
                                    "fixture_id": fixture_id})
                return
            if live.paused:
                await ws.send_json({"type": "frames", **_state(live), "frames": []})
                await asyncio.sleep(0.25)
                continue
            frames, highlight = _advance(live)
            await ws.send_json(_update(live, frames, highlight))
            elapsed = loop.time() - started
            await asyncio.sleep(max(0.0, TICK_INTERVAL - elapsed))
    finally:
        live.paused = True
        task.cancel()
        with contextlib.suppress(Exception):
            await ws.close()

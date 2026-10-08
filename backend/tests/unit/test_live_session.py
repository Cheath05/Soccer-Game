"""Watching a match: playback speed and pauses change how fast you see it, never the match."""

import json
from collections import deque

import pytest

from footsim.core.rng import derive_rng
from footsim.match.engine.engine import MatchEngine
from footsim.match.live.session import LiveSession, replay
from footsim.match.synthetic import synthetic_sheet
from footsim.world.context import World, get_world

TICK = 0.05  # the WebSocket loop's cadence, in real seconds


@pytest.fixture(scope="module")
def world() -> World:
    return get_world()


def _engine(world: World) -> MatchEngine:
    home = synthetic_sheet(world.defs, world.picker, 1, 73)
    away = synthetic_sheet(world.defs, world.picker, 2, 71, formation="4-4-2")
    return MatchEngine(world.defs, home, away, derive_rng(21, "live"), record=False)


def _session(world: World) -> LiveSession:
    return LiveSession(_engine(world), world, world.defs.presentation, user_team=0)


def _play(session: LiveSession, now: float, seconds: float) -> float:
    """Pump the session like the WebSocket loop does for ``seconds`` of real time."""
    end = now + seconds
    while now < end:
        session.pump(now)
        now += TICK
    return now


def test_one_real_second_is_nine_match_seconds_at_1x(world: World) -> None:
    session = _session(world)
    assert session.apply({"type": "resume"}, 0.0) is None
    _play(session, 0.0, 20.0)
    lookahead = session.p.lookahead_seconds * session.rate
    assert 180 - 1 <= session.engine.clock.elapsed <= 180 + lookahead + 1


class _Recording(deque[list[float]]):
    """The engine's frame buffer, remembering every frame ever put in it."""

    def __init__(self, maxlen: int | None) -> None:
        super().__init__(maxlen=maxlen)
        self.everything: list[list[float]] = []

    def append(self, frame: list[float]) -> None:
        self.everything.append(frame)
        super().append(frame)


def test_frames_are_limited_for_the_viewer_but_every_touch_is_kept(world: World) -> None:
    """At 8x most frames are skipped, but every frame where the ball changes hands is sent,
    so a pass is seen from the foot that plays it to the one that takes it."""
    session = _session(world)
    frames = session.engine.frames = _Recording(session.engine.frames.maxlen)
    session.apply({"type": "speed", "value": 8}, 0.0)
    session.apply({"type": "resume"}, 0.0)
    sent: list[list[float]] = []
    now = 0.0
    while now < 5.0:
        sent += session.pump(now).frames
        now += TICK
    every = frames.everything
    touches = [f for prev, f in zip(every, every[1:], strict=False) if f[4] != prev[4]]
    assert touches
    sent_ids = {id(f) for f in sent}
    assert all(id(f) in sent_ids for f in touches)
    assert len(sent) <= 5.0 * (session.p.max_frames_per_second + 1 / TICK) + len(touches)


def test_the_picture_carries_on_through_speed_changes_and_pauses(world: World) -> None:
    """Play-test, 30 Sep: slowing from 8x to 1x made the picture jump 13-18 match seconds ahead.
    The timeline restarted from where the engine had got to, which runs ahead of the screen,
    instead of from the moment on screen."""
    session = _session(world)
    session.apply({"type": "resume"}, 0.0)
    now = _play(session, 0.0, 3.0)
    for cmd in ({"type": "speed", "value": 8}, {"type": "speed", "value": 1},
                {"type": "pause"}, {"type": "resume"}, {"type": "speed", "value": 4},
                {"type": "speed", "value": 0.5}, {"type": "speed", "value": 2}):
        before = session.shown(now)
        assert session.apply(cmd, now) is None
        assert session.shown(now) == pytest.approx(before)  # no jump
        start, began = session.shown(now), now
        now = _play(session, now, 2.0)
        moved = 0.0 if session.paused else (now - began) * session.play_rate
        assert session.shown(now) - start == pytest.approx(moved, rel=0.02, abs=0.01)


def test_pause_stops_the_match_and_resume_does_not_jump(world: World) -> None:
    session = _session(world)
    session.apply({"type": "resume"}, 0.0)
    now = _play(session, 0.0, 2.0)
    session.apply({"type": "pause"}, now)
    frozen = session.engine.t
    assert session.pump(now + 60).frames == [] and session.engine.t == frozen
    session.apply({"type": "resume"}, now + 60)  # a minute later in real time
    _play(session, now + 60, 1.0)
    assert session.engine.t - frozen < 9 * 1.0 + 3  # one second's worth, not 61


def test_unknown_speed_is_refused(world: World) -> None:
    session = _session(world)
    assert session.apply({"type": "speed", "value": 64}, 0.0) is not None
    assert session.speed == 1


def test_speed_changes_and_half_time_changes_replay_exactly(world: World) -> None:
    watched = _session(world)
    watched.apply({"type": "resume"}, 0.0)
    now = _play(watched, 0.0, 10.0)
    watched.apply({"type": "speed", "value": 8}, now)
    watched.apply({"type": "instruction", "key": "pressing", "value": "high"}, now)
    while not watched.engine.at_break:
        watched.pump(now)
        now += TICK
    assert watched.paused  # half-time stops playback
    assert watched.apply({"type": "resume"}, now) is not None
    assert watched.apply({"type": "formation", "key": "4-2-3-1"}, now) is None
    assert watched.apply({"type": "start_period"}, now) is None
    assert watched.engine.period == 2 and not watched.paused
    now = _play(watched, now, 2.0)
    watched.apply({"type": "speed", "value": 0.5}, now)
    now = _play(watched, now, 2.0)
    watched.finish()

    replayed = _engine(world)
    replay(replayed, 0, watched.log)
    assert replayed.finished and watched.engine.finished
    assert replayed.tick_count == watched.engine.tick_count
    assert replayed.score == watched.engine.score
    assert replayed.pos.tobytes() == watched.engine.pos.tobytes()
    assert [(s.shots, s.passes, s.fouls) for s in replayed.stats] == \
        [(s.shots, s.passes, s.fouls) for s in watched.engine.stats]


def test_the_assistant_can_take_over_the_users_tactics(world: World) -> None:
    home = synthetic_sheet(world.defs, world.picker, 1, 73)
    away = synthetic_sheet(world.defs, world.picker, 2, 71, formation="4-4-2")
    engine = MatchEngine(world.defs, home, away, derive_rng(21, "live"), record=False,
                         ai_manager=(False, True))  # as in a career: the user manages his side
    session = LiveSession(engine, world, world.defs.presentation, user_team=0)
    assert session.init_message(("Home", "Away"), 0.0)["ai_manager"] == [False, True]
    assert session.apply({"type": "assistant", "value": True}, 0.0) is None
    session.apply({"type": "resume"}, 0.0)
    pump = session.pump(0.5)
    assert session.update_message(pump, 0.5)["ai_manager"] == [True, True]
    assert session.apply({"type": "assistant", "value": False}, 1.0) is None
    assert engine.ai_manager == [False, True]
    assert [cmd["type"] for _, cmd in session.log] == ["assistant", "assistant"]


def test_the_debug_overlay_shows_intentions_without_changing_the_match(world: World) -> None:
    watched, plain = _session(world), _session(world)
    assert watched.apply({"type": "debug", "value": True}, 0.0) is None
    snapshots = []
    for session in (watched, plain):
        session.apply({"type": "resume"}, 0.0)
        now = 0.0
        while now < 5.0:  # an update per pump, as the WebSocket loop sends them
            message = session.update_message(session.pump(now), now)
            json.dumps(message, allow_nan=False)  # what the socket sends must be valid JSON
            if "debug" in message:
                snapshots.append(message["debug"])
            now += TICK
    assert snapshots and len(snapshots[-1]["targets"]) == 44
    assert snapshots[-1]["decision"] is not None
    assert all({"phase", "back", "front", "pressers"} <= set(team)
               for team in snapshots[-1]["teams"])
    assert [s["t"] for s in snapshots] == sorted(s["t"] for s in snapshots)
    assert watched.engine.tick_count == plain.engine.tick_count
    assert watched.engine.pos.tobytes() == plain.engine.pos.tobytes()  # nothing read back
    assert (watched.engine.rng.bit_generator.state == plain.engine.rng.bit_generator.state)


def _first_goal(session: LiveSession, now: float) -> tuple[float, object]:
    """Pump at 8x until the engine has scored; returns the real time and the goal's hold."""
    session.apply({"type": "speed", "value": 8}, now)
    session.apply({"type": "resume"}, now)
    while not session.holds:
        session.pump(now)
        now += TICK
        if session.engine.at_break:
            session.apply({"type": "start_period"}, now)
        assert not session.engine.finished, "no goal in this match"
    return now, session.holds[0]


def test_a_goal_holds_the_picture_while_the_scorer_is_shown(world: World) -> None:
    """Play-test, 30 Sep: the user wants a pause and a banner at each goal, so it can't be
    missed at any speed."""
    session = _session(world)
    now, hold = _first_goal(session, 0.0)
    goal_t = hold.t  # type: ignore[attr-defined]
    pause = session.p.goal_pause
    # The engine runs ahead, so the hold is known before the picture gets there.
    assert session.shown(now) < goal_t
    while session.shown(now) < goal_t:
        session.pump(now)
        now += TICK
    reached = now
    info = session.state(now)["holding"]
    assert info is not None and info["scorer"] and info["team"] in (0, 1)
    assert info["score"][info["team"]] >= 1
    while now < reached + pause - 2 * TICK:  # the picture stays on the goal...
        session.pump(now)
        assert session.shown(now) == pytest.approx(goal_t)
        now += TICK
    _play(session, now, 1.0)  # ...and then carries on
    assert session.shown(now + 1.0) > goal_t + 30
    assert session.state(now + 1.0)["holding"] is None


def test_goal_pauses_never_change_the_result(world: World) -> None:
    watched = _session(world)
    now, _ = _first_goal(watched, 0.0)
    while not watched.engine.finished:
        watched.pump(now)
        now += TICK
        if watched.engine.at_break:
            watched.apply({"type": "start_period"}, now)
    headless = _engine(world)
    headless.run()
    assert watched.engine.score == headless.score
    assert watched.engine.tick_count == headless.tick_count


def test_two_players_can_swap_positions_and_the_match_replays_exactly(world: World) -> None:
    """The user's position swap is an input like a substitution: no one jumps, a goalkeeper
    stays in goal, and the same inputs give the same match."""
    watched = _session(world)
    watched.apply({"type": "resume"}, 0.0)
    now = _play(watched, 0.0, 5.0)
    engine = watched.engine
    outfield = [engine.players[int(i)] for i in engine.team_indices(0)
                if engine.position[int(i)] != "GK"]
    first, second = outfield[0], outfield[-1]
    where = {sp.player_id: (engine.slot[i], engine.position[i])
             for i, sp in enumerate(engine.players) if sp.player_id in (first.player_id,
                                                                         second.player_id)}
    keeper = next(sp for i, sp in enumerate(engine.players)
                  if engine.team_of[i] == 0 and engine.position[i] == "GK")
    before = engine.pos.copy()
    assert watched.apply({"type": "swap", "a": keeper.player_id, "b": first.player_id},
                         now) is not None
    assert watched.apply({"type": "swap", "a": first.player_id, "b": first.player_id},
                         now) is not None
    assert watched.apply({"type": "swap", "a": first.player_id, "b": second.player_id},
                         now) is None
    assert engine.pos.tobytes() == before.tobytes()  # nobody was moved
    now_where = {sp.player_id: (engine.slot[i], engine.position[i])
                 for i, sp in enumerate(engine.players) if sp.player_id in where}
    assert now_where[first.player_id] == where[second.player_id]
    assert now_where[second.player_id] == where[first.player_id]
    status = {p["player_id"]: p for p in watched.status()["players"]}
    assert status[first.player_id]["slot"] == where[second.player_id][0]
    now = _play(watched, now, 5.0)
    watched.finish()

    replayed = _engine(world)
    replay(replayed, 0, watched.log)
    assert replayed.tick_count == watched.engine.tick_count
    assert replayed.score == watched.engine.score
    assert replayed.pos.tobytes() == watched.engine.pos.tobytes()
    assert [cmd["type"] for _, cmd in watched.log] == ["swap"]  # the refused ones aren't logged


def test_the_init_message_carries_each_formations_slots(world: World) -> None:
    init = _session(world).init_message(("Home", "Away"), 0.0)
    shape = next(f for f in init["formations"] if f["key"] == "4-3-3")
    assert len(shape["slots"]) == 11 and {"id", "position", "x", "y"} <= set(shape["slots"][0])

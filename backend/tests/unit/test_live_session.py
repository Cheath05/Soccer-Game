"""Watching a match: playback speed and pauses change how fast you see it, never the match."""

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


def test_frames_are_limited_for_the_viewer(world: World) -> None:
    session = _session(world)
    session.apply({"type": "speed", "value": 8}, 0.0)
    session.apply({"type": "resume"}, 0.0)
    sent = 0
    now = 0.0
    while now < 5.0:
        sent += len(session.pump(now).frames)
        now += TICK
    assert sent <= 5.0 * (session.p.max_frames_per_second + 1 / TICK)


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

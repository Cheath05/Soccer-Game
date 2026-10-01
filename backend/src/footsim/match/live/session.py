"""A watched match: the engine plus playback, with no web framework in sight.

The engine only knows simulation time. LiveSession maps it onto the viewer's real time: at
1x a 45-minute half plays in ``real_seconds_per_half`` (5 minutes), at 2x in half that, and
so on (data/config/match/presentation.yaml). Speed only changes how fast the viewer sees
the match, never the match itself: the engine runs the same ticks in the same order at any
speed, and highlights mode just skips frames.

One timeline says what the viewer should be showing (``shown``). Pausing, resuming and
changing speed or mode carry on from the moment on screen, so the picture never jumps; the
engine runs a little ahead of it (``lookahead_seconds``), and the viewer steers towards it.

Commands that do change the match (formation, instructions, substitutions, starting the
next period) are applied between two ticks and logged with that tick, so a watched match
can be replayed exactly with ``replay``.
"""

import math
from dataclasses import dataclass
from typing import Any

from footsim.defs.match import PresentationDef
from footsim.match.engine.engine import MatchEngine
from footsim.match.ratings import match_rating
from footsim.match.teams import SquadPlayer
from footsim.ratings.overall import familiarity_factor
from footsim.world.context import World

HIGHLIGHT_TYPES = frozenset({"goal", "shot", "penalty", "red"})
MATCH_COMMANDS = frozenset({"formation", "instruction", "sub", "auto_subs", "assistant",
                            "start_period"})
MAX_TICKS_PER_PUMP = 3000  # never hold the event loop for long, even after falling behind
SKIP_TICKS = 600  # highlights mode: most match time skipped in one go (60 s)
STATUS_EVERY = 1.0  # real seconds between player status updates
STATS_EVERY = 0.5  # real seconds between team stats updates

Command = dict[str, Any]


def apply_command(engine: MatchEngine, team: int, cmd: Command) -> None:
    """Change the match for ``team`` (raises ValueError on an invalid command)."""
    kind = cmd.get("type")
    if kind == "formation":
        engine.set_formation(team, str(cmd["key"]))
    elif kind == "instruction":
        engine.set_instruction(team, str(cmd["key"]), str(cmd["value"]))
    elif kind == "sub":
        engine.substitute(team, int(cmd["out"]), int(cmd["in"]))
    elif kind == "auto_subs":
        engine.auto_subs[team] = bool(cmd.get("value"))
    elif kind == "assistant":
        engine.set_ai_manager(team, bool(cmd.get("value")))
    elif kind == "start_period":
        engine.start_next_period()
    else:
        raise ValueError(f"unknown match command {kind!r}")


def replay(engine: MatchEngine, team: int, log: list[tuple[int, Command]]) -> None:
    """Play a match headless, applying a watched match's logged commands at the same ticks.
    Given the same inputs and seed, the result is the one the viewer saw."""
    engine.hold_at_breaks = True
    for tick, cmd in log:
        while engine.tick_count < tick and not engine.finished:
            if engine.at_break:
                raise RuntimeError(f"replay reached a break before tick {tick}")
            engine.step()
        apply_command(engine, team, cmd)
    engine.hold_at_breaks = False
    engine.run()


@dataclass
class Pump:
    frames: list[list[float]]
    highlight: bool = False


class LiveSession:
    def __init__(self, engine: MatchEngine, world: World, presentation: PresentationDef,
                 user_team: int) -> None:
        engine.hold_at_breaks = True
        engine.record = True
        self.engine = engine
        self.world = world
        self.p = presentation
        self.user_team = user_team
        self.speed = float(presentation.default_speed)
        self.paused = True
        self.mode = "full"  # full | highlights
        self.debug = False  # send the engine's debug snapshot with each update
        self.anchor_sim = engine.t  # the match time on screen at real time anchor_wall
        self.anchor_wall = 0.0
        self.replay_until = -1.0  # highlights: play at normal speed until this match time
        self.last_owner = -2.0  # the ball's owner in the last frame looked at (_drain)
        self.log: list[tuple[int, Command]] = []
        self.feed_sent = 0
        self.lineup_sent = -1
        self.last_status = -99.0
        self.last_stats = -99.0
        self._ovr_cache: dict[tuple[int, str, str], int] = {}

    # --- time ----------------------------------------------------------------------------

    @property
    def compression(self) -> float:
        """Match seconds per real second at 1x (9 when a half takes 5 minutes)."""
        return 45 * 60 / self.p.real_seconds_per_half

    @property
    def rate(self) -> float:
        return self.compression * self.speed

    @property
    def play_rate(self) -> float:
        """Match seconds per real second on screen: a highlight is replayed no faster than
        ``highlight_rate``."""
        if self.mode == "highlights":
            return min(self.rate, self.p.highlight_rate)
        return self.rate

    def shown(self, now: float) -> float:
        """The match time the viewer should be showing at real time ``now``. It stands still
        while paused, and runs on to the whistle at a break."""
        engine = self.engine
        moving = not self.paused or engine.at_break or engine.finished
        t = self.anchor_sim
        if moving:
            t += max(0.0, now - self.anchor_wall) * self.play_rate
        return min(t, engine.t)

    def _reanchor(self, now: float) -> None:
        """Carry on from the moment on screen (not from where the engine has got to)."""
        self.anchor_sim = self.shown(now)
        self.anchor_wall = now

    def pause(self, now: float) -> None:
        """Stop the picture on the moment it's showing."""
        if not self.paused:
            self._reanchor(now)
        self.paused = True

    # --- commands --------------------------------------------------------------------------

    def apply(self, cmd: Command, now: float) -> str | None:
        """Apply a viewer command. Returns an error message, or None."""
        kind = cmd.get("type")
        engine = self.engine
        try:
            if kind == "pause":
                self.pause(now)
            elif kind == "resume":
                if engine.at_break:
                    return "start the next period first"
                self._reanchor(now)
                self.paused = False
            elif kind == "speed":
                value = float(cmd.get("value", self.p.default_speed))
                if value not in self.p.speeds:
                    return f"speed must be one of {self.p.speeds}"
                self._reanchor(now)
                self.speed = value
            elif kind == "debug":  # the viewer's overlay: doesn't change the match
                self.debug = engine.debug = bool(cmd.get("value"))
                engine.shape_debug = [{}, {}]
                engine.decision_debug = None
            elif kind == "mode":
                self._reanchor(now)
                self.mode = "highlights" if cmd.get("value") == "highlights" else "full"
                self.replay_until = -1.0
            elif kind in MATCH_COMMANDS:
                if engine.finished:
                    return "the match is over"
                apply_command(engine, self.user_team, cmd)
                self.log.append((engine.tick_count,
                                 {k: v for k, v in cmd.items() if k != "cmd_id"}))
                if kind == "start_period":
                    self.anchor_sim, self.anchor_wall = engine.t, now
                    self.paused = False
            else:
                return f"unknown command {kind!r}"
        except (ValueError, KeyError, TypeError) as exc:
            return str(exc)
        return None

    def finish(self) -> None:
        """Play the rest of the match straight away (Instant)."""
        self.engine.hold_at_breaks = False
        self.engine.record = False
        self.debug = self.engine.debug = False
        self.engine.run()

    # --- playback --------------------------------------------------------------------------

    def pump(self, now: float) -> Pump:
        """Advance the match to where the viewer's clock says it should be (plus a little
        lookahead) and return the frames to show."""
        engine = self.engine
        if self.paused or engine.finished or engine.at_break:
            return Pump([])
        if self.mode == "highlights" and self.shown(now) >= self.replay_until:
            return self._skip_to_highlight(now)
        due = self.anchor_sim + (now - self.anchor_wall) * self.play_rate
        target = due + self.p.lookahead_seconds * self.play_rate
        ticks = 0
        while (engine.t < target and ticks < MAX_TICKS_PER_PUMP and not engine.finished
               and not engine.at_break):
            engine.step()
            ticks += 1
        if engine.at_break:
            self.paused = True
        return Pump(self._drain())

    def _drain(self, limit: int | None = None) -> list[list[float]]:
        frames = list(self.engine.frames)
        self.engine.frames.clear()
        if limit is not None:
            frames = frames[-limit:]
        if not frames:
            return []
        every = max(1, math.ceil(self.play_rate * 10 / self.p.max_frames_per_second))
        picked = []
        for f in frames:
            # Every frame where the ball changes hands is kept, so a pass is seen from the
            # foot that plays it to the one that takes it even when most frames are skipped.
            if round(f[0] * 10) % every == 0 or f[4] != self.last_owner:
                picked.append(f)
            self.last_owner = f[4]
        if not picked or picked[-1] is not frames[-1]:
            picked.append(frames[-1])
        return picked

    def _skip_to_highlight(self, now: float) -> Pump:
        engine = self.engine
        start = len(engine.feed)
        for _ in range(SKIP_TICKS):
            engine.step()
            if engine.finished or engine.at_break or any(
                    f["type"] in HIGHLIGHT_TYPES for f in engine.feed[start:]):
                break
        if engine.at_break:
            self.paused = True
        if not any(f["type"] in HIGHLIGHT_TYPES for f in engine.feed[start:]):
            self.engine.frames.clear()
            return Pump([])
        before = int(self.p.highlight_before * 10)
        frames = self._drain(limit=before)
        self.replay_until = engine.t + self.p.highlight_after
        # Show the build-up first: the engine waits until the viewer has caught up.
        self.anchor_wall = now
        self.anchor_sim = frames[0][0] if frames else engine.t
        return Pump(frames, highlight=True)

    # --- what the viewer sees --------------------------------------------------------------

    def clock(self) -> dict[str, Any]:
        c = self.engine.clock
        return {"period": c.period, "display": c.display(), "label": c.label(),
                "state": c.state.value, "added": c.announced, "elapsed": round(c.elapsed, 1)}

    def state(self, now: float) -> dict[str, Any]:
        e = self.engine
        return {"score": list(e.score), "minute": e.minute, "period": e.period,
                "t": round(e.t, 1), "shown": round(self.shown(now), 2),
                "clock": self.clock(), "paused": self.paused,
                "speed": self.speed,
                "rate": self.rate, "play_rate": self.play_rate, "mode": self.mode,
                "finished": e.finished,
                "at_break": e.at_break,
                "restart": ({"kind": e.restart.kind, "variant": e.restart.variant,
                             "team": e.restart.team} if e.restart is not None else None),
                "pending_subs": [[{"out": off, "in": on} for off, on in e.pending_for(t)]
                                 for t in (0, 1)],
                "subs_left": [5 - e.subs_used[0], 5 - e.subs_used[1]]}

    def _ovr(self, player: SquadPlayer, position: str, role: str) -> int:
        """Ability in a slot: the role overall, adjusted for familiarity with the position."""
        key = (player.player_id, position, role)
        if key not in self._ovr_cache:
            model = self.world.model
            overall = float(model.role_overalls(player.attrs)[model.role_index(role)])
            self._ovr_cache[key] = round(overall * familiarity_factor(
                player.positions.get(position, 0)))
        return self._ovr_cache[key]

    def status(self) -> dict[str, Any]:
        """Everyone's condition and performance so far, for the subs panel and player cards."""
        e = self.engine
        players = []
        for i, sp in enumerate(e.players):
            team = int(e.team_of[i])
            line = e.lines[sp.player_id]
            result = (e.score[team] > e.score[1 - team]) - (e.score[team] < e.score[1 - team])
            minutes = (e.left.get(sp.player_id, e.t) - e.entered.get(sp.player_id, 0.0)) / 60
            players.append({
                "index": i, "team": team, "player_id": sp.player_id, "name": sp.player.name,
                "short_name": sp.player.short_name, "number": sp.number,
                "position": e.position[i], "role": e.role[i].name, "active": bool(e.active[i]),
                "ovr": self._ovr(sp.player, e.position[i], e.role[i].key),
                "rating": match_rating(line, e.group[i], result, e.score[1 - team], minutes),
                "energy": round(float(e.stamina[i]) * 100),
                "condition": round(sp.player.condition),
                "yellow": int(e.yellows[i]), "red": line.red > 0,
                "goals": line.goals, "assists": line.assists, "shots": line.shots,
                "on_target": line.shots_on_target, "passes": line.passes,
                "pass_pct": (round(100 * line.passes_completed / line.passes)
                             if line.passes else None),
                "tackles": line.tackles, "interceptions": line.interceptions,
                "fouls": e.player_fouls.get(sp.player_id, 0), "saves": line.saves,
                "xg": round(e.player_xg.get(sp.player_id, 0.0), 2),
                "minutes": round(minutes),
            })
        bench = []
        for team in (0, 1):
            on_pitch = [i for i in e.team_indices(team)]
            entries = []
            for sp in e.bench[team]:
                entry: dict[str, Any] = {
                    "player_id": sp.player_id, "name": sp.player.name,
                    "short_name": sp.player.short_name, "number": sp.number,
                    "position": sp.position, "ovr": round(sp.rating),
                    "condition": round(sp.player.condition), "age": sp.player.age,
                    "positions": [p for p, f in sorted(sp.player.positions.items(),
                                                       key=lambda kv: -kv[1]) if f >= 15],
                }
                if team == self.user_team:  # ability in each slot he could come on in
                    entry["fit"] = {str(e.players[i].player_id): self._ovr(
                        sp.player, e.position[i], e.role[i].key) for i in on_pitch}
                entries.append(entry)
            bench.append(entries)
        return {"players": players, "bench": bench}

    def init_message(self, names: tuple[str, str], now: float) -> dict[str, Any]:
        e = self.engine
        self.feed_sent = len(e.feed)
        self.lineup_sent = e.lineup_version
        return {
            "type": "init", "protocol": 2, **self.state(now),
            "teams": [{"name": names[0], "club_id": e.sheets[0].club_id},
                      {"name": names[1], "club_id": e.sheets[1].club_id}],
            "user_team": self.user_team,
            "speeds": self.p.speeds, "compression": self.compression,
            "lineup": e.lineup(),
            "bench": [e.bench_info(0), e.bench_info(1)],
            "status": self.status(),
            "formation": [e.formation[0].key, e.formation[1].key],
            "formations": [{"key": f.key, "name": f.name} for f in e.defs.formations.values()],
            "instructions": [dict(e.instructions[0]), dict(e.instructions[1])],
            "instruction_options": [{"key": d.key, "label": d.label, "options": d.options}
                                    for d in e.defs.instructions.values()],
            "auto_subs": list(e.auto_subs),
            "ai_manager": list(e.ai_manager),
            "stats": e.live_stats(),
            "feed": e.feed[-30:],
            "frames": list(e.frames)[-5:],
        }

    def update_message(self, pump: Pump, now: float) -> dict[str, Any]:
        e = self.engine
        message: dict[str, Any] = {"type": "frames", **self.state(now), "frames": pump.frames,
                                   "highlight": pump.highlight}
        changed = False
        if len(e.feed) > self.feed_sent:
            message["feed"] = e.feed[self.feed_sent:]
            self.feed_sent = len(e.feed)
            changed = True
        if e.lineup_version != self.lineup_sent:
            self.lineup_sent = e.lineup_version
            message["lineup"] = e.lineup()
            message["bench"] = [e.bench_info(0), e.bench_info(1)]
            message["formation"] = [e.formation[0].key, e.formation[1].key]
            changed = True
        if now - self.last_stats >= STATS_EVERY or pump.highlight or changed:
            self.last_stats = now
            message["stats"] = e.live_stats()
            message["lineup_stamina"] = [round(float(s) * 100) for s in e.stamina]
        if now - self.last_status >= STATUS_EVERY or changed:
            self.last_status = now
            message["status"] = self.status()
        message["instructions"] = [dict(e.instructions[0]), dict(e.instructions[1])]
        message["auto_subs"] = list(e.auto_subs)
        message["ai_manager"] = list(e.ai_manager)
        if self.debug:
            message["debug"] = e.debug_snapshot()
        return message

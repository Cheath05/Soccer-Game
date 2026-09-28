"""Agent-based match engine (Tier 0 in the design): the match you watch.

Twenty-two players move continuously on a 105 x 68 m pitch at 10 ticks per second. Each
player's target comes from his formation slot, role, the tactical phase, the ball and the
space around him (behaviours.py); the player on the ball weighs shooting, passing and
dribbling options (actions.py). Passes travel physically and can be intercepted, tackles
can become fouls, shots can be blocked, saved or scored, and the ball can go out for
throw-ins, corners and goal kicks.

Everything the viewer shows comes from this simulation: it records a frame of all
positions every tick plus an event feed. Live tactical commands (formation, instructions,
substitutions) change the engine's state between ticks, so their effect is real.
"""

from collections import deque
from typing import Any

import numpy as np
import numpy.typing as npt
from scipy.optimize import linear_sum_assignment

from footsim.defs.formations import FormationDef
from footsim.defs.loader import GameDefinitions
from footsim.defs.positions import PositionGroup
from footsim.defs.roles import RoleDef
from footsim.domain.attributes import ATTR_INDEX
from footsim.match.engine import actions, behaviours
from footsim.match.engine.pitch import GOAL_HALF, GOAL_HEIGHT, LENGTH, MID_X, MID_Y, WIDTH
from footsim.match.engine.state import MAX_SUBS, PassInfo, Restart, ShotInfo
from footsim.match.penalties import shootout
from footsim.match.report import Decider, Injury, MatchEvent, MatchReport, PlayerLine, TeamStats
from footsim.match.teams import SheetPlayer, TeamSheet
from footsim.ratings.overall import familiarity_factor

DT = 0.1  # seconds per tick
TARGET_EVERY = 3  # ticks between off-ball target updates
PERIOD_SECONDS = {1: 45 * 60, 2: 45 * 60, 3: 15 * 60, 4: 15 * 60}
PERIOD_START_MINUTE = {1: 0, 2: 45, 3: 90, 4: 105}
ROLL_FRICTION = 4.0  # m/s^2, rolling ball deceleration
GRAVITY = 9.81
DRIBBLE_SPEED = 0.85  # share of top speed a player keeps with the ball at his feet
PRESS_FATIGUE = {"low": 0.9, "normal": 1.0, "high": 1.15}
FRAME_BUFFER = 600  # frames kept for a consumer that hasn't drained them (60 s)
FATIGUE_BASE = 0.00001
FATIGUE_SPEED = 0.0000055

Array = npt.NDArray[np.float64]


class MatchEngine:
    def __init__(self, defs: GameDefinitions, home: TeamSheet, away: TeamSheet,
                 rng: np.random.Generator, *, neutral: bool = False,
                 decider: Decider | None = None, record: bool = True,
                 auto_subs: tuple[bool, bool] = (True, True)) -> None:
        self.defs = defs
        self.rng = rng
        self.neutral = neutral
        self.decider = decider
        self.record = record
        self.sheets = [home, away]
        self.formation: list[FormationDef] = [home.formation, away.formation]
        self.roles: list[dict[str, str]] = [dict(home.roles), dict(away.roles)]
        self.instructions: list[dict[str, str]] = [dict(home.instructions),
                                                   dict(away.instructions)]
        self.bench: list[list[SheetPlayer]] = [list(home.bench), list(away.bench)]
        self.subs_used = [0, 0]
        self.auto_subs = list(auto_subs)

        n = 22
        self.team_of = np.array([0] * 11 + [1] * 11)
        self.pos = np.zeros((n, 2))
        self.vel = np.zeros((n, 2))
        self.target = np.zeros((n, 2))
        self.urgent = np.zeros(n, dtype=bool)
        self.running = np.zeros(n, dtype=bool)  # making a forward run
        self.active = np.ones(n, dtype=bool)
        self.attr = np.zeros((n, len(ATTR_INDEX)))
        self.max_speed = np.zeros(n)
        self.accel = np.zeros(n)
        self.stamina = np.ones(n)
        self.tackle_ready = np.zeros(n)  # time a player may next attempt a tackle
        self.players: list[SheetPlayer] = []
        self.slot: list[str] = []
        self.position: list[str] = []
        self.group: list[PositionGroup] = []
        self.role: list[RoleDef] = []
        self.yellows = np.zeros(n, dtype=int)
        for sheet in self.sheets:
            starters = sorted(sheet.starters, key=lambda sp: [s.id for s in sheet.formation.slots]
                              .index(sp.slot or ""))
            if len(starters) != 11:
                raise ValueError(f"{sheet.name} needs 11 starters, has {len(starters)}")
            for sp in starters:
                self._load(len(self.players), sp, new=True)

        self.ball = np.array([MID_X, MID_Y])
        self.ball_v = np.zeros(2)
        self.prev_ball = self.ball.copy()
        self.ball_z = 0.0
        self.ball_vz = 0.0
        self.owner = -1
        self.state = "dead"  # dead | owned | pass | loose | shot
        self.pass_info: PassInfo | None = None
        self.stopped_pass: tuple[PassInfo, float] | None = None
        self.shot_info: ShotInfo | None = None
        self.last_touch = -1
        self.decide_at = 0.0
        self.turnover_at = -99.0  # when the ball last changed teams (counter-press window)
        self.carry_target: Array | None = None
        self.carry_urgent = False
        self.restart: Restart | None = None
        self.last_completed_pass: tuple[int, int, float] | None = None  # passer, receiver, time

        self.t = 0.0
        self.tick_count = 0
        self.period = 1
        self.period_clock = 0.0
        self.stoppage = float(rng.integers(1, 4)) * 60
        self.attack_dir = [1, -1]
        self.finished = False
        self.score = [0, 0]
        self.pens: tuple[int, int] | None = None
        self.stats = [TeamStats(), TeamStats()]
        self.possession_ticks = [0, 0]
        self.lines: dict[int, PlayerLine] = {}
        for i, sp in enumerate(self.players):
            self.lines[sp.player_id] = PlayerLine(sp.player_id, self._club(i), started=True)
        self.entered: dict[int, float] = {sp.player_id: 0.0 for sp in self.players}
        self.left: dict[int, float] = {}
        self.minutes_played_end = 90
        self.events: list[MatchEvent] = []
        self.injuries: list[Injury] = []
        self.feed: list[dict[str, Any]] = []
        self.frames: deque[list[float]] = deque(maxlen=FRAME_BUFFER)
        self.lineup_version = 0
        self.last_sub_check = 0.0
        self.last_comment = -99.0
        self.last_possession_note = 0.0

        self._kickoff(team=0, teleport=True)

    # --- setup --------------------------------------------------------------------------

    def _load(self, i: int, sp: SheetPlayer, new: bool = False) -> None:
        """Put ``sp`` in player index ``i`` (initial load or a substitution)."""
        if new:
            self.players.append(sp)
            self.slot.append(sp.slot or "")
            self.position.append(sp.position)
            self.group.append(sp.group)
            self.role.append(self.defs.roles[sp.role])
        else:
            self.players[i] = sp
        self.attr[i] = sp.player.attrs
        a = self.attr[i]
        self.max_speed[i] = 5.8 + 3.6 * a[ATTR_INDEX["sprint_speed"]] / 100
        self.accel[i] = 2.6 + 4.2 * a[ATTR_INDEX["acceleration"]] / 100
        self.stamina[i] = max(0.35, sp.player.condition / 100)
        self.active[i] = True

    def _club(self, i: int) -> int:
        return self.sheets[int(self.team_of[i])].club_id

    def a(self, i: int, name: str) -> float:
        return float(self.attr[i, ATTR_INDEX[name]])

    # --- frames of reference ------------------------------------------------------------

    def to_att(self, team: int, x: float, y: float) -> tuple[float, float]:
        if self.attack_dir[team] > 0:
            return x, y
        return LENGTH - x, WIDTH - y

    def to_pitch(self, team: int, x: float, y: float) -> tuple[float, float]:
        return self.to_att(team, x, y)  # the transform is its own inverse

    def att_points(self, team: int, pts: Array) -> Array:
        if self.attack_dir[team] > 0:
            return pts.copy()
        result: Array = np.column_stack((LENGTH - pts[:, 0], WIDTH - pts[:, 1]))
        return result

    def team_indices(self, team: int) -> npt.NDArray[np.int64]:
        idx: npt.NDArray[np.int64] = np.flatnonzero(self.active & (self.team_of == team))
        return idx

    def keeper(self, team: int) -> int | None:
        for i in self.team_indices(team):
            if self.group[i] is PositionGroup.GK:
                return int(i)
        return None

    @property
    def minute(self) -> int:
        return PERIOD_START_MINUTE[self.period] + int(self.period_clock // 60) + 1

    def possession_team(self) -> int | None:
        if self.owner >= 0:
            return int(self.team_of[self.owner])
        if self.state == "pass" and self.pass_info is not None:
            return int(self.team_of[self.pass_info.passer])
        if self.restart is not None:
            return self.restart.team
        if self.last_touch >= 0:
            return int(self.team_of[self.last_touch])
        return None

    # --- main loop ----------------------------------------------------------------------

    def step(self) -> None:
        if self.finished:
            return
        if self.restart is not None:
            self._restart_tick()
        elif self.owner >= 0:
            actions.owner_tick(self)
        self._ball_tick()
        if self.tick_count % TARGET_EVERY == 0:
            behaviours.update_targets(self)
        self._move_players()
        self._fatigue()
        team = self.possession_team()
        if team is not None and self.restart is None:
            self.possession_ticks[team] += 1
        self._clock()
        if self.record:
            self._frame()
        self.tick_count += 1

    def run(self, max_ticks: int | None = None) -> None:
        ticks = 0
        while not self.finished and (max_ticks is None or ticks < max_ticks):
            self.step()
            ticks += 1

    # --- clock and periods --------------------------------------------------------------

    def _clock(self) -> None:
        self.t += DT
        self.period_clock += DT
        if self.period_clock >= PERIOD_SECONDS[self.period] + self.stoppage and self._can_stop():
            self._end_period()
        if self.t - self.last_possession_note >= 300 and not self.finished:
            self.last_possession_note = self.t
            total = sum(self.possession_ticks) or 1
            share = [round(100 * p / total) for p in self.possession_ticks]
            leader = 0 if share[0] >= share[1] else 1
            name = self.sheets[leader].name
            self._announce("play", leader, f"{name} have had {share[leader]}% of the ball so far")
        if self.minute >= 58 and self.t - self.last_sub_check >= 60:
            self.last_sub_check = self.t
            for team in (0, 1):
                if self.auto_subs[team]:
                    actions.ai_substitutions(self, team)

    def _can_stop(self) -> bool:
        """Don't blow the whistle while a shot is in the air."""
        return self.state != "shot"

    def _end_period(self) -> None:
        if self.period == 1:
            self._announce("half_time", None, "Half-time")
            self._start_period(2, kickoff_team=1, stoppage=float(self.rng.integers(2, 7)) * 60)
            return
        needs_winner = self.decider is not None and self.decider.level(*self.score)
        if self.period == 2 and needs_winner and self.decider and self.decider.extra_time:
            self._announce("full_time", None, "Full-time: extra time to be played")
            self._start_period(3, kickoff_team=0, stoppage=60.0)
            return
        if self.period == 3:
            self._start_period(4, kickoff_team=1, stoppage=60.0)
            return
        if needs_winner and self.decider and self.decider.penalties:
            self._shootout()
        self.minutes_played_end = 120 if self.period == 4 else 90
        self.finished = True
        self._announce("full_time", None, f"Full-time: {self.score[0]}-{self.score[1]}")

    def _start_period(self, period: int, kickoff_team: int, stoppage: float) -> None:
        self.period = period
        self.period_clock = 0.0
        self.stoppage = stoppage
        self.attack_dir = [-d for d in self.attack_dir]
        self.stamina = np.minimum(1.0, self.stamina + 0.04)
        self._kickoff(kickoff_team, teleport=True)

    def _shootout(self) -> None:
        takers = [[self.players[i].player for i in self.team_indices(t)] for t in (0, 1)]
        keepers = [self.keeper(t) for t in (0, 1)]
        home_k = self.players[keepers[0]].player if keepers[0] is not None else None
        away_k = self.players[keepers[1]].player if keepers[1] is not None else None
        self.pens = shootout(takers[0], away_k, takers[1], home_k, self.rng)
        self._announce("penalties", None,
                       f"Penalty shootout: {self.pens[0]}-{self.pens[1]}")

    # --- movement -----------------------------------------------------------------------

    def _move_players(self) -> None:
        delta = self.target - self.pos
        dist = np.linalg.norm(delta, axis=1)
        fatigue = 0.78 + 0.22 * self.stamina
        top = self.max_speed * fatigue
        if self.owner >= 0:
            top[self.owner] *= DRIBBLE_SPEED
            rivals = self.team_indices(1 - int(self.team_of[self.owner]))
            if len(rivals) and float(np.min(np.linalg.norm(self.pos[rivals] - self.pos[self.owner],
                                                            axis=1))) < 2.5:
                top[self.owner] *= 0.75  # tight control under pressure
        cruise = np.where(dist > 6, 0.62 * top, np.where(dist > 1.5, 0.4 * top, 0.9 * dist))
        speed = np.where(self.urgent, top, cruise)
        direction = np.divide(delta, dist[:, None], out=np.zeros_like(delta),
                              where=dist[:, None] > 1e-6)
        desired = direction * speed[:, None]
        change = desired - self.vel
        change_norm = np.linalg.norm(change, axis=1)
        limit = self.accel * DT
        scale = np.minimum(1.0, np.divide(limit, change_norm, out=np.ones_like(limit),
                                          where=change_norm > 1e-6))
        self.vel = self.vel + change * scale[:, None]
        self.vel[~self.active] = 0
        self.pos = self.pos + self.vel * DT
        self.pos[:, 0] = np.clip(self.pos[:, 0], -2, LENGTH + 2)
        self.pos[:, 1] = np.clip(self.pos[:, 1], -2, WIDTH + 2)
        self.pos[~self.active] = (-10.0, -10.0)

    def _fatigue(self) -> None:
        speed_sq = np.sum(self.vel**2, axis=1)
        stamina_attr = self.attr[:, ATTR_INDEX["stamina"]] / 100
        effort = [PRESS_FATIGUE.get(self.instructions[t].get("pressing", ""), 1.0) for t in (0, 1)]
        press = np.where(self.team_of == 0, effort[0], effort[1])
        drain = DT * (FATIGUE_BASE + FATIGUE_SPEED * speed_sq) * (1.35 - 0.7 * stamina_attr)
        self.stamina = np.maximum(0.0, self.stamina - drain * press * self.active)

    # --- ball ---------------------------------------------------------------------------

    def _ball_tick(self) -> None:
        if self.state == "owned":
            i = self.owner
            v = self.vel[i]
            speed = float(np.linalg.norm(v))
            if speed > 0.3:
                ahead = v / speed * 0.7
            else:
                dx = 1.0 if self.attack_dir[int(self.team_of[i])] > 0 else -1.0
                ahead = np.array([0.5 * dx, 0.0])
            self.ball = self.pos[i] + ahead
            self.ball_v = v.copy()
            self.ball_z = 0.0
            x, y = self.ball
            if not (0 <= x <= LENGTH and 0 <= y <= WIDTH):
                self.owner = -1
                self.state = "loose"
                self.last_touch = i
                self._out_of_play(float(x), float(y))
            return
        if self.state == "dead":
            return
        # Flight and roll.
        if self.ball_z > 0 or self.ball_vz > 0:
            self.ball_z += self.ball_vz * DT
            self.ball_vz -= GRAVITY * DT
            if self.state != "shot":
                self.ball_v *= 0.995
            if self.ball_z <= 0:
                self.ball_z = 0.0
                self.ball_vz = -self.ball_vz * 0.3 if self.ball_vz < -3 else 0.0
                self.ball_v *= 0.75
        else:
            speed = float(np.linalg.norm(self.ball_v))
            if speed > 0:
                self.ball_v *= max(0.0, speed - ROLL_FRICTION * DT) / speed
        step = self.ball_v * DT
        self.prev_ball = self.ball.copy()
        self.ball = self.ball + step
        if self.state == "shot" and self.shot_info is not None:
            self.shot_info.travelled += float(np.linalg.norm(step))
            actions.shot_tick(self)
            if self.state != "shot":
                return
        if self._check_out_of_play():
            return
        if self.state in ("pass", "loose"):
            actions.resolve_loose_or_pass(self)

    def _check_out_of_play(self) -> bool:
        x, y = self.ball
        if 0 <= x <= LENGTH and 0 <= y <= WIDTH:
            return False
        if self.state == "shot" or (x < 0 or x > LENGTH):
            goal_mouth = abs(y - MID_Y) <= GOAL_HALF and self.ball_z <= GOAL_HEIGHT
            if goal_mouth and (x < 0 or x > LENGTH):
                scoring = 0 if (x > LENGTH) == (self.attack_dir[0] > 0) else 1
                self._goal(scoring)
                return True
        self._out_of_play(float(x), float(y))
        return True

    def _out_of_play(self, x: float, y: float) -> None:
        last = self.last_touch if self.last_touch >= 0 else 0
        last_team = int(self.team_of[last])
        other = 1 - last_team
        self.shot_info = None
        self.pass_info = None
        if 0 <= x <= LENGTH:  # over a touchline
            spot = (min(max(x, 1.0), LENGTH - 1.0), 0.0 if y < 0 else WIDTH)
            self._set_restart("throw_in", other, spot, delay=2.5)
            return
        # Over a goal line: whose goal line is it?
        defending = 0 if (x < 0) == (self.attack_dir[0] > 0) else 1
        if last_team == defending:
            corner_x = 0.0 if x < 0 else LENGTH
            corner_y = 0.0 if y < MID_Y else WIDTH
            self.stats[1 - defending].corners += 1
            self._announce("corner", 1 - defending, "Corner")
            self._set_restart("corner", 1 - defending, (corner_x, corner_y), delay=5.0)
        else:
            gx, gy = self.to_pitch(defending, 5.5, MID_Y + float(self.rng.uniform(-6, 6)))
            self._set_restart("goal_kick", defending, (gx, gy), delay=4.0)

    def _goal(self, team: int) -> None:
        info = self.shot_info
        scorer = info.shooter if info is not None else self.last_touch
        own_goal = scorer < 0 or int(self.team_of[scorer]) != team
        self.score[team] += 1
        self.stats[team].goals = self.score[team]
        club = self.sheets[team].club_id
        if own_goal:
            name = self.players[scorer].player.name if scorer >= 0 else "?"
            self.events.append(MatchEvent(self.minute, "own_goal", club,
                                          self.players[scorer].player_id if scorer >= 0 else None))
            self._announce("goal", team, f"GOAL! Own goal by {name}")
        else:
            penalty = info is not None and info.penalty
            line = self.lines[self.players[scorer].player_id]
            line.goals += 1
            assist = None
            if (not penalty and self.last_completed_pass is not None
                    and self.last_completed_pass[1] == scorer
                    and self.t - self.last_completed_pass[2] < 12):
                assist = self.last_completed_pass[0]
                self.lines[self.players[assist].player_id].assists += 1
            kind = "penalty_goal" if penalty else "goal"
            self.events.append(MatchEvent(
                self.minute, kind, club, self.players[scorer].player_id,
                self.players[assist].player_id if assist is not None else None))
            text = f"GOAL! {self.players[scorer].player.name}"
            if assist is not None:
                text += f", assisted by {self.players[assist].player.name}"
            if penalty:
                text += " (penalty)"
            self._announce("goal", team, text)
        self.shot_info = None
        self.state = "dead"
        self.ball_v[:] = 0
        self.ball_vz = 0.0
        self._kickoff(1 - team, teleport=False, delay=10.0)

    # --- restarts -----------------------------------------------------------------------

    def _set_restart(self, kind: str, team: int, spot: tuple[float, float], delay: float) -> None:
        self.owner = -1
        self.state = "dead"
        self.pass_info = None
        self.shot_info = None
        self.ball = np.array(spot, dtype=float)
        self.ball_v[:] = 0
        self.ball_z = 0.0
        self.ball_vz = 0.0
        self.restart = Restart(kind, team, spot, self.t + delay)
        self.restart.taker = actions.pick_taker(self, self.restart)

    def _kickoff(self, team: int, teleport: bool, delay: float = 1.5) -> None:
        self._set_restart("kickoff", team, (MID_X, MID_Y), delay)
        behaviours.update_targets(self)
        if teleport:
            self.pos = self.target.copy()
            self.vel[:] = 0

    def _restart_tick(self) -> None:
        restart = self.restart
        assert restart is not None
        taker = restart.taker
        if taker is None or not self.active[taker]:
            restart.taker = taker = actions.pick_taker(self, restart)
        if taker is None:
            return
        spot = np.array(restart.spot)
        close = float(np.linalg.norm(self.pos[taker] - spot)) < 1.2
        if self.t < restart.ready_at or (not close and self.t < restart.ready_at + 6):
            return
        if not close:
            self.pos[taker] = spot
        self.restart = None
        actions.take_restart(self, restart, taker)

    # --- recording ----------------------------------------------------------------------

    def commentate(self, team: int | None, text: str, gap: float = 6.0) -> None:
        """Open-play commentary, rate-limited so fast playback doesn't flood the feed."""
        if self.t - self.last_comment < gap:
            return
        self.last_comment = self.t
        self._announce("play", team, text)

    def _announce(self, kind: str, team: int | None, text: str) -> None:
        self.feed.append({"t": round(self.t, 1), "minute": self.minute, "type": kind,
                          "team": team, "text": text,
                          "score": [self.score[0], self.score[1]]})

    def _frame(self) -> None:
        frame = [round(self.t, 1), round(float(self.ball[0]), 2), round(float(self.ball[1]), 2),
                 round(self.ball_z, 2), float(self.owner)]
        frame.extend(np.round(self.pos.ravel(), 2).tolist())
        self.frames.append(frame)

    def lineup(self) -> list[dict[str, Any]]:
        return [{"index": i, "team": int(self.team_of[i]), "name": sp.player.short_name,
                 "number": sp.number, "position": self.position[i],
                 "player_id": sp.player_id, "active": bool(self.active[i]),
                 "stamina": round(float(self.stamina[i]) * 100)}
                for i, sp in enumerate(self.players)]

    def bench_info(self, team: int) -> list[dict[str, Any]]:
        return [{"player_id": sp.player_id, "name": sp.player.name, "number": sp.number,
                 "position": sp.position} for sp in self.bench[team]]

    def live_stats(self) -> dict[str, list[float]]:
        total = sum(self.possession_ticks) or 1
        return {
            "possession": [round(100 * self.possession_ticks[t] / total) for t in (0, 1)],
            "shots": [self.stats[t].shots for t in (0, 1)],
            "on_target": [self.stats[t].shots_on_target for t in (0, 1)],
            "xg": [round(float(self.stats[t].xg), 2) for t in (0, 1)],
            "passes": [self.stats[t].passes for t in (0, 1)],
            "pass_pct": [round(100 * self.stats[t].passes_completed / self.stats[t].passes)
                         if self.stats[t].passes else 0 for t in (0, 1)],
            "corners": [self.stats[t].corners for t in (0, 1)],
            "fouls": [self.stats[t].fouls for t in (0, 1)],
        }

    # --- commands -----------------------------------------------------------------------

    def set_instruction(self, team: int, key: str, value: str) -> None:
        options = self.defs.instructions.get(key)
        if options is None or value not in options.options:
            raise ValueError(f"invalid instruction {key}={value}")
        self.instructions[team][key] = value
        self._announce("tactics", team, f"{key.title()} set to {value}")

    def set_formation(self, team: int, key: str) -> None:
        """Re-deploy the players on the pitch into a new shape, keeping everyone on."""
        formation = self.defs.formations[key]
        idx = [int(i) for i in self.team_indices(team)]
        slots = formation.slots
        score = np.zeros((len(idx), len(slots)))
        for r, i in enumerate(idx):
            fam = self.players[i].player.positions
            for c, slot in enumerate(slots):
                score[r, c] = familiarity_factor(fam.get(slot.position, 0)) * 100 + (
                    self.players[i].rating / 100)
        rows, cols = linear_sum_assignment(-score)
        for r, c in zip(rows.tolist(), cols.tolist(), strict=True):
            i, slot = idx[r], slots[c]
            self.slot[i] = slot.id
            self.position[i] = slot.position
            self.group[i] = self.defs.positions[slot.position].group
            self.role[i] = self.defs.roles[slot.default_role]
        self.formation[team] = formation
        self.roles[team] = {}
        self.lineup_version += 1
        self._announce("tactics", team, f"Formation changed to {formation.name}")

    def substitute(self, team: int, out_player_id: int, in_player_id: int) -> None:
        if self.subs_used[team] >= MAX_SUBS:
            raise ValueError("no substitutions left")
        idx = next((i for i in self.team_indices(team)
                    if self.players[i].player_id == out_player_id), None)
        incoming = next((sp for sp in self.bench[team] if sp.player_id == in_player_id), None)
        if idx is None or incoming is None:
            raise ValueError("invalid substitution")
        if self.owner == idx:
            raise ValueError("wait until the player isn't on the ball")
        outgoing = self.players[idx]
        self.bench[team].remove(incoming)
        entering = SheetPlayer(incoming.player, incoming.number, self.slot[idx],
                               self.position[idx], self.group[idx], self.role[idx].key,
                               incoming.rating)
        self._load(int(idx), entering)
        self.subs_used[team] += 1
        self.left[outgoing.player_id] = self.t
        self.entered[entering.player_id] = self.t
        self.lines[entering.player_id] = PlayerLine(entering.player_id,
                                                    self.sheets[team].club_id, started=False)
        self.events.append(MatchEvent(self.minute, "sub", self.sheets[team].club_id,
                                      outgoing.player_id, entering.player_id))
        self.lineup_version += 1
        self._announce("sub", team, f"Substitution: {entering.player.name} replaces "
                                    f"{outgoing.player.name}")

    def send_off(self, i: int, detail: str) -> None:
        sp = self.players[i]
        team = int(self.team_of[i])
        self.lines[sp.player_id].red += 1
        self.stats[team].red += 1
        self.events.append(MatchEvent(self.minute, "red", self.sheets[team].club_id,
                                      sp.player_id, detail=detail))
        self._announce("red", team, f"RED CARD! {sp.player.name} is sent off ({detail})")
        self.active[i] = False
        self.left[sp.player_id] = self.t
        if self.owner == i:
            self.owner = -1
        self.lineup_version += 1

    # --- final report -------------------------------------------------------------------

    def report(self) -> MatchReport:
        total = sum(self.possession_ticks) or 1
        for t in (0, 1):
            self.stats[t].possession = round(100 * self.possession_ticks[t] / total, 1)
            self.stats[t].goals = self.score[t]
            self.stats[t].xg = round(float(self.stats[t].xg), 2)
        end = self.t
        for pid, line in self.lines.items():
            start = self.entered.get(pid, 0.0)
            stop = self.left.get(pid, end)
            share = (stop - start) / max(end, 1.0)
            line.minutes = max(1, round(share * self.minutes_played_end))
        actions.rate_players(self)
        fitness = {}
        for i, sp in enumerate(self.players):
            fitness[sp.player_id] = round(float(self.stamina[i]) * 100, 1)
        report = MatchReport(
            self.sheets[0].club_id, self.sheets[1].club_id, self.score[0], self.score[1],
            extra_time=self.period >= 3,
            home_pens=self.pens[0] if self.pens else None,
            away_pens=self.pens[1] if self.pens else None,
            events=sorted(self.events, key=lambda e: e.minute),
            players=dict(self.lines), home_stats=self.stats[0], away_stats=self.stats[1],
            injuries=list(self.injuries), fitness=fitness,
        )
        return report

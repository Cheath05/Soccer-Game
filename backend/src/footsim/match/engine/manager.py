"""The in-match manager of a computer-controlled side.

Every few minutes, and after every goal or red card, he looks at the game and adjusts his
team's instructions from the plan he started with. He only changes what players are asked to
do, through the same ``set_instruction`` the user's commands go through, so nothing here makes
anyone better. And he reads the opponent only from what he can see on the pitch (how high
their back line holds, how many of them close down his ball carrier near his own goal), never
from their settings. Everything he weighs is in the ``manager`` section of tactics.yaml.

  - Late on, a side that's ahead slows the game down and stops pressing high; protecting a
    one-goal lead it sits deeper, and in the last ten minutes drops its line a step.
  - A side that's behind late on pushes more players forward and speeds up, and in the last
    minutes goes direct and presses high.
  - Down to fewer players, he steps back from attacking and pressing high, unless he's
    chasing the game.
  - Against a high line or a hard press he plays more directly, into the space it leaves.
"""

import math
from collections import deque
from typing import TYPE_CHECKING

import numpy as np

from footsim.defs.positions import PositionGroup
from footsim.match.engine.pitch import MID_X

if TYPE_CHECKING:
    from footsim.defs.match import ManagerDef
    from footsim.match.engine.engine import MatchEngine

LESS_ATTACKING = {"attacking": "balanced", "balanced": "defensive"}
DEEPER = {"high": "normal", "normal": "deep"}
LESS_PRESSING = {"high": "normal"}

# What the commentary says when he moves an instruction up or down its list of options
# (match/instructions/team.yaml orders them from cautious to bold).
UP = {
    "mentality": "push more players forward",
    "pressing": "press higher up the pitch",
    "line": "push their defensive line up",
    "width": "spread the play wider",
    "tempo": "try to speed the game up",
    "passing": "go longer, looking for the space behind",
}
DOWN = {
    "mentality": "sit deeper",
    "pressing": "ease off the press",
    "line": "drop their defensive line",
    "width": "tuck in narrower",
    "tempo": "slow the game down",
    "passing": "keep the ball on the ground",
}

Looks = deque[tuple[float, float]]  # (match time, what he saw)


class ManagerAI:
    """The touchline decisions of one side. ``plan`` is what he would pick at 0-0 with
    eleven against eleven; every review starts from it again, so changes are undone when the
    reason for them goes away."""

    def __init__(self, eng: "MatchEngine", team: int) -> None:
        self.team = team
        self.plan = _complete(eng, eng.instructions[team])
        self.line_seen: Looks = deque()  # opponent back line, m from their goal
        self.press_seen: Looks = deque()  # opponents on our ball carrier near our goal
        # His verdicts on the opponent, kept until enough new looks say otherwise: once he
        # goes long against a press, his side has the ball near its own goal less often, and
        # a lack of evidence mustn't read as the press having stopped.
        self.high_line = False
        self.pressing = False
        self.next_review = eng.defs.tactics.manager.review_every
        self.next_look = 0.0
        self.last_state = self._state(eng)

    def adopt(self, eng: "MatchEngine") -> None:
        """Take over from the instructions as they stand (the user handing his side over)."""
        self.plan = _complete(eng, eng.instructions[self.team])
        self.line_seen.clear()
        self.press_seen.clear()
        self.high_line = self.pressing = False
        self.next_review = eng.t  # look at the game straight away

    def planned(self, key: str, value: str) -> None:
        """Someone else set an instruction: it becomes part of his plan."""
        self.plan[key] = value

    def tick(self, eng: "MatchEngine") -> None:
        p = eng.defs.tactics.manager
        if eng.t >= self.next_look:
            self.next_look = eng.t + p.sample_every
            self._look(eng, p)
        state = self._state(eng)
        if eng.t < self.next_review and state == self.last_state:
            return
        self.next_review = eng.t + p.review_every
        self.last_state = state
        wanted = self.decide(eng)
        current = _complete(eng, eng.instructions[self.team])
        changes = [(key, current[key], value) for key, value in wanted.items()
                   if current[key] != value]
        if not changes:
            return
        text = self._describe(eng, changes)
        for key, _, value in changes:
            eng.set_instruction(self.team, key, value, by_manager=True)
        eng.announce_tactics(self.team, f"{eng.sheets[self.team].name} {text}")

    def decide(self, eng: "MatchEngine") -> dict[str, str]:
        """The instructions he wants now: the plan, adjusted for the opponent and the game."""
        p = eng.defs.tactics.manager
        wanted = dict(self.plan)
        if self.opponent_high_line(eng.t, p) or self.opponent_pressing(eng.t, p):
            wanted["passing"] = "direct"  # play past the press, into the space behind the line
        lead = self._lead(eng)
        minute = eng.minute
        chasing = minute >= p.late and lead < 0
        if self._short(eng) and not chasing:
            wanted["mentality"] = LESS_ATTACKING.get(wanted["mentality"], wanted["mentality"])
            wanted["pressing"] = LESS_PRESSING.get(wanted["pressing"], wanted["pressing"])
        if minute >= p.late and lead > 0:
            wanted["tempo"] = "slow"
            wanted["pressing"] = LESS_PRESSING.get(wanted["pressing"], wanted["pressing"])
            if lead == 1:
                wanted["mentality"] = "defensive"
                if minute >= p.protect_from:
                    wanted["line"] = DEEPER.get(wanted["line"], wanted["line"])
            elif wanted["mentality"] == "attacking":
                wanted["mentality"] = "balanced"
        elif chasing:
            wanted["mentality"] = "attacking"
            wanted["tempo"] = "fast"
            if minute >= p.very_late:
                wanted["passing"] = "direct"
                wanted["pressing"] = "high"
        return wanted

    def opponent_high_line(self, now: float, p: "ManagerDef") -> bool:
        read = _read(self.line_seen, now, p)
        if not math.isnan(read):
            self.high_line = read >= p.high_line
        return self.high_line

    def opponent_pressing(self, now: float, p: "ManagerDef") -> bool:
        read = _read(self.press_seen, now, p)
        if not math.isnan(read):
            self.pressing = read >= p.high_press
        return self.pressing

    def _lead(self, eng: "MatchEngine") -> int:
        return eng.score[self.team] - eng.score[1 - self.team]

    def _short(self, eng: "MatchEngine") -> bool:
        return len(eng.team_indices(self.team)) < len(eng.team_indices(1 - self.team))

    def _state(self, eng: "MatchEngine") -> tuple[int, int, int]:
        """What triggers an early review: a goal, or a player sent off (checked every tick, so
        it only reads counters)."""
        return (eng.score[0] + eng.score[1], eng.stats[0].red, eng.stats[1].red)

    def _describe(self, eng: "MatchEngine", changes: list[tuple[str, str, str]]) -> str:
        """What the commentator says: the new moves, then anything put back to the plan."""
        moves = [self._phrase(eng, key, old, new) for key, old, new in changes
                 if new != self.plan.get(key)]
        back = [eng.defs.instructions[key].label.lower() for key, _, new in changes
                if new == self.plan.get(key)]
        parts = moves[:3]
        if back:
            parts.append(f"go back to their usual {_join(back)}")
        return _join(parts)

    def _phrase(self, eng: "MatchEngine", key: str, old: str, new: str) -> str:
        options = eng.defs.instructions[key].options
        if options.index(new) > options.index(old):
            return UP[key]
        if key == "mentality":
            if self._lead(eng) > 0:
                return "drop deeper to protect their lead"
            if self._short(eng):
                return "sit deeper with a man down"
        return DOWN[key]

    def _look(self, eng: "MatchEngine", p: "ManagerDef") -> None:
        """While we have the ball in open play in our own half, note how high the opponent's
        back line holds; with it near our own goal, how many of them are on our carrier."""
        if eng.restart is not None or eng.state == "dead" or eng.possession_team() != self.team:
            return
        bx, _ = eng.to_att(self.team, float(eng.ball[0]), float(eng.ball[1]))
        if bx >= MID_X:
            return
        rival = 1 - self.team
        outfield = [int(i) for i in eng.team_indices(rival)
                    if eng.group[i] is not PositionGroup.GK]
        if len(outfield) < 4:
            return
        theirs = eng.att_points(rival, eng.pos[outfield])
        self.line_seen.append((eng.t, float(np.mean(np.sort(theirs[:, 0])[:4]))))
        if bx < p.press_zone and eng.owner >= 0 and int(eng.team_of[eng.owner]) == self.team:
            gaps = np.linalg.norm(eng.pos[outfield] - eng.pos[eng.owner], axis=1)
            self.press_seen.append((eng.t, float(np.sum(gaps < p.press_radius))))


def _complete(eng: "MatchEngine", instructions: dict[str, str]) -> dict[str, str]:
    """Every instruction, with the default level for any the team sheet leaves out."""
    return {**{key: d.default for key, d in eng.defs.instructions.items()}, **instructions}


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} and {items[-1]}"


def _read(seen: Looks, now: float, p: "ManagerDef") -> float:
    """The average of the looks from the last ``memory`` seconds, or NaN (which compares
    false with everything) while there are too few of them."""
    while seen and now - seen[0][0] > p.memory:
        seen.popleft()
    if len(seen) < p.min_samples:
        return float("nan")
    return float(np.mean([value for _, value in seen]))

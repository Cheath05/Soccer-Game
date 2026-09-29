"""The match's structured event log: what happened, where, when and to whom.

The engine appends an EngineEvent for every football action as it happens. Nothing in the
simulation reads the log back, so recording it can never change a match. The calibration
probe, commentary and match analytics interpret it afterwards.

Event kinds and their data:
  restart        kind, spot                       a restart is awarded
  restart_taken  kind, wait, teleported, box_attackers, box_defenders (corners)
  pass           kind, lofted, estimate, length, xa  (xa: passer's x in his attacking frame)
  pass_result    result (complete|intercepted), kind, xa
  aerial         won (attack|defence|keeper)
  clearance
  duel           outcome (won|beaten|foul), carrier, xa (tackler's attacking frame)
  foul           victim, card (none|yellow|second_yellow|red), penalty
  shot           xg, outcome, header, penalty, free_kick, distance, xa, ya, goal_side,
                 nearest, blockers
  save           how (catch|tip|parry), teleported
  block          how (cleared|corner|loose)
  goal           own_goal, penalty, assist
  offside, sub, injury, period
Positions (x, y) are pitch coordinates in metres; ``team`` is 0 (home) or 1 (away).
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class EngineEvent:
    t: float
    kind: str
    team: int | None
    player: int | None  # engine index 0-21, None for team-level events
    x: float
    y: float
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Possession:
    """One team's uninterrupted control of the ball, from winning it to losing it."""

    team: int
    start_t: float
    start_x: float  # where it was won, in the team's attacking frame
    source: str  # tackle | interception | loose | save | claim | kickoff | throw_in | ...
    end_t: float | None = None
    max_x: float = 0.0
    final_third: bool = False
    box: bool = False
    passes: int = 0
    shots: int = 0
    goals: int = 0

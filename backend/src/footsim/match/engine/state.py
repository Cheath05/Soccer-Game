"""Small state records shared by the engine modules."""

from dataclasses import dataclass, field

MAX_SUBS = 5


@dataclass
class PassInfo:
    passer: int
    receiver: int  # -1 for a clearance
    target: tuple[float, float]  # pitch coordinates
    lofted: bool
    kind: str  # pass | through | cross | clearance | throw
    tried: set[int] = field(default_factory=set)  # players who already tried to control it
    estimate: float = 1.0  # the passer's estimated success chance (for debugging/calibration)
    restart: str | None = None  # the restart this pass took (no offside from some, Law 11)


@dataclass
class ShotInfo:
    shooter: int
    outcome: str  # goal | saved | off | blocked
    xg: float
    keeper: int | None
    resolve_distance: float  # ball travel after which a save or block happens
    travelled: float = 0.0
    header: bool = False
    penalty: bool = False


@dataclass
class Restart:
    kind: str  # kickoff | throw_in | goal_kick | corner | free_kick | penalty
    team: int
    spot: tuple[float, float]
    ready_at: float  # the earliest it can be taken
    taker: int | None = None
    # Timing and layout (restarts.yaml): throw_in, long_throw, dangerous_free_kick, ...
    variant: str = ""
    awarded_at: float = 0.0
    deadline: float = 0.0  # taken by then even if not everyone is in place
    placed: bool = True  # False while the ball is still where it went out

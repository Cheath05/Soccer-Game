"""Player roles: suitability weights and behaviour parameters (data/config/roles/*.yaml).

Suitability weights are the position group's base weights plus ``weight_modifiers``,
clipped at zero and renormalised (see footsim.ratings). Behaviour parameters are read by
the match engine; all default to neutral so a role only states what makes it distinct.
"""

from enum import StrEnum

from pydantic import Field

from footsim.defs.common import AttributeDeltas, DefModel, SignedUnit, Unit
from footsim.defs.formations import Phase
from footsim.defs.positions import PositionGroup


class RunType(StrEnum):
    IN_BEHIND = "in_behind"
    OVERLAP = "overlap"
    UNDERLAP = "underlap"
    DROP_DEEP = "drop_deep"
    DRIFT_WIDE = "drift_wide"
    INVERT = "invert"
    ARRIVE_LATE = "arrive_late"


class RoleOffset(DefModel):
    """Side-agnostic offset. ``d_out`` > 0 moves towards the slot's own touchline,
    < 0 towards the centre, so one role definition works on either flank."""

    dx: SignedUnit = 0.0
    d_out: SignedUnit = 0.0


class RoleMovement(DefModel):
    phase_offsets: dict[Phase, RoleOffset] = {}
    freedom: float = Field(default=0.06, ge=0.0, le=0.3)
    runs: dict[RunType, Unit] = {}


class RoleOnBall(DefModel):
    pass_risk: SignedUnit = 0.0
    shoot_bias: SignedUnit = 0.0
    dribble_bias: SignedUnit = 0.0
    cross_bias: SignedUnit = 0.0


class RoleDefending(DefModel):
    press_bias: SignedUnit = 0.0
    track_runners: Unit = 0.5
    hold_line: bool = False


class RoleDef(DefModel):
    key: str
    name: str
    group: PositionGroup
    description: str = ""
    weight_modifiers: AttributeDeltas = {}
    movement: RoleMovement = RoleMovement()
    on_ball: RoleOnBall = RoleOnBall()
    defending: RoleDefending = RoleDefending()

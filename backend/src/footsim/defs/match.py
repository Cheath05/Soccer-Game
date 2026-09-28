"""Match-simulation parameters (data/config/match/*.yaml)."""

from pydantic import Field, model_validator

from footsim.defs.common import DefModel
from footsim.defs.positions import PositionGroup


class InstructionDef(DefModel):
    key: str
    label: str
    options: list[str]
    default: str

    @model_validator(mode="after")
    def _default_is_option(self) -> "InstructionDef":
        if self.default not in self.options:
            raise ValueError(f"{self.key}: default {self.default!r} is not an option")
        return self


class InstructionEffect(DefModel):
    own_goals: float = 1.0  # multiplier on own expected goals
    opponent_goals: float = 1.0  # multiplier on the opponent's expected goals
    fatigue: float = 1.0  # multiplier on stamina drain


class QuickEngineParams(DefModel):
    """Fast statistical engine for matches nobody watches (Tier 1 in the design)."""

    base_goals: float = Field(gt=0)  # expected goals for level teams, per 90 minutes
    home_advantage: float = Field(ge=1)  # home xG multiplier; away is divided by it
    attack_beta: float  # per overall point of (attack - opposing defence)
    midfield_beta: float  # per overall point of (midfield - opposing midfield)
    second_half_share: float = Field(gt=0, lt=1)
    attack_weights: dict[PositionGroup, float]
    defence_weights: dict[PositionGroup, float]
    midfield_weights: dict[PositionGroup, float]
    scorer_weights: dict[PositionGroup, float]
    assist_weights: dict[PositionGroup, float]
    assist_share: float = Field(ge=0, le=1)
    own_goal_share: float = Field(ge=0, le=1)
    penalty_share: float = Field(ge=0, le=1)
    xg_per_shot: float = Field(gt=0)
    on_target_share: float = Field(gt=0, lt=1)
    yellows_per_team: float = Field(ge=0)
    straight_reds_per_team: float = Field(ge=0)
    red_card_own_goals: float  # multiplier on a side's xG while it's a man down
    red_card_opponent_goals: float
    injuries_per_team: float = Field(ge=0)
    chasing_own_goals: float  # trailing side after chasing_minute
    chasing_opponent_goals: float
    chasing_minute: int
    easing_lead: int = Field(ge=1)  # a side this many goals up eases off...
    easing_own_goals: float = Field(gt=0, le=1)  # ...scoring at this fraction of its rate
    subs_per_team: int = Field(ge=0, le=5)
    instructions: dict[str, dict[str, InstructionEffect]] = {}

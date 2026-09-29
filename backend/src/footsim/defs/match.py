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


class PresentationDef(DefModel):
    """How a watched match is played back (data/config/match/presentation.yaml). None of it
    changes the match itself: the engine always simulates the full 90 minutes."""

    real_seconds_per_half: float = Field(gt=0)  # a 45-minute half at 1x takes this long
    speeds: list[float]
    default_speed: float
    max_frames_per_second: int = Field(gt=0)
    lookahead_seconds: float = Field(ge=0)  # real seconds simulated ahead of what's shown
    highlight_before: float = Field(ge=0)  # game seconds shown before a highlight
    highlight_after: float = Field(ge=0)

    @model_validator(mode="after")
    def _default_speed_offered(self) -> "PresentationDef":
        if self.default_speed not in self.speeds:
            raise ValueError("default_speed must be one of speeds")
        return self


class RestartTiming(DefModel):
    setup: tuple[float, float]  # match seconds from the award to the earliest kick
    max_setup: float = Field(gt=0)  # taken by then, even if players are still arriving

    @model_validator(mode="after")
    def _ordered(self) -> "RestartTiming":
        low, high = self.setup
        if not 0 <= low <= high <= self.max_setup:
            raise ValueError("need 0 <= setup low <= setup high <= max_setup")
        return self


RESTART_KINDS = ("throw_in", "long_throw", "goal_kick", "corner", "free_kick",
                 "dangerous_free_kick", "quick_free_kick", "offside", "penalty", "kickoff",
                 "kickoff_after_goal")


class RestartsDef(DefModel):
    """Dead-ball restarts in the agent engine (data/config/match/restarts.yaml)."""

    ball_out: float = Field(ge=0)
    timing: dict[str, RestartTiming]
    quick_free_kick_chance: float = Field(ge=0, le=1)
    corner_attackers: int = Field(ge=1, le=9)
    min_corner_attackers: int = Field(ge=0, le=9)
    long_throw_range: float = Field(gt=0)
    long_throw_strength: float = Field(ge=1, le=99)
    late_minute: int = Field(ge=0, le=120)
    time_wasting: float = Field(gt=0)
    hurry: float = Field(gt=0)
    time_wasting_allowance: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def _all_kinds(self) -> "RestartsDef":
        missing = set(RESTART_KINDS) - set(self.timing)
        if missing:
            raise ValueError(f"restart timing missing for {sorted(missing)}")
        return self


class YellowCardDef(DefModel):
    base: float = Field(ge=0, le=1)
    sliding: float = Field(ge=0, le=1)
    aggressive: float = Field(ge=0, le=1)
    from_behind: float = Field(ge=0, le=1)
    tactical: float = Field(ge=0, le=1)


class RedCardDef(DefModel):
    base: float = Field(ge=0, le=1)
    reckless: float = Field(ge=0, le=1)


class DuelsDef(DefModel):
    """Tackles, take-ons, fouls and cards in the agent engine (data/config/match/duels.yaml)."""

    engage_radius: float = Field(gt=0)
    reaction: tuple[float, float]
    tackle_rate: float = Field(ge=0)
    pressing_commitment: dict[str, float]
    careful_in_own_box: float = Field(ge=0, le=1)
    box_foul_scale: float = Field(ge=0, le=1)
    touchline_knock_out: float = Field(ge=0, le=1)
    tackle_cooldown: float = Field(ge=0)
    beaten_recovery: float = Field(ge=0)
    take_on_cooldown: float = Field(ge=0)
    contact_radius: float = Field(gt=0)
    take_on_speed: float = Field(ge=0)
    take_on_appetite: float = Field(ge=0, le=1)
    tackle_edge: float
    take_on_edge: float
    keep_after_tackle: tuple[float, float]
    foul_chance: float = Field(ge=0, le=1)
    aerial_foul_chance: float = Field(ge=0, le=1)
    tactical_foul_chance: float = Field(ge=0, le=1)
    booked_caution: float = Field(ge=0, le=1)
    yellow: YellowCardDef
    red: RedCardDef


class PassExecutionDef(DefModel):
    base: float = Field(ge=0)
    skill: float = Field(ge=0)
    pressure: float = Field(ge=0)
    fatigue: float = Field(ge=0)
    per_metre: float = Field(ge=0)
    lofted: float = Field(ge=0)
    length_skill: float = Field(ge=0)
    length_per_metre: float = Field(ge=0)


class ControlDef(DefModel):
    receiver: float = Field(ge=0, le=1)
    teammate: float = Field(ge=0, le=1)
    pressure_radius: float = Field(gt=0)
    pressure_penalty: float = Field(ge=0, le=1)
    heavy_touch_speed: tuple[float, float]


class PassingDef(DefModel):
    """Passing, first touch and clearances (data/config/match/passing.yaml)."""

    execution: PassExecutionDef
    control: ControlDef
    clearance_wide_share: float = Field(ge=0, le=1)
    target_area: float = Field(gt=0)
    aerial_contest_radius: float = Field(gt=0)
    header_to_feet: float = Field(ge=0, le=1)


class MentalityEffect(DefModel):
    push: float
    shoot_preference: float


class PressingEffect(DefModel):
    trigger: float = Field(gt=0)
    pressers: int = Field(ge=1, le=4)
    fatigue: float = Field(gt=0)


class LineEffect(DefModel):
    height: float = Field(gt=0)
    span: float = Field(gt=0)


class WidthEffect(DefModel):
    width: float = Field(gt=0, le=68)


class TempoEffect(DefModel):
    hold: float = Field(gt=0)
    hurry: float
    care: float


class PassingEffect(DefModel):
    directness: float


class TransitionDef(DefModel):
    reaction: tuple[float, float]
    counter_hold: float = Field(gt=0)
    counter_window: float = Field(gt=0)


class ManagerDef(DefModel):
    """How a computer-controlled side's manager reads the match (match/engine/manager.py)."""

    review_every: float = Field(gt=0)
    sample_every: float = Field(gt=0)
    memory: float = Field(gt=0)
    min_samples: int = Field(ge=1)
    late: int = Field(ge=1)
    very_late: int = Field(ge=1)
    protect_from: int = Field(ge=1)
    high_line: float = Field(gt=0)
    press_zone: float = Field(gt=0)
    press_radius: float = Field(gt=0)
    high_press: float = Field(gt=0)


class TacticsDef(DefModel):
    """What each team instruction does in the agent engine (data/config/match/tactics.yaml).
    Keys are the instruction levels in match/instructions/team.yaml."""

    mentality: dict[str, MentalityEffect]
    pressing: dict[str, PressingEffect]
    line: dict[str, LineEffect]
    width: dict[str, WidthEffect]
    tempo: dict[str, TempoEffect]
    passing: dict[str, PassingEffect]
    transition: TransitionDef
    manager: ManagerDef


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

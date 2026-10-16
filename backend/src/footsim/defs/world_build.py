"""Rules for filling values the source data doesn't have when building a world
(data/config/world_build.yaml): hidden potential, physique, personality, contracts,
reputation."""

from pydantic import Field, model_validator

from footsim.defs.common import AttributeDeltas, DefModel


class PotentialRules(DefModel):
    # Mean expected improvement in overall by age at the season start. Missing ages above the
    # table get 0; ages below its youngest entry get the youngest entry's value.
    growth_by_age: dict[int, float]
    sd_ratio: float = Field(ge=0)
    sd_floor: float = Field(ge=0)
    headroom_share: float = Field(gt=0, le=1)  # max share of (99 - overall) a player can grow
    elite_threshold: float
    elite_compression: float = Field(gt=0, le=1)
    max_potential: int = Field(ge=1, le=99)


class PhysiqueRules(DefModel):
    height_by_position: dict[str, float]
    height_sd: float
    attribute_reference: float
    height_per_point: AttributeDeltas = {}  # outfield players only
    height_range: tuple[int, int]
    bmi_mean: float
    bmi_sd: float
    bmi_per_strength_point: float
    weight_range: tuple[int, int]


class TraitDistribution(DefModel):
    mean: float
    sd: float


class PersonalityRules(DefModel):
    default: TraitDistribution
    overrides: dict[str, TraitDistribution] = {}
    overall_reference: float
    overall_effect_per_point: dict[str, float] = {}


class ContractBand(DefModel):
    max_age: int
    min_years: int = Field(ge=1)
    max_years: int = Field(ge=1)

    @model_validator(mode="after")
    def _ordered(self) -> "ContractBand":
        if self.max_years < self.min_years:
            raise ValueError("max_years < min_years")
        return self


class ContractRules(DefModel):
    remaining_years: list[ContractBand]


class ReputationRules(DefModel):
    club_top_players: int = Field(ge=1)
    club_reference_overall: float
    club_base: float
    club_per_point: float
    player_reference_overall: float
    player_per_point: float
    player_club_weight: float


class EloRules(DefModel):
    """Club Elo from Transfermarkt's games (World Football Elo's way; the step for a bigger win
    is its formula, in code)."""

    since: str  # the first day of games counted (ISO)
    k: float = Field(gt=0)
    home: float  # home advantage, in rating points
    scale: float = Field(gt=0)  # the rating gap that makes a side ten times as likely to win
    start: float  # a new club's rating
    min_games: int = Field(ge=1)  # an Elo from fewer games stands for nothing
    fc27_min_games: int = Field(ge=1)  # for FC 27's clubs, which the slope is fitted on


class GeneratedAgeRules(DefModel):
    mean: float
    sd: float = Field(gt=0)
    min: float
    max: float


class ForeignRules(DefModel):
    """How many of a generated squad's players are foreign, and from where."""

    default_share: float = Field(ge=0, le=1)
    share: dict[str, float] = {}  # by nation code
    neighbours: dict[str, list[str]] = {}  # by nation code: where its foreigners come from first
    travellers: list[str]  # everyone's: the countries whose players move most


class NewLeagueRules(DefModel):
    """The squads of the leagues FC 27 doesn't cover (importers/synthetic.py, W7 A6)."""

    squad_size: int = Field(ge=11)
    level_players: int = Field(ge=1)  # a club's level is the mean overall of its best this many
    # a generated squad's positions by depth: a first eleven, then the cover
    squad_shape: list[str]
    # each player's overall about the club's level, in squad_shape's order
    spread: list[float]
    noise_sd: float = Field(ge=0)  # a generated player's overall about his place in the spread
    template_pool: int = Field(ge=1)  # his attributes: one of the FC 27 players this near him
    age: GeneratedAgeRules
    foreign: ForeignRules
    elo: EloRules
    unrated_gap: float  # a club without a rated Elo starts this far below its league's lowest
    unrated_span: float  # ... and the unrated spread this far over last season's table
    max_real_players: int = Field(ge=1)  # the most of a club's real players taken
    min_valued: int = Field(ge=1)  # real players with values needed to shift them onto a level
    unvalued_below: float  # a real player with no value sits this far below his club's level
    min_real_for_tm: int = Field(ge=1)  # a squad with this many real players counts as "tm"


class WorldBuildRules(DefModel):
    potential: PotentialRules
    physique: PhysiqueRules
    personality: PersonalityRules
    contracts: ContractRules
    reputation: ReputationRules
    new_leagues: NewLeagueRules

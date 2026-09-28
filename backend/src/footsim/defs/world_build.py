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


class WorldBuildRules(DefModel):
    potential: PotentialRules
    physique: PhysiqueRules
    personality: PersonalityRules
    contracts: ContractRules
    reputation: ReputationRules

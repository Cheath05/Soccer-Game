"""Positions, position groups and their base attribute weights (data/config/positions.yaml)."""

from enum import StrEnum
from typing import Annotated

from pydantic import Field, model_validator

from footsim.defs.common import AttributeWeights, DefModel


class PositionGroup(StrEnum):
    GK = "GK"
    CB = "CB"
    FB = "FB"
    DM = "DM"
    CM = "CM"
    AM = "AM"
    W = "W"
    ST = "ST"


class Side(StrEnum):
    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"


Familiarity = Annotated[int, Field(ge=0, le=20)]


class PositionDef(DefModel):
    code: str
    name: str
    group: PositionGroup
    side: Side


class PositionGroupDef(DefModel):
    group: PositionGroup
    weights: AttributeWeights


class AdjacencyDef(DefModel):
    """Familiarity a player gets in ``to`` for being natural in ``from_``."""

    from_: str = Field(alias="from")
    to: str
    familiarity: Familiarity


class PositionsFile(DefModel):
    positions: list[PositionDef]
    groups: list[PositionGroupDef]
    adjacency: list[AdjacencyDef] = []

    @model_validator(mode="after")
    def _consistent(self) -> "PositionsFile":
        codes = [p.code for p in self.positions]
        if len(codes) != len(set(codes)):
            raise ValueError("duplicate position codes")
        groups = [g.group for g in self.groups]
        if sorted(groups) != sorted(set(PositionGroup)):
            raise ValueError("every position group needs exactly one weights entry")
        for adj in self.adjacency:
            for code in (adj.from_, adj.to):
                if code not in codes:
                    raise ValueError(f"adjacency references unknown position {code!r}")
        return self

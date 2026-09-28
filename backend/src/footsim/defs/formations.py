"""Formations: spatial structure per tactical phase (data/config/formations/*.yaml)."""

from enum import StrEnum

from pydantic import model_validator

from footsim.defs.common import DefModel, Offset, Point


class Phase(StrEnum):
    """Phases that change a team's shape. Transitions blend between these."""

    BUILD_UP = "build_up"
    PROGRESSION = "progression"
    FINAL_THIRD = "final_third"
    DEF_HIGH = "def_high"
    DEF_MID = "def_mid"
    DEF_LOW = "def_low"


class SlotDef(DefModel):
    id: str
    position: str
    default_role: str
    base: Point
    phase_offsets: dict[Phase, Offset] = {}


class RelationshipDef(DefModel):
    type: str
    slots: list[str]


class FormationDef(DefModel):
    key: str
    name: str
    description: str = ""
    slots: list[SlotDef]
    relationships: list[RelationshipDef] = []

    @model_validator(mode="after")
    def _shape(self) -> "FormationDef":
        if len(self.slots) != 11:
            raise ValueError(f"{self.key}: a formation needs 11 slots, got {len(self.slots)}")
        ids = [s.id for s in self.slots]
        if len(ids) != len(set(ids)):
            raise ValueError(f"{self.key}: duplicate slot ids")
        if sum(1 for s in self.slots if s.position == "GK") != 1:
            raise ValueError(f"{self.key}: exactly one GK slot required")
        for rel in self.relationships:
            missing = set(rel.slots) - set(ids)
            if missing:
                raise ValueError(f"{self.key}: relationship references unknown slots {missing}")
        return self

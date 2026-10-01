"""How a player's overall is made (data/config/overall.yaml): see ratings/overall.py."""

from pydantic import Field, model_validator

from footsim.defs.common import DefModel
from footsim.defs.positions import PositionGroup


class OverallDef(DefModel):
    face_blend: float = Field(ge=0, le=1)  # share of the overall from the six headline ratings
    face_weights: dict[PositionGroup, dict[str, float]]  # per position group: headline -> weight

    @model_validator(mode="after")
    def _complete(self) -> "OverallDef":
        missing = set(PositionGroup) - set(self.face_weights)
        if missing:
            raise ValueError(f"face_weights lacks {sorted(missing)}")
        for group, weights in self.face_weights.items():
            if any(w < 0 for w in weights.values()) or abs(sum(weights.values()) - 1) > 1e-6:
                raise ValueError(f"face_weights {group}: weights must be >= 0 and add up to 1")
        return self

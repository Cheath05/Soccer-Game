"""Everything the simulation needs besides the save database, loaded once per process."""

from dataclasses import dataclass
from functools import cache

from footsim.core.paths import config_dir
from footsim.defs.loader import GameDefinitions, load_definitions
from footsim.match.quick import QuickEngine
from footsim.match.teams import LineupPicker
from footsim.ratings.overall import RatingModel, load_overall_scaling

AI_FORMATIONS = ["4-3-3", "4-2-3-1", "4-4-2"]


@dataclass(frozen=True)
class World:
    defs: GameDefinitions
    model: RatingModel
    picker: LineupPicker
    quick: QuickEngine


def default_instructions(defs: GameDefinitions) -> dict[str, str]:
    return {key: d.default for key, d in defs.instructions.items()}


@cache
def get_world() -> World:
    defs = load_definitions()
    model = RatingModel.build(
        defs, load_overall_scaling(config_dir() / "calibration" / "overall_scaling.yaml")
    )
    return World(defs=defs, model=model, picker=LineupPicker(defs, model), quick=QuickEngine(defs))

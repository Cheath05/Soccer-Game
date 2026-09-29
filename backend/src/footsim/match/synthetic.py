"""Synthetic squads for tests and engine calibration.

Players are built from the position groups' attribute weightings: the attributes that matter
for a position sit around the requested quality, the rest lower, with a little noise. That
makes believable teams of any strength without the EA ratings file, so the match engine can
be tested and calibrated anywhere.
"""

import numpy as np

from footsim.defs.formations import FormationDef
from footsim.defs.loader import GameDefinitions
from footsim.defs.positions import PositionGroup
from footsim.domain.attributes import ATTRIBUTE_GROUP, ATTRIBUTES, AttrGroup
from footsim.match.teams import LineupPicker, SquadPlayer, TeamSheet

# A 24-player squad: primary position and head count.
SQUAD_SHAPE: tuple[tuple[str, int], ...] = (
    ("GK", 2), ("CB", 4), ("LB", 2), ("RB", 2), ("DM", 2), ("CM", 4), ("AM", 1),
    ("LW", 2), ("RW", 2), ("ST", 3),
)
_HEIGHT = {"GK": 190, "CB": 188, "LB": 177, "RB": 177, "DM": 182, "CM": 179, "AM": 176,
           "LW": 175, "RW": 175, "ST": 184}


def synthetic_player(defs: GameDefinitions, player_id: int, position: str, quality: float,
                     rng: np.random.Generator) -> SquadPlayer:
    group = defs.positions[position].group
    weights = defs.group_weights[group]
    top = max(weights.values())
    level = quality - 7  # the overall scaling lifts weighted attributes by about this much
    values = np.empty(len(ATTRIBUTES))
    for i, name in enumerate(ATTRIBUTES):
        kind = ATTRIBUTE_GROUP[name]
        if group is PositionGroup.GK:
            if kind is AttrGroup.GOALKEEPING:
                base = level + 2
            elif name in weights:
                base = level - 5
            elif kind in (AttrGroup.TECHNICAL, AttrGroup.DEFENSIVE):
                base = level - 30
            else:
                base = level - 15
        elif kind is AttrGroup.GOALKEEPING:
            base = 12
        elif name in weights:
            base = level + 2 + 8 * weights[name] / top
        else:
            base = level - 10
        values[i] = base + rng.normal(0, 4)
    attrs = np.clip(np.round(values), 1, 99)
    familiarity = {position: 20}
    for adj in defs.adjacency:
        if adj.from_ == position:
            familiarity[adj.to] = adj.familiarity
    return SquadPlayer(
        player_id=player_id, name=f"Player {player_id}", short_name=f"P{player_id}",
        primary_position=position, positions=familiarity, attrs=attrs,
        height_cm=_HEIGHT[position] + int(rng.integers(-4, 5)),
    )


def synthetic_squad(defs: GameDefinitions, club_id: int, quality: float,
                    seed: int = 0) -> list[SquadPlayer]:
    """24 players whose key attributes sit around ``quality`` (roughly their overall)."""
    rng = np.random.default_rng([club_id, seed])
    squad = []
    number = 0
    for position, count in SQUAD_SHAPE:
        for _ in range(count):
            number += 1
            squad.append(synthetic_player(defs, club_id * 100 + number, position, quality, rng))
    return squad


def synthetic_sheet(defs: GameDefinitions, picker: LineupPicker, club_id: int, quality: float,
                    formation: str = "4-3-3", instructions: dict[str, str] | None = None,
                    seed: int = 0) -> TeamSheet:
    squad = synthetic_squad(defs, club_id, quality, seed)
    base = {key: d.default for key, d in defs.instructions.items()}
    shape: FormationDef = defs.formations[formation]
    return picker.pick(club_id, f"Club {club_id}", squad, shape,
                       instructions={**base, **(instructions or {})})

"""Team sheets: who plays where, and how good they are in that slot.

Both match engines take two TeamSheets. A player's slot rating is his role overall for the
slot's role, times his familiarity with the slot's position, times a condition factor.
"""

import math
from dataclasses import dataclass, field

import numpy as np
import numpy.typing as npt
from scipy.optimize import linear_sum_assignment

from footsim.defs.formations import FormationDef
from footsim.defs.loader import GameDefinitions
from footsim.defs.positions import PositionGroup
from footsim.domain.attributes import ATTR_INDEX
from footsim.ratings.overall import RatingModel, familiarity_factor

BENCH_SIZE = 9


def condition_factor(condition: float) -> float:
    return 0.7 + 0.3 * math.sqrt(max(0.0, min(100.0, condition)) / 100.0)


@dataclass
class SquadPlayer:
    player_id: int
    name: str
    short_name: str
    primary_position: str
    positions: dict[str, int]  # position -> familiarity 0-20
    attrs: npt.NDArray[np.float64]  # canonical attribute vector
    condition: float = 100.0
    available: bool = True
    height_cm: int = 180
    preferred_foot: str = "right"
    weak_foot: int = 3
    age: int = 25

    def attr(self, name: str) -> float:
        return float(self.attrs[ATTR_INDEX[name]])


@dataclass
class SheetPlayer:
    player: SquadPlayer
    number: int
    slot: str | None  # None on the bench
    position: str
    group: PositionGroup
    role: str
    rating: float

    @property
    def player_id(self) -> int:
        return self.player.player_id


@dataclass
class TeamSheet:
    club_id: int
    name: str
    formation: FormationDef
    roles: dict[str, str]
    starters: list[SheetPlayer]
    bench: list[SheetPlayer]
    instructions: dict[str, str] = field(default_factory=dict)

    def instruction(self, key: str, default: str = "normal") -> str:
        return self.instructions.get(key, default)


class LineupPicker:
    """Assigns players to formation slots, maximising the sum of slot ratings."""

    def __init__(self, defs: GameDefinitions, model: RatingModel) -> None:
        self.defs = defs
        self.model = model

    def slot_rating(self, p: SquadPlayer, position: str, role: str,
                    role_overalls: npt.NDArray[np.float64] | None = None) -> float:
        overalls = role_overalls if role_overalls is not None else self.model.role_overalls(p.attrs)
        base = float(overalls[self.model.role_index(role)])
        return base * familiarity_factor(p.positions.get(position, 0)) * condition_factor(
            p.condition
        )

    def pick(
        self,
        club_id: int,
        name: str,
        squad: list[SquadPlayer],
        formation: FormationDef,
        roles: dict[str, str] | None = None,
        fixed: dict[str, int] | None = None,
        instructions: dict[str, str] | None = None,
    ) -> TeamSheet:
        roles = {s.id: (roles or {}).get(s.id, s.default_role) for s in formation.slots}
        available = [p for p in squad if p.available] or list(squad)
        if len(available) < 11:  # emergency: play unavailable players rather than forfeit
            available += [p for p in squad if p not in available][: 11 - len(available)]
        overalls = self.model.role_overalls(np.stack([p.attrs for p in available]))

        slots = formation.slots
        score = np.zeros((len(available), len(slots)))
        for i, p in enumerate(available):
            for j, slot in enumerate(slots):
                score[i, j] = self.slot_rating(p, slot.position, roles[slot.id], overalls[i])

        # Honour manually fixed slots where that player is available.
        by_id = {p.player_id: i for i, p in enumerate(available)}
        slot_index = {s.id: k for k, s in enumerate(slots)}
        for slot_id, player_id in (fixed or {}).items():
            if slot_id in slot_index and player_id in by_id:
                score[by_id[player_id], slot_index[slot_id]] = 1e6

        rows, cols = linear_sum_assignment(-score)
        chosen = {int(r) for r in rows}
        starters = []
        for row, col in zip(rows.tolist(), cols.tolist(), strict=True):
            slot = slots[col]
            starters.append(SheetPlayer(
                player=available[row], number=0, slot=slot.id, position=slot.position,
                group=self.defs.positions[slot.position].group, role=roles[slot.id],
                rating=float(min(score[row, col], 99.0)),
            ))
        starters.sort(key=lambda sp: [s.id for s in slots].index(sp.slot or ""))

        best = overalls.max(axis=1)
        rest = sorted((i for i in range(len(available)) if i not in chosen),
                      key=lambda i: -best[i])
        bench_idx = rest[:BENCH_SIZE]
        keepers = [i for i in rest if available[i].primary_position == "GK"]
        if keepers and not any(available[i].primary_position == "GK" for i in bench_idx):
            bench_idx = [*bench_idx[: BENCH_SIZE - 1], keepers[0]]
        bench = []
        for i in bench_idx:
            p = available[i]
            pos = p.primary_position
            bench.append(SheetPlayer(
                player=p, number=0, slot=None, position=pos,
                group=self.defs.positions[pos].group,
                role=self.defs.roles_for(self.defs.positions[pos].group)[0].key,
                rating=float(best[i]),
            ))
        sheet = TeamSheet(club_id, name, formation, roles, starters, bench, instructions or {})
        _number(sheet)
        return sheet

    def best_formation(self, club_id: int, name: str, squad: list[SquadPlayer],
                       keys: list[str]) -> str:
        """The formation whose best XI rates highest (used by AI clubs)."""
        totals = {}
        for key in keys:
            sheet = self.pick(club_id, name, squad, self.defs.formations[key])
            totals[key] = sum(sp.rating for sp in sheet.starters)
        return max(totals, key=lambda k: totals[k])


_GROUP_ORDER = list(PositionGroup)


# Traditional numbers by position, most preferred first.
_PREFERRED_NUMBERS = {
    "GK": [1], "RB": [2], "RWB": [2], "LB": [3], "LWB": [3], "CB": [5, 4, 6],
    "DM": [6, 4], "CM": [8, 4, 16], "AM": [10, 8], "RM": [7], "LM": [11],
    "RW": [7], "LW": [11], "ST": [9, 10, 19],
}


def _number(sheet: TeamSheet) -> None:
    """Shirt numbers: traditional numbers for the starters where free, then the rest."""
    used: set[int] = set()
    starters = sorted(sheet.starters, key=lambda s: _GROUP_ORDER.index(s.group))
    for sp in starters:
        free = [n for n in _PREFERRED_NUMBERS.get(sp.position, []) if n not in used]
        if free:
            sp.number = free[0]
            used.add(sp.number)
    for sp in [*starters, *sheet.bench]:
        if sp.number == 0:
            sp.number = next(n for n in range(2 if sp.group is not PositionGroup.GK else 1, 100)
                             if n not in used)
            used.add(sp.number)

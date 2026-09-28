"""Canonical player attribute model.

Every system (importers, ratings, match engine, development) refers to attributes by these
keys. Values are integers on a 1-99 scale. The order of ``ATTRIBUTES`` is the column order
used for NumPy attribute matrices, so append new attributes rather than reordering.
"""

from enum import StrEnum


class AttrGroup(StrEnum):
    PHYSICAL = "physical"
    TECHNICAL = "technical"
    MENTAL = "mental"
    DEFENSIVE = "defensive"
    GOALKEEPING = "goalkeeping"


_GROUPED: dict[AttrGroup, tuple[str, ...]] = {
    AttrGroup.PHYSICAL: (
        "acceleration",
        "sprint_speed",
        "agility",
        "balance",
        "strength",
        "stamina",
        "jumping",
        "natural_fitness",
    ),
    AttrGroup.TECHNICAL: (
        "first_touch",
        "dribbling",
        "short_passing",
        "long_passing",
        "crossing",
        "finishing",
        "shot_power",
        "long_shots",
        "volleys",
        "curve",
        "free_kicks",
        "penalties",
        "heading_accuracy",
    ),
    AttrGroup.MENTAL: (
        "vision",
        "composure",
        "reactions",
        "off_ball",
        "anticipation",
        "decisions",
        "concentration",
        "aggression",
        "work_rate",
        "teamwork",
        "bravery",
        "flair",
    ),
    AttrGroup.DEFENSIVE: (
        "marking",
        "def_positioning",
        "interceptions",
        "standing_tackle",
        "sliding_tackle",
    ),
    AttrGroup.GOALKEEPING: (
        "gk_diving",
        "gk_handling",
        "gk_kicking",
        "gk_throwing",
        "gk_positioning",
        "gk_reflexes",
        "gk_one_on_ones",
        "gk_command_of_area",
        "gk_rushing_out",
    ),
}

ATTRIBUTES: tuple[str, ...] = tuple(a for group in _GROUPED.values() for a in group)
ATTRIBUTE_GROUP: dict[str, AttrGroup] = {a: g for g, attrs in _GROUPED.items() for a in attrs}
ATTR_INDEX: dict[str, int] = {a: i for i, a in enumerate(ATTRIBUTES)}

ATTR_MIN = 1
ATTR_MAX = 99


def attributes_in(group: AttrGroup) -> tuple[str, ...]:
    return _GROUPED[group]

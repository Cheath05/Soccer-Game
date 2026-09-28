"""Card-style summary ("face") stats. Display only: nothing in the simulation reads them."""

from collections.abc import Mapping

OUTFIELD_FACE: dict[str, dict[str, float]] = {
    "PAC": {"acceleration": 0.40, "sprint_speed": 0.60},
    "SHO": {"finishing": 0.40, "shot_power": 0.18, "long_shots": 0.17, "off_ball": 0.12,
            "volleys": 0.07, "penalties": 0.06},
    "PAS": {"short_passing": 0.30, "vision": 0.22, "long_passing": 0.18, "crossing": 0.15,
            "curve": 0.10, "free_kicks": 0.05},
    "DRI": {"dribbling": 0.35, "first_touch": 0.28, "agility": 0.15, "balance": 0.10,
            "reactions": 0.07, "composure": 0.05},
    "DEF": {"marking": 0.25, "def_positioning": 0.22, "standing_tackle": 0.20,
            "interceptions": 0.18, "sliding_tackle": 0.10, "heading_accuracy": 0.05},
    "PHY": {"strength": 0.35, "stamina": 0.30, "aggression": 0.20, "jumping": 0.15},
}

GOALKEEPER_FACE: dict[str, dict[str, float]] = {
    "DIV": {"gk_diving": 1.0},
    "HAN": {"gk_handling": 1.0},
    "KIC": {"gk_kicking": 0.7, "gk_throwing": 0.3},
    "REF": {"gk_reflexes": 1.0},
    "SPD": {"acceleration": 0.45, "sprint_speed": 0.55},
    "POS": {"gk_positioning": 0.7, "gk_command_of_area": 0.3},
}


def face_stats(attrs: Mapping[str, float], goalkeeper: bool = False) -> dict[str, int]:
    table = GOALKEEPER_FACE if goalkeeper else OUTFIELD_FACE
    return {
        stat: round(sum(attrs[a] * w for a, w in weights.items()))
        for stat, weights in table.items()
    }

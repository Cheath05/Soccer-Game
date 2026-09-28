"""What the manager can see of hidden values (a first cut of design §18).

Potential is never shown exactly: the visible range narrows as a player gets older (there is
less left to find out) and is wider for players at other clubs. The range's centre carries
a fixed per-player bias, so it's an honest-looking estimate rather than a leak of the truth.
"""

from footsim.core.rng import derive_rng

OWN_CLUB_KNOWLEDGE = 0.8
OTHER_CLUB_KNOWLEDGE = 0.4


def potential_range(true_potential: int, current: float, age: int, knowledge: float,
                    seed: int, player_id: int) -> tuple[int, int]:
    uncertainty = max(1.0, (24 - age) * 1.1) * (1.6 - knowledge)
    bias = float(derive_rng(seed, "scout-bias", player_id).normal(0, uncertainty / 2))
    centre = true_potential + bias
    low = max(round(current), round(centre - uncertainty))
    high = max(low, min(99, round(centre + uncertainty)))
    return low, high


def potential_label(high: int) -> str:
    if high >= 88:
        return "Could become a world-class player"
    if high >= 82:
        return "Could become a top-level player"
    if high >= 75:
        return "Could become a good first-team player"
    if high >= 68:
        return "Should become a decent professional"
    return "Limited potential"

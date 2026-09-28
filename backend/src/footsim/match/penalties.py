"""Penalty kicks and shootouts, shared by both match engines."""

import numpy as np

from footsim.match.teams import SquadPlayer


def penalty_probability(taker: SquadPlayer, keeper: SquadPlayer | None) -> float:
    skill = 0.004 * (taker.attr("penalties") - 70) + 0.002 * (taker.attr("composure") - 70)
    keeping = 0.0
    if keeper is not None:
        keeping = 0.004 * ((keeper.attr("gk_diving") + keeper.attr("gk_reflexes")) / 2 - 70)
    return float(np.clip(0.76 + skill - keeping, 0.55, 0.92))


def shootout(
    home_takers: list[SquadPlayer],
    home_keeper: SquadPlayer | None,
    away_takers: list[SquadPlayer],
    away_keeper: SquadPlayer | None,
    rng: np.random.Generator,
) -> tuple[int, int]:
    """Five kicks each (stopping once decided), then sudden death. Best takers go first."""
    home = sorted(home_takers, key=lambda p: -p.attr("penalties"))
    away = sorted(away_takers, key=lambda p: -p.attr("penalties"))
    scores = [0, 0]
    sides = ((home, away_keeper), (away, home_keeper))
    for kick in range(5):
        for side, (takers, keeper) in enumerate(sides):
            if rng.random() < penalty_probability(takers[kick % len(takers)], keeper):
                scores[side] += 1
            home_left = 4 - kick
            away_left = 5 - kick if side == 0 else 4 - kick
            if scores[0] + home_left < scores[1] or scores[1] + away_left < scores[0]:
                return scores[0], scores[1]
    kick = 5
    while scores[0] == scores[1]:
        for side, (takers, keeper) in enumerate(sides):
            if rng.random() < penalty_probability(takers[kick % len(takers)], keeper):
                scores[side] += 1
        kick += 1
    return scores[0], scores[1]

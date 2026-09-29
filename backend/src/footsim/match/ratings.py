"""Player match ratings (3.5-10, 6.0 is an average game).

A match rating is how well someone played today. It isn't the player's overall (OVR), which
is his long-term ability. The same formula gives the live rating shown while a match is being
watched and the final one in the match report.
"""

from footsim.defs.positions import PositionGroup
from footsim.match.report import PlayerLine

DEFENSIVE_GROUPS = (PositionGroup.GK, PositionGroup.CB, PositionGroup.FB)


def match_rating(line: PlayerLine, group: PositionGroup, result: int, conceded: int,
                 minutes: float) -> float:
    """``result`` is +1/0/-1 for the player's side as things stand; ``minutes`` played so far
    (short appearances are pulled towards 6.0)."""
    rating = 6.0 + 0.3 * result + 1.0 * line.goals + 0.6 * line.assists
    rating += 0.12 * line.shots_on_target + 0.07 * (line.tackles + line.interceptions)
    if line.passes >= 10:
        rating += (line.passes_completed / line.passes - 0.78) * 2.5
    if group in DEFENSIVE_GROUPS:
        rating += 0.5 if conceded == 0 else -0.15 * conceded
    if group is PositionGroup.GK:
        rating += 0.2 * min(line.saves, 6) - 0.15 * conceded
    rating -= 0.3 * line.yellow + 1.5 * line.red
    if minutes < 20:
        rating = 6.0 + (rating - 6.0) * 0.4
    return round(min(10.0, max(3.5, rating)), 1)

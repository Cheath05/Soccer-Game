"""Fit synthetic players' attributes to real ones (`footsim fit-synthetic`).

Synthetic squads (match/synthetic.py) stand in for real ones in tests and in calibration runs
that can't use the EA data. To play like real sides, each of their attributes has to relate to
a player's overall as it does for real players in his position: a centre-back's aggression sits
near his overall, a striker's tackling far below it, a winger's pace above it.

For every position group and attribute this fits a line through the real players of a built
world (attribute = a + b x overall, overall being the group overall the engine uses) and the
spread around it. Only those aggregates are written, to
data/config/calibration/synthetic_attributes.yaml: never a player's ratings.
"""

from datetime import date
from pathlib import Path

import numpy as np
import yaml
from sqlalchemy import text

from footsim.calibration.engine_batch import open_readonly
from footsim.defs.positions import PositionGroup
from footsim.domain.attributes import ATTRIBUTES
from footsim.world.context import World

OVERALL_RANGE = (45.0, 90.0)  # fit on players in the range synthetic sides are made in


def fit_synthetic_attributes(world_path: Path, world: World) -> tuple[
        dict[str, dict[str, list[float]]], dict[str, int]]:
    """``{group: {attribute: [a, b, spread]}}`` and the number of players behind each group."""
    engine = open_readonly(world_path)
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT a.*, (SELECT position FROM player_position pp
                             WHERE pp.player_id = a.player_id
                             ORDER BY familiarity DESC LIMIT 1) AS primary_position
                FROM player_attr a JOIN contract k ON k.person_id = a.player_id
                WHERE k.is_active = 1
            """)).all()
    finally:
        engine.dispose()
    attrs = np.array([[getattr(r, a) for a in ATTRIBUTES] for r in rows], dtype=float)
    overalls = world.model.group_overalls(attrs)
    groups = np.array([world.defs.positions[r.primary_position].group.value for r in rows])
    fits: dict[str, dict[str, list[float]]] = {}
    counts: dict[str, int] = {}
    low, high = OVERALL_RANGE
    for group in PositionGroup:
        mine = groups == group.value
        overall = overalls[group][mine]
        keep = (overall >= low) & (overall <= high)
        x, table = overall[keep], attrs[mine][keep]
        counts[group.value] = int(len(x))
        fits[group.value] = {}
        for j, name in enumerate(ATTRIBUTES):
            slope, intercept = np.polyfit(x, table[:, j], 1)
            spread = float(np.std(table[:, j] - (intercept + slope * x)))
            fits[group.value][name] = [round(float(intercept), 2), round(float(slope), 3),
                                       round(spread, 2)]
    return fits, counts


def write_fits(path: Path, fits: dict[str, dict[str, list[float]]],
               counts: dict[str, int]) -> None:
    header = (
        "# Synthetic players' attributes, fitted to real players (`footsim fit-synthetic`).\n"
        "# Per position group and attribute: [a, b, spread], meaning attribute = a + b x overall\n"
        "# plus normal noise with that spread. Aggregates only: no player's ratings.\n"
        f"# Fitted {date.today().isoformat()} on players with overall "
        f"{OVERALL_RANGE[0]:.0f}-{OVERALL_RANGE[1]:.0f}: "
        + ", ".join(f"{g} {n}" for g, n in counts.items()) + ".\n"
    )
    body = yaml.safe_dump(fits, sort_keys=False, default_flow_style=None, width=100)
    path.write_text(header + body, "utf-8")

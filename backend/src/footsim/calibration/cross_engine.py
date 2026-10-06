"""B2: the fast engine against the agent engine, on the same fixtures.

An agent-engine batch report (``footsim calibrate-engine --division ...``) keeps a row per
match: the clubs, their starting elevens' average rating, the score. This replays each fixture
with the fast engine (cheap, so many times over) and compares the two engines on what a
league table is made of: goals, home wins, draws and away wins, and how much a gap in the
elevens' ratings moves the goal difference (the rating response)."""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from footsim.calibration.engine_batch import MATCH_DAY
from footsim.core.rng import derive_rng
from footsim.match.teams import TeamSheet
from footsim.persistence.database import open_database
from footsim.world.context import AI_FORMATIONS, World
from footsim.world.squads import load_squad, team_sheet


@dataclass(frozen=True)
class Response:
    """Results against the elevens' rating gap (home minus away)."""

    matches: int
    goals: float
    home_win: float
    draw: float
    away_win: float
    home_edge: float  # goal difference at an even rating gap: home advantage
    per_point: float  # goal difference per point of rating gap

    def row(self) -> str:
        return (f"{self.matches:6d} {self.goals:6.2f} {self.home_win:6.3f} {self.draw:6.3f} "
                f"{self.away_win:6.3f} {self.home_edge:+7.3f} {self.per_point:+8.4f}")


def fit_response(gaps: Sequence[float], scores: Sequence[tuple[int, int]]) -> Response:
    """Goal difference = home_edge + per_point * rating gap, by least squares."""
    gap = np.asarray(gaps, dtype=float)
    home = np.array([s[0] for s in scores], dtype=float)
    away = np.array([s[1] for s in scores], dtype=float)
    diff = home - away
    per_point, home_edge = np.polyfit(gap, diff, 1) if len(set(gap.tolist())) > 1 else (0.0, 0.0)
    return Response(matches=len(diff), goals=float(np.mean(home + away)),
                    home_win=float(np.mean(diff > 0)), draw=float(np.mean(diff == 0)),
                    away_win=float(np.mean(diff < 0)), home_edge=float(home_edge),
                    per_point=float(per_point))


def compare_engines(world: World, report: Path, world_db: Path, reps: int,
                    seed: int) -> tuple[Response, Response]:
    """(agent engine, fast engine) on the report's fixtures."""
    rows: list[dict[str, Any]] = json.loads(report.read_text("utf-8"))["matches"]
    rows = [r for r in rows if r["arm"] == "baseline"]
    engine = open_database(world_db)
    sheets: dict[int, TeamSheet] = {}
    with engine.connect() as conn:
        for club in {r[k] for r in rows for k in ("home_club", "away_club")}:
            base = team_sheet(conn, world, club, MATCH_DAY)
            squad = load_squad(conn, club, MATCH_DAY)
            shape = world.picker.best_formation(club, base.name, squad, AI_FORMATIONS)
            sheets[club] = world.picker.pick(club, base.name, squad, world.defs.formations[shape],
                                             instructions=base.instructions)
    engine.dispose()

    def rating(sheet: TeamSheet) -> float:
        return float(np.mean([sp.rating for sp in sheet.starters]))

    agent = fit_response([r["xi_rating"][0] - r["xi_rating"][1] for r in rows],
                         [tuple(r["score"]) for r in rows])
    gaps, scores = [], []
    for r in rows:
        home, away = sheets[r["home_club"]], sheets[r["away_club"]]
        for rep in range(reps):
            played = world.quick.play(home, away, derive_rng(seed, "cross", r["index"], rep))
            gaps.append(rating(home) - rating(away))
            scores.append((played.home_goals, played.away_goals))
    return agent, fit_response(gaps, scores)

"""The agent engine's shot model, fitted to real shots: StatsBomb's open data.

Every StatsBomb shot comes with a freeze frame: where each visible player stood when it was
struck. That is what the engine measures about its own shots (actions.shot_chance), so the
chance model can be fitted to real football directly instead of stacked from guesses:

- the place: distance and the angle the posts make;
- a header or not;
- outfield defenders in the triangle between the ball and the posts (the cone);
- how close the nearest outfield defender is (within 5 m, as defending.yaml's shot_pressure);
- outfield defenders close enough to the shot's line to block it.

``fit`` gives P(goal) for an average shooter against an average keeper. That is the shot's xG,
blocks included, since a blocked shot doesn't score. It also gives the per-blocker chance that
makes the engine's block model match the real share of blocked shots.

The events are downloaded once and cached under ``data/raw/statsbomb`` (never committed).
StatsBomb's open data is free for research with attribution: github.com/statsbomb/open-data.
"""

import json
import math
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import minimize

from footsim.match.engine.pitch import GOAL_HALF, LENGTH, MID_Y, goal_angle

BASE = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"
YARD = 0.9144
PRESSURE_RADIUS = 5.0  # m, as defending.yaml shot_pressure.radius
CONE_MAX = 3
FEATURES = ("intercept", "angle", "distance", "header", "cone", "closeness")


@dataclass(frozen=True)
class Shot:
    x: float  # metres, attacking towards x = LENGTH, goal centre at MID_Y
    y: float
    header: bool
    goal: bool
    blocked: bool
    statsbomb_xg: float
    defenders: tuple[tuple[float, float], ...]  # outfield opponents in the freeze frame

    @property
    def distance(self) -> float:
        return math.hypot(LENGTH - self.x, MID_Y - self.y)


def _metres(location: Sequence[float]) -> tuple[float, float]:
    """StatsBomb's 120 x 80 yard pitch, attacking towards x = 120, to the engine's frame.
    Distances are kept true from the goal (yards to metres), which is what a shot is about."""
    return LENGTH - (120.0 - location[0]) * YARD, MID_Y + (location[1] - 40.0) * YARD


def _get(url: str) -> Any:
    with urllib.request.urlopen(url, timeout=60) as response:  # noqa: S310 (fixed https host)
        return json.loads(response.read())


def download(cache: Path, competition: int, season: int) -> list[dict[str, Any]]:
    """The competition-season's open-play shots, each with its freeze frame (cached)."""
    path = cache / f"shots-{competition}-{season}.json"
    if path.exists():
        cached: list[dict[str, Any]] = json.loads(path.read_text("utf-8"))
        return cached
    cache.mkdir(parents=True, exist_ok=True)
    shots: list[dict[str, Any]] = []
    for match in _get(f"{BASE}/matches/{competition}/{season}.json"):
        for event in _get(f"{BASE}/events/{match['match_id']}.json"):
            if event["type"]["name"] != "Shot" or event["shot"]["type"]["name"] != "Open Play":
                continue
            shot = event["shot"]
            shots.append({
                "location": event["location"],
                "header": shot["body_part"]["name"] == "Head",
                "outcome": shot["outcome"]["name"],
                "statsbomb_xg": shot.get("statsbomb_xg", float("nan")),
                "freeze_frame": [
                    {"location": p["location"], "teammate": p["teammate"],
                     "keeper": p["position"]["name"] == "Goalkeeper"}
                    for p in shot.get("freeze_frame", [])
                ],
            })
    path.write_text(json.dumps(shots), "utf-8")
    return shots


def parse(raw: Sequence[dict[str, Any]]) -> list[Shot]:
    shots = []
    for s in raw:
        x, y = _metres(s["location"])
        if x >= LENGTH:
            continue
        defenders = tuple(_metres(p["location"]) for p in s["freeze_frame"]
                          if not p["teammate"] and not p["keeper"])
        shots.append(Shot(x, y, bool(s["header"]), s["outcome"] == "Goal",
                          s["outcome"] == "Blocked", float(s["statsbomb_xg"]), defenders))
    return shots


def cone_count(x: float, y: float, pts: np.ndarray) -> int:
    """Outfield defenders inside the triangle between the ball and the posts (+0.5 m), as
    actions._defenders_in_cone counts them."""
    if not len(pts):
        return 0
    share = (pts[:, 0] - x) / max(LENGTH - x, 0.1)
    low = y + share * (MID_Y - GOAL_HALF - y)
    high = y + share * (MID_Y + GOAL_HALF - y)
    inside = (np.minimum(low, high) - 0.5 <= pts[:, 1]) & (pts[:, 1] <= np.maximum(low, high) + 0.5)
    return int(np.sum((pts[:, 0] > x) & inside))


def in_line(x: float, y: float, pts: np.ndarray, reach: float, near: float = 0.8,
            far: float = 14.0) -> int:
    """Outfield defenders close enough to the shot's line to block it (actions.shot_chance)."""
    if not len(pts):
        return 0
    distance = math.hypot(LENGTH - x, MID_Y - y)
    goal_dir = np.array([LENGTH - x, MID_Y - y]) / max(distance, 1e-6)
    rel = pts - np.array([x, y])
    along = rel @ goal_dir
    perp = np.abs(rel[:, 0] * goal_dir[1] - rel[:, 1] * goal_dir[0])
    return int(np.sum((along > near) & (along < min(distance, far)) & (perp < reach)))


def features(shots: Sequence[Shot]) -> np.ndarray:
    rows = []
    for s in shots:
        pts = np.array(s.defenders) if s.defenders else np.zeros((0, 2))
        nearest = float(np.min(np.hypot(pts[:, 0] - s.x, pts[:, 1] - s.y))) if len(pts) else 99.0
        closeness = max(0.0, (PRESSURE_RADIUS - nearest) / PRESSURE_RADIUS)
        rows.append([1.0, goal_angle(s.x, s.y), s.distance, float(s.header),
                     float(min(cone_count(s.x, s.y, pts), CONE_MAX)), closeness])
    return np.array(rows)


def _logistic_fit(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Maximum-likelihood logistic regression: coefficients and their standard errors."""

    def loss(beta: np.ndarray) -> tuple[float, np.ndarray]:
        z = x @ beta
        p = 1.0 / (1.0 + np.exp(-z))
        nll = float(np.sum(np.logaddexp(0.0, z) - y * z))
        return nll, x.T @ (p - y)

    result = minimize(loss, np.zeros(x.shape[1]), jac=True, method="BFGS")
    beta = result.x
    p = 1.0 / (1.0 + np.exp(-(x @ beta)))
    hessian = x.T @ (x * (p * (1 - p))[:, None])
    se = np.sqrt(np.diag(np.linalg.inv(hessian)))
    return beta, se


def block_chance(shots: Sequence[Shot], reach: float, chance: float, cap: float) -> np.ndarray:
    """The engine's block model at reference ratings: each defender in the line blocks with
    ``chance``, independently, up to ``cap``."""
    out = []
    for s in shots:
        pts = np.array(s.defenders) if s.defenders else np.zeros((0, 2))
        n = in_line(s.x, s.y, pts, reach)
        out.append(min(cap, 1.0 - (1.0 - chance) ** n))
    return np.array(out)


def fit_blocks(shots: Sequence[Shot], reach: float, cap: float) -> float:
    """The per-blocker chance that makes predicted blocks add up to the real blocked share."""
    blocked = np.array([s.blocked for s in shots], dtype=float)
    low, high = 0.0, 1.0
    for _ in range(40):
        mid = (low + high) / 2
        if block_chance(shots, reach, mid, cap).mean() < blocked.mean():
            low = mid
        else:
            high = mid
    return (low + high) / 2


def report(shots: Sequence[Shot], beta: np.ndarray, se: np.ndarray, reach: float,
           chance: float, cap: float) -> str:
    x = features(shots)
    p = 1.0 / (1.0 + np.exp(-(x @ beta)))
    goals = np.array([s.goal for s in shots], dtype=float)
    blocked = np.array([s.blocked for s in shots], dtype=float)
    sb = np.array([s.statsbomb_xg for s in shots])
    predicted_blocks = block_chance(shots, reach, chance, cap)
    lines = [f"{len(shots)} open-play shots, {goals.mean():.3f} scored, {blocked.mean():.3f} "
             f"blocked, mean StatsBomb xG {np.nanmean(sb):.3f}, fitted {p.mean():.3f}", "",
             "| Term | Coefficient | SE |", "|---|---|---|"]
    lines += [f"| {name} | {b:+.4f} | {e:.4f} |" for name, b, e in zip(FEATURES, beta, se,
                                                                       strict=True)]
    lines += ["", f"Blocks: reach {reach} m, per-blocker chance {chance:.3f} (cap {cap}).", "",
              "| Distance | Shots | Share | Scored | Fitted | StatsBomb xG | Blocked | "
              "Model blocks | Mean cone | Mean closeness |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    distance = x[:, 2]
    for lo, hi in ((0, 8), (8, 12), (12, 16.5), (16.5, 20), (20, 25), (25, 40)):
        m = (distance >= lo) & (distance < hi)
        if m.any():
            lines.append(
                f"| {lo}-{hi} m | {int(m.sum())} | {m.mean():.3f} | {goals[m].mean():.3f} | "
                f"{p[m].mean():.3f} | {np.nanmean(sb[m]):.3f} | {blocked[m].mean():.3f} | "
                f"{predicted_blocks[m].mean():.3f} | {x[m, 4].mean():.2f} | {x[m, 5].mean():.2f} |")
    outside = distance >= 16.5
    lines += ["", f"From 16.5 m or more: {outside.mean():.3f} of shots, xG {p[outside].mean():.3f};"
              f" closer: xG {p[~outside].mean():.3f}.",
              "Fitted xG percentiles (5/10/25/50): "
              + " / ".join(f"{np.percentile(p, q):.3f}" for q in (5, 10, 25, 50))]
    return "\n".join(lines)


def fit(cache: Path, competitions: Sequence[tuple[int, int]], reach: float = 0.9,
        cap: float = 0.65) -> str:
    shots: list[Shot] = []
    for competition, season in competitions:
        shots += parse(download(cache, competition, season))
    x = features(shots)
    y = np.array([s.goal for s in shots], dtype=float)
    beta, se = _logistic_fit(x, y)
    chance = fit_blocks(shots, reach, cap)
    return report(shots, beta, se, reach, chance, cap)

"""How much a rating advantage shows in a batch's matches (the draws investigation, 17 Oct).

For each team-match, its XI rating minus its opponent's against what it did: the slope per point
of that advantage, with its 95% interval. Real football's, from FC 27's elevens against
football-data's 2025-26 results (Premier League): goal difference +0.176 a point (so +0.088
for each side), shots +0.57 a side, shots on target +0.20 a side; conversion +0.28 points of its
own shots and -0.15 of its opponents'."""

import json
import math
from pathlib import Path
from typing import Any

import numpy as np

REAL = {"goals": 0.088, "shots": 0.57, "shots_on_target": 0.20}


def _rows(report: Path) -> list[dict[str, Any]]:
    data = json.loads(report.read_text("utf-8"))
    first = next(iter(data["arms"]))
    rows = []
    for m in data["matches"]:
        if m["arm"] != first:
            continue
        for t in (0, 1):
            row: dict[str, Any] = {
                "advantage": m["xi_rating"][t] - m["xi_rating"][1 - t],
                "goals": m["score"][t], "shots": m["shots"][t], "xg": m["xg"][t]}
            for key, values in m.items():
                if isinstance(values, list) and len(values) == 2 and key not in (
                        "score", "xi_rating", "shots", "xg"):
                    row[key] = values[t]
            if row.get("passes"):
                row["pass_accuracy"] = row["passes_completed"] / row["passes"]
            if row["shots"]:
                row["xg_per_shot"] = row["xg"] / row["shots"]
            rows.append(row)
    return rows


def responses(report: Path) -> dict[str, tuple[float, float, float]]:
    """Each measurement's slope per point of XI advantage, its 95% half-width, and its mean."""
    rows = _rows(report)
    gap = np.array([r["advantage"] for r in rows], dtype=float)
    out = {}
    for key in rows[0]:
        if key == "advantage":
            continue
        values = np.array([r.get(key, math.nan) for r in rows], dtype=float)
        ok = ~np.isnan(values)
        if ok.sum() < 10 or gap[ok].std() == 0:
            continue
        slope, intercept = np.polyfit(gap[ok], values[ok], 1)
        resid = values[ok] - (intercept + slope * gap[ok])
        half = 1.96 * resid.std(ddof=2) / (gap[ok].std() * math.sqrt(ok.sum()))
        out[key] = (float(slope), float(half), float(values[ok].mean()))
    return out


def lines(report: Path) -> list[str]:
    result = [f"Rating responses in {report.name} (per point of XI advantage; real where known):"]
    for key, (slope, half, mean) in responses(report).items():
        real = f"  real {REAL[key]:+.3f}" if key in REAL else ""
        result.append(f"  {key:20s} {slope:+.4f} ±{half:.4f} (mean {mean:.3f}){real}")
    return result

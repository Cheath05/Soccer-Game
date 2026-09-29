"""Batches of agent-engine matches for calibration and validation (`footsim calibrate-engine`).

Plays many matches in parallel, between real squads from a built world or synthetic teams,
summarises each with match.engine.probe, and compares the averages with real-football
reference ranges (data/config/calibration/match_targets.yaml).

A/B arms replay exactly the same fixtures and seeds with different instructions (or a
different formation) for one side, the "focus" team, so the differences between arms come
from the tactic rather than from luck.
"""

import json
import math
import os
import sqlite3
import time
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime
from multiprocessing import get_context
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from sqlalchemy import Engine, create_engine, text

from footsim.core.paths import REPO_ROOT, config_dir
from footsim.core.rng import derive_rng
from footsim.match.engine.engine import MatchEngine
from footsim.match.engine.probe import aggregate, summarize
from footsim.match.synthetic import synthetic_sheet
from footsim.match.teams import TeamSheet
from footsim.world.context import AI_FORMATIONS, World, get_world

MATCH_DAY = date(2026, 8, 22)  # ages and availability are taken on this day
TARGETS = config_dir() / "calibration" / "match_targets.yaml"


@dataclass(frozen=True)
class Arm:
    """Instructions (and optionally a formation) for the focus side in an A/B comparison."""

    name: str
    instructions: dict[str, str] = field(default_factory=dict)
    formation: str | None = None


BASELINE = Arm("baseline")


@dataclass(frozen=True)
class MatchTask:
    index: int
    seed: int
    home: int  # club id, or a synthetic team id
    away: int
    focus: int = 0  # which side (0 home, 1 away) an A/B arm applies to
    arm: Arm = BASELINE
    home_quality: float | None = None  # synthetic teams only
    away_quality: float | None = None


def parse_arm(spec: str) -> Arm:
    """``name:key=value,key=value`` (``formation=4-4-2`` sets the focus side's formation)."""
    name, _, body = spec.partition(":")
    pairs = [part.split("=", 1) for part in body.split(",") if part.strip()]
    settings = {key.strip(): value.strip() for key, value in pairs}
    formation = settings.pop("formation", None)
    return Arm(name.strip(), settings, formation)


# --- workers -------------------------------------------------------------------------------

_WORLD: World | None = None
_DB: Engine | None = None
_SHEETS: dict[tuple[int, str | None, float | None], TeamSheet] = {}


def open_readonly(path: Path) -> Engine:
    """A read-only view of a world or save that never writes WAL or journal files."""
    uri = f"file:{path}?immutable=1"
    return create_engine("sqlite://", creator=lambda: sqlite3.connect(
        uri, uri=True, check_same_thread=False))


def _init(world_path: str | None) -> None:
    global _WORLD, _DB
    _WORLD = get_world()
    _DB = open_readonly(Path(world_path)) if world_path else None


def _sheet(club_id: int, formation: str | None, quality: float | None) -> TeamSheet:
    from footsim.world.squads import load_squad, team_sheet

    assert _WORLD is not None
    key = (club_id, formation, quality)
    if key not in _SHEETS:
        if quality is not None:
            _SHEETS[key] = synthetic_sheet(_WORLD.defs, _WORLD.picker, club_id, quality,
                                           formation or "4-3-3")
        else:
            assert _DB is not None, "real squads need a world database"
            with _DB.connect() as conn:
                base = team_sheet(conn, _WORLD, club_id, MATCH_DAY)
                squad = load_squad(conn, club_id, MATCH_DAY)
            shape = formation or _WORLD.picker.best_formation(club_id, base.name, squad,
                                                              AI_FORMATIONS)
            _SHEETS[key] = _WORLD.picker.pick(club_id, base.name, squad,
                                              _WORLD.defs.formations[shape],
                                              instructions=base.instructions)
    sheet = _SHEETS[key]
    return replace(sheet, instructions=dict(sheet.instructions), starters=list(sheet.starters),
                   bench=list(sheet.bench))


def play_task(task: MatchTask) -> dict[str, Any]:
    assert _WORLD is not None
    focus_home = task.focus == 0
    home = _sheet(task.home, task.arm.formation if focus_home else None, task.home_quality)
    away = _sheet(task.away, None if focus_home else task.arm.formation, task.away_quality)
    target = home if focus_home else away
    target.instructions.update(task.arm.instructions)
    engine = MatchEngine(_WORLD.defs, home, away, derive_rng(task.seed, "calibrate", task.index),
                         record=False)
    engine.run()
    engine.report()
    summary = summarize(engine)
    summary.update(index=task.index, arm=task.arm.name, focus=task.focus,
                   home_club=task.home, away_club=task.away)
    return summary


def run_tasks(tasks: Sequence[MatchTask], world: Path | None, workers: int) -> list[dict[str, Any]]:
    if workers <= 1:
        _init(str(world) if world else None)
        return [play_task(t) for t in tasks]
    with ProcessPoolExecutor(max_workers=workers, mp_context=get_context("spawn"),
                             initializer=_init,
                             initargs=(str(world) if world else None,)) as pool:
        return list(pool.map(play_task, tasks, chunksize=2))


# --- fixtures ------------------------------------------------------------------------------


def division_clubs(world: Path, division: str) -> list[int]:
    engine = open_readonly(world)
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT m.club_id FROM club_league_membership m
                JOIN competition c ON c.id = m.competition_id
                WHERE c.key = :key AND m.season_id = 1 ORDER BY m.club_id
            """), {"key": division}).all()
    finally:
        engine.dispose()
    clubs = [int(r.club_id) for r in rows]
    if not clubs:
        raise ValueError(f"no clubs found for {division} in {world}")
    return clubs


def make_tasks(n: int, seed: int, arms: Sequence[Arm], clubs: Sequence[int] | None,
               focus_club: int | None = None,
               quality: tuple[float, float] = (62.0, 86.0)) -> list[MatchTask]:
    """``n`` fixtures, each played once per arm with the same seed. With ``clubs`` the teams
    are real; otherwise synthetic with qualities drawn from ``quality``."""
    rng = np.random.default_rng(seed)
    tasks = []
    for k in range(n):
        focus = k % 2
        if clubs is not None:
            if focus_club is not None:
                others = [c for c in clubs if c != focus_club]
                opponent = int(others[k // 2 % len(others)])
                pair = (focus_club, opponent) if focus == 0 else (opponent, focus_club)
            else:
                picked = rng.choice(len(clubs), 2, replace=False)
                pair = (int(clubs[picked[0]]), int(clubs[picked[1]]))
            qualities: tuple[float | None, float | None] = (None, None)
        else:
            pair = (1000 + 2 * k, 1001 + 2 * k)
            low, high = quality
            qualities = (float(rng.uniform(low, high)), float(rng.uniform(low, high)))
        for arm in arms:
            tasks.append(MatchTask(k, seed, pair[0], pair[1], focus, arm,
                                   qualities[0], qualities[1]))
    return tasks


# --- reports -------------------------------------------------------------------------------


def load_targets(division: str) -> dict[str, dict[str, Any]]:
    raw: dict[str, dict[str, dict[str, Any]]] = yaml.safe_load(TARGETS.read_text("utf-8"))
    return raw["ENG1" if division == "ENG1" else "EFL"]


def _fmt(value: float) -> str:
    if math.isnan(value):
        return "–"
    if abs(value) >= 100:
        return f"{value:.0f}"
    if abs(value) >= 10:
        return f"{value:.1f}"
    return f"{value:.3f}" if abs(value) < 1 else f"{value:.2f}"


def compare(agg: dict[str, float], targets: dict[str, dict[str, Any]]) -> list[tuple[str, ...]]:
    rows: list[tuple[str, ...]] = []
    for metric, value in agg.items():
        target = targets.get(metric)
        if target is None:
            rows.append((metric, _fmt(value), "", "", ""))
            continue
        low, high = target["range"]
        ok = not math.isnan(value) and low - 1e-9 <= value <= high + 1e-9
        rows.append((metric, _fmt(value), f"{_fmt(low)}–{_fmt(high)}", "ok" if ok else "OFF",
                     str(target.get("ref", ""))))
    return rows


def focus_view(results: Sequence[dict[str, Any]]) -> dict[str, float]:
    """A/B view from the focus side: its results, what it created and what it conceded."""
    def mean(values: list[float]) -> float:
        clean = [v for v in values if not math.isnan(v)]
        return float(np.mean(clean)) if clean else float("nan")

    rows: dict[str, list[float]] = {}
    for r in results:
        f, o = r["focus"], 1 - r["focus"]
        mine, theirs = r["teams"][f], r["teams"][o]
        values = {
            "win": float(r["score"][f] > r["score"][o]),
            "draw": float(r["score"][f] == r["score"][o]),
            "goals_for": float(r["score"][f]), "goals_against": float(r["score"][o]),
            "xg_for": mine["xg"], "xg_against": theirs["xg"],
            "shots_for": float(mine["shots"]), "shots_against": float(theirs["shots"]),
            "possession": mine["possession"], "ppda": mine["ppda"],
            "high_regains": float(mine["high_regains"]),
            "fast_break_shots_against": float(theirs["fast_break_shots"]),
            "pass_accuracy": mine["passes_completed"] / max(1, mine["passes"]),
            "distance_km": mine["distance_km"], "end_stamina": mine["end_stamina"],
            "fouls": float(mine["fouls"]), "reds": float(mine["reds"]),
        }
        for key, value in values.items():
            rows.setdefault(key, []).append(value)
    return {key: mean(values) for key, values in rows.items()}


def write_report(out: Path, label: str, division: str, synthetic: bool,
                 results: Sequence[dict[str, Any]], arms: Sequence[Arm],
                 elapsed: float) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    targets = load_targets(division)
    lines = [f"# Engine calibration: {label}", "",
             f"{len(results)} matches ({'synthetic teams' if synthetic else division}) in "
             f"{elapsed:.0f} s, {stamp} UTC.", ""]
    baseline = [r for r in results if r["arm"] == arms[0].name]
    agg = aggregate(baseline)
    lines += ["## Baseline vs real football", "",
              "| Metric | Engine | Target | | Reference |", "|---|---|---|---|---|"]
    lines += [f"| {' | '.join(row)} |" for row in compare(agg, targets)]
    if len(arms) > 1:
        views = {arm.name: focus_view([r for r in results if r["arm"] == arm.name])
                 for arm in arms}
        keys = list(next(iter(views.values())))
        lines += ["", "## A/B arms (focus side)", "",
                  "| Metric | " + " | ".join(views) + " |",
                  "|---|" + "---|" * len(views)]
        for key in keys:
            lines.append(f"| {key} | " + " | ".join(_fmt(v[key]) for v in views.values()) + " |")
    path = out / f"{stamp}-{label}.md"
    path.write_text("\n".join(lines) + "\n", "utf-8")
    (out / f"{stamp}-{label}.json").write_text(json.dumps(
        {"label": label, "division": division, "synthetic": synthetic, "aggregate": agg,
         "arms": {arm.name: aggregate([r for r in results if r["arm"] == arm.name])
                  for arm in arms}},
        indent=1, default=float), "utf-8")
    return path


def calibrate(division: str, n: int, seed: int, arms: Sequence[Arm], world: Path | None,
              synthetic: bool, workers: int | None = None, focus_club: int | None = None,
              out: Path | None = None) -> Path:
    workers = workers or max(1, (os.cpu_count() or 2) - 1)
    clubs = None if synthetic or world is None else division_clubs(world, division)
    tasks = make_tasks(n, seed, arms, clubs, focus_club)
    started = time.perf_counter()
    results = run_tasks(tasks, None if synthetic else world, workers)
    elapsed = time.perf_counter() - started
    label = f"{'synthetic' if synthetic else division}-n{n}"
    if len(arms) > 1:
        label += "-ab"
    return write_report(out or REPO_ROOT / "reports" / "engine", label, division, synthetic,
                        results, arms, elapsed)

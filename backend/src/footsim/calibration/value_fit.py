"""Fit the market-value model (W4-1) on the base world's Transfermarkt values.

``footsim fit-values`` copies the base world, brings the copy up to the current schema, and
fits log(value) by least squares on every player under contract who has a Transfermarkt value
(about 12,400 of 17,800). The model's shape (the overall knee, the ages where value turns) stays
as data/config/transfers/valuation.yaml sets it; the fit replaces the coefficients and records
how well they fit. docs/calibration/value-model.md has the result.
"""

import shutil
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import yaml
from sqlalchemy import Connection, text

from footsim.defs.valuation import ValuationDef
from footsim.persistence.database import open_database
from footsim.persistence.migrations import migrate
from footsim.transfers.valuation import FEATURES, features, years_old
from footsim.world.context import World
from footsim.world.overall_history import player_overalls

BANDS = ((0, 65), (65, 75), (75, 82), (82, 86), (86, 100))
SIGNS = {"decline": -1.0, "late_decline": -1.0}  # stored as positive rates of decline


@dataclass(frozen=True)
class ValueFit:
    model: ValuationDef
    players: int
    r2: float
    residual_sd: float
    band_residuals: dict[str, float]  # median log residual by overall band (+: model too low)
    sample: tuple[np.ndarray, ...] = ()  # overall, age, keeper, reputation, log value

    def report(self) -> str:
        coeffs = ", ".join(f"{name} {getattr(self.model, name):+.4f}" for name in FEATURES)
        bands = ", ".join(f"{band} {r:+.2f}" for band, r in self.band_residuals.items())
        return (f"{self.players} players, R² {self.r2:.3f}, residual sd {self.residual_sd:.3f} "
                f"(log)\n  {coeffs}\n  median residual by overall: {bands}")


def _sample(conn: Connection, world: World, day: date) -> tuple[np.ndarray, ...]:
    overall = player_overalls(conn, world)
    rows = conn.execute(text(
        "SELECT p.person_id AS id, p.value_eur_cents AS value, pe.birth_date AS birth, "
        "c.reputation AS reputation, (SELECT position FROM player_position pp "
        "  WHERE pp.player_id = p.person_id ORDER BY familiarity DESC, position LIMIT 1) AS pos "
        "FROM player p JOIN person pe ON pe.id = p.person_id "
        "JOIN contract k ON k.person_id = p.person_id AND k.is_active = 1 "
        "JOIN club c ON c.id = k.club_id "
        "WHERE p.retired_on IS NULL AND p.value_eur_cents > 0 ORDER BY p.person_id")).all()
    rows = [r for r in rows if r.id in overall]
    return (np.array([overall[r.id] for r in rows], dtype=float),
            np.array([years_old(r.birth, day) for r in rows], dtype=float),
            np.array([r.pos == "GK" for r in rows], dtype=float),
            np.array([r.reputation for r in rows], dtype=float),
            np.log(np.array([r.value / 100 for r in rows], dtype=float)))


def fit_values(conn: Connection, world: World, shape: ValuationDef, day: date) -> ValueFit:
    """Fit the coefficients of ``shape`` on the players of the world open on ``conn``."""
    overall, age, keeper, reputation, target = _sample(conn, world, day)
    x = features(shape, overall, age, keeper, reputation)
    beta, *_ = np.linalg.lstsq(x, target, rcond=None)
    residual = target - x @ beta
    fitted = {name: float(b) * SIGNS.get(name, 1.0) for name, b in zip(FEATURES, beta, strict=True)}
    r2 = 1 - float((residual ** 2).sum() / ((target - target.mean()) ** 2).sum())
    bands = {f"{lo}-{hi}": float(np.median(residual[(overall >= lo) & (overall < hi)]))
             for lo, hi in BANDS if ((overall >= lo) & (overall < hi)).any()}
    model = shape.model_copy(update={
        **fitted, "fit": {"players": float(len(target)), "r2": round(r2, 4),
                          "residual_sd": round(float(residual.std()), 4)}})
    return ValueFit(model, len(target), r2, float(residual.std()), bands,
                    (overall, age, keeper, reputation, target))


def fit_base_world(base_world: Path, world: World, shape: ValuationDef, day: date) -> ValueFit:
    """``fit_values`` on a migrated copy of the base world (the file itself is left alone)."""
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "world.sqlite"
        shutil.copy(base_world, copy)
        engine = open_database(copy)
        try:
            migrate(engine)
            with engine.connect() as conn:
                return fit_values(conn, world, shape, day)
        finally:
            engine.dispose()


def write_model(fit: ValueFit, path: Path) -> None:
    """Rewrite valuation.yaml's numbers, keeping its header comments."""
    header = [line for line in path.read_text().splitlines() if line.startswith("#")]
    data = fit.model.model_dump()
    body = yaml.safe_dump({k: (round(v, 5) if isinstance(v, float) else v)
                           for k, v in data.items()}, sort_keys=False)
    path.write_text("\n".join(header) + "\n" + body)

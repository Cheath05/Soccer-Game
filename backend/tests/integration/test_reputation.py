"""Clubs' reputations move with their squads (world/reputation.py).

Skipped when the base world hasn't been built (it needs the locally downloaded EA FC 27 file,
which isn't in the repository)."""

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Connection, Engine, text

from footsim.core.paths import data_dir
from footsim.persistence.database import open_database
from footsim.persistence.migrations import migrate
from footsim.world.career import initialize_career
from footsim.world.context import get_world
from footsim.world.meta import read_meta
from footsim.world.reputation import _squad_targets, drift_reputations

BASE_WORLD = data_dir() / "worlds" / "base-2026-27.sqlite"
pytestmark = pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")


@pytest.fixture(scope="module")
def career(tmp_path_factory: pytest.TempPathFactory) -> Engine:
    path = Path(tmp_path_factory.mktemp("reputation")) / "career.sqlite"
    shutil.copy(BASE_WORLD, path)
    engine = open_database(path)
    migrate(engine)
    with engine.begin() as conn:
        initialize_career(conn, get_world(), None, None, seed=5)
    return engine


@pytest.fixture
def conn(career: Engine) -> Iterator[Connection]:
    with career.connect() as connection:
        transaction = connection.begin()
        yield connection
        transaction.rollback()


def _reputations(conn: Connection) -> dict[int, int]:
    return {int(r.id): int(r.reputation) for r in conn.execute(
        text("SELECT id, reputation FROM club"))}


def test_reputation_drifts_towards_what_the_squad_is_worth(conn: Connection) -> None:
    world = get_world()
    drift = world.defs.reputation_drift.drift
    before = _reputations(conn)
    targets = _squad_targets(conn, world)
    drift_reputations(conn, world, read_meta(conn), 1, 1)  # no honours in a season not played
    after = _reputations(conn)
    for club_id, target in targets.items():
        old, new = before[club_id], after[club_id]
        expected = old + drift * (target - old)
        assert abs(new - expected) <= 0.5 + 1e-9, club_id  # rounded to a whole number
        assert abs(new - target) <= abs(old - target) + 0.5, club_id  # never overshoots


def test_a_club_that_loses_its_best_players_loses_stature(conn: Connection) -> None:
    world = get_world()
    club_id = conn.execute(text(
        "SELECT m.club_id FROM club_league_membership m JOIN competition c ON c.id = "
        "m.competition_id WHERE c.key = 'ENG1' ORDER BY m.club_id LIMIT 1")).scalar_one()
    before = _reputations(conn)[club_id]
    natural = _squad_targets(conn, world)[club_id]
    best = conn.execute(text(
        "SELECT k.person_id FROM contract k JOIN player_attr a ON a.player_id = k.person_id "
        "WHERE k.club_id = :c AND k.is_active = 1 ORDER BY (a.reactions + a.composure) DESC "
        "LIMIT 12"), {"c": club_id}).scalars().all()
    conn.execute(text("UPDATE contract SET is_active = 0 WHERE person_id IN (" + ", ".join(
        str(p) for p in best) + ") AND is_active = 1"))
    assert _squad_targets(conn, world)[club_id] < natural
    drift_reputations(conn, world, read_meta(conn), 1, 1)
    assert _reputations(conn)[club_id] < before

"""Loans (W4-8): a loaned player plays for the borrowing club and only there, his parent keeps
his permanent contract, and every euro of his wage is paid once.

Skipped when the base world hasn't been built (it needs the locally downloaded EA FC 27 file,
which isn't in the repository)."""

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import IntegrityError

from footsim.core.paths import data_dir
from footsim.persistence.database import open_database
from footsim.persistence.migrations import migrate
from footsim.world.career import initialize_career
from footsim.world.context import get_world
from footsim.world.finance import wage_bills
from footsim.world.squads import load_squad
from footsim.world.transfers import Move, MoveRefused, validate_move

BASE_WORLD = data_dir() / "worlds" / "base-2026-27.sqlite"
pytestmark = pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")


@pytest.fixture(scope="module")
def career(tmp_path_factory: pytest.TempPathFactory) -> Engine:
    path = Path(tmp_path_factory.mktemp("loans")) / "career.sqlite"
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


def _loan(conn: Connection) -> tuple[int, int, int, int]:
    """A hand-made loan: an ENG1 club's player to an ENG2 club, the borrower paying half."""
    parent, borrower = (conn.execute(text(
        "SELECT m.club_id FROM club_league_membership m JOIN competition c ON c.id = "
        "m.competition_id WHERE c.key = :k ORDER BY m.club_id LIMIT 1"), {"k": k}).scalar_one()
        for k in ("ENG1", "ENG2"))
    player, wage = conn.execute(text(
        "SELECT person_id, wage_weekly_cents FROM contract WHERE club_id = :c AND is_active = 1 "
        "ORDER BY person_id DESC LIMIT 1"), {"c": parent}).one()
    conn.execute(text(
        "INSERT INTO contract (person_id, club_id, kind, start_date, end_date, wage_weekly_cents, "
        "is_active, listed) VALUES (:p, :b, 'loan', '2026-07-01', '2027-06-30', :w, 1, 0)"),
        {"p": player, "b": borrower, "w": wage // 2})
    return int(player), int(parent), int(borrower), int(wage)


def test_a_loaned_player_plays_in_one_squad(conn: Connection) -> None:
    from datetime import date

    player, parent, borrower, _ = _loan(conn)
    day = date(2026, 7, 1)
    assert player in {p.player_id for p in load_squad(conn, borrower, day)}
    assert player not in {p.player_id for p in load_squad(conn, parent, day)}
    assert conn.execute(text("SELECT COUNT(*) FROM (SELECT person_id FROM playing GROUP BY "
                             "person_id HAVING COUNT(*) > 1)")).scalar_one() == 0
    # His permanent contract is still his parent's.
    owner = conn.execute(text("SELECT club_id FROM contract WHERE person_id = :p AND "
                              "is_active = 1 AND kind != 'loan'"), {"p": player}).scalar_one()
    assert owner == parent


def test_every_euro_of_a_loaned_players_wage_is_paid_once(conn: Connection) -> None:
    before = wage_bills(conn)
    player, parent, borrower, wage = _loan(conn)
    after = wage_bills(conn)
    assert after[borrower] - before[borrower] == wage // 2
    assert before[parent] - after[parent] == wage // 2
    assert sum(after.values()) == sum(before.values())


def test_a_player_has_one_loan_and_cant_be_sold_while_away(conn: Connection) -> None:
    from datetime import date

    player, parent, borrower, _ = _loan(conn)
    with pytest.raises(IntegrityError), conn.begin_nested():
        conn.execute(text(
            "INSERT INTO contract (person_id, club_id, kind, start_date, end_date, "
            "wage_weekly_cents, is_active, listed) VALUES (:p, :b, 'loan', '2026-07-01', "
            "'2027-06-30', 100, 1, 0)"), {"p": player, "b": parent})
    meta_world = get_world()
    from footsim.world.meta import read_meta

    with pytest.raises(MoveRefused, match="on loan"):
        validate_move(conn, meta_world, read_meta(conn),
                      Move(player, borrower, 0, 100_000, date(2029, 6, 30)), date(2026, 7, 20))

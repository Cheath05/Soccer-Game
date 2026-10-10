"""Saves written by an older build are upgraded in place on load."""

import shutil
from pathlib import Path

import numpy as np
import pytest
from sqlalchemy import inspect, text

from footsim.api.session import CareerSession
from footsim.core.paths import data_dir
from footsim.persistence.database import (
    SchemaMismatch,
    create_database,
    open_database,
    read_meta,
    write_meta,
)
from footsim.persistence.migrations import STEPS, migrate
from footsim.persistence.schema import SCHEMA_VERSION


def _v2_database(path: Path) -> None:
    """A database as version 2 wrote it: match events without period/second."""
    engine = create_database(path)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE match_event DROP COLUMN period"))
        conn.execute(text("ALTER TABLE match_event DROP COLUMN second"))
    write_meta(engine, {"schema_version": 2})
    engine.dispose()


def test_version_2_is_upgraded(tmp_path: Path) -> None:
    path = tmp_path / "old.sqlite"
    _v2_database(path)
    engine = open_database(path)
    assert migrate(engine) == 2
    assert read_meta(engine)["schema_version"] == SCHEMA_VERSION
    with engine.connect() as conn:
        columns = {c["name"] for c in inspect(conn).get_columns("match_event")}
    assert {"period", "second"} <= columns
    assert migrate(engine) == SCHEMA_VERSION  # nothing left to do
    engine.dispose()


def test_newer_databases_are_refused(tmp_path: Path) -> None:
    path = tmp_path / "future.sqlite"
    engine = create_database(path)
    write_meta(engine, {"schema_version": SCHEMA_VERSION + 1})
    with pytest.raises(SchemaMismatch):
        migrate(engine)
    engine.dispose()


def test_version_3_gains_player_development(tmp_path: Path) -> None:
    """Saves from before monthly development traits get the table when loaded (1 Oct)."""
    path = tmp_path / "v3.sqlite"
    engine = create_database(path)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE player_development"))
    write_meta(engine, {"schema_version": 3})
    engine.dispose()
    engine = open_database(path)
    assert migrate(engine) == 3
    with engine.connect() as conn:
        assert "player_development" in inspect(conn).get_table_names()
    engine.dispose()


BASE_WORLD = data_dir() / "worlds" / "base-2026-27.sqlite"


@pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")
def test_version_4_moves_potential_with_the_new_overall(tmp_path: Path) -> None:
    """Overalls count every headline rating from v5 (P14): each player's hidden potential moves
    with his overall, so his room to grow is unchanged, and it moves only once."""
    path = tmp_path / "v4.sqlite"
    shutil.copy(BASE_WORLD, path)
    engine = open_database(path)
    write_meta(engine, {"schema_version": 4})
    with engine.connect() as conn:
        before = dict(conn.execute(text("SELECT person_id, pa_hidden FROM player")).all())
    migrate(engine)
    with engine.connect() as conn:
        after = dict(conn.execute(text("SELECT person_id, pa_hidden FROM player")).all())
    shifts = np.array([after[p] - before[p] for p in before])
    assert abs(shifts.mean()) < 0.5  # each group's average overall is unchanged...
    assert (shifts != 0).mean() > 0.5  # ...but most players' overall moved
    assert np.abs(shifts).max() <= 10
    assert read_meta(engine)["schema_version"] == SCHEMA_VERSION
    migrate(engine)  # loading it again changes nothing
    with engine.connect() as conn:
        again = dict(conn.execute(text("SELECT person_id, pa_hidden FROM player")).all())
    assert again == after
    engine.dispose()


def test_version_5_gains_the_overall_trend(tmp_path: Path) -> None:
    """Saves from before the up/down arrow get each player's trend, starting level."""
    path = tmp_path / "v5.sqlite"
    engine = create_database(path)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE player_development DROP COLUMN trend"))
    write_meta(engine, {"schema_version": 5})
    engine.dispose()
    engine = open_database(path)
    assert migrate(engine) == 5
    with engine.connect() as conn:
        columns = {c["name"] for c in inspect(conn).get_columns("player_development")}
    assert "trend" in columns
    engine.dispose()


def test_version_7_gains_retirement(tmp_path: Path) -> None:
    """Saves from before retirement get the column, every player still playing."""
    path = tmp_path / "v7.sqlite"
    engine = create_database(path)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE player DROP COLUMN retired_on"))
    write_meta(engine, {"schema_version": 7})
    engine.dispose()
    engine = open_database(path)
    assert migrate(engine) == 7
    assert migrate(engine) == SCHEMA_VERSION  # and running it again changes nothing
    with engine.connect() as conn:
        columns = {c["name"] for c in inspect(conn).get_columns("player")}
    assert "retired_on" in columns
    engine.dispose()


def test_version_8_gains_the_season_overalls(tmp_path: Path) -> None:
    """Saves from before the season summary's development table get its record table. A world
    that isn't a career yet has no season to record."""
    path = tmp_path / "v8.sqlite"
    engine = create_database(path)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE player_season_overall"))
    write_meta(engine, {"schema_version": 8})
    engine.dispose()
    engine = open_database(path)
    assert migrate(engine) == 8
    assert migrate(engine) == SCHEMA_VERSION
    with engine.connect() as conn:
        assert "player_season_overall" in inspect(conn).get_table_names()
        assert conn.execute(text("SELECT COUNT(*) FROM player_season_overall")).scalar_one() == 0
    engine.dispose()


@pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")
def test_version_8_starts_the_record_for_a_career_under_way(tmp_path: Path) -> None:
    """A career already under way has the current season recorded from the day it is upgraded
    (it can't know the season's start), once, for every player still playing."""
    session = CareerSession(tmp_path / "saves", BASE_WORLD)
    session.new_career(1, 218, "Upgrade")
    engine = session.engine
    with engine.begin() as conn:
        playing: int = conn.execute(text(
            "SELECT COUNT(*) FROM player WHERE retired_on IS NULL")).scalar_one()
        conn.execute(text("DROP TABLE player_season_overall"))
        conn.execute(text("UPDATE game_meta SET value = '\"2026-10-14\"' "
                          "WHERE key = 'game_date'"))
    write_meta(engine, {"schema_version": 8})
    assert migrate(engine) == 8
    for _ in range(2):  # and upgrading again changes nothing
        with engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT season_id, recorded_on, COUNT(*) AS n FROM player_season_overall "
                "GROUP BY season_id, recorded_on")).all()
        assert [(r.season_id, r.recorded_on, r.n) for r in rows] == [(1, "2026-10-14", playing)]
        migrate(engine)
    session.close()


def test_version_9_gains_club_finances(tmp_path: Path) -> None:
    """Saves from before club finances (W3) get their tables. A world that isn't a career yet
    has no finances until a career begins."""
    path = tmp_path / "v9.sqlite"
    engine = create_database(path)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE finance_ledger"))
        conn.execute(text("DROP TABLE club_finance"))
    write_meta(engine, {"schema_version": 9})
    engine.dispose()
    engine = open_database(path)
    assert migrate(engine) == 9
    assert migrate(engine) == SCHEMA_VERSION
    with engine.connect() as conn:
        tables = inspect(conn).get_table_names()
        assert "club_finance" in tables and "finance_ledger" in tables
        assert conn.execute(text("SELECT COUNT(*) FROM club_finance")).scalar_one() == 0
    engine.dispose()


@pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")
def test_version_9_starts_finances_for_a_career_under_way(tmp_path: Path) -> None:
    """A career already under way gets every club's finances from the day it's upgraded, with
    each balance its ledger, once."""
    session = CareerSession(tmp_path / "saves", BASE_WORLD)
    session.new_career(1, 218, "Upgrade")
    engine = session.engine
    with engine.begin() as conn:
        clubs: int = conn.execute(text("SELECT COUNT(*) FROM club")).scalar_one()
        conn.execute(text("DROP TABLE finance_ledger"))
        conn.execute(text("DROP TABLE club_finance"))
        conn.execute(text("UPDATE game_meta SET value = '\"2026-10-14\"' "
                          "WHERE key = 'game_date'"))
    write_meta(engine, {"schema_version": 9})
    assert migrate(engine) == 9
    snapshots = []
    for _ in range(2):  # and running the step again changes nothing
        with engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT date, kind, COUNT(*) AS n FROM finance_ledger GROUP BY date, kind")).all()
            assert [(r.date, r.kind, r.n) for r in rows] == [("2026-10-14", "opening", clubs)]
            assert conn.execute(text(
                "SELECT COUNT(*) FROM club_finance f JOIN (SELECT club_id, SUM(amount_cents) s "
                "FROM finance_ledger GROUP BY club_id) l ON l.club_id = f.club_id "
                "WHERE f.balance_cents = l.s AND f.budget_season_id = 1 "
                "AND f.wage_budget_cents > 0 AND f.settled_on = '2026-10-14'")
            ).scalar_one() == clubs
            snapshots.append(conn.execute(text(
                "SELECT * FROM club_finance ORDER BY club_id")).all())
        with engine.begin() as conn:
            STEPS[10](conn)
    assert snapshots[0] == snapshots[1]
    session.close()


@pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")
def test_version_10_gains_the_market_and_one_owner_per_player(tmp_path: Path) -> None:
    """A career from before the transfer market gets its tables, listing, players' market
    premiums and the one-owner rule; a player with two active contracts (there shouldn't be
    any) keeps the latest one. Running the step again changes nothing."""
    session = CareerSession(tmp_path / "saves", BASE_WORLD)
    session.new_career(1, 218, "Upgrade")
    engine = session.engine
    with engine.begin() as conn:
        conn.execute(text("DROP INDEX ux_contract_owner"))
        conn.execute(text("DROP TABLE transfer"))
        conn.execute(text("UPDATE player SET value_premium = NULL"))
        doubled = conn.execute(text(
            "SELECT id, person_id FROM contract WHERE is_active = 1 ORDER BY id LIMIT 1")).one()
        conn.execute(text(
            "INSERT INTO contract (person_id, club_id, kind, start_date, end_date, "
            "wage_weekly_cents, is_active, listed) VALUES (:p, 1, 'player', '2026-08-01', "
            "'2028-06-30', 100, 1, 0)"), {"p": doubled.person_id})
    write_meta(engine, {"schema_version": 10})
    assert migrate(engine) == 10
    snapshots = []
    for _ in range(2):
        with engine.connect() as conn:
            owners = conn.execute(text(
                "SELECT club_id, start_date FROM contract WHERE person_id = :p "
                "AND is_active = 1"), {"p": doubled.person_id}).all()
            assert [(r.club_id, r.start_date) for r in owners] == [(1, "2026-08-01")]
            assert "ux_contract_owner" in {i["name"] for i in inspect(conn).get_indexes(
                "contract")}
            assert conn.execute(text("SELECT COUNT(*) FROM transfer")).scalar_one() == 0
            assert conn.execute(text(
                "SELECT COUNT(*) FROM player WHERE value_premium IS NULL "
                "AND retired_on IS NULL")).scalar_one() == 0
            assert conn.execute(text(
                "SELECT COUNT(*) FROM player WHERE value_premium != 0")).scalar_one() > 5000
            snapshots.append(conn.execute(text(
                "SELECT person_id, value_premium FROM player ORDER BY person_id")).all())
        with engine.begin() as conn:
            STEPS[11](conn)
    assert snapshots[0] == snapshots[1]
    session.close()


def _v11_database(path: Path) -> None:
    """A database as version 11 wrote it: a player, his state and development row, and none of
    the first-team rewards' columns (the bench minutes, the academy boost)."""
    engine = create_database(path)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO person (id, first_name, last_name, birth_date) "
                          "VALUES (1, 'Young', 'Player', '2008-03-01')"))
        conn.execute(text("INSERT INTO player (person_id, preferred_foot, weak_foot, "
                          "skill_moves, pa_hidden, reputation) VALUES (1, 'Right', 3, 2, 80, 40)"))
        conn.execute(text("INSERT INTO player_state (player_id, condition, form, "
                          "suspended_matches, season_yellows) VALUES (1, 100.0, 6.5, 0, 0)"))
        conn.execute(text("INSERT INTO player_development (player_id, peak_age, decline_age, "
                          "ceiling_bonus, ageless, progress, trend) "
                          "VALUES (1, 27.0, 32.0, 0, 0, 0.3, 0.1)"))
        conn.execute(text("ALTER TABLE player_state DROP COLUMN bench_minutes"))
        conn.execute(text("ALTER TABLE player_development DROP COLUMN potential_boost"))
    write_meta(engine, {"schema_version": 11})
    engine.dispose()


def test_version_11_gains_the_first_team_rewards(tmp_path: Path) -> None:
    """Saves from before the bench credit and the academy boost get their two columns; every
    player starts with nothing credited. Running the step again, or after a crash left one
    column added, changes nothing."""
    path = tmp_path / "v11.sqlite"
    _v11_database(path)
    engine = open_database(path)
    assert migrate(engine) == 11
    assert read_meta(engine)["schema_version"] == SCHEMA_VERSION
    with engine.connect() as conn:
        state = {c["name"]: c for c in inspect(conn).get_columns("player_state")}
        development = {c["name"]: c for c in inspect(conn).get_columns("player_development")}
        assert "bench_minutes" in state and "potential_boost" in development
        assert conn.execute(text("SELECT bench_minutes FROM player_state")).scalar_one() == 0
        assert conn.execute(text(
            "SELECT potential_boost, progress, trend FROM player_development")
        ).one() == (0, 0.3, 0.1)  # the rest of his row is untouched
    # What a career then credits survives running the step again...
    with engine.begin() as conn:
        conn.execute(text("UPDATE player_state SET bench_minutes = 40.5"))
        conn.execute(text("UPDATE player_development SET potential_boost = 2.25"))
        STEPS[12](conn)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT bench_minutes FROM player_state")).scalar_one() == 40.5
        assert conn.execute(text(
            "SELECT potential_boost FROM player_development")).scalar_one() == 2.25
    # ...and a crash that left one column added, the other not, is made good.
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE player_state DROP COLUMN bench_minutes"))
        STEPS[12](conn)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT bench_minutes FROM player_state")).scalar_one() == 0
        assert conn.execute(text(
            "SELECT potential_boost FROM player_development")).scalar_one() == 2.25
    assert migrate(engine) == SCHEMA_VERSION  # nothing left to do
    engine.dispose()


@pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")
def test_version_12_gains_the_playing_view_and_one_loan_per_player(tmp_path: Path) -> None:
    """Loans (W4-8): a save from before them gets the playing view and the one-loan rule, and
    running the step again changes nothing."""
    session = CareerSession(tmp_path / "saves", BASE_WORLD)
    session.new_career(1, 218, "Upgrade")
    engine = session.engine
    with engine.begin() as conn:
        conn.execute(text("DROP VIEW playing"))
        conn.execute(text("DROP INDEX ux_contract_loan"))
    write_meta(engine, {"schema_version": 12})
    assert migrate(engine) == 12
    for _ in range(2):
        with engine.begin() as conn:
            names = {r.name for r in conn.execute(text("SELECT name FROM sqlite_master"))}
            assert {"playing", "ux_contract_loan"} <= names
            playing = conn.execute(text("SELECT COUNT(*) FROM playing")).scalar_one()
            active = conn.execute(text("SELECT COUNT(*) FROM contract WHERE is_active = 1")
                                  ).scalar_one()
            assert playing == active  # no loans yet: everyone plays where he's contracted
            STEPS[13](conn)
    session.close()


@pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")
def test_version_14_gains_haggling_and_position_training(tmp_path: Path) -> None:
    session = CareerSession(tmp_path / "saves", BASE_WORLD)
    session.new_career(1, 218, "Upgrade")
    engine = session.engine
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE position_training"))
        conn.execute(text("ALTER TABLE transfer_offer DROP COLUMN rounds"))
    write_meta(engine, {"schema_version": 14})
    assert migrate(engine) == 14
    for _ in range(2):
        with engine.begin() as conn:
            assert "rounds" in {c["name"] for c in inspect(conn).get_columns("transfer_offer")}
            assert "position_training" in inspect(conn).get_table_names()
            STEPS[15](conn)
    session.close()


@pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")
def test_version_15_gains_the_loan_list(tmp_path: Path) -> None:
    session = CareerSession(tmp_path / "saves", BASE_WORLD)
    session.new_career(1, 218, "Upgrade")
    engine = session.engine
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE contract DROP COLUMN loan_listed"))
    write_meta(engine, {"schema_version": 15})
    assert migrate(engine) == 15
    for _ in range(2):
        with engine.begin() as conn:
            assert "loan_listed" in {c["name"] for c in inspect(conn).get_columns("contract")}
            assert conn.execute(text("SELECT MAX(loan_listed) FROM contract")).scalar_one() == 0
            STEPS[16](conn)
    session.close()


@pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")
def test_version_16_gains_saved_tactics(tmp_path: Path) -> None:
    session = CareerSession(tmp_path / "saves", BASE_WORLD)
    session.new_career(1, 218, "Upgrade")
    engine = session.engine
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE tactic_preset"))
    write_meta(engine, {"schema_version": 16})
    assert migrate(engine) == 16
    for _ in range(2):
        with engine.begin() as conn:
            assert "tactic_preset" in inspect(conn).get_table_names()
            STEPS[17](conn)
    session.close()

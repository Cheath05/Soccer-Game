"""Real names for the made-up clubs (v14 migration, world build) and the server-computed
"Sim to…" targets and club search that U2 added."""

from datetime import date
from pathlib import Path

from sqlalchemy import Connection, insert, text

from footsim.api.queries import search_clubs
from footsim.api.sim import sim_targets
from footsim.persistence.database import create_database, open_database, read_meta, write_meta
from footsim.persistence.migrations import STEPS, migrate
from footsim.persistence.schema import (
    SCHEMA_VERSION,
    club,
    club_league_membership,
    competition,
    fixture,
    nation,
    season,
)
from footsim.world.club_names import apply_club_names, load_club_names


def _world(conn: Connection) -> None:
    conn.execute(insert(nation), [{"id": 1, "name": "Italy", "code": "ITA"},
                                  {"id": 2, "name": "Spain", "code": "ESP"}])
    conn.execute(insert(season), [{"id": 1, "label": "2026/27", "start_date": "2026-08-01",
                                   "end_date": "2027-06-30"}])
    conn.execute(insert(competition), [
        {"id": 1, "key": "ITA1", "name": "Serie A", "short_name": "SA", "nation_id": 1,
         "type": "league", "tier": 1, "sim_level": "playable"},
        {"id": 2, "key": "ESP_CUP", "name": "Copa del Rey", "short_name": "CdR", "nation_id": 2,
         "type": "cup", "tier": None, "sim_level": "playable"},
        {"id": 3, "key": "ESP_SUPER", "name": "Supercopa", "short_name": "SC", "nation_id": 2,
         "type": "cup", "tier": None, "sim_level": "playable"}])
    clubs = [(1, "Milano FC", 1), (2, "Lombardia FC", 1), (3, "Juventus", 1),
             (4, "Atlético de Madrid", 2), (5, "Milano FC", 2)]  # a Spanish "Milano FC": untouched
    conn.execute(insert(club), [{"id": i, "name": n, "nation_id": c, "reputation": 50 + i}
                                for i, n, c in clubs])
    conn.execute(insert(club_league_membership),
                 [{"club_id": 1, "season_id": 1, "competition_id": 1}])


def test_names_file_holds_real_italian_names() -> None:
    names = load_club_names()["Italy"]
    assert names["Milano FC"] == "AC Milan" and names["Latium"] == "Lazio"
    assert names["Lombardia FC"] == "Inter" and names["Bergamo Calcio"] == "Atalanta"


def test_v14_renames_by_old_name_once_and_keeps_the_users_club_in_step(tmp_path: Path) -> None:
    path = tmp_path / "v13.sqlite"
    engine = create_database(path)
    with engine.begin() as conn:
        _world(conn)
    write_meta(engine, {"schema_version": 13, "club_name": "Milano FC"})
    engine.dispose()
    engine = open_database(path)
    assert 14 in STEPS and SCHEMA_VERSION >= 14
    assert migrate(engine) == 13
    with engine.connect() as conn:
        names = dict(conn.execute(text("SELECT id, name FROM club")).all())
    assert names == {1: "AC Milan", 2: "Inter", 3: "Juventus", 4: "Atlético de Madrid",
                     5: "Milano FC"}
    assert read_meta(engine)["club_name"] == "AC Milan"
    with engine.begin() as conn:
        assert apply_club_names(conn) == 0  # idempotent
    engine.dispose()


def test_search_ignores_accents_and_ranks_prefixes_first(tmp_path: Path) -> None:
    engine = create_database(tmp_path / "w.sqlite")
    with engine.begin() as conn:
        _world(conn)
    write_meta(engine, {"world_seed": 1, "season_id": 1, "game_date": "2026-08-01"})
    with engine.connect() as conn:
        found = search_clubs(conn, "atletico")
        assert [c.name for c in found] == ["Atlético de Madrid"]
        assert found[0].nation == "Spain" and found[0].competition is None
        milan = search_clubs(conn, "mil")
        assert {c.id for c in milan} == {1, 5}
        assert next(c for c in milan if c.id == 1).competition == "Serie A"
        assert search_clubs(conn, "   ") == [] and search_clubs(conn, "zzz") == []
    engine.dispose()


def test_next_cup_match_is_the_next_non_league_fixture(tmp_path: Path) -> None:
    engine = create_database(tmp_path / "w.sqlite")
    with engine.begin() as conn:
        _world(conn)
        base = {"season_id": 1, "stage": "league", "round": 1, "status": "scheduled"}
        conn.execute(insert(fixture), [
            {**base, "competition_id": 1, "date": "2026-08-05", "home_club_id": 4,
             "away_club_id": 5},
            {**base, "competition_id": 3, "date": "2026-09-20", "home_club_id": 5,
             "away_club_id": 4},
            {**base, "competition_id": 2, "date": "2026-09-10", "home_club_id": 4,
             "away_club_id": 5},
            {**base, "competition_id": 2, "date": "2026-08-01", "home_club_id": 4,
             "away_club_id": 5}])  # today: not a target
    with engine.connect() as conn:
        found = sim_targets(conn, 4, date(2026, 8, 1))
        assert [(t.key, t.date) for t in found] == [
            ("next_cup", "2026-09-10"), ("next:ESP_CUP", "2026-09-10"),
            ("next:ESP_SUPER", "2026-09-20")]
        assert found[0].label == "Next cup match" and found[0].opponent == "Milano FC"
        assert sim_targets(conn, 1, date(2026, 8, 1)) == []  # no cup fixtures
    engine.dispose()

"""The FIFA Club World Cup (W10: world/international/guests.py and club_world_cup.py). A new
career has the guest clubs, with squads of their country's made-up players (also its national
pool). The 2029 edition is drawn on its day: 32 entrants by each confederation's share and
country cap, the host's club, 8 groups with no two clubs of one confederation (UEFA's, two at
most); its results filled in, the knockouts follow to a champion, and prize money is paid to
the clubs with finances. Needs the built world."""

import shutil
from collections import Counter
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine, text

from footsim.api.app import create_app
from footsim.api.session import CareerSession
from footsim.core.paths import data_dir
from footsim.persistence.database import open_database
from footsim.persistence.migrations import migrate
from footsim.world.career import initialize_career
from footsim.world.context import World, get_world
from footsim.world.international.club_world_cup import (
    LETTERS,
    choose_entrants,
    club_world_cup_day,
    draw_date,
    group_tables,
)
from footsim.world.meta import read_meta, write_meta
from footsim.world.squads import team_sheet

BASE_WORLD = data_dir() / "worlds" / "base-2026-27.sqlite"
pytestmark = pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")
YEAR = 2029


def _play(conn: Connection, stage: str) -> None:
    """Every scheduled fixture of ``stage``: the club whose id is lower wins 2-1."""
    for f in conn.execute(text("SELECT id, home_club_id, away_club_id FROM fixture "
                               "WHERE stage = :s AND status = 'scheduled'"), {"s": stage}).all():
        home_wins = f.home_club_id < f.away_club_id
        conn.execute(text("UPDATE fixture SET status = 'played', home_goals = :h, away_goals = :a,"
                          " sim = 'test' WHERE id = :i"),
                     {"h": 2 if home_wins else 1, "a": 1 if home_wins else 2, "i": f.id})


@pytest.fixture(scope="module")
def career(tmp_path_factory: pytest.TempPathFactory) -> tuple[Engine, World, list[str]]:
    world = get_world()
    path = tmp_path_factory.mktemp("cwc") / "career.sqlite"
    shutil.copy(BASE_WORLD, path)
    engine = open_database(path)
    migrate(engine)
    with engine.begin() as conn:
        initialize_career(conn, world, None, None, seed=37)
    news: list[str] = []
    spec = world.defs.international.club_world_cup
    with engine.begin() as conn:
        meta = read_meta(conn)
        meta.current_date = draw_date(world, YEAR)
        write_meta(conn, meta)
        news += club_world_cup_day(conn, world, meta, draw_date(world, YEAR))
        for stage, month_day in (("CWC:G", spec.dates.groups[0]),
                                 ("CWC:R16", spec.dates.round_of_16),
                                 ("CWC:QF", spec.dates.quarter_finals),
                                 ("CWC:SF", spec.dates.semi_finals),
                                 ("CWC:F", spec.dates.final)):
            day = date(YEAR, int(month_day[:2]), int(month_day[3:]))
            news += club_world_cup_day(conn, world, meta, day)
            _play(conn, stage)
            news += club_world_cup_day(conn, world, meta, day)
    return engine, world, news


def test_guest_clubs_have_squads_of_their_country(career: tuple[Engine, World, list[str]]
                                                  ) -> None:
    engine, world, _ = career
    with engine.connect() as conn:
        guests = conn.execute(text("SELECT g.club_id, c.name, g.level FROM guest_club g "
                                   "JOIN club c ON c.id = g.club_id")).all()
        assert len(guests) == len(world.defs.international.club_world_cup.guests)
        day = read_meta(conn).current_date
        for g in guests:
            sheet = team_sheet(conn, world, g.club_id, day)
            rating = sum(sp.rating for sp in sheet.starters) / 11
            assert abs(rating - g.level) < 3.0, g.name
        # Al Ahly's players are Egypt's home-based players too.
        egypt = conn.execute(text(
            "SELECT COUNT(*) FROM guest_player p JOIN national_pool n ON n.player_id = p.player_id "
            "JOIN club c ON c.id = p.club_id WHERE c.name = 'Al Ahly' AND n.code = 'EGY'")
            ).scalar_one()
        assert egypt == 26
        assert conn.execute(text("SELECT COUNT(*) FROM club_finance WHERE club_id IN "
                                 "(SELECT club_id FROM guest_club)")).scalar_one() == 0


def test_entrants_follow_the_shares(career: tuple[Engine, World, list[str]]) -> None:
    engine, world, _ = career
    spec = world.defs.international.club_world_cup
    with engine.connect() as conn:
        entrants = choose_entrants(conn, world, read_meta(conn), YEAR)
    assert len(entrants) == 32 and len({e.club_id for e in entrants}) == 32
    per = Counter(e.confederation for e in entrants if e.how != "Hosts")
    assert per == Counter({name: s.slots for name, s in spec.slots.items()})
    for name, slots in spec.slots.items():
        countries = Counter(e.country for e in entrants
                            if e.confederation == name and e.how != "Hosts")
        assert max(countries.values()) <= slots.per_country, name
    assert [e.country for e in entrants if e.how == "Hosts"] == [spec.host]
    assert {e.how for e in entrants if e.confederation in ("CAF", "OFC")} == {"Guest"}


def test_the_tournament_is_played_to_a_champion(career: tuple[Engine, World, list[str]]
                                                ) -> None:
    engine, world, news = career
    with engine.connect() as conn:
        tables = group_tables(conn)
        assert sorted(tables) == list(LETTERS) and all(len(t) == 4 for t in tables.values())
        confed = {int(r.club_id): str(r.conf) for r in conn.execute(text(
            "SELECT c.id AS club_id, COALESCE(g.confederation, 'X') AS conf FROM club c "
            "LEFT JOIN guest_club g ON g.club_id = c.id"))}
        counts = {s: conn.execute(text("SELECT COUNT(*) FROM fixture WHERE stage = :s"),
                                  {"s": s}).scalar_one()
                  for s in ("CWC:G", "CWC:R16", "CWC:QF", "CWC:SF", "CWC:F")}
        assert counts == {"CWC:G": 48, "CWC:R16": 8, "CWC:QF": 4, "CWC:SF": 2, "CWC:F": 1}
        assert conn.execute(text("SELECT COUNT(*) FROM fixture WHERE stage LIKE 'CWC:%' "
                                 "AND neutral = 0")).scalar_one() == 0
        # No group has two guests of one confederation.
        for table in tables.values():
            guests = Counter(confed[r.club_id] for r in table if confed[r.club_id] != "X")
            assert all(n <= 1 for n in guests.values())
        prizes = conn.execute(text(
            "SELECT COUNT(DISTINCT l.club_id) FROM finance_ledger l JOIN competition c "
            "ON c.id = l.ref_id WHERE c.key = 'CWC' AND l.kind = 'prize'")).scalar_one()
        assert prizes > 20
    assert any("win the 2029 FIFA Club World Cup" in m for m in news)
    assert any(m.startswith("The 2029 Club World Cup draw") for m in news)


def test_the_page_before_the_draw(tmp_path: Path) -> None:
    client = TestClient(create_app(session=CareerSession(tmp_path / "saves", BASE_WORLD),
                                   frontend=None))
    league = next(lg for lg in client.get("/api/world/leagues").json() if lg["key"] == "ENG4")
    client.post("/api/saves/1/new", json={"club_id": league["clubs"][0]["id"],
                                          "manager_name": "Tester"})
    view = client.get("/api/international/club-world-cup").json()
    assert view["year"] == YEAR and view["draw"] == "2028-12-05" and view["host"] == "USA"
    assert view["entrants"] == [] and view["groups"] == [] and view["rounds"] == []

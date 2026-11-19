"""National teams (W8 I1, world/international): every FIFA member but Russia has a team in a new
career, with a 26-man squad of its own nationality. Nations whose players are mostly at home,
in leagues the game doesn't simulate, are filled out with made-up home-based players at their
real strength; nations with a league in the game only fill empty places. The made-up players
stay out of the market. Needs the built world."""

import shutil
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from footsim.api.app import create_app
from footsim.api.session import CareerSession
from footsim.core.paths import data_dir
from footsim.persistence.database import open_database
from footsim.persistence.migrations import migrate
from footsim.world.career import initialize_career
from footsim.world.context import World, get_world
from footsim.world.international import ensure_international
from footsim.world.international.common import nation_ids
from footsim.world.meta import read_meta
from footsim.world.squads import team_sheet
from footsim.world.transfers import Move, MoveRefused, validate_move

BASE_WORLD = data_dir() / "worlds" / "base-2026-27.sqlite"
pytestmark = pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")


@pytest.fixture(scope="module")
def career(tmp_path_factory: pytest.TempPathFactory) -> tuple[Engine, World]:
    world = get_world()
    path = tmp_path_factory.mktemp("intl") / "career.sqlite"
    shutil.copy(BASE_WORLD, path)
    engine = open_database(path)
    migrate(engine)
    with engine.begin() as conn:
        initialize_career(conn, world, None, None, seed=17)
    return engine, world


def _club(engine: Engine, code: str) -> int:
    with engine.connect() as conn:
        return int(conn.execute(text("SELECT club_id FROM national_team WHERE code = :c"),
                                {"c": code}).scalar_one())


def test_every_nation_has_a_squad_of_its_own(career: tuple[Engine, World]) -> None:
    engine, world = career
    size = world.defs.international.rules.squad_size
    with engine.connect() as conn:
        teams = conn.execute(text("SELECT code, club_id FROM national_team")).all()
        assert len(teams) == len(world.defs.international.teams) == 210
        assert "RUS" not in {t.code for t in teams}  # suspended
        ids = nation_ids(conn, world)
        pooled = {int(r.player_id): str(r.code) for r in conn.execute(text(
            "SELECT player_id, code FROM national_pool"))}
        for t in teams:
            squad = conn.execute(text(
                "SELECT s.player_id, p.nation_id FROM national_squad s JOIN person p "
                "ON p.id = s.player_id WHERE s.club_id = :c"), {"c": t.club_id}).all()
            assert len(squad) == size, t.code
            for r in squad:  # each of the nationality, or one of its made-up players
                assert r.nation_id in ids[t.code] or pooled.get(r.player_id) == t.code, t.code
        # A player is in one squad at most.
        assert conn.execute(text("SELECT COUNT(*) - COUNT(DISTINCT player_id) "
                                 "FROM national_squad")).scalar_one() == 0
        # Ensuring again changes nothing.
        before = conn.execute(text("SELECT COUNT(*) FROM national_pool")).scalar_one()
    with engine.begin() as conn:
        assert ensure_international(conn, world, read_meta(conn), read_meta(conn).current_date
                                    ) == []
        assert conn.execute(text("SELECT COUNT(*) FROM national_pool")).scalar_one() == before


def test_line_ups_follow_real_strength(career: tuple[Engine, World]) -> None:
    engine, world = career
    level = world.defs.international.rules.level
    covered = {lg.nation for lg in world.defs.leagues.values()}
    with engine.connect() as conn:
        day = read_meta(conn).current_date
        gaps = []
        for r in conn.execute(text("SELECT club_id, code, elo FROM national_team")).all():
            xi = float(np.mean([sp.rating for sp in team_sheet(conn, world, r.club_id, day)
                                .starters]))
            if r.code not in covered:  # made up to their Elo
                gaps.append(xi - level.of(r.elo))
        assert abs(float(np.mean(gaps))) < 1.0 and float(np.std(gaps)) < 2.5
        # Stronger nations field stronger teams: Spain over Egypt over Qatar over Tonga.
        xis = {code: float(np.mean([sp.rating for sp in team_sheet(
            conn, world, _club(engine, code), day).starters]))
            for code in ("ESP", "EGY", "QAT", "TGA")}
        assert xis["ESP"] > xis["EGY"] > xis["QAT"] > xis["TGA"]
        # Spain's squad is its real players: made-up ones fill no place it has players for.
        made_up = conn.execute(text("SELECT COUNT(*) FROM national_squad s JOIN national_pool n "
                                    "ON n.player_id = s.player_id WHERE s.club_id = :c"),
                               {"c": _club(engine, "ESP")}).scalar_one()
        assert made_up == 0


def test_made_up_players_stay_out_of_the_market(career: tuple[Engine, World]) -> None:
    engine, world = career
    with engine.begin() as conn:
        meta = read_meta(conn)
        pid = int(conn.execute(text("SELECT player_id FROM national_pool LIMIT 1")).scalar_one())
        buyer = int(conn.execute(text(
            "SELECT club_id FROM club_league_membership LIMIT 1")).scalar_one())
        with pytest.raises(MoveRefused, match="plays at home"):
            validate_move(conn, world, meta, Move(pid, buyer, 0, 100_000), meta.current_date)
        # National teams have no finances.
        assert conn.execute(text("SELECT COUNT(*) FROM club_finance WHERE club_id IN "
                                 "(SELECT club_id FROM national_team)")).scalar_one() == 0


def test_a_national_teams_club_page(tmp_path: Path) -> None:
    client = TestClient(create_app(session=CareerSession(tmp_path / "saves", BASE_WORLD),
                                   frontend=None))
    league = next(lg for lg in client.get("/api/world/leagues").json() if lg["key"] == "ENG4")
    client.post("/api/saves/1/new", json={"club_id": league["clubs"][0]["id"],
                                          "manager_name": "Tester"})
    found = client.get("/api/clubs/search", params={"q": "Egypt"}).json()
    egypt = next(c for c in found if c["name"] == "Egypt")
    assert client.get(f"/api/clubs/{egypt['id']}").status_code == 200
    squad = client.get(f"/api/clubs/{egypt['id']}/players").json()
    assert len(squad) == 26
    # Made-up players don't show in the transfer search.
    names = {p["name"] for p in squad}
    hits = client.get("/api/transfers/search", params={"min_overall": 40}).json()
    assert not names & {p["name"] for p in hits if p.get("club") is None}

"""The World Cup finals (W8 I4, world/international/finals.py) and the editions after 2030
(world/international/editions.py), run quickly in a new career: the 2030 qualifiers (their
results filled in as in test_wc_qualifiers), then the finals: the 48 drawn into 12 groups with
the hosts heading groups A to C at home and the confederation rule kept; the squads called up
the day before; the round of 32 from the top two and the 8 best thirds without a group rematch;
single matches to the final, with the match for third place; the champion in the news and in
its trophy cabinet. Then the 2034 edition: its qualifiers drawn after the 2030 final in their own
stages, Saudi Arabia hosting, 48 through by the shares its hosts make, and its own finals' draw.
Needs the built world."""

from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine, text

from footsim.api.app import create_app
from footsim.api.session import CareerSession
from footsim.core.paths import data_dir
from footsim.world.context import World, get_world
from footsim.world.international.common import away_players
from footsim.world.international.editions import Edition, edition
from footsim.world.international.finals import finals_day, group_tables, state
from footsim.world.international.qualifiers import (
    _Teams,
    draw_day,
    qualified_teams,
    qualifiers_day,
    stage_days,
)
from footsim.world.meta import read_meta, write_meta

BASE_WORLD = data_dir() / "worlds" / "base-2026-27.sqlite"
pytestmark = pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")
SHARES_2034 = {"UEFA": 16, "CONMEBOL": 6, "CAF": 9, "AFC": 8, "CONCACAF": 6, "OFC": 1}


def _play(conn: Connection, stage: str) -> None:
    """Every scheduled fixture of ``stage``: the higher Elo wins 2-0, except groups' level
    pairs (1-1); a knockout never ends level."""
    teams = _Teams.load(conn)
    for f in conn.execute(text("SELECT id, home_club_id, away_club_id, tie FROM fixture "
                               "WHERE stage = :s AND status = 'scheduled'"), {"s": stage}).all():
        home, away = teams.elo[f.home_club_id], teams.elo[f.away_club_id]
        group = stage.endswith(":G") or (stage.startswith("WCQ:") and "-" not in (f.tie or ""))
        if group and abs(home - away) < 15:
            hg, ag = 1, 1
        else:
            hg, ag = (2, 0) if home >= away else (0, 2)
        conn.execute(text("UPDATE fixture SET status = 'played', home_goals = :h, "
                          "away_goals = :a, sim = 'test' WHERE id = :i"),
                     {"h": hg, "a": ag, "i": f.id})


def _qualify(conn: Connection, world: World, ed: Edition) -> list[str]:
    """An edition's qualifiers, each stage drawn on its day and played out."""
    meta = read_meta(conn)
    news: list[str] = []
    for stage in sorted(ed.stages, key=lambda s: draw_day(world, meta, s)):
        news += qualifiers_day(conn, world, meta, draw_day(world, meta, stage))
        for _ in range(3):  # semi-finals, then finals
            _play(conn, ed.qualifier_stage(stage.key))
            news += qualifiers_day(conn, world, meta, stage_days(world, meta, stage)[-1])
    return news


def _finals(conn: Connection, world: World, ed: Edition) -> list[str]:
    meta = read_meta(conn)
    spec = ed.dates
    news = finals_day(conn, world, meta, date.fromisoformat(spec.draw))
    first = date.fromisoformat(spec.groups[0])
    news += finals_day(conn, world, meta, first - timedelta(days=1))
    news.append(f"away:{len(away_players(conn, first))}")
    for rnd, day in (("G", spec.groups[-1]), ("R32", spec.round_of_32),
                     ("R16", spec.round_of_16), ("QF", spec.quarter_finals),
                     ("SF", spec.semi_finals), ("3P", spec.third_place), ("F", spec.final)):
        for _ in range(2):
            _play(conn, ed.finals_stage(rnd))
            news += finals_day(conn, world, meta, date.fromisoformat(day))
    return news


@pytest.fixture(scope="module")
def finals(tmp_path_factory: pytest.TempPathFactory
           ) -> tuple[TestClient, Engine, World, list[str]]:
    world = get_world()
    session = CareerSession(tmp_path_factory.mktemp("wcf") / "saves", BASE_WORLD)
    client = TestClient(create_app(session=session, frontend=None))
    league = next(lg for lg in client.get("/api/world/leagues").json() if lg["key"] == "ENG4")
    client.post("/api/saves/1/new", json={"club_id": league["clubs"][0]["id"],
                                          "manager_name": "Tester"})
    ed = edition(world, 2030)
    with session.write() as conn:
        _qualify(conn, world, ed)
        news = _finals(conn, world, ed)
    return client, session.engine, world, news


def test_the_draw(finals: tuple[TestClient, Engine, World, list[str]]) -> None:
    _, engine, world, news = finals
    ed = edition(world, 2030)
    hosts = set(ed.hosts)
    with engine.connect() as conn:
        teams = _Teams.load(conn)
        elo = teams.elo
        tables = group_tables(conn, ed, elo)
        assert len(tables) == 12 and all(len(t) == 4 for t in tables.values())
        for letter, table in tables.items():
            confed = Counter(teams.confederation[r.club_id] for r in table)
            assert all(n <= (2 if c == "UEFA" else 1) for c, n in confed.items()), letter
        heads = {letter: {teams.code[r.club_id] for r in table} & hosts
                 for letter, table in tables.items()}
        assert heads["A"] and heads["B"] and heads["C"]
        # Hosts at home, everyone else neutral.
        for f in conn.execute(text("SELECT home_club_id, neutral FROM fixture WHERE stage = :s"),
                              {"s": ed.groups}):
            assert (f.neutral == 0) == (teams.code[f.home_club_id] in hosts)
    assert any(m.startswith("The 2030 World Cup draw") for m in news)
    away = next(m for m in news if m.startswith("away:"))
    assert int(away.split(":")[1]) >= 48 * 25


def test_the_knockouts_to_a_champion(finals: tuple[TestClient, Engine, World, list[str]]
                                     ) -> None:
    _, engine, world, news = finals
    ed = edition(world, 2030)
    with engine.connect() as conn:
        counts = {s: conn.execute(text("SELECT COUNT(*) FROM fixture WHERE stage = :s"),
                                  {"s": s}).scalar_one()
                  for s in ("WCF:G", "WCF:R32", "WCF:R16", "WCF:QF", "WCF:SF", "WCF:3P",
                            "WCF:F")}
        assert counts == {"WCF:G": 72, "WCF:R32": 16, "WCF:R16": 8, "WCF:QF": 4, "WCF:SF": 2,
                          "WCF:3P": 1, "WCF:F": 1}
        group_of = {r.club_id: r.group for t in group_tables(conn, ed, {}).values() for r in t}
        for f in conn.execute(text("SELECT home_club_id, away_club_id FROM fixture "
                                   "WHERE stage = 'WCF:R32'")):
            assert group_of[f.home_club_id] != group_of[f.away_club_id]
    assert any("win the 2030 World Cup" in m for m in news)


def _trophies(client: TestClient, club_id: int) -> list[dict[str, Any]]:
    response = client.get(f"/api/clubs/{club_id}/history")
    assert response.status_code == 200, response.text
    return list(response.json()["trophies"])


def test_the_champion_has_the_trophy(finals: tuple[TestClient, Engine, World, list[str]]
                                     ) -> None:
    client, engine, world, _ = finals
    with engine.connect() as conn:
        champion = state(conn, edition(world, 2030))["champion"]
        final = conn.execute(text("SELECT home_club_id, away_club_id FROM fixture "
                                  "WHERE stage = 'WCF:F'")).one()
    runner_up = final.away_club_id if final.home_club_id == champion else final.home_club_id
    assert _trophies(client, champion) == [
        {"kind": "world", "key": "WC", "name": "FIFA World Cup", "seasons": ["2030"]}]
    assert _trophies(client, runner_up) == []
    view = client.get("/api/international/world-cup?year=2030").json()
    assert view["champion"]["id"] == champion


def test_the_2034_edition_follows(finals: tuple[TestClient, Engine, World, list[str]]) -> None:
    client, engine, world, _ = finals
    ed = edition(world, 2034)
    assert ed.hosts == ("KSA",)
    with engine.begin() as conn:
        meta = read_meta(conn)
        first = min(ed.stages, key=lambda s: draw_day(world, meta, s))
        assert draw_day(world, meta, first) > edition(world, 2030).final_day
        # Nothing of 2034's is drawn before its first stage's day.
        qualifiers_day(conn, world, meta, draw_day(world, meta, first) - timedelta(days=1))
        assert conn.execute(text("SELECT COUNT(*) FROM fixture WHERE stage LIKE 'WCQ:2034:%'")
                            ).scalar_one() == 0
        news = _qualify(conn, world, ed)
        teams = _Teams.load(conn)
        by_code = {code: c for c, code in teams.code.items()}
        drawn = {r.stage for r in conn.execute(text(
            "SELECT DISTINCT f.stage FROM fixture f JOIN competition c "
            "ON c.id = f.competition_id WHERE c.key = 'WCQ2034'"))}
        assert drawn == {ed.qualifier_stage(s.key) for s in ed.stages}
        # The hosts play no qualifiers; 48 are through by 2034's shares.
        assert conn.execute(text("SELECT COUNT(*) FROM fixture WHERE stage LIKE 'WCQ:2034:%' "
                                 "AND :k IN (home_club_id, away_club_id)"),
                            {"k": by_code["KSA"]}).scalar_one() == 0
        through = qualified_teams(conn, ed)
        assert len(through) == 48 and through["KSA"] == "Hosts"
        per = Counter(teams.confederation[by_code[code]] for code in through)
        for conf, share in SHARES_2034.items():
            extra = sum(1 for code, how in through.items() if how == "Intercontinental play-off"
                        and teams.confederation[by_code[code]] == conf)
            assert per[conf] == share + extra, conf
        # 2030's qualifiers and finals are as they were.
        assert qualified_teams(conn, edition(world, 2030))["ESP"] == "Hosts"
        assert conn.execute(text("SELECT COUNT(*) FROM fixture WHERE stage = 'WCF:G'")
                            ).scalar_one() == 72
        news += finals_day(conn, world, meta, date.fromisoformat(ed.dates.draw))
        assert conn.execute(text("SELECT COUNT(*) FROM fixture WHERE stage = 'WCF:2034:G'")
                            ).scalar_one() == 72
        assert conn.execute(text("SELECT COUNT(*) FROM fixture WHERE stage = 'WCF:2034:G' "
                                 "AND neutral = 0")).scalar_one() == 3  # the hosts' games
        meta.current_date = date(2031, 10, 1)
        write_meta(conn, meta)
    assert any(m.startswith("World Cup 2034:") for m in news)
    assert any(m.startswith("The 2034 World Cup draw") for m in news)
    # The pages show the next edition once 2030's is over.
    qualifiers = client.get("/api/international/qualifiers").json()
    assert qualifiers["cycle"] == 2034 and all(s["drawn"] for s in qualifiers["stages"])
    assert qualifiers["stages"][0]["starts"].startswith("203")
    assert client.get("/api/international/world-cup").json()["year"] == 2034
    assert client.get("/api/international/world-cup?year=2031").status_code == 404


def test_the_page_before_the_draw(tmp_path: Path) -> None:
    client = TestClient(create_app(session=CareerSession(tmp_path / "saves", BASE_WORLD),
                                   frontend=None))
    league = next(lg for lg in client.get("/api/world/leagues").json() if lg["key"] == "ENG4")
    client.post("/api/saves/1/new", json={"club_id": league["clubs"][0]["id"],
                                          "manager_name": "Tester"})
    view = client.get("/api/international/world-cup").json()
    assert view["year"] == 2030 and view["draw"] == "2030-04-05"
    assert view["groups"] == [] and view["rounds"] == [] and view["champion"] is None

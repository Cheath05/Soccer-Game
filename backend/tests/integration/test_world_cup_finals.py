"""The World Cup 2030 finals (W8 I4, world/international/finals.py), run quickly after the
qualifiers (their results filled in as in test_wc_qualifiers): the 48 drawn into 12 groups with
the hosts heading groups A to C at home and the confederation rule kept; the squads called up
the day before; the round of 32 from the top two and the 8 best thirds without a group rematch;
single matches to the final, with the match for third place; the champion in the news. Needs
the built world."""

import shutil
from collections import Counter
from datetime import date, timedelta
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
from footsim.world.international.common import away_players
from footsim.world.international.finals import GROUPS, finals_day, group_tables
from footsim.world.international.qualifiers import (
    STAGE,
    _Teams,
    draw_day,
    qualifiers_day,
    stage_days,
)
from footsim.world.meta import read_meta

BASE_WORLD = data_dir() / "worlds" / "base-2026-27.sqlite"
pytestmark = pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")


def _play(conn: Connection, stage: str) -> None:
    """Every scheduled fixture of ``stage``: the higher Elo wins 2-0, except groups' level
    pairs (1-1); a knockout never ends level."""
    teams = _Teams.load(conn)
    for f in conn.execute(text("SELECT id, home_club_id, away_club_id, tie FROM fixture "
                               "WHERE stage = :s AND status = 'scheduled'"), {"s": stage}).all():
        home, away = teams.elo[f.home_club_id], teams.elo[f.away_club_id]
        group = stage in (GROUPS,) or (stage.startswith(STAGE) and "-" not in (f.tie or ""))
        if group and abs(home - away) < 15:
            hg, ag = 1, 1
        else:
            hg, ag = (2, 0) if home >= away else (0, 2)
        conn.execute(text("UPDATE fixture SET status = 'played', home_goals = :h, "
                          "away_goals = :a, sim = 'test' WHERE id = :i"),
                     {"h": hg, "a": ag, "i": f.id})


@pytest.fixture(scope="module")
def finals(tmp_path_factory: pytest.TempPathFactory) -> tuple[Engine, World, list[str]]:
    world = get_world()
    path = tmp_path_factory.mktemp("wcf") / "career.sqlite"
    shutil.copy(BASE_WORLD, path)
    engine = open_database(path)
    migrate(engine)
    with engine.begin() as conn:
        initialize_career(conn, world, None, None, seed=41)
    news: list[str] = []
    spec = world.defs.international.world_cup
    with engine.begin() as conn:
        meta = read_meta(conn)
        for stage in sorted(world.defs.international.qualifiers.stages,
                            key=lambda s: draw_day(world, meta, s)):
            qualifiers_day(conn, world, meta, draw_day(world, meta, stage))
            for _ in range(3):
                _play(conn, STAGE + stage.key)
                qualifiers_day(conn, world, meta, stage_days(world, meta, stage)[-1])
        news += finals_day(conn, world, meta, date.fromisoformat(spec.draw))
        first = date.fromisoformat(spec.groups[0])
        news += finals_day(conn, world, meta, first - timedelta(days=1))
        news.append(f"away:{len(away_players(conn, first))}")
        for stage, day in ((GROUPS, spec.groups[-1]), ("WCF:R32", spec.round_of_32),
                           ("WCF:R16", spec.round_of_16), ("WCF:QF", spec.quarter_finals),
                           ("WCF:SF", spec.semi_finals), ("WCF:3P", spec.third_place),
                           ("WCF:F", spec.final)):
            _play(conn, stage)
            news += finals_day(conn, world, meta, date.fromisoformat(day))
            _play(conn, stage)
            news += finals_day(conn, world, meta, date.fromisoformat(day))
    return engine, world, news


def test_the_draw(finals: tuple[Engine, World, list[str]]) -> None:
    engine, world, news = finals
    hosts = set(world.defs.international.qualifiers.hosts)
    with engine.connect() as conn:
        teams = _Teams.load(conn)
        elo = teams.elo
        tables = group_tables(conn, elo)
        assert len(tables) == 12 and all(len(t) == 4 for t in tables.values())
        for letter, table in tables.items():
            confed = Counter(teams.confederation[r.club_id] for r in table)
            assert all(n <= (2 if c == "UEFA" else 1) for c, n in confed.items()), letter
        heads = {letter: {teams.code[r.club_id] for r in table} & hosts
                 for letter, table in tables.items()}
        assert heads["A"] and heads["B"] and heads["C"]
        # Hosts at home, everyone else neutral.
        for f in conn.execute(text("SELECT home_club_id, neutral FROM fixture WHERE stage = :s"),
                              {"s": GROUPS}):
            assert (f.neutral == 0) == (teams.code[f.home_club_id] in hosts)
    assert any(m.startswith("The 2030 World Cup draw") for m in news)
    away = next(m for m in news if m.startswith("away:"))
    assert int(away.split(":")[1]) >= 48 * 25


def test_the_knockouts_to_a_champion(finals: tuple[Engine, World, list[str]]) -> None:
    engine, _, news = finals
    with engine.connect() as conn:
        counts = {s: conn.execute(text("SELECT COUNT(*) FROM fixture WHERE stage = :s"),
                                  {"s": s}).scalar_one()
                  for s in ("WCF:G", "WCF:R32", "WCF:R16", "WCF:QF", "WCF:SF", "WCF:3P",
                            "WCF:F")}
        assert counts == {"WCF:G": 72, "WCF:R32": 16, "WCF:R16": 8, "WCF:QF": 4, "WCF:SF": 2,
                          "WCF:3P": 1, "WCF:F": 1}
        group_of = {r.club_id: r.group for t in group_tables(conn, {}).values() for r in t}
        for f in conn.execute(text("SELECT home_club_id, away_club_id FROM fixture "
                                   "WHERE stage = 'WCF:R32'")):
            assert group_of[f.home_club_id] != group_of[f.away_club_id]
    assert any("win the 2030 World Cup" in m for m in news)


def test_the_page_before_the_draw(tmp_path: Path) -> None:
    client = TestClient(create_app(session=CareerSession(tmp_path / "saves", BASE_WORLD),
                                   frontend=None))
    league = next(lg for lg in client.get("/api/world/leagues").json() if lg["key"] == "ENG4")
    client.post("/api/saves/1/new", json={"club_id": league["clubs"][0]["id"],
                                          "manager_name": "Tester"})
    view = client.get("/api/international/world-cup").json()
    assert view["year"] == 2030 and view["draw"] == "2030-04-05"
    assert view["groups"] == [] and view["rounds"] == [] and view["champion"] is None

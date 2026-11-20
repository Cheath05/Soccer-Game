"""The user as a national team's manager (W8 I5, world/international/manager.py). A watch-only
career (every league on fast results, to be quick) takes Wales's job and calls up its own 23 with
its own formation; the first window's call-ups keep them; the advance stops at Wales's friendly
as the user's match, which plays as Instant (the agent engine) and the next one follows. Then the
API: the job, the call-ups, the country's tactics and the career's next match. Needs the built
world."""

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from footsim.api.app import create_app
from footsim.api.session import CareerSession
from footsim.core.paths import data_dir
from footsim.persistence.database import open_database
from footsim.persistence.migrations import migrate
from footsim.world import fast_sim
from footsim.world.career import advance, initialize_career, play_user_instant, set_user_tactic
from footsim.world.context import World, get_world
from footsim.world.international import manager
from footsim.world.meta import read_meta

BASE_WORLD = data_dir() / "worlds" / "base-2026-27.sqlite"
pytestmark = pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")
CODE = "WAL"


@pytest.fixture(scope="module")
def career(tmp_path_factory: pytest.TempPathFactory) -> tuple[Engine, World, dict[str, object]]:
    world = get_world()
    path = tmp_path_factory.mktemp("manager") / "career.sqlite"
    shutil.copy(BASE_WORLD, path)
    engine = open_database(path)
    migrate(engine)
    seen: dict[str, object] = {}
    with engine.begin() as conn:
        initialize_career(conn, world, None, None, seed=29,
                          fast_leagues=list(fast_sim.selectable(world)))
        meta = read_meta(conn)
        nation = manager.take_job(conn, world, meta, CODE, meta.current_date)
        picked = [c.player_id for c in manager.candidates(conn, world, meta) if c.selected]
        seen["auto"] = len(picked)
        mine = [c.player_id for c in manager.candidates(conn, world, meta)][:23]
        manager.set_squad(conn, world, meta, mine)
        seen["mine"] = set(mine)
        set_user_tactic(conn, world, "4-4-2", {}, None, {}, club_id=nation)
    stops: list[tuple[str, int | None]] = []
    while len(stops) < 2:
        with engine.begin() as conn:
            result = advance(conn, world)
            stops.append((result.stop, result.fixture_id))
            assert result.stop == "match", result.stop
            meta = read_meta(conn)
            fx = conn.execute(text("SELECT * FROM fixture WHERE id = :i"),
                              {"i": result.fixture_id}).one()
            play_user_instant(conn, world, meta, fx, meta.current_date)
    with engine.connect() as conn:
        seen["squad"] = {int(r[0]) for r in conn.execute(text(
            "SELECT player_id FROM national_squad WHERE club_id = :c"), {"c": nation})}
        seen["formation"] = conn.execute(text("SELECT formation FROM tactic WHERE club_id = :c"),
                                         {"c": nation}).scalar_one()
        seen["played"] = conn.execute(text(
            "SELECT id, home_club_id, away_club_id, sim, status FROM fixture "
            "WHERE id IN (SELECT value FROM json_each(:i))"),
            {"i": str([s[1] for s in stops])}).all()
    seen["nation"] = nation
    return engine, world, seen


def test_the_squad_and_tactic_are_the_users(career: tuple[Engine, World, dict[str, object]]
                                            ) -> None:
    _, world, seen = career
    assert seen["auto"] == manager.squad_size(world)  # picked for him when he took the job
    assert seen["squad"] == seen["mine"]  # the window's call-ups kept his 23
    assert seen["formation"] == "4-4-2"


def test_the_nations_matches_are_the_users(career: tuple[Engine, World, dict[str, object]]
                                           ) -> None:
    _, _, seen = career
    played = seen["played"]
    assert isinstance(played, list) and len(played) == 2
    for f in played:
        assert seen["nation"] in (f.home_club_id, f.away_club_id)
        assert f.status == "played" and f.sim == "instant"


def test_the_api(tmp_path: Path) -> None:
    client = TestClient(create_app(session=CareerSession(tmp_path / "saves", BASE_WORLD),
                                   frontend=None))
    league = next(lg for lg in client.get("/api/world/leagues").json() if lg["key"] == "ENG1")
    client.post("/api/saves/1/new", json={"club_id": league["clubs"][0]["id"],
                                          "manager_name": "Tester"})
    assert client.get("/api/international/my-team").json()["team"] is None
    assert client.get("/api/tactics", params={"team": "nation"}).status_code == 404
    assert client.post("/api/international/job", json={"code": "XXX"}).status_code == 404
    view = client.post("/api/international/job", json={"code": CODE}).json()
    assert view["code"] == CODE and view["fixtures"] == []  # friendlies come with a window
    assert sum(p["selected"] for p in view["players"]) == view["squad_size"]
    ids = [p["id"] for p in view["players"]]
    assert client.put("/api/international/my-team/squad",
                      json={"player_ids": ids[:5]}).status_code == 400
    view = client.put("/api/international/my-team/squad", json={"player_ids": ids[:20]}).json()
    assert {p["id"] for p in view["players"] if p["selected"]} == set(ids[:20])
    tactics = client.get("/api/tactics", params={"team": "nation"}).json()
    assert {s["player_id"] for s in tactics["starters"]} <= set(ids[:20])
    career = client.get("/api/career").json()
    assert career["nation"]["id"] == view["team"]["id"]
    assert career["next_fixture"] is not None
    assert client.delete("/api/international/job").json()["team"] is None
    assert client.get("/api/career").json()["nation"] is None

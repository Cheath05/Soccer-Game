"""Contracts running out (W4-7): AI clubs keep the players in their plans and let the rest go;
the user's players leave unless renewed; reminders come in spring.

Skipped when the base world hasn't been built (it needs the locally downloaded EA FC 27 file,
which isn't in the repository)."""

from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from footsim.api.app import create_app
from footsim.api.session import CareerSession
from footsim.core.paths import data_dir
from footsim.world.context import get_world
from footsim.world.meta import read_meta
from footsim.world.renewals import contract_reminders, settle_expiring

BASE_WORLD = data_dir() / "worlds" / "base-2026-27.sqlite"
pytestmark = pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")
SEASON_END = date(2027, 6, 30)
NEXT_END = date(2028, 6, 30)


@pytest.fixture
def game(tmp_path: Path) -> tuple[TestClient, CareerSession, int]:
    session = CareerSession(tmp_path / "saves", BASE_WORLD)
    client = TestClient(create_app(session=session, frontend=None))
    league = next(lg for lg in client.get("/api/world/leagues").json() if lg["key"] == "ENG2")
    club_id = int(league["clubs"][0]["id"])
    client.post("/api/saves/1/new", json={"club_id": club_id, "manager_name": "Renewer"})
    return client, session, club_id


def _club(session: CareerSession, key: str, index: int) -> int:
    with session.read() as conn:
        return int(conn.execute(text(
            "SELECT m.club_id FROM club_league_membership m JOIN competition c ON c.id = "
            "m.competition_id WHERE c.key = :k ORDER BY m.club_id LIMIT 1 OFFSET :i"),
            {"k": key, "i": index}).scalar_one())


def test_an_ai_club_keeps_its_team_and_lets_the_rest_go(
        game: tuple[TestClient, CareerSession, int]) -> None:
    client, session, user = game
    ai = _club(session, "ENG1", 0)
    with session.write() as conn:
        conn.execute(text("UPDATE contract SET end_date = :e WHERE club_id IN (:a, :u) "
                          "AND is_active = 1"), {"e": SEASON_END.isoformat(), "a": ai, "u": user})
        before = conn.execute(text("SELECT COUNT(*) FROM contract WHERE club_id = :a "
                                   "AND is_active = 1"), {"a": ai}).scalar_one()
        news = settle_expiring(conn, get_world(), read_meta(conn), SEASON_END, NEXT_END)
        kept = conn.execute(text("SELECT COUNT(*) FROM contract WHERE club_id = :a AND "
                                 "is_active = 1 AND end_date >= :n"),
                            {"a": ai, "n": NEXT_END.isoformat()}).scalar_one()
        gone = conn.execute(text("SELECT COUNT(*) FROM transfer WHERE from_club_id = :a "
                                 "AND kind = 'expired'"), {"a": ai}).scalar_one()
        stale = conn.execute(text("SELECT COUNT(*) FROM contract WHERE is_active = 1 AND "
                                  "end_date <= :e"), {"e": SEASON_END.isoformat()}).scalar_one()
        users_left = conn.execute(text("SELECT COUNT(*) FROM contract WHERE club_id = :u AND "
                                       "is_active = 1"), {"u": user}).scalar_one()
    assert kept + gone == before
    assert kept >= 16 and gone >= 1  # the team stays, the spare and the old go
    assert stale == 0  # nobody is left on an expired contract
    # The user renewed nobody: all of them would leave, but the club keeps the squad floor
    # (its best leavers sign on for a year), and the news says who goes and who stays.
    floor = get_world().defs.lifecycle.squads.user_min_players
    assert users_left == floor
    assert sum("contract runs out" in n for n in news) > 5
    assert sum("another year" in n for n in news) == floor


def test_renewals_are_the_same_every_time(game: tuple[TestClient, CareerSession, int]) -> None:
    client, session, user = game
    ai = _club(session, "ENG1", 1)
    results = []
    for _ in range(2):
        with session.engine.connect() as conn:
            transaction = conn.begin()
            conn.execute(text("UPDATE contract SET end_date = :e WHERE club_id = :a AND "
                              "is_active = 1"), {"e": SEASON_END.isoformat(), "a": ai})
            settle_expiring(conn, get_world(), read_meta(conn), SEASON_END, NEXT_END)
            results.append(conn.execute(text(
                "SELECT person_id, end_date, wage_weekly_cents, is_active FROM contract "
                "WHERE club_id = :a ORDER BY id"), {"a": ai}).all())
            transaction.rollback()
    assert results[0] == results[1]


def test_the_user_renews_whom_they_want(game: tuple[TestClient, CareerSession, int]) -> None:
    client, session, user = game
    squad = client.get(f"/api/clubs/{user}/squad").json()
    star = max(squad, key=lambda p: p["overall"])["id"]
    with session.write() as conn:
        conn.execute(text("UPDATE contract SET end_date = :e WHERE person_id = :p AND "
                          "is_active = 1"), {"e": SEASON_END.isoformat(), "p": star})
    expiring = client.get("/api/transfers/contracts").json()
    terms = next(e for e in expiring if e["player_id"] == star)  # others may end too (the data)
    assert terms["willing"] and terms["asks_eur"] >= terms["wage_eur"]
    low = client.post(f"/api/transfers/contracts/{star}/renew",
                      json={"wage_eur": terms["asks_eur"] - 100})
    assert low.status_code == 409 and "wants at least" in low.json()["detail"]
    budget = client.get("/api/finances").json()["budget_eur"]
    done = client.post(f"/api/transfers/contracts/{star}/renew", json={})
    assert done.status_code == 200 and "new contract" in done.json()["message"]
    assert star not in {e["player_id"] for e in client.get("/api/transfers/contracts").json()}
    assert client.get("/api/finances").json()["budget_eur"] <= budget  # the raise is paid for
    with session.write() as conn:
        news = settle_expiring(conn, get_world(), read_meta(conn), SEASON_END, NEXT_END)
        active = conn.execute(text("SELECT is_active FROM contract WHERE person_id = :p AND "
                                   "club_id = :u ORDER BY id DESC LIMIT 1"),
                              {"p": star, "u": user}).scalar_one()
    assert active == 1  # renewed: he stays, while the others ending now leave
    assert all("contract runs out" in n or "another year" in n for n in news)


def test_the_user_is_reminded_in_spring(game: tuple[TestClient, CareerSession, int]) -> None:
    client, session, user = game
    with session.write() as conn:
        conn.execute(text("UPDATE contract SET end_date = :e WHERE club_id = :u AND "
                          "is_active = 1"), {"e": SEASON_END.isoformat(), "u": user})
        meta = read_meta(conn)
        world = get_world()
        assert contract_reminders(conn, world, meta, date(2027, 4, 1), SEASON_END)
        assert contract_reminders(conn, world, meta, date(2027, 4, 2), SEASON_END) == []

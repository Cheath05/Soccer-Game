"""The user's transfer market (W4-6): search, terms, offers answered at once by the club and the
player, listing, AI clubs' bids for the user's players, and sim-to-date stopping for them.

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
from footsim.world.career import advance
from footsim.world.context import get_world
from footsim.world.meta import read_meta, write_meta
from footsim.world.transfers import Move, complete_move

BASE_WORLD = data_dir() / "worlds" / "base-2026-27.sqlite"
pytestmark = pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")


@pytest.fixture
def game(tmp_path: Path) -> tuple[TestClient, CareerSession, int]:
    session = CareerSession(tmp_path / "saves", BASE_WORLD)
    client = TestClient(create_app(session=session, frontend=None))
    league = next(lg for lg in client.get("/api/world/leagues").json() if lg["key"] == "ENG1")
    club_id = int(league["clubs"][3]["id"])
    client.post("/api/saves/1/new", json={"club_id": club_id, "manager_name": "Buyer"})
    return client, session, club_id


def test_an_offer_is_answered_by_the_club_then_the_player(
        game: tuple[TestClient, CareerSession, int]) -> None:
    client, session, club_id = game
    found = client.get("/api/transfers/search", params={"min_overall": 66, "max_overall": 72,
                                                        "max_age": 27}).json()
    assert found and all(p["club"] is None or p["club"]["id"] != club_id for p in found)
    target = next(p for p in found if p["club"] is not None)
    terms = client.get(f"/api/transfers/terms/{target['id']}").json()
    assert terms["window_open"] and terms["wage_eur"] > 0 and terms["years"] >= 1
    # Far too little: rejected outright.
    low = client.post("/api/transfers/offer", json={"player_id": target["id"],
                                                    "fee_eur": 1000}).json()
    assert low["status"] == "rejected"
    # A little short: the club names its price; meeting it gets the player's answer.
    near = client.post("/api/transfers/offer", json={
        "player_id": target["id"], "fee_eur": int(terms["value_eur"] * 0.9)}).json()
    if near["status"] == "countered":
        near = client.post("/api/transfers/offer", json={"player_id": target["id"],
                                                         "fee_eur": near["fee_eur"]}).json()
    assert near["status"] in ("accepted", "rejected", "refused"), near
    if near["status"] == "accepted":
        squad = {p["id"] for p in client.get(f"/api/clubs/{club_id}/squad").json()}
        assert target["id"] in squad
        mine = client.get("/api/transfers/history", params={"mine": True}).json()
        assert mine[0]["player"]["id"] == target["id"] and mine[0]["yours"]
        money = client.get("/api/finances").json()
        assert any(t["kind"] == "transfer" for t in money["transactions"])


def test_a_free_agent_signs_for_his_wage_and_no_fee(
        game: tuple[TestClient, CareerSession, int]) -> None:
    client, session, club_id = game
    world = get_world()
    with session.write() as conn:
        meta = read_meta(conn)
        player = conn.execute(text(
            "SELECT k.person_id FROM contract k JOIN club_league_membership m ON m.club_id = "
            "k.club_id JOIN competition c ON c.id = m.competition_id WHERE c.key = 'ENG3' AND "
            "k.is_active = 1 AND k.kind = 'player' ORDER BY k.wage_weekly_cents DESC LIMIT 1"
        )).scalar_one()
        complete_move(conn, world, meta, Move(player, None), meta.current_date)
    assert client.post("/api/transfers/offer", json={"player_id": player, "fee_eur": 5}
                       ).json()["status"] == "refused"
    terms = client.get(f"/api/transfers/terms/{player}").json()
    assert terms["free_agent"]
    # A squad at the limit must make room first, like any club's ("The squad is full").
    limit = world.defs.lifecycle.squads.max_players
    squad = client.get(f"/api/clubs/{club_id}/squad").json()
    for p in sorted(squad, key=lambda p: p["overall"])[:max(0, len(squad) - limit + 1)]:
        client.post(f"/api/players/{p['id']}/release")
    stingy = client.post("/api/transfers/offer", json={
        "player_id": player, "fee_eur": 0, "wage_eur": terms["wage_eur"] // 2}).json()
    assert stingy["status"] == "rejected" and stingy["wage_eur"] == terms["wage_eur"]
    signed = client.post("/api/transfers/offer", json={"player_id": player, "fee_eur": 0}).json()
    assert signed["status"] == "accepted", signed
    assert "free transfer" in signed["message"]


def test_the_window_and_the_budget_bind_the_user_too(
        game: tuple[TestClient, CareerSession, int]) -> None:
    client, session, club_id = game
    target = client.get("/api/transfers/search", params={"min_overall": 85}).json()[0]
    pricey = client.post("/api/transfers/offer", json={"player_id": target["id"],
                                                       "fee_eur": 900_000_000}).json()
    assert pricey["status"] == "refused" and "budget" in pricey["message"]
    with session.write() as conn:
        meta = read_meta(conn)
        meta.current_date = date(2026, 10, 15)
        write_meta(conn, meta)
    closed = client.post("/api/transfers/offer", json={"player_id": target["id"],
                                                       "fee_eur": 1_000_000}).json()
    assert closed["status"] == "refused" and "window" in closed["message"]


def _bid(session: CareerSession, club_id: int, fee: int) -> tuple[int, int, int]:
    """An AI club's bid for the user's best-paid player, as the market makes one."""
    with session.write() as conn:
        meta = read_meta(conn)
        player = conn.execute(text(
            "SELECT person_id FROM contract WHERE club_id = :c AND is_active = 1 "
            "ORDER BY wage_weekly_cents DESC LIMIT 1"), {"c": club_id}).scalar_one()
        bidder = conn.execute(text(
            "SELECT m.club_id FROM club_league_membership m JOIN competition c ON c.id = "
            "m.competition_id WHERE c.key = 'ENG1' AND m.club_id != :c ORDER BY m.club_id "
            "LIMIT 1"), {"c": club_id}).scalar_one()
        offer = conn.execute(text(
            "INSERT INTO transfer_offer (player_id, bidder_club_id, owner_club_id, kind, status, "
            "fee_cents, wage_weekly_cents, years, created, expires, by_user) VALUES (:p, :b, :c, "
            "'transfer', 'pending', :f, 5000000, 3, :d, :e, 0)"),
            {"p": player, "b": bidder, "c": club_id, "f": fee * 100,
             "d": meta.current_date.isoformat(), "e": "2026-08-30"}).lastrowid
    return int(offer), int(player), int(bidder)


def test_the_user_answers_bids_for_their_players(
        game: tuple[TestClient, CareerSession, int]) -> None:
    client, session, club_id = game
    offer, player, bidder = _bid(session, club_id, 2_000_000)
    bids = client.get("/api/transfers/bids").json()
    assert [b["id"] for b in bids] == [offer] and bids[0]["bidder"]["id"] == bidder
    # Asking far too much: they walk away.
    walked = client.post(f"/api/transfers/bids/{offer}",
                         json={"action": "counter", "fee_eur": 2_000_000_000}).json()
    assert walked["status"] == "rejected" and client.get("/api/transfers/bids").json() == []
    offer, player, bidder = _bid(session, club_id, 2_000_000)
    assert client.post(f"/api/transfers/bids/{offer}", json={"action": "reject"}
                       ).json()["status"] == "rejected"
    offer, player, bidder = _bid(session, club_id, 2_000_000)
    sold = client.post(f"/api/transfers/bids/{offer}", json={"action": "accept"}).json()
    assert sold["status"] == "accepted", sold
    squad = {p["id"] for p in client.get(f"/api/clubs/{club_id}/squad").json()}
    assert player not in squad
    assert client.post(f"/api/transfers/bids/{offer}", json={"action": "accept"}
                       ).json()["status"] == "refused"  # once only


def test_a_bid_for_a_users_player_stops_the_sim(
        game: tuple[TestClient, CareerSession, int]) -> None:
    client, session, club_id = game
    _bid(session, club_id, 1_000_000)  # made today, as the market would
    with session.write() as conn:
        result = advance(conn, get_world(), max_days=20)
    assert result.stop == "offer"
    assert (result.date - date(2026, 7, 1)).days == 1  # it stopped after the day it came


def test_the_user_lists_and_unlists_their_players(
        game: tuple[TestClient, CareerSession, int]) -> None:
    client, session, club_id = game
    squad = client.get(f"/api/clubs/{club_id}/squad").json()
    player = squad[-1]["id"]
    assert client.put(f"/api/transfers/listed/{player}").json() == {"listed": True}
    with session.read() as conn:
        assert conn.execute(text("SELECT listed FROM contract WHERE person_id = :p AND "
                                 "is_active = 1"), {"p": player}).scalar_one() == 1
    assert client.put(f"/api/transfers/listed/{player}", params={"listed": False}
                      ).json() == {"listed": False}
    other = client.get("/api/transfers/search").json()[0]["id"]
    assert client.put(f"/api/transfers/listed/{other}").status_code == 400


def test_the_user_borrows_and_lends(game: tuple[TestClient, CareerSession, int]) -> None:
    client, session, club_id = game
    # Borrowing: a young player a bigger club can spare.
    young = client.get("/api/transfers/search", params={"max_age": 21, "min_overall": 60}
                       ).json()
    answers = []
    for p in young[:15]:
        answer = client.post("/api/transfers/loan",
                             json={"player_id": p["id"], "share": 1.0}).json()
        answers.append(answer["status"])
        if answer["status"] == "accepted":
            loans = client.get("/api/transfers/loans").json()
            assert any(lo["player"]["id"] == p["id"] and not lo["yours_out"] for lo in loans)
            squad = {s["id"] for s in client.get(f"/api/clubs/{club_id}/squad").json()}
            assert p["id"] in squad
            break
    assert "accepted" in answers or set(answers) <= {"rejected", "refused"}
    # Lending: an AI club asks to borrow one of the user's players; accepting sends him there.
    with session.write() as conn:
        meta = read_meta(conn)
        player, wage_cents = conn.execute(text(
            "SELECT person_id, wage_weekly_cents FROM contract WHERE club_id = :c AND "
            "is_active = 1 AND kind = 'player' ORDER BY wage_weekly_cents LIMIT 1"),
            {"c": club_id}).one()
        borrower = conn.execute(text(
            "SELECT m.club_id FROM club_league_membership m JOIN competition c ON c.id = "
            "m.competition_id WHERE c.key = 'ENG4' ORDER BY m.club_id LIMIT 1")).scalar_one()
        offer = conn.execute(text(
            "INSERT INTO transfer_offer (player_id, bidder_club_id, owner_club_id, kind, status, "
            "fee_cents, wage_weekly_cents, years, created, expires, by_user) VALUES (:p, :b, :c, "
            "'loan', 'pending', 0, :w, NULL, :d, '2026-08-30', 0)"),
            {"p": player, "b": borrower, "c": club_id, "w": wage_cents // 2,
             "d": meta.current_date.isoformat()}).lastrowid
    bids = client.get("/api/transfers/bids").json()
    assert [b["kind"] for b in bids if b["id"] == offer] == ["loan"]
    assert client.post(f"/api/transfers/bids/{offer}", json={"action": "counter", "fee_eur": 1}
                       ).json()["status"] == "refused"
    lent = client.post(f"/api/transfers/bids/{offer}", json={"action": "accept"}).json()
    assert lent["status"] == "accepted", lent
    loans = client.get("/api/transfers/loans").json()
    assert any(lo["player"]["id"] == player and lo["yours_out"] for lo in loans)

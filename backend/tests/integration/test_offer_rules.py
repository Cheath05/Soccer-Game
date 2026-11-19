"""Settings → Transfer offers (world/offers.py): bids for the user's players can stop the game
(the default), wait without stopping, or be answered by the user's asking prices: sold at or
above the price, countered at it below, turned down for a player who isn't for sale; loan
requests accepted or turned down. Needs the built world."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from footsim.api.app import create_app
from footsim.api.session import CareerSession
from footsim.core.paths import data_dir
from footsim.world.career import advance
from footsim.world.context import get_world
from footsim.world.meta import read_meta

BASE_WORLD = data_dir() / "worlds" / "base-2026-27.sqlite"
pytestmark = pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")


@pytest.fixture
def game(tmp_path: Path) -> tuple[TestClient, CareerSession, int]:
    session = CareerSession(tmp_path / "saves", BASE_WORLD)
    client = TestClient(create_app(session=session, frontend=None))
    league = next(lg for lg in client.get("/api/world/leagues").json() if lg["key"] == "ENG1")
    club_id = int(league["clubs"][3]["id"])
    client.post("/api/saves/1/new", json={"club_id": club_id, "manager_name": "Seller"})
    return client, session, club_id


def _bid(session: CareerSession, club_id: int, fee: int, kind: str = "transfer",
         nth: int = 0) -> tuple[int, int, int]:
    """A pending AI bid (or loan request) for one of the user's squad players."""
    with session.write() as conn:
        meta = read_meta(conn)
        player = conn.execute(text(
            "SELECT person_id FROM contract WHERE club_id = :c AND is_active = 1 "
            "ORDER BY wage_weekly_cents DESC LIMIT 1 OFFSET :n"),
            {"c": club_id, "n": 5 + nth}).scalar_one()
        bidder = conn.execute(text(
            "SELECT m.club_id FROM club_league_membership m JOIN competition c ON c.id = "
            "m.competition_id WHERE c.key = 'ENG1' AND m.club_id != :c ORDER BY m.club_id "
            "LIMIT 1 OFFSET :n"), {"c": club_id, "n": nth}).scalar_one()
        offer = conn.execute(text(
            "INSERT INTO transfer_offer (player_id, bidder_club_id, owner_club_id, kind, status, "
            "fee_cents, wage_weekly_cents, years, created, expires, by_user) VALUES (:p, :b, :c, "
            ":k, 'pending', :f, 5000000, 3, :d, :e, 0)"),
            {"p": player, "b": bidder, "c": club_id, "k": kind, "f": fee * 100,
             "d": meta.current_date.isoformat(), "e": "2026-08-30"}).lastrowid
    return int(offer), int(player), int(bidder)


def _status(session: CareerSession, offer: int) -> str:
    with session.read() as conn:
        return str(conn.execute(text("SELECT status FROM transfer_offer WHERE id = :o"),
                                {"o": offer}).scalar_one())


def _club_of(session: CareerSession, player: int) -> int:
    with session.read() as conn:
        return int(conn.execute(text(
            "SELECT club_id FROM contract WHERE person_id = :p AND is_active = 1 "
            "AND kind != 'loan'"), {"p": player}).scalar_one())


def _day(session: CareerSession) -> list[str]:
    with session.write() as conn:
        return advance(conn, get_world(), max_days=1).messages


def test_bids_are_answered_by_the_asking_prices(
        game: tuple[TestClient, CareerSession, int]) -> None:
    client, session, club_id = game
    assert client.get("/api/settings/offers").json()["mode"] == "stop"  # the default
    assert client.put("/api/settings/offers", json={"mode": "auto"}).json()["mode"] == "auto"
    # At the asking price: sold.
    sold, sold_player, bidder = _bid(session, club_id, 20_000_000)
    assert client.put(f"/api/settings/asking-price/{sold_player}",
                      json={"fee_eur": 15_000_000}).json()["asking_prices"] == {
        str(sold_player): 15_000_000}
    # No price and no default: not for sale.
    kept, kept_player, _ = _bid(session, club_id, 5_000_000, nth=1)
    # Far below an absurd price: countered, and the bidder walks away.
    walked, walked_player, _ = _bid(session, club_id, 1_000_000, nth=2)
    client.put(f"/api/settings/asking-price/{walked_player}", json={"fee_eur": 2_000_000_000})
    news = _day(session)
    assert _status(session, sold) == "accepted" and _club_of(session, sold_player) == bidder
    assert _status(session, kept) == "rejected" and _club_of(session, kept_player) == club_id
    assert _status(session, walked) == "withdrawn" and _club_of(session, walked_player) == club_id
    assert any("sold." in m for m in news) and any("not for sale" in m for m in news)
    assert any("walked away" in m for m in news)
    assert client.get("/api/transfers/bids").json() == []
    # A cleared price, and a bad one refused.
    assert client.put(f"/api/settings/asking-price/{walked_player}",
                      json={"fee_eur": None}).json()["asking_prices"] == {
        str(sold_player): 15_000_000}
    assert client.put(f"/api/settings/asking-price/{walked_player}",
                      json={"fee_eur": -5}).status_code == 422
    assert client.put(f"/api/settings/asking-price/{sold_player}",
                      json={"fee_eur": 5}).status_code == 400  # not his player any more


def test_a_share_of_the_value_and_loan_requests(
        game: tuple[TestClient, CareerSession, int]) -> None:
    client, session, club_id = game
    client.put("/api/settings/offers", json={"mode": "auto", "value_pct": 50, "loans": "accept"})
    # A bid above half his value: sold without a price of his own.
    sold, player, bidder = _bid(session, club_id, 60_000_000)
    loan, _, _ = _bid(session, club_id, 0, kind="loan", nth=1)
    news = _day(session)
    assert _status(session, sold) == "accepted" and _club_of(session, player) == bidder, news
    assert _status(session, loan) == "accepted", news
    assert client.put("/api/settings/offers", json={"mode": "auto", "value_pct": 5}
                      ).status_code == 422
    assert client.put("/api/settings/offers", json={"mode": "never"}).status_code == 422


def test_waiting_bids_do_not_stop_the_game(game: tuple[TestClient, CareerSession, int]) -> None:
    client, session, club_id = game
    _bid(session, club_id, 5_000_000)
    with session.write() as conn:
        conn.execute(text("UPDATE transfer_offer SET created = :d"),
                     {"d": read_meta(conn).current_date.isoformat()})
    # The default stops for a bid that arrived today...
    with session.write() as conn:
        assert advance(conn, get_world(), max_days=3).stop == "offer"
    offer, _, _ = _bid(session, club_id, 5_000_000, nth=1)
    with session.write() as conn:
        conn.execute(text("UPDATE transfer_offer SET created = :d WHERE id = :o"),
                     {"d": read_meta(conn).current_date.isoformat(), "o": offer})
    # ..."wait" doesn't, and leaves it on the Transfers page.
    client.put("/api/settings/offers", json={"mode": "wait"})
    with session.write() as conn:
        assert advance(conn, get_world(), max_days=3).stop == "limit"
    assert _status(session, offer) == "pending"

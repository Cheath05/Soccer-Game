"""The finances page (W3-3, simplified in W3-4): the user's club's balance and one budget, a
month's money at today's rates, the changes in it, the one-off transactions, the optional board,
and the sandbox budget a new career can start with.

Skipped when the base world hasn't been built (it needs the locally downloaded EA FC 27 file,
which isn't in the repository)."""

from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from footsim.api import sim
from footsim.api.app import create_app
from footsim.api.session import CareerSession
from footsim.core.paths import data_dir
from footsim.persistence.schema import competition
from footsim.world.context import get_world
from footsim.world.finance import Entry, post, weeks_left
from footsim.world.meta import read_meta
from footsim.world.transfers import Move, complete_move

BASE_WORLD = data_dir() / "worlds" / "base-2026-27.sqlite"
pytestmark = pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")
END = date(2029, 6, 30)


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    session = CareerSession(tmp_path / "saves", BASE_WORLD)
    return TestClient(create_app(session=session, frontend=None))


def _club(client: TestClient, key: str, index: int = 0) -> int:
    league = next(lg for lg in client.get("/api/world/leagues").json() if lg["key"] == key)
    return int(league["clubs"][index]["id"])


def test_the_finances_page_follows_the_clubs_money(client: TestClient) -> None:
    club_id = _club(client, "ENG4")
    client.post("/api/saves/1/new", json={"club_id": club_id, "manager_name": "Tester"})
    start = client.get("/api/finances").json()
    assert start["club"]["id"] == club_id and start["league"]
    assert start["balance_eur"] > 0 and start["budget_eur"] > 0
    assert start["wage_capacity_weekly_eur"] >= start["wage_bill_weekly_eur"] > 0
    # A month at today's rates: TV money and commercial in, wages and running costs out, and the
    # profit is their sum. The page shows it once, however many months have passed.
    month = start["monthly"]
    assert month["tv_eur"] > 0 and month["commercial_eur"] > 0
    assert month["wages_eur"] < 0 and month["running_eur"] < 0
    assert month["profit_eur"] == (month["tv_eur"] + month["commercial_eur"]
                                   + month["wages_eur"] + month["running_eur"])
    assert start["season_profit_so_far_eur"] == 0 and start["changes"] == []
    assert [t["kind"] for t in start["transactions"]] == ["opening"]
    assert start["board_enabled"] is True
    board = start["board"]
    assert 1 <= board["target"] <= board["league_size"] and board["position"] is None
    assert board["confidence"] == 60 and board["mood"] == "Satisfied"

    # To the first match day, past the 1st of August: one month is settled. It is the season's
    # profit so far, not a list of transactions, and with only one settlement nothing has changed.
    stop = client.post("/api/career/advance").json()
    assert stop["stop"] == "match"
    later = client.get("/api/finances").json()
    assert abs(later["season_profit_so_far_eur"] - month["profit_eur"]) <= 4  # rounding
    assert abs(later["balance_eur"] - (start["balance_eur"] + month["profit_eur"])) <= 4
    assert [t["kind"] for t in later["transactions"]] == ["opening"]
    assert later["changes"] == [] and later["monthly"] == month


def test_a_sandbox_career_can_start_with_billions(client: TestClient) -> None:
    club_id = _club(client, "ENG4", 1)
    too_much = {"club_id": club_id, "manager_name": "Tester", "budget_eur": 10_000_000_001}
    assert client.post("/api/saves/1/new", json=too_much).status_code == 422
    rich = {"club_id": club_id, "manager_name": "Tester", "budget_eur": 2_000_000_000}
    assert client.post("/api/saves/1/new", json=rich).status_code == 200
    money = client.get("/api/finances").json()
    assert money["budget_eur"] == 2_000_000_000
    assert money["balance_eur"] >= 2_000_000_000  # the owner puts the cash in
    assert {t["kind"] for t in money["transactions"]} == {"opening", "adjustment"}
    overview = client.get(f"/api/clubs/{club_id}").json()
    assert overview["budget_eur"] == 2_000_000_000  # exact: it's the user's own
    # The budget used to be called the transfer budget: a client that still says so is heard.
    old = {"club_id": club_id, "manager_name": "Tester", "transfer_budget_eur": 3_000_000_000}
    assert client.post("/api/saves/1/new", json=old).status_code == 200
    assert client.get("/api/finances").json()["budget_eur"] == 3_000_000_000


def test_a_career_can_play_without_a_board(client: TestClient) -> None:
    club_id = _club(client, "ENG4", 2)
    start = {"club_id": club_id, "manager_name": "Tester", "board_enabled": False}
    assert client.post("/api/saves/1/new", json=start).status_code == 200
    money = client.get("/api/finances").json()
    assert money["board_enabled"] is False and money["board"] is None
    assert money["budget_eur"] == money["balance_eur"] > 0  # all their cash
    # With the sandbox it is all the cash the owner puts in, with no board to hold it back.
    rich = {**start, "budget_eur": 5_000_000_000}
    assert client.post("/api/saves/1/new", json=rich).status_code == 200
    money = client.get("/api/finances").json()
    assert money["board"] is None and money["budget_eur"] == 5_000_000_000
    assert money["balance_eur"] >= money["budget_eur"]


def test_the_board_can_be_switched_off_and_on(client: TestClient) -> None:
    club_id = _club(client, "ENG4")
    client.post("/api/saves/1/new", json={"club_id": club_id, "manager_name": "Tester"})
    on = client.get("/api/finances").json()
    assert on["board_enabled"] and on["board"] is not None

    off = client.put("/api/career/board", json={"enabled": False})
    assert off.status_code == 200
    off_money = off.json()
    assert off_money["board_enabled"] is False and off_money["board"] is None
    # Worked out again at once: all the club's cash.
    assert off_money["budget_eur"] == off_money["balance_eur"] != on["budget_eur"]
    assert client.get("/api/finances").json() == off_money

    # The choice is saved with the career.
    client.post("/api/saves/save")
    client.post("/api/saves/1/load")
    assert client.get("/api/finances").json()["board_enabled"] is False

    back = client.put("/api/career/board", json={"enabled": True}).json()
    assert back["board_enabled"] and back["budget_eur"] == on["budget_eur"]
    # The board's view was only hidden: its target and confidence are still there.
    assert back["board"]["target"] == on["board"]["target"]
    assert back["board"]["confidence"] == on["board"]["confidence"]
    assert client.put("/api/career/board", json={"enabled": "maybe"}).status_code == 422


def test_the_board_waits_while_the_game_is_simulating(client: TestClient,
                                                      monkeypatch: pytest.MonkeyPatch) -> None:
    client.post("/api/saves/1/new", json={"club_id": _club(client, "ENG4"),
                                          "manager_name": "Tester"})
    monkeypatch.setattr(sim, "running", lambda session: True)
    assert client.put("/api/career/board", json={"enabled": False}).status_code == 409
    monkeypatch.undo()
    assert client.get("/api/finances").json()["board_enabled"] is True


def _outfielder(client: TestClient, club_id: int) -> dict[str, object]:
    players = client.get(f"/api/clubs/{club_id}/players").json()
    return dict(next(p for p in players if p["position"] != "GK"))


def test_transactions_are_one_off_money_with_a_label_for_each(client: TestClient) -> None:
    mine, other = _club(client, "ENG4", 3), _club(client, "ENG4", 4)
    client.post("/api/saves/1/new", json={"club_id": mine, "manager_name": "Tester"})
    before = client.get("/api/finances").json()
    other_name = client.get(f"/api/clubs/{other}").json()["club"]["name"]
    bought, sold = _outfielder(client, other), _outfielder(client, mine)
    world, cup = get_world(), get_world().defs.cups["FA_CUP"]
    session: CareerSession = client.app.state.session
    with session.write() as conn:
        meta = read_meta(conn)
        today = meta.current_date
        weeks = weeks_left(conn, meta.season_id, today)
        sold_wage = int(conn.execute(text(
            "SELECT wage_weekly_cents FROM contract WHERE person_id = :p AND is_active = 1"),
            {"p": int(str(sold["id"]))}).scalar_one())
        # The user signs a player from the other club, and sells one of theirs to it.
        complete_move(conn, world, meta, Move(
            int(str(bought["id"])), mine, 150_000_00, 2_000_00, END, by_user=True), today)
        complete_move(conn, world, meta, Move(
            int(str(sold["id"])), other, 80_000_00, 2_000_00, END, by_user=True), today)
        cup_id = conn.execute(select(competition.c.id).where(competition.c.key == cup.key)
                              ).scalar_one()
        post(conn, today, meta.season_id, [Entry(mine, "prize", 12_345_00, cup_id)])
    after = client.get("/api/finances").json()
    got = [(t["kind"], t["label"], t["amount_eur"]) for t in after["transactions"]]
    # The latest first: the prize, the sale, the signing, then the opening balance. Wages are
    # not transactions: they are in the month, and the budget.
    assert got == [
        ("prize", f"{cup.name} prize money", 12_345),
        ("transfer", f"Sold {sold['name']} to {other_name}", 80_000),
        ("transfer", f"Signed {bought['name']} from {other_name}", -150_000),
        ("opening", "Opening balance", before["balance_eur"]),
    ]
    # The budget paid the signing's fee and his wage for the rest of the season, and got back a
    # share of the sale's fee and the wage the sold player no longer draws for those weeks.
    change = (-(150_000_00 + round(2_000_00 * weeks))
              + round(world.defs.finance.reinvest * 80_000_00) + round(sold_wage * weeks))
    assert after["budget_eur"] - before["budget_eur"] == pytest.approx(change / 100, abs=2)


def test_changes_in_the_months_money_are_listed_once(client: TestClient) -> None:
    """Relegated, a club's TV money falls: one change, not a lower line in every month."""
    club_id = _club(client, "ENG3")
    client.post("/api/saves/1/new", json={"club_id": club_id, "manager_name": "Tester"})
    session: CareerSession = client.app.state.session
    with session.write() as conn:
        meta = read_meta(conn)
        for day, tv in ((date(2026, 8, 1), 1_400_000), (date(2026, 9, 1), 1_400_000),
                        (date(2026, 10, 1), 720_000)):
            post(conn, day, meta.season_id, [
                Entry(club_id, "broadcast", tv * 100), Entry(club_id, "club_income", 800_000_00),
                Entry(club_id, "wages", -900_000_00), Entry(club_id, "operating", -500_000_00)])
    money = client.get("/api/finances").json()
    assert money["changes"] == [{"date": "2026-10-01", "label": "League TV money",
                                 "before_eur": 1_400_000, "after_eur": 720_000}]
    # The three months settled are the season's profit so far; none is a transaction.
    assert money["season_profit_so_far_eur"] == (1_400_000 + 1_400_000 + 720_000
                                                 + 3 * (800_000 - 900_000 - 500_000))
    assert [t["kind"] for t in money["transactions"]] == ["opening"]


def test_no_finances_page_without_a_club(client: TestClient) -> None:
    assert client.get("/api/finances").status_code in (404, 409)  # no career loaded

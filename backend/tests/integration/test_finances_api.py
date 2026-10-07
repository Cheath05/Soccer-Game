"""The finances page (W3-3): the user's club's money, and the sandbox budget a new career can
start with.

Skipped when the base world hasn't been built (it needs the locally downloaded EA FC 27 file,
which isn't in the repository)."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from footsim.api.app import create_app
from footsim.api.session import CareerSession
from footsim.core.paths import data_dir

BASE_WORLD = data_dir() / "worlds" / "base-2026-27.sqlite"
pytestmark = pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")


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
    assert start["balance_eur"] > 0 and start["transfer_budget_eur"] > 0
    assert start["wage_budget_weekly_eur"] >= start["wage_bill_weekly_eur"] > 0
    assert start["income"] == [] and start["expenses"] == [] and start["net_eur"] == 0
    assert [r["kind"] for r in start["recent"]] == ["opening"]
    board = start["board"]
    assert 1 <= board["target"] <= board["league_size"] and board["position"] is None
    assert board["confidence"] == 60 and board["mood"] == "Satisfied"

    # To the first match day, past the 1st of August: the month is settled, itemised.
    stop = client.post("/api/career/advance").json()
    assert stop["stop"] == "match"
    later = client.get("/api/finances").json()
    kinds = {x["kind"] for x in later["income"]} | {x["kind"] for x in later["expenses"]}
    assert kinds == {"broadcast", "club_income", "wages", "operating"}
    assert all(x["amount_eur"] > 0 for x in later["income"])
    assert all(x["amount_eur"] < 0 for x in later["expenses"])
    assert later["net_eur"] == sum(x["amount_eur"] for x in later["income"] + later["expenses"])
    assert abs(later["balance_eur"] - (start["balance_eur"] + later["net_eur"])) <= 4  # rounding


def test_a_sandbox_career_can_start_with_billions(client: TestClient) -> None:
    club_id = _club(client, "ENG4", 1)
    too_much = {"club_id": club_id, "manager_name": "Tester",
                "transfer_budget_eur": 10_000_000_001}
    assert client.post("/api/saves/1/new", json=too_much).status_code == 422
    rich = {"club_id": club_id, "manager_name": "Tester", "transfer_budget_eur": 2_000_000_000}
    assert client.post("/api/saves/1/new", json=rich).status_code == 200
    money = client.get("/api/finances").json()
    assert money["transfer_budget_eur"] == 2_000_000_000
    assert money["balance_eur"] >= 2_000_000_000  # the owner puts the cash in
    assert {r["kind"] for r in money["recent"]} == {"opening", "adjustment"}
    overview = client.get(f"/api/clubs/{club_id}").json()
    assert overview["transfer_budget_eur"] == 2_000_000_000  # exact: it's the user's own


def test_no_finances_page_without_a_club(client: TestClient) -> None:
    assert client.get("/api/finances").status_code in (404, 409)  # no career loaded

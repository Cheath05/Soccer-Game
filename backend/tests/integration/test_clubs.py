"""Browsing other clubs: a club overview and its squad as seen from outside, without what only
a club itself knows (its players' fitness and wages, its exact finances)."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from match_day import advance_to_match

from footsim.api.app import create_app
from footsim.api.session import CareerSession
from footsim.core.paths import data_dir
from footsim.persistence.schema import transfer

BASE_WORLD = data_dir() / "worlds" / "base-2026-27.sqlite"
pytestmark = pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    session = CareerSession(tmp_path / "saves", BASE_WORLD)
    return TestClient(create_app(session=session, frontend=None))


def _significant_figures(value: int) -> int:
    return len(str(value).rstrip("0"))


def test_another_clubs_profile_and_squad(client: TestClient) -> None:
    leagues = client.get("/api/world/leagues").json()
    premier = next(lg for lg in leagues if lg["key"] == "ENG1")
    mine, other = premier["clubs"][0], premier["clubs"][1]
    client.post("/api/saves/1/new", json={"club_id": mine["id"], "manager_name": "Tester"})

    overview = client.get(f"/api/clubs/{other['id']}").json()
    assert overview["club"]["name"] == other["name"] and not overview["own_club"]
    assert overview["competition"]["key"] == "ENG1"
    assert overview["position"] is None  # pre-season
    assert overview["manager"] is None and overview["recent_transfers"] == []
    assert overview["squad_size"] >= 18 and 16 < overview["average_age"] < 35
    assert len(overview["top_players"]) == 5
    assert overview["budget_eur"] > 0 and overview["wage_bill_weekly_eur"] > 0
    assert overview["balance_eur"] > 0
    assert "transfer_budget_eur" not in overview  # it is the club's one budget now
    for figure in ("wage_bill_weekly_eur", "budget_eur", "balance_eur"):
        assert _significant_figures(overview[figure]) <= 2, figure  # only a rough figure
    dates = [f["date"] for f in overview["upcoming"]]
    assert len(dates) == 5 and dates == sorted(dates) and overview["recent"] == []

    players = client.get(f"/api/clubs/{other['id']}/players").json()
    assert len(players) == overview["squad_size"]
    first = players[0]
    assert first["status"] in ("available", "injured", "suspended")
    assert first["transfer_status"] is None and first["interested_clubs"] == []
    assert "condition" not in first and "wage_weekly_eur" not in first

    theirs = client.get(f"/api/players/{first['id']}").json()
    assert not theirs["own_player"]
    assert theirs["condition"] is None and theirs["wage_weekly_eur"] is None
    assert client.get(f"/api/clubs/{other['id']}/squad").status_code == 403

    own = client.get(f"/api/clubs/{mine['id']}").json()
    assert own["own_club"] and own["manager"] == "Tester"
    money = client.get("/api/finances").json()  # your own club's money is exact, not rounded
    assert (own["budget_eur"], own["balance_eur"]) == (money["budget_eur"], money["balance_eur"])
    my_squad = client.get(f"/api/clubs/{mine['id']}/squad").json()
    ours = client.get(f"/api/players/{my_squad[0]['id']}").json()
    assert ours["own_player"] and ours["condition"] is not None
    assert ours["wage_weekly_eur"] is not None

    # Match day one: play the user's game too, so every club has played once.
    stop = advance_to_match(client)
    assert stop["stop"] == "match"
    client.post(f"/api/fixtures/{stop['fixture_id']}/play")
    played = client.get(f"/api/clubs/{other['id']}").json()
    assert played["played"] == 1 and played["position"] is not None
    assert len(played["recent"]) == 1 and played["recent"][0]["status"] == "played"

    assert client.get("/api/clubs/999999").status_code == 404
    assert client.get("/api/clubs/999999/players").status_code == 404


def test_a_clubs_recent_transfers_in_words(client: TestClient) -> None:
    leagues = client.get("/api/world/leagues").json()
    premier = next(lg for lg in leagues if lg["key"] == "ENG1")
    mine, other, third = (premier["clubs"][k] for k in range(3))
    client.post("/api/saves/1/new", json={"club_id": mine["id"], "manager_name": "Tester"})
    squad = client.get(f"/api/clubs/{other['id']}").json()["top_players"]
    session = client.app.state.registry.sessions()[0]  # type: ignore[attr-defined]
    with session.write() as conn:
        conn.execute(transfer.insert(), [
            {"player_id": squad[0]["id"], "from_club_id": other["id"], "to_club_id": third["id"],
             "date": "2026-07-10", "season_id": 1, "kind": "transfer", "fee_cents": 1_200_000_000,
             "wage_weekly_cents": 0, "contract_end": None, "by_user": 0},
            {"player_id": squad[1]["id"], "from_club_id": other["id"], "to_club_id": third["id"],
             "date": "2026-07-12", "season_id": 1, "kind": "loan", "fee_cents": 0,
             "wage_weekly_cents": 0, "contract_end": None, "by_user": 0},
            {"player_id": squad[2]["id"], "from_club_id": other["id"], "to_club_id": third["id"],
             "date": "2026-07-14", "season_id": 1, "kind": "loan_return", "fee_cents": 0,
             "wage_weekly_cents": 0, "contract_end": None, "by_user": 0}])
    lines = client.get(f"/api/clubs/{other['id']}").json()["recent_transfers"]
    assert len(lines) == 2  # the loan's return isn't a move worth listing
    assert lines[0].startswith(f"{squad[1]['name']} loaned to {third['name']}")
    assert lines[1].startswith(f"Sold {squad[0]['name']} to {third['name']} for $")
    assert lines[1].endswith("(Jul 2026)")
    theirs = client.get(f"/api/clubs/{third['id']}").json()["recent_transfers"]
    assert theirs[1].startswith(f"Signed {squad[0]['name']} from {other['name']} for $")

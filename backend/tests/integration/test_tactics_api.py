"""The tactics screen's data: why a starter rates what he does, and who is on the bench."""

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
    client = TestClient(create_app(session=session, frontend=None))
    leagues = client.get("/api/world/leagues").json()
    arsenal = next(c for lg in leagues if lg["key"] == "ENG1" for c in lg["clubs"]
                   if c["name"] == "Arsenal")
    client.post("/api/saves/1/new", json={"club_id": arsenal["id"], "manager_name": "Tester"})
    return client


def _save(client: TestClient, tactics: dict, lineup: dict | None) -> dict:
    response = client.put("/api/tactics", json={
        "formation": tactics["formation"], "roles": tactics["roles"], "lineup": lineup,
        "instructions": tactics["instructions"]})
    assert response.status_code == 200, response.text
    return response.json()


def test_a_starters_adjustments_add_up_to_his_slot_rating(client: TestClient) -> None:
    tactics = client.get("/api/tactics").json()
    for s in tactics["starters"]:
        assert s["overall"] + sum(a["delta"] for a in s["adjustments"]) == s["rating"]
        assert s["position_fit"] in ("natural", "adjusted", "out")
        assert s["best_position"]
    # Putting an outfielder in goal-adjacent trouble: swap a striker with a centre-back.
    lineup = {s["slot"]: s["player_id"] for s in tactics["starters"]}
    striker = next(s for s in tactics["starters"] if s["position"] == "ST")
    back = next(s for s in tactics["starters"] if s["position"] == "CB")
    lineup[striker["slot"]], lineup[back["slot"]] = back["player_id"], striker["player_id"]
    swapped = _save(client, tactics, lineup)
    moved = next(s for s in swapped["starters"] if s["slot"] == striker["slot"])
    assert moved["player_id"] == back["player_id"]
    assert moved["position_fit"] == "out"
    assert any(a["kind"] == "position" and a["delta"] < 0 for a in moved["adjustments"])
    assert moved["overall"] + sum(a["delta"] for a in moved["adjustments"]) == moved["rating"]
    assert moved["rating"] < moved["overall"]


def test_the_manager_picks_the_bench_and_everyone_else_is_a_reserve(client: TestClient) -> None:
    tactics = client.get("/api/tactics").json()
    assert not tactics["bench_chosen"] and tactics["bench_size"] == 9
    starters = {s["slot"]: s["player_id"] for s in tactics["starters"]}
    everyone = len(tactics["starters"]) + len(tactics["bench"]) + len(tactics["reserves"])
    assert everyone == len(client.get(
        f"/api/clubs/{client.get('/api/career').json()['club']['id']}/squad").json())
    reserve = tactics["reserves"][0]
    dropped = tactics["bench"][0]
    bench = [reserve["player_id"], *[b["player_id"] for b in tactics["bench"][1:]]]
    lineup = {**starters, **{f"SUB{n + 1}": pid for n, pid in enumerate(bench)}}

    chosen = _save(client, tactics, lineup)

    assert chosen["bench_chosen"]
    assert [b["player_id"] for b in chosen["bench"]] == bench
    assert dropped["player_id"] in [r["player_id"] for r in chosen["reserves"]]
    assert reserve["player_id"] not in [r["player_id"] for r in chosen["reserves"]]

    best = _save(client, chosen, None)  # "Pick best XI" gives the bench back to the picker
    assert not best["bench_chosen"]


def test_a_nonsense_line_up_is_refused(client: TestClient) -> None:
    tactics = client.get("/api/tactics").json()
    starters = {s["slot"]: s["player_id"] for s in tactics["starters"]}
    pid = tactics["bench"][0]["player_id"]
    for lineup in ({**starters, "SUB10": pid}, {**starters, "SUB1": starters["GK"]},
                   {**starters, "XX": pid}):
        response = client.put("/api/tactics", json={
            "formation": tactics["formation"], "roles": tactics["roles"], "lineup": lineup,
            "instructions": tactics["instructions"]})
        assert response.status_code == 400

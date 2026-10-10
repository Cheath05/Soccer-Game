"""The user's saved tactics: save the tactic now under a name, load it back, delete it.

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
    client = TestClient(create_app(session=session, frontend=None))
    league = next(lg for lg in client.get("/api/world/leagues").json() if lg["key"] == "ENG1")
    client.post("/api/saves/1/new", json={"club_id": int(league["clubs"][5]["id"]),
                                         "manager_name": "Coach"})
    return client


def _set(client: TestClient, formation: str, pressing: str,
         lineup: dict[str, int] | None = None) -> dict:
    now = client.get("/api/tactics").json()
    body = {"formation": formation, "roles": {}, "lineup": lineup,
            "instructions": {**now["instructions"], "pressing": pressing}}
    response = client.put("/api/tactics", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def test_tactics_are_saved_loaded_and_deleted(client: TestClient) -> None:
    _set(client, "4-4-2", "high")
    saved = client.post("/api/tactics/presets", json={"name": "Press high"}).json()
    assert [(p["name"], p["formation"], p["with_lineup"]) for p in saved] == \
        [("Press high", "4-4-2", False)]
    _set(client, "5-3-2", "low")
    saved = client.post("/api/tactics/presets", json={"name": "Park the bus"}).json()
    assert [p["name"] for p in saved] == ["Park the bus", "Press high"]
    press = next(p for p in saved if p["name"] == "Press high")
    loaded = client.post(f"/api/tactics/presets/{press['id']}/load").json()
    assert loaded["formation"] == "4-4-2" and loaded["instructions"]["pressing"] == "high"
    assert client.get("/api/tactics").json()["formation"] == "4-4-2"  # it's the tactic now
    # Saving under a name again replaces it.
    _set(client, "4-3-3", "high")
    again = client.post("/api/tactics/presets", json={"name": "Press high"}).json()
    assert len(again) == 2 and next(p for p in again if p["name"] == "Press high")[
        "formation"] == "4-3-3"
    assert client.post("/api/tactics/presets", json={"name": "  "}).status_code == 400
    left = client.delete(f"/api/tactics/presets/{press['id']}").json()
    assert [p["name"] for p in left] == ["Park the bus"]
    assert client.post(f"/api/tactics/presets/{press['id']}/load").status_code == 400


def test_a_saved_line_up_drops_players_who_have_left(client: TestClient) -> None:
    tactics = client.get("/api/tactics").json()
    lineup = {s["slot"]: s["player_id"] for s in tactics["starters"]}
    _set(client, tactics["formation"], "normal", lineup)
    saved = client.post("/api/tactics/presets", json={"name": "First XI", "with_lineup": True})
    preset = saved.json()[0]
    assert preset["with_lineup"]
    gone_slot, gone = next((slot, pid) for slot, pid in lineup.items() if slot != "GK")
    assert client.post(f"/api/players/{gone}/release").status_code == 200
    loaded = client.post(f"/api/tactics/presets/{preset['id']}/load").json()
    assert gone not in (loaded["lineup"] or {}).values()
    kept = {slot: pid for slot, pid in lineup.items() if slot != gone_slot}
    assert {k: v for k, v in (loaded["lineup"] or {}).items() if k in kept} == kept

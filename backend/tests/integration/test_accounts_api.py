"""Accounts on the server (api/auth.py, SessionRegistry): each player signs in and plays their
own careers; nobody signed in gets nothing but health. Needs the built world."""

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from match_day import advance_to_match
from starlette.websockets import WebSocketDisconnect

from footsim.accounts.store import AccountStore
from footsim.api.app import create_app
from footsim.api.session import SessionRegistry
from footsim.core.paths import data_dir
from footsim.defs.loader import load_server

BASE_WORLD = data_dir() / "worlds" / "base-2026-27.sqlite"
pytestmark = pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")


@pytest.fixture
def server(tmp_path: Path) -> tuple[Any, Path]:
    saves = tmp_path / "saves"
    accounts = AccountStore.in_saves(saves)
    accounts.add("Alex", "password1", owner=True, min_password_length=8)
    accounts.add("Sam", "password2", min_password_length=8)
    settings = load_server().model_copy(update={"failure_delay_seconds": 0.0,
                                                "sim_workers": 0})
    registry = SessionRegistry(saves, BASE_WORLD, settings, accounts)
    return create_app(frontend=None, registry=registry), saves


def _signed_in(app: Any, name: str, password: str) -> TestClient:
    client = TestClient(app)
    assert client.post("/api/auth/login", json={"name": name, "password": password}
                       ).status_code == 200
    return client


def _start(client: TestClient, pick: int) -> str:
    leagues = client.get("/api/world/leagues").json()
    club = [c for lg in leagues if lg["key"] == "ENG2" for c in lg["clubs"]][pick]
    assert client.post("/api/saves/1/new", json={"club_id": club["id"],
                                                 "manager_name": "T"}).status_code == 200
    name: str = club["name"]
    return name


def test_nobody_signed_in_gets_only_health_and_sign_in(server: tuple[Any, Path]) -> None:
    app, _ = server
    anon = TestClient(app)
    assert anon.get("/api/career").status_code == 401
    assert anon.get("/api/saves").status_code == 401
    assert anon.post("/api/saves/1/new", json={"club_id": 1, "manager_name": "x"}
                     ).status_code == 401
    health = anon.get("/api/health").json()
    assert health["accounts"] is True and health["in_use"] is False
    assert anon.get("/api/auth/me").json() == {"auth": True, "name": None, "is_owner": False}
    assert anon.post("/api/auth/login", json={"name": "sam", "password": "nope-nope"}
                     ).status_code == 401
    with pytest.raises(WebSocketDisconnect), anon.websocket_connect("/api/fixtures/1/live"):
        pass


def test_each_player_has_their_own_careers(server: tuple[Any, Path]) -> None:
    app, saves = server
    alex, sam = _signed_in(app, "alex", "password1"), _signed_in(app, "SAM", "password2")
    assert alex.get("/api/auth/me").json()["name"] == "Alex"
    alex_club, sam_club = _start(alex, 0), _start(sam, 1)
    assert alex.get("/api/career").json()["club"]["name"] == alex_club
    assert sam.get("/api/career").json()["club"]["name"] == sam_club
    assert [s["club"] for s in alex.get("/api/saves").json()] == [alex_club, None, None]
    assert [s["club"] for s in sam.get("/api/saves").json()] == [sam_club, None, None]
    # The owner plays from the saves folder itself; a friend from their own folder in it.
    assert (saves / "slot_1" / "career.sqlite").exists()
    folder = AccountStore.in_saves(saves).get("sam").folder
    assert (saves / "users" / folder / "slot_1" / "career.sqlite").exists()

    # Sam moving on doesn't move Alex.
    before = alex.get("/api/career").json()["date"]
    advance_to_match(sam)
    assert alex.get("/api/career").json()["date"] == before

    assert sam.post("/api/auth/logout").status_code == 200
    assert sam.get("/api/career").status_code == 401
    assert alex.get("/api/career").status_code == 200


def test_a_live_match_survives_another_player_loading(server: tuple[Any, Path]) -> None:
    app, _ = server
    alex, sam = _signed_in(app, "alex", "password1"), _signed_in(app, "sam", "password2")
    _start(alex, 2)
    fixture_id = advance_to_match(alex)["fixture_id"]
    _start(sam, 3)
    with alex.websocket_connect(f"/api/fixtures/{fixture_id}/live") as ws:
        assert ws.receive_json()["type"] == "init"
        assert sam.get("/api/health").json()["in_use"] is True  # anyone's match counts
        assert sam.post("/api/saves/1/load").status_code == 200  # Sam reloads their own
        ws.send_json({"type": "speed", "value": 8})
        ws.send_json({"type": "resume"})
        for _ in range(5):
            assert ws.receive_json()["type"] != "error"
    # Someone else's page can't open Alex's match.
    with pytest.raises(WebSocketDisconnect), alex.websocket_connect(
            f"/api/fixtures/{fixture_id}/live", headers={"origin": "https://evil.example"}):
        pass


def test_failed_sign_ins_are_throttled(server: tuple[Any, Path]) -> None:
    app, _ = server
    client = TestClient(app)
    for _ in range(load_server().login_attempts):
        assert client.post("/api/auth/login", json={"name": "sam", "password": "wrong-pass"}
                           ).status_code == 401
    blocked = client.post("/api/auth/login", json={"name": "sam", "password": "password2"})
    assert blocked.status_code == 429

"""The game as the iOS app runs it (footsim.phone.main): one career, the sim in this process,
and nothing answered without the launch's key. Needs the built world."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from match_day import advance_to_match
from starlette.websockets import WebSocketDisconnect

from footsim.api import workers
from footsim.core.paths import data_dir
from footsim.phone import main as phone

BASE_WORLD = data_dir() / "worlds" / "base-2026-27.sqlite"
pytestmark = pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")
PORT, SECRET = 47631, "s3cret"
HOST = f"127.0.0.1:{PORT}"


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("FOOTSIM_SAVES_DIR", str(tmp_path / "saves"))
    return phone.build(PORT, SECRET)


def _client(app: object, key: str | None = SECRET, host: str = HOST) -> TestClient:
    client = TestClient(app, base_url=f"http://{host}")  # type: ignore[arg-type]
    if key is not None:
        client.cookies.set(phone.COOKIE, key)
    return client


def test_a_career_plays_on_the_phone(app: object, tmp_path: Path) -> None:
    client = _client(app)
    assert (tmp_path / "worlds" / BASE_WORLD.name).exists()  # the bundle's world, copied once
    leagues = client.get("/api/world/leagues").json()
    club = next(c for lg in leagues if lg["key"] == "ENG4" for c in lg["clubs"])
    career = client.post("/api/saves/1/new", json={"club_id": club["id"], "manager_name": "P"})
    assert career.status_code == 200
    stop = advance_to_match(client)
    assert stop["stop"] == "match"
    assert workers._pool is None  # iOS has no processes: the sim ran here
    with client.websocket_connect(f"ws://{HOST}/api/fixtures/{stop['fixture_id']}/live",
                                  headers={"origin": f"http://{HOST}"}) as ws:
        assert ws.receive_json()["type"] == "init"
    assert client.get("/api/career").json()["date"] == stop["date"]
    assert client.get("/").status_code == 200 or not (phone.REPO_ROOT / "frontend/dist").exists()


def test_nothing_answers_without_the_key(app: object) -> None:
    for stranger in (_client(app, key=None), _client(app, key="wrong"),
                     _client(app, host="evil.example")):
        assert stranger.get("/api/world/leagues").status_code == 403  # never 401: not "signed out"
        assert stranger.get("/").status_code == 403
        with pytest.raises(WebSocketDisconnect), stranger.websocket_connect(
                f"ws://{stranger.base_url.netloc.decode()}/api/fixtures/1/live"):
            pass
    assert _client(app, key=None).get("/api/health").status_code == 200  # the host's own check
    assert _client(app, key=None, host="evil.example").get("/api/health").status_code == 403


def test_the_server_stops_listening_and_starts_again() -> None:
    phone.pause()
    assert phone.state() == {"awake": False, "serving": False}
    phone.resume()
    assert phone.state()["awake"]

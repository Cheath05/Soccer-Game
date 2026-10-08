"""Position training: a player the user chooses learns a position, month by month, until he's
natural in it (world/training.py).

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
from footsim.world.training import train_positions

BASE_WORLD = data_dir() / "worlds" / "base-2026-27.sqlite"
pytestmark = pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")


def test_a_player_learns_a_position_until_he_is_natural(tmp_path: Path) -> None:
    session = CareerSession(tmp_path / "saves", BASE_WORLD)
    client = TestClient(create_app(session=session, frontend=None))
    league = next(lg for lg in client.get("/api/world/leagues").json() if lg["key"] == "ENG1")
    club_id = int(league["clubs"][0]["id"])
    client.post("/api/saves/1/new", json={"club_id": club_id, "manager_name": "Coach"})
    natural = get_world().defs.development.position_training.natural
    with session.read() as conn:
        player, position, start = conn.execute(text(
            "SELECT pp.player_id, pp.position, pp.familiarity FROM player_position pp "
            "JOIN contract k ON k.person_id = pp.player_id AND k.is_active = 1 "
            "WHERE k.club_id = :c AND pp.familiarity BETWEEN 10 AND :n - 1 "
            "ORDER BY pp.familiarity, pp.player_id LIMIT 1"),
            {"c": club_id, "n": natural}).one()
    view = client.get(f"/api/players/{player}/training").json()
    assert view["position"] is None and view["rate_per_month"] > 0
    assert client.put(f"/api/players/{player}/training", json={"position": "XX"}
                      ).status_code == 409
    set_ = client.put(f"/api/players/{player}/training", json={"position": position}).json()
    assert set_["position"] == position
    news: list[str] = []
    for month in range(1, 25):  # it can't take more than two years from 10
        with session.write() as conn:
            news += train_positions(conn, get_world(), read_meta(conn),
                                    date(2026 + (6 + month) // 12, (6 + month) % 12 + 1, 1))
        familiarity = {p["position"]: p["familiarity"] for p in client.get(
            f"/api/players/{player}/training").json()["positions"]}[position]
        if familiarity >= natural:
            break
    assert familiarity == natural > start
    assert any("now natural" in n for n in news)
    assert client.get(f"/api/players/{player}/training").json()["position"] is None  # done
    # Already natural, or someone else's player: refused.
    assert client.put(f"/api/players/{player}/training", json={"position": position}
                      ).status_code == 409
    other = client.get("/api/clubs/1/players").json()[0]["id"]
    assert client.put(f"/api/players/{other}/training", json={"position": "CM"}
                      ).status_code == 409

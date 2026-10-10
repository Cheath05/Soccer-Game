"""The market overview: biggest transfers, most valuable players and young prospects. Prospects
show only the public potential estimate. Skipped when the base world hasn't been built."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from footsim.api.app import create_app
from footsim.api.session import CareerSession
from footsim.core.paths import data_dir

BASE_WORLD = data_dir() / "worlds" / "base-2026-27.sqlite"
pytestmark = pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")


def test_overview_lists_values_and_prospects(tmp_path: Path) -> None:
    session = CareerSession(tmp_path / "saves", BASE_WORLD)
    client = TestClient(create_app(session=session, frontend=None))
    league = next(lg for lg in client.get("/api/world/leagues").json() if lg["key"] == "ENG1")
    client.post("/api/saves/1/new", json={"club_id": int(league["clubs"][3]["id"]),
                                          "manager_name": "Scout"})
    body = client.get("/api/market/overview").json()
    assert body["season"]
    values = [p["value_eur"] for p in body["most_valuable"]]
    assert values and values == sorted(values, reverse=True)
    prospects = body["prospects"]
    assert prospects and all(p["age"] <= 21 for p in prospects)
    assert all(p["potential_low"] <= p["potential_high"] <= 99 for p in prospects)
    assert all("pa_hidden" not in p for p in prospects)
    mids = [p["potential_low"] + p["potential_high"] for p in prospects]
    assert mids == sorted(mids, reverse=True)
    fees = [t["fee_eur"] for t in body["biggest_transfers"]]
    assert fees == sorted(fees, reverse=True)

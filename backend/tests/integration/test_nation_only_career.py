"""A national team's manager without a club: a new career that only manages Wales (every league
on fast results, to be quick). Through the API it starts with Wales as its team, Continue stops
at Wales's first friendly, which plays as Instant, and sim-to-date runs on, playing Wales's
matches, to the season's end. Needs the built world."""

import time
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from footsim.api.app import create_app
from footsim.api.session import CareerSession
from footsim.core.paths import data_dir

BASE_WORLD = data_dir() / "worlds" / "base-2026-27.sqlite"
pytestmark = pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")
CODE = "WAL"


def test_a_country_only_career(tmp_path: Path) -> None:
    client = TestClient(create_app(session=CareerSession(tmp_path / "saves", BASE_WORLD),
                                   frontend=None))
    nations = client.get("/api/world/national-teams").json()
    assert CODE in {n["code"] for n in nations}
    assert [n["rank"] for n in nations] == list(range(1, len(nations) + 1))
    fast = [lg["key"] for lg in client.get("/api/world/simulation").json()]
    assert client.post("/api/saves/1/new", json={
        "nation_code": "XXX", "manager_name": "Tester"}).status_code == 404
    assert client.post("/api/saves/1/new", json={
        "nation_code": CODE, "club_id": 1, "manager_name": "Tester"}).status_code == 422
    career = client.post("/api/saves/1/new", json={
        "nation_code": CODE, "manager_name": "Tester", "fast_leagues": fast}).json()
    team = career["club"]["id"]
    assert career["nation_only"] and career["nation"]["id"] == team
    assert career["competition"] is None and career["position"] is None
    mine = client.get("/api/international/my-team").json()
    assert mine["code"] == CODE and mine["team"]["id"] == team
    assert sum(p["selected"] for p in mine["players"]) == mine["squad_size"]
    # His only team: he can move to another country, not leave.
    assert client.delete("/api/international/job").status_code == 409
    # The Tactics page's default team is the country.
    assert client.get("/api/tactics").json() == client.get(
        "/api/tactics", params={"team": "nation"}).json()
    season_end = date.fromisoformat(career["season_end"])
    first_season = career["season"]
    assert client.get("/api/calendar", params={
        "from": career["date"], "to": season_end.isoformat()}).status_code == 200

    # Continue: on through the world to his first friendly, played as Instant.
    stop = client.post("/api/career/advance").json()
    assert stop["stop"] == "match", stop["stop"]
    fixture = client.get(f"/api/fixtures/{stop['fixture_id']}").json()["fixture"]
    assert team in (fixture["home"]["id"], fixture["away"]["id"])
    assert fixture["competition"] == "INTL-FRIENDLY" or "friendl" in fixture[
        "competition_name"].lower(), fixture["competition_name"]
    played = client.post(f"/api/fixtures/{stop['fixture_id']}/play")
    assert played.status_code == 200, played.text
    assert not played.json()["fast_result"]  # Instant: the agent engine
    career = client.get("/api/career").json()
    assert career["recent"][0]["id"] == stop["fixture_id"]

    # Sim to a date past the season's end: his matches are played on the way, and it stops there.
    today = date.fromisoformat(career["date"])
    until = min(season_end + timedelta(days=60), today + timedelta(days=400))
    started = client.post("/api/career/sim", json={"until": until.isoformat()})
    assert started.status_code == 200, started.text
    deadline = time.monotonic() + 900
    status = started.json()
    while status["running"] and time.monotonic() < deadline:
        time.sleep(0.5)
        status = client.get("/api/career/sim").json()
    assert status["stop"] == "season_end", (status["stop"], status["error"])
    assert status["season_final"] is None  # the season's summary is a club's
    assert status["results"]  # the windows' matches were his
    career = client.get("/api/career").json()
    assert career["season"] != first_season and date.fromisoformat(career["date"]) > season_end
    assert career["nation_only"] and career["club"]["id"] == team

"""Careers ending and starting at a season's end (W1), on the real base world. Skipped when the
world hasn't been built (it needs the locally downloaded EA FC 27 file)."""

from datetime import date
from pathlib import Path

import numpy as np
import pytest
from sqlalchemy import text

from footsim.api.session import CareerSession
from footsim.core.paths import data_dir
from footsim.domain.attributes import ATTRIBUTES
from footsim.world.context import get_world
from footsim.world.lifecycle import season_turnover
from footsim.world.meta import read_meta

BASE_WORLD = data_dir() / "worlds" / "base-2026-27.sqlite"
pytestmark = pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")
WREXHAM = 182


def test_a_season_end_retires_some_and_brings_in_youngsters(tmp_path: Path) -> None:
    world = get_world()
    session = CareerSession(tmp_path / "saves", BASE_WORLD)
    session.new_career(1, WREXHAM, "Turnover")
    day = date(2027, 7, 1)
    with session.write() as conn:
        meta = read_meta(conn)
        before = conn.execute(text("SELECT COUNT(*) FROM person")).scalar_one()
        squad_before = conn.execute(text(
            "SELECT COUNT(*) FROM contract WHERE club_id = :c AND is_active = 1"),
            {"c": WREXHAM}).scalar_one()
        news = season_turnover(conn, world, meta, day)
        retired = conn.execute(text(
            "SELECT p.birth_date FROM player pl JOIN person p ON p.id = pl.person_id "
            "WHERE pl.retired_on IS NOT NULL")).all()
        new = conn.execute(text("""
            SELECT p.id, p.birth_date, pl.pa_hidden, k.club_id, k.kind, a.*
            FROM person p JOIN player pl ON pl.person_id = p.id
            JOIN player_attr a ON a.player_id = p.id
            JOIN contract k ON k.person_id = p.id AND k.is_active = 1
            WHERE p.id > :before"""), {"before": before}).all()
        largest = conn.execute(text("""
            SELECT MAX(n) FROM (SELECT club_id, COUNT(*) n FROM contract WHERE is_active = 1
                                AND club_id != :user AND kind != 'youth' GROUP BY club_id)"""),
            {"user": WREXHAM}).scalar_one()
        squad_after = conn.execute(text(
            "SELECT COUNT(*) FROM contract WHERE club_id = :c AND is_active = 1"),
            {"c": WREXHAM}).scalar_one()
        states = conn.execute(text("SELECT COUNT(*) FROM player_state WHERE player_id > :b"),
                              {"b": before}).scalar_one()
    ages = [(day - date.fromisoformat(r.birth_date)).days / 365.25 for r in retired]
    assert len(retired) > 100 and np.median(ages) > 33  # mostly from their mid-thirties
    assert len(new) > 1000 and states == len(new)  # every club's intake, ready to play
    assert all(r.kind == "youth" for r in new)
    young = [(day - date.fromisoformat(r.birth_date)).days / 365.25 for r in new]
    assert min(young) >= 15 and max(young) < 18.1
    overalls = world.model.group_overalls(
        np.array([[getattr(r, a) for a in ATTRIBUTES] for r in new], dtype=float))
    assert np.median(np.max([overalls[g] for g in overalls], axis=0)) < 60  # not ready yet
    # Computer-run senior squads are trimmed (the youth squad doesn't count).
    assert largest <= world.defs.lifecycle.squads.max_players
    ours = [r for r in new if r.club_id == WREXHAM]
    assert squad_after >= squad_before - 3 + len(ours)  # the user's squad isn't trimmed
    assert any(m.startswith("Youth intake:") for m in news)


def test_the_user_can_release_their_own_players_only(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from footsim.api.app import create_app

    session = CareerSession(tmp_path / "saves", BASE_WORLD)
    client = TestClient(create_app(session=session, frontend=None))
    client.post("/api/saves/1/new", json={"club_id": WREXHAM, "manager_name": "Release"})
    squad = client.get(f"/api/clubs/{WREXHAM}/squad").json()
    leaving = squad[-1]["id"]
    released = client.post(f"/api/players/{leaving}/release").json()
    assert released["club"] is None and not released["own_player"]
    assert len(client.get(f"/api/clubs/{WREXHAM}/squad").json()) == len(squad) - 1
    # Not below the floor: a side has to be able to play.
    floor = get_world().defs.lifecycle.squads.user_min_players
    for p in client.get(f"/api/clubs/{WREXHAM}/squad").json():
        if len(client.get(f"/api/clubs/{WREXHAM}/squad").json()) <= floor:
            break
        if p["position"] != "GK":
            client.post(f"/api/players/{p['id']}/release")
    remaining = client.get(f"/api/clubs/{WREXHAM}/squad").json()
    blocked = next(p for p in remaining if p["position"] != "GK")
    refused = client.post(f"/api/players/{blocked['id']}/release")
    assert refused.status_code == 409 and "at least" in refused.json()["detail"]
    other = client.get("/api/clubs/1/players").json()[0]["id"]
    assert client.post(f"/api/players/{other}/release").status_code == 400
    assert client.post(f"/api/players/{leaving}/release").status_code == 400  # already gone

"""A season of MLS under its roster rules (W9a B3-B4): every MLS club starts compliant, with its
stars as Designated Players on DP wages, and is compliant at the start of every month while the
AI market trades; trades between MLS clubs move GAM, sales out of MLS bring the seller 95% (up to
the season's cap as GAM), moves elsewhere are untouched; the next season's allocations follow.
Needs the built world."""

import shutil
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
from mls_world import mls_world
from sqlalchemy import Connection, text

from footsim.core.paths import data_dir
from footsim.persistence.database import open_database
from footsim.persistence.migrations import migrate
from footsim.world import mls
from footsim.world.career import advance, initialize_career
from footsim.world.context import World
from footsim.world.meta import read_meta

BASE_WORLD = data_dir() / "worlds" / "base-2026-27.sqlite"
pytestmark = pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")


def _problems(conn: Connection, world: World) -> dict[int, list[str]]:
    meta = read_meta(conn)
    found = {}
    for club_id in sorted(mls.mls_club_ids(conn, world, meta.season_id)):
        report = mls.club_report(conn, world, meta, club_id, meta.current_date)
        if not report.compliant:
            found[club_id] = [p.text for p in report.problems]
    return found


@pytest.fixture(scope="module")
def world() -> World:
    return mls_world()


@pytest.fixture(scope="module")
def season(world: World, tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """A watch-only career played month by month to the next season, noting where every MLS
    club stands on the 2nd of each month (after the 1st's fixes)."""
    path = tmp_path_factory.mktemp("mls") / "season.sqlite"
    shutil.copy(BASE_WORLD, path)
    engine = open_database(path)
    migrate(engine)
    with engine.begin() as conn:
        initialize_career(conn, world, None, None, seed=11)
        start = _problems(conn, world)
    months: dict[str, dict[int, list[str]]] = {}
    for _ in range(14):
        with engine.begin() as conn:
            meta = read_meta(conn)
            day = meta.current_date
            target = (day.replace(day=1) + timedelta(days=32)).replace(day=2)
            result = advance(conn, world, max_days=(target - day).days)
            if result.stop == "season_end":
                break
            months[read_meta(conn).current_date.isoformat()] = _problems(conn, world)
    engine.dispose()
    return {"path": path, "start": start, "months": months}


def _conn(path: Path) -> Connection:
    return open_database(path).connect()


def test_every_mls_club_starts_compliant(season: dict[str, Any]) -> None:
    assert season["start"] == {}


def test_every_mls_club_is_compliant_each_month(season: dict[str, Any]) -> None:
    assert len(season["months"]) >= 10
    assert {day: found for day, found in season["months"].items() if found} == {}


def test_the_stars_are_designated_players_on_dp_wages(season: dict[str, Any],
                                                      world: World) -> None:
    fig = mls.figures(world)
    with _conn(season["path"]) as conn:
        rows = conn.execute(text(
            "SELECT p.known_as, p.last_name, k.wage_weekly_cents, r.designation FROM person p "
            "JOIN contract k ON k.person_id = p.id AND k.is_active = 1 AND k.kind != 'loan' "
            "JOIN mls_roster r ON r.player_id = p.id AND r.season_id = 1 "
            "WHERE p.last_name = 'Messi' OR p.known_as = 'Messi'")).all()
        assert rows, "Messi is in FC 27's MLS"
        assert rows[0].designation == "dp"
        assert rows[0].wage_weekly_cents * 52 / 100 * fig.per_euro > 10_000_000
        dps = conn.execute(text("SELECT COUNT(*) FROM mls_roster WHERE season_id = 1 AND "
                                "designation = 'dp'")).scalar_one()
        assert 50 <= dps <= 90


def test_trades_within_mls_move_gam(season: dict[str, Any], world: World) -> None:
    with _conn(season["path"]) as conn:
        clubs = mls.mls_club_ids(conn, world, 1)
        for t in conn.execute(text("SELECT id, from_club_id, to_club_id, fee_cents FROM transfer "
                                   "WHERE kind = 'transfer' AND fee_cents > 0")).all():
            moves = {(r.club_id, r.amount_cents) for r in conn.execute(text(
                "SELECT club_id, amount_cents FROM mls_gam WHERE ref_id = :t AND kind IN "
                "('trade', 'sale')"), {"t": t.id})}
            cash = {r.club_id: r.amount_cents for r in conn.execute(text(
                "SELECT club_id, amount_cents FROM finance_ledger WHERE kind = 'transfer' AND "
                "ref_id = :t"), {"t": t.id})}
            if t.from_club_id in clubs and t.to_club_id in clubs:
                assert (t.from_club_id, t.fee_cents) in moves
                assert cash.get(t.from_club_id, 0) == 0
            elif t.from_club_id in clubs:  # a sale out of MLS: 95% to the club
                gam = sum(a for c, a in moves if c == t.from_club_id)
                assert gam + cash.get(t.from_club_id, 0) == round(t.fee_cents * 0.95)
                assert cash[t.to_club_id] == -t.fee_cents
            else:  # nothing changes outside MLS
                assert not moves
                assert cash.get(t.to_club_id) == -t.fee_cents
                assert cash.get(t.from_club_id) == t.fee_cents


def test_clubs_outside_mls_have_no_mls_rows(season: dict[str, Any], world: World) -> None:
    with _conn(season["path"]) as conn:
        clubs = mls.mls_club_ids(conn, world, 1)
        assert len(clubs) == 30
        others = conn.execute(text(
            "SELECT COUNT(*) FROM mls_roster WHERE club_id NOT IN (SELECT club_id FROM "
            "mls_club_season)")).scalar_one()
        assert others == 0
        assert {int(r.club_id) for r in conn.execute(text(
            "SELECT DISTINCT club_id FROM mls_club_season"))} == clubs


def test_mls_clubs_still_trade(season: dict[str, Any], world: World) -> None:
    with _conn(season["path"]) as conn:
        clubs = mls.mls_club_ids(conn, world, 1)
        signed = conn.execute(text(
            "SELECT COUNT(*) FROM transfer WHERE kind IN ('transfer', 'free', 'loan') AND "
            "season_id = 1 AND date > '2026-07-01' AND to_club_id IN (" + ", ".join(
                str(c) for c in clubs) + ")")).scalar_one()
        assert signed > 0


def test_the_next_seasons_allocations(season: dict[str, Any], world: World) -> None:
    fig = mls.figures(world)
    with _conn(season["path"]) as conn:
        meta = read_meta(conn)
        assert meta.season_id == 2
        for r in conn.execute(text("SELECT * FROM mls_club_season WHERE season_id = 2")).all():
            old = conn.execute(text("SELECT * FROM mls_club_season WHERE season_id = 1 AND "
                                    "club_id = :c"), {"c": r.club_id}).one()
            assert r.tam_cents == fig.c(2_025_000)  # the 2027 season's TAM
            spent = old.gam_committed_cents
            carried = old.gam_cents - max(0, spent - old.gam_expiring_cents)
            gained = conn.execute(text(
                "SELECT COALESCE(SUM(amount_cents), 0) FROM mls_gam WHERE club_id = :c AND "
                "season_id = 2 AND kind NOT IN ('allocation', 'model')"),
                {"c": r.club_id}).scalar_one()
            extra = fig.c(2_000_000) if r.roster_model == 2 else 0
            assert r.gam_cents + r.gam_expiring_cents == (carried + fig.c(3_280_000) + extra
                                                          + gained)
        assert meta.current_date >= date(2027, 7, 1)
        # Slots are traded, never made: the league's 30 clubs hold 8 each between them.
        assert conn.execute(text("SELECT SUM(international_slots) FROM mls_club_season WHERE "
                                 "season_id = 2")).scalar_one() == 30 * 8

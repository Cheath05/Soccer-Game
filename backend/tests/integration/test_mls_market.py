"""MLS's roster rules in the market (W9a B4): the user's moves into an MLS club refused with the
rule that blocks them, trades within MLS paid in GAM, sales out of MLS paying the seller 95%
(GAM up to the season's cap, the rest cash), moves elsewhere untouched, the user's designation
and roster-model choices, and the roster page's API. Needs the built world."""

import shutil
import sqlite3
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from mls_world import mls_world
from sqlalchemy import Connection, text

from footsim.api.app import create_app
from footsim.api.session import CareerSession
from footsim.core.paths import data_dir
from footsim.persistence.database import open_database
from footsim.persistence.migrations import migrate
from footsim.world import mls, mls_market
from footsim.world.career import initialize_career
from footsim.world.context import World
from footsim.world.loans import Loan, validate_loan
from footsim.world.meta import read_meta, write_meta
from footsim.world.transfers import Move, MoveRefused, complete_move, validate_move

BASE_WORLD = data_dir() / "worlds" / "base-2026-27.sqlite"
pytestmark = pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")
DAY = date(2026, 7, 1)
END = date(2029, 6, 30)


@pytest.fixture(scope="module")
def world() -> World:
    return mls_world()


@pytest.fixture(scope="module")
def career(world: World, tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """A new career, the user's club an MLS club with three DPs (Model 1), its international
    slots full and room on its roster."""
    path = tmp_path_factory.mktemp("mls-market") / "career.sqlite"
    shutil.copy(BASE_WORLD, path)
    engine = open_database(path)
    migrate(engine)
    with engine.begin() as conn:
        initialize_career(conn, world, None, None, seed=5)
        meta = read_meta(conn)
        chosen = None
        for club_id in sorted(mls.mls_club_ids(conn, world, 1)):
            report = mls.club_report(conn, world, meta, club_id, DAY)
            row = mls.state(conn, club_id, 1)
            assert row is not None
            if (row.roster_model == 1 and report.dps == 3 and len(report.members) <= 28
                    and report.internationals == row.international_slots):
                chosen = club_id
                break
        assert chosen is not None
        meta.user_club_id = chosen
        write_meta(conn, meta)
    engine.dispose()
    return {"path": path, "club": chosen}


@pytest.fixture
def conn(career: dict[str, Any]) -> Iterator[Connection]:
    """A connection whose changes are thrown away after the test."""
    engine = open_database(career["path"])
    with engine.connect() as connection:
        trans = connection.begin()
        connection.execute(text("UPDATE club_finance SET transfer_budget_cents = 10000000000"))
        yield connection
        trans.rollback()
    engine.dispose()


def _player(conn: Connection, world: World, *, mls_club: bool, domestic: bool,
            exclude: set[int] | None = None, club: int | None = None) -> tuple[int, int]:
    """A player aged 26-30 with three years on his contract: (player, club)."""
    clubs = mls.mls_club_ids(conn, world, 1)
    exclude = exclude or set()
    for r in conn.execute(text(
            "SELECT k.person_id, k.club_id, n.code FROM contract k JOIN person p ON p.id = "
            "k.person_id LEFT JOIN nation n ON n.id = p.nation_id JOIN club_league_membership m "
            "ON m.club_id = k.club_id AND m.season_id = 1 WHERE k.is_active = 1 AND "
            "k.kind = 'player' AND k.end_date >= '2028-06-30' AND p.birth_date BETWEEN "
            "'1996-01-01' AND '2000-01-01' ORDER BY k.person_id")):
        if (r.club_id in clubs) != mls_club or r.club_id in exclude:
            continue
        if club is not None and r.club_id != club:
            continue
        if (r.code == "USA") == domestic:
            return int(r.person_id), int(r.club_id)
    raise AssertionError("no such player")


def _weekly(world: World, usd: int) -> int:
    return mls._weekly(mls.figures(world).c(usd))


def _refusal(conn: Connection, world: World, move: Move) -> str:
    with pytest.raises(MoveRefused) as exc:
        validate_move(conn, world, read_meta(conn), move, DAY)
    return str(exc.value)


def test_no_international_slot_free(conn: Connection, world: World,
                                    career: dict[str, Any]) -> None:
    pid, _ = _player(conn, world, mls_club=False, domestic=False)
    move = Move(pid, career["club"], 0, _weekly(world, 120_000), END, by_user=True)
    assert _refusal(conn, world, move) == "No international slot free."


def test_a_loan_needs_an_international_slot_too(conn: Connection, world: World,
                                                career: dict[str, Any]) -> None:
    pid, _ = _player(conn, world, mls_club=False, domestic=False)
    with pytest.raises(MoveRefused, match="No international slot free"):
        validate_loan(conn, world, read_meta(conn),
                      Loan(pid, career["club"], date(2027, 6, 30), 0.5, by_user=True), DAY)


def test_all_designated_player_slots_are_full(conn: Connection, world: World,
                                              career: dict[str, Any]) -> None:
    pid, _ = _player(conn, world, mls_club=False, domestic=True)
    move = Move(pid, career["club"], 0, _weekly(world, 6_000_000), END, by_user=True)
    assert _refusal(conn, world, move) == "All 3 Designated Player slots are full."


def test_over_the_salary_budget(conn: Connection, world: World, career: dict[str, Any]) -> None:
    conn.execute(text("UPDATE mls_club_season SET tam_cents = 0, gam_cents = 0, "
                      "gam_expiring_cents = 0 WHERE club_id = :c"), {"c": career["club"]})
    pid, _ = _player(conn, world, mls_club=False, domestic=True)
    move = Move(pid, career["club"], 0, _weekly(world, 700_000), END, by_user=True)
    message = _refusal(conn, world, move)
    assert message.startswith("Over the salary budget by $")
    assert message.endswith("after allocation money.")


def test_a_renewal_within_the_rules(conn: Connection, world: World,
                                    career: dict[str, Any]) -> None:
    meta = read_meta(conn)
    report = mls.club_report(conn, world, meta, career["club"], DAY)
    senior = next(m for m in report.members if m.designation == "senior" and m.loan is None)
    assert mls_market.wage_problem(conn, world, meta, career["club"], senior.player_id,
                            senior.wage // 52, DAY) is None
    problem = mls_market.wage_problem(conn, world, meta, career["club"], senior.player_id,
                               _weekly(world, 6_000_000), DAY)
    assert problem == "All 3 Designated Player slots are full."


def test_a_trade_within_mls_is_paid_in_gam(conn: Connection, world: World,
                                           career: dict[str, Any]) -> None:
    buyer = career["club"]
    pid, seller = _player(conn, world, mls_club=True, domestic=True, exclude={buyer})
    fee = mls.figures(world).c(400_000)
    meta = read_meta(conn)
    gam = {c: mls.gam_held(conn, c, 1) for c in (buyer, seller)}
    cash = {c: conn.execute(text("SELECT balance_cents FROM club_finance WHERE club_id = :c"),
                            {"c": c}).scalar_one() for c in (buyer, seller)}
    complete_move(conn, world, meta, Move(pid, buyer, fee, _weekly(world, 120_000), END,
                                          by_user=True), DAY)
    assert mls.gam_held(conn, buyer, 1) == gam[buyer] - fee
    assert mls.gam_held(conn, seller, 1) == gam[seller] + fee
    for c in (buyer, seller):
        assert conn.execute(text("SELECT balance_cents FROM club_finance WHERE club_id = :c"),
                            {"c": c}).scalar_one() == cash[c]
    rows = {(r.club_id, r.amount_cents) for r in conn.execute(text(
        "SELECT club_id, amount_cents FROM mls_gam WHERE kind = 'trade' AND ref_id = "
        "(SELECT MAX(id) FROM transfer)"))}
    assert rows == {(buyer, -fee), (seller, fee)}


def test_a_trade_beyond_the_buyers_gam_needs_cash(conn: Connection, world: World,
                                                  career: dict[str, Any]) -> None:
    buyer = career["club"]
    _, seller = _player(conn, world, mls_club=True, domestic=True, exclude={buyer})
    meta = read_meta(conn)
    fig = mls.figures(world)
    held = mls.gam_held(conn, buyer, 1)
    # $10,000 short of GAM: the cash part is the $50,000 least, the rest GAM.
    split = mls_market.fee_split(conn, world, meta, seller, buyer, held + fig.c(10_000))
    assert split.buyer_gam == held - fig.c(40_000)
    assert split.buyer_cash == fig.c(50_000)
    assert split.seller_gam == held + fig.c(10_000) and split.seller_cash == 0


def test_a_sale_out_of_mls(conn: Connection, world: World, career: dict[str, Any]) -> None:
    pid, seller = _player(conn, world, mls_club=True, domestic=True, exclude={career["club"]})
    _, buyer = _player(conn, world, mls_club=False, domestic=False)
    fig = mls.figures(world)
    fee = 400_000_000  # €4M: 95% is €3.8M, of which the season's $3M cap comes as GAM
    meta = read_meta(conn)
    before = mls.gam_held(conn, seller, 1)
    complete_move(conn, world, meta, Move(pid, buyer, fee, 5_000_000, END), DAY)
    gam = fig.c(3_000_000)
    assert mls.gam_held(conn, seller, 1) == before + gam
    ledger = {r.club_id: r.amount_cents for r in conn.execute(text(
        "SELECT club_id, amount_cents FROM finance_ledger WHERE kind = 'transfer' AND ref_id = "
        "(SELECT MAX(id) FROM transfer)"))}
    assert ledger == {buyer: -fee, seller: round(fee * 0.95) - gam}
    # The cap is the season's: the next sale brings cash only.
    split = mls_market.fee_split(conn, world, meta, seller, buyer, fee)
    assert split.seller_gam == 0 and split.seller_cash == round(fee * 0.95)


def test_moves_outside_mls_are_untouched(conn: Connection, world: World) -> None:
    pid, seller = _player(conn, world, mls_club=False, domestic=False)
    meta = read_meta(conn)
    clubs = mls.mls_club_ids(conn, world, 1)
    buyer = next(int(r.club_id) for r in conn.execute(text(
        "SELECT m.club_id FROM club_league_membership m JOIN competition c ON c.id = "
        "m.competition_id WHERE c.key = 'ENG1' AND m.season_id = 1 ORDER BY m.club_id"))
        if r.club_id != seller and r.club_id not in clubs)
    split = mls_market.fee_split(conn, world, meta, seller, buyer, 123_456)
    assert split == mls_market.FeeSplit(123_456, 123_456)
    assert mls_market.addition_problem(conn, world, meta, buyer, pid, 100_000, DAY) is None


def test_designations_within_the_rules(conn: Connection, world: World,
                                       career: dict[str, Any]) -> None:
    meta = read_meta(conn)
    report = mls.club_report(conn, world, meta, career["club"], DAY)
    senior = next(m for m in report.members if m.designation == "senior" and m.age > 25)
    with pytest.raises(mls.RosterRefused, match="All 3 Designated Player slots are full"):
        mls.set_designation(conn, world, meta, DAY, senior.player_id, "dp")
    with pytest.raises(mls.RosterRefused, match="isn't a Generation adidas player"):
        mls.set_designation(conn, world, meta, DAY, senior.player_id, "generation_adidas")
    with pytest.raises(mls.RosterRefused, match="All 2 Designated Player slots are full"):
        mls.set_roster_model(conn, world, meta, DAY, 2)
    # A choice that keeps the roster compliant is made and kept.
    kid = next((m for m in report.members if m.slot == "supplemental"
                and m.designation == "supplemental"), None)
    if kid is not None:
        try:
            after = mls.set_designation(conn, world, meta, DAY, kid.player_id, "senior")
        except mls.RosterRefused as exc:  # his move up would break a rule: it says which
            assert str(exc).endswith(".")
            return
        assert next(m for m in after.members if m.player_id == kid.player_id).slot == "senior"
        stored = conn.execute(text("SELECT designation FROM mls_roster WHERE season_id = 1 AND "
                                   "player_id = :p"), {"p": kid.player_id}).scalar_one()
        assert stored == "senior"


def test_the_roster_page(tmp_path: Path) -> None:
    """The roster page's API on a career from the game's own definitions: MLS's clubs play by its
    rules before the save has the league (they're its source data's MLS)."""
    with sqlite3.connect(BASE_WORLD) as db:
        club_id = db.execute("SELECT id FROM club WHERE name = 'Austin FC'").fetchone()[0]
    client = TestClient(create_app(session=CareerSession(tmp_path / "saves", BASE_WORLD),
                                   frontend=None))
    client.post("/api/saves/1/new", json={"club_id": club_id, "manager_name": "Tester"})
    page = client.get("/api/mls/roster").json()
    assert page["club"]["id"] == club_id and page["yours"] and page["compliant"]
    assert page["problems"] == [] and not page["adding_blocked"]
    assert page["budget_used_eur"] <= page["budget_eur"]
    assert page["slots"]["designated_players"] <= page["slots"]["designated_slots"]
    assert page["slots"]["internationals"] <= page["slots"]["international_slots"]
    assert sum(p["charge"]["charge_eur"] for p in page["players"] if p["roster"] == "senior") \
        + page["empty_senior_slots_charged"] * round(mls.figures(
            mls_world()).senior_minimum / 100) == pytest.approx(page["budget_used_eur"], abs=40)
    senior = next(p for p in page["players"] if p["designation"] == "senior")
    refused = client.put("/api/mls/designation", json={"player_id": senior["id"],
                                                       "designation": "generation_adidas"})
    assert refused.status_code == 409 and "Generation adidas" in refused.json()["detail"]
    other = client.get("/api/mls/roster", params={"club_id": club_id + 1}).json()
    assert not other["yours"]
    # The clubs an international slot could be bought from: other MLS clubs with one to spare.
    slots = client.get("/api/mls/international-slot").json()
    assert slots["price_eur"] > 0 and slots["gam_left_eur"] == page["allocation"]["gam_left_eur"]
    assert all(s["club"]["id"] != club_id and s["spare"] > 0 for s in slots["sellers"])
    # Before the field is picked a college tournament's bracket is empty (the page says when).
    for event in ("NCAA", "CT:ACC"):
        bracket = client.get("/api/college/bracket", params={"event": event})
        assert bracket.status_code == 200 and bracket.json()["rounds"] == []

"""Moving players between clubs (W4-3; docs/plans/w3-w4-finances-transfers.md).

This is the one place a player changes club. ``validate_move`` says why a move can't happen, before
anything is written. ``complete_move`` makes it, in the caller's transaction:
- the old contract ends and the new one starts;
- the fee moves between the clubs' balances (through the finance ledger);
- the clubs' budgets move: the buyer's by the signing's cost, the seller's by what it gets back;
- the history records it;
- the selling club's saved line-up lets him go.

AI clubs and the user go through the same two functions, so they play by the same rules:
- the buying club's country has a transfer window open (a release needs none);
- the signing is within the buyer's budget: it costs the fee and the player's weekly wage for
  the weeks left in the season (``signing_cost_cents``). The seller's budget gets back
  ``reinvest`` of the fee and the old wage for those weeks; a release changes no budget;
- the seller keeps enough senior players and keepers, and the buyer stays within the squad
  limit;
- one club owns a player at a time. The database enforces it too (``ux_contract_owner``).

It also holds the market values of whole squads, with each player's stored market premium.
"""

import json
from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np
from sqlalchemy import Connection, Row, bindparam, select, text, update

from footsim.persistence.schema import club_finance, contract, tactic, transfer
from footsim.transfers.valuation import plain_values, values_eur, years_old
from footsim.world.context import World
from footsim.world.finance import Entry, post, signing_cost_cents, weeks_left
from footsim.world.meta import CareerMeta
from footsim.world.overall_history import player_overalls, primary_positions
from footsim.world.squads import club_name, display_name
from footsim.world.windows import club_window_nation, window_open

PLAYER_CONTRACT = "player"


class MoveRefused(Exception):
    """Why a move can't happen (the message is shown to the user)."""


@dataclass(frozen=True)
class Move:
    """A player's move. ``to_club_id`` None releases him into free agency. A free agent (no
    club) costs no fee."""

    player_id: int
    to_club_id: int | None
    fee_cents: int = 0
    wage_weekly_cents: int = 0
    contract_end: date | None = None
    by_user: bool = False


def owner_contract(conn: Connection, player_id: int) -> Row[Any] | None:
    """The contract of the club that owns the player (not a loan), if any."""
    return conn.execute(select(contract).where(
        contract.c.person_id == player_id, contract.c.is_active == 1,
        contract.c.kind != "loan")).first()


def senior_squad(conn: Connection, world: World, club_id: int, day: date) -> list[int]:
    """A club's senior players, where they play (its loans in, not its players out on loan):
    its players, with youngsters on youth contracts once they're old enough for a first contract
    (as the squad limit counts them: lifecycle.trim_squads)."""
    adult = world.defs.lifecycle.youth.contract_age
    rows = conn.execute(text(
        "SELECT k.person_id, k.kind, p.birth_date FROM playing k "
        "JOIN person p ON p.id = k.person_id WHERE k.club_id = :club "
        "AND k.kind IN ('player', 'youth', 'loan') ORDER BY k.person_id"),
        {"club": club_id}).all()
    return [r.person_id for r in rows
            if r.kind != "youth" or years_old(r.birth_date, day) >= adult]


def on_loan(conn: Connection, player_id: int) -> bool:
    """Whether he's out on loan now (W4-8)."""
    return conn.execute(text("SELECT 1 FROM contract WHERE person_id = :p AND is_active = 1 "
                             "AND kind = 'loan'"), {"p": player_id}).first() is not None


def _check_seller(conn: Connection, world: World, club_id: int, player_id: int,
                  day: date) -> None:
    rules = world.defs.lifecycle.squads
    seniors = senior_squad(conn, world, club_id, day)
    if player_id not in seniors:
        return  # a youth player's leaving doesn't thin the senior squad
    if len(seniors) - 1 < rules.user_min_players:
        raise MoveRefused(f"You need at least {rules.user_min_players} senior players.")
    positions = primary_positions(conn, seniors)
    if positions.get(player_id) == "GK":
        keepers = sum(1 for p in seniors if positions.get(p) == "GK")
        if keepers - 1 < rules.user_min_keepers:
            raise MoveRefused(f"You need at least {rules.user_min_keepers} keepers.")


def validate_move(conn: Connection, world: World, meta: CareerMeta, move: Move,
                  day: date) -> None:
    """Raise MoveRefused, with the reason, unless ``move`` can happen on ``day``."""
    alive = conn.execute(text("SELECT retired_on FROM player WHERE person_id = :p"),
                         {"p": move.player_id}).first()
    if alive is None or alive.retired_on is not None:
        raise MoveRefused("No such player.")
    owner = owner_contract(conn, move.player_id)
    if on_loan(conn, move.player_id):
        raise MoveRefused("He's out on loan: he can move when he's back.")
    if move.to_club_id is None:
        if owner is None:
            raise MoveRefused("He has no club to leave.")
        if move.fee_cents or move.wage_weekly_cents:
            raise MoveRefused("A release has no fee and no new wage.")
        _check_seller(conn, world, owner.club_id, move.player_id, day)
        return
    if owner is not None and owner.club_id == move.to_club_id:
        raise MoveRefused("He already plays for that club.")
    if move.fee_cents < 0 or move.wage_weekly_cents < 0:
        raise MoveRefused("A fee and a wage can't be negative.")
    if move.wage_weekly_cents < round(world.defs.wage_levels.minimum_weekly_wage * 100):
        raise MoveRefused("His wage is below the minimum.")
    if owner is None and move.fee_cents:
        raise MoveRefused("A free agent costs no fee.")
    if move.contract_end is None or move.contract_end <= day:
        raise MoveRefused("His contract must run beyond today.")
    nation = club_window_nation(conn, move.to_club_id, meta.season_id)
    if not window_open(world, nation, meta.season_id, day):
        raise MoveRefused("The transfer window is closed.")
    money = conn.execute(select(club_finance).where(
        club_finance.c.club_id == move.to_club_id)).first()
    if money is None:
        raise MoveRefused("That club has no finances.")
    weeks = weeks_left(conn, meta.season_id, day)
    if signing_cost_cents(move.fee_cents, move.wage_weekly_cents, weeks) > (
            money.transfer_budget_cents):
        raise MoveRefused("That's beyond the budget.")
    if (len(senior_squad(conn, world, move.to_club_id, day)) + 1
            > world.defs.lifecycle.squads.max_players):
        raise MoveRefused("The squad is full.")
    if owner is not None:
        _check_seller(conn, world, owner.club_id, move.player_id, day)


def _drop_from_lineup(conn: Connection, club_id: int, player_id: int) -> None:
    """A saved line-up forgets a player who has left (an empty slot is picked automatically)."""
    row = conn.execute(select(tactic.c.lineup).where(tactic.c.club_id == club_id)).first()
    if row is None or not row.lineup:
        return
    lineup = json.loads(row.lineup)
    kept = {slot: pid for slot, pid in lineup.items() if pid != player_id}
    if kept != lineup:
        conn.execute(update(tactic).where(tactic.c.club_id == club_id)
                     .values(lineup=json.dumps(kept) if kept else None))


def fee_text(cents: int) -> str:
    eur = cents / 100
    if eur >= 999_500:
        return f"€{eur / 1_000_000:.1f}M".replace(".0M", "M")
    return f"€{round(eur / 1_000)}K"


def complete_move(conn: Connection, world: World, meta: CareerMeta, move: Move,
                  day: date) -> list[str]:
    """Make ``move`` (it's checked first: nothing is written unless every rule holds). Returns
    the news."""
    validate_move(conn, world, meta, move, day)
    owner = owner_contract(conn, move.player_id)
    seller = owner.club_id if owner is not None else None
    kind = "release" if move.to_club_id is None else "free" if owner is None else "transfer"
    if owner is not None:
        conn.execute(update(contract).where(contract.c.id == owner.id)
                     .values(is_active=0, end_date=day.isoformat(), listed=0))
        _drop_from_lineup(conn, owner.club_id, move.player_id)
    transfer_id: int = conn.execute(transfer.insert().values(
        player_id=move.player_id, from_club_id=seller, to_club_id=move.to_club_id,
        date=day.isoformat(), season_id=meta.season_id, kind=kind, fee_cents=move.fee_cents,
        wage_weekly_cents=move.wage_weekly_cents,
        contract_end=move.contract_end.isoformat() if move.contract_end else None,
        by_user=int(move.by_user))).inserted_primary_key[0]  # type: ignore[index]
    if move.to_club_id is not None:
        assert move.contract_end is not None  # validated
        conn.execute(contract.insert().values(
            person_id=move.player_id, club_id=move.to_club_id, kind=PLAYER_CONTRACT,
            start_date=day.isoformat(), end_date=move.contract_end.isoformat(),
            wage_weekly_cents=move.wage_weekly_cents, release_clause_cents=None, is_active=1,
            listed=0))
    if move.fee_cents and seller is not None and move.to_club_id is not None:
        post(conn, day, meta.season_id, [
            Entry(move.to_club_id, "transfer", -move.fee_cents, transfer_id),
            Entry(seller, "transfer", move.fee_cents, transfer_id)])
    if move.to_club_id is not None:  # a release changes no budget
        _move_budgets(conn, world, meta, move, owner, day)
    return [_news(conn, move, seller, kind)]


def _move_budgets(conn: Connection, world: World, meta: CareerMeta, move: Move,
                  owner: Row[Any] | None, day: date) -> None:
    """The buyer's budget pays the signing's cost (the fee and his new wage for the rest of the
    season). The seller's gets back ``reinvest`` of the fee, and the wage it no longer pays for
    the rest of the season (``owner``: the contract he left)."""
    weeks = weeks_left(conn, meta.season_id, day)
    changes = [{"club": move.to_club_id,
                "change": -signing_cost_cents(move.fee_cents, move.wage_weekly_cents, weeks)}]
    if owner is not None:
        changes.append({"club": owner.club_id,
                        "change": round(world.defs.finance.reinvest * move.fee_cents)
                        + round(owner.wage_weekly_cents * weeks)})
    conn.execute(text(
        "UPDATE club_finance SET transfer_budget_cents = transfer_budget_cents + :change "
        "WHERE club_id = :club"), changes)


def _news(conn: Connection, move: Move, seller: int | None, kind: str) -> str:
    who = conn.execute(text("SELECT first_name, last_name, known_as FROM person WHERE id = :p"),
                       {"p": move.player_id}).one()
    name = display_name(who.first_name, who.last_name, who.known_as)
    if kind == "release":
        assert seller is not None
        return f"{name} leaves {club_name(conn, seller)} as a free agent."
    assert move.to_club_id is not None
    buyer = club_name(conn, move.to_club_id)
    if kind == "free":
        return f"{name} joins {buyer} on a free transfer."
    assert seller is not None
    return f"{name} joins {buyer} from {club_name(conn, seller)} for {fee_text(move.fee_cents)}."


# --- market values --------------------------------------------------------------------


def _market_rows(conn: Connection, world: World, day: date, ids: list[int] | None
                 ) -> tuple[list[int], tuple[list[float], list[float], list[bool], list[float]],
                            dict[int, Row[Any]]]:
    """What the value model needs for each player still playing (or just ``ids``): overall,
    age to the day, keeper or not, and his market's reputation (the owning club's, else his
    own)."""
    rows = conn.execute(text(
        "SELECT p.person_id AS id, pe.birth_date AS birth, p.reputation AS own, "
        "p.value_premium AS premium, p.value_eur_cents AS listed_value, c.reputation AS club "
        "FROM player p JOIN person pe ON pe.id = p.person_id "
        "LEFT JOIN contract k ON k.person_id = p.person_id AND k.is_active = 1 "
        "  AND k.kind != 'loan' LEFT JOIN club c ON c.id = k.club_id "
        "WHERE p.retired_on IS NULL" + (" AND p.person_id IN :ids" if ids is not None else "")
        + " ORDER BY p.person_id").bindparams(*(
            [bindparam("ids", expanding=True)] if ids is not None else [])),
        {"ids": list(ids)} if ids is not None else {}).all()
    subset = [r.id for r in rows] if ids is not None else None
    overall = player_overalls(conn, world, subset)
    positions = primary_positions(conn, subset)
    rows = [r for r in rows if r.id in overall]
    terms = ([float(overall[r.id]) for r in rows], [years_old(r.birth, day) for r in rows],
             [positions.get(r.id) == "GK" for r in rows],
             [float(r.club if r.club is not None else r.own) for r in rows])
    return [r.id for r in rows], terms, {r.id: r for r in rows}


def player_values(conn: Connection, world: World, day: date,
                  ids: list[int] | None = None) -> dict[int, int]:
    """Market values in euros (every player still playing, or just ``ids``), with each one's
    market premium."""
    order, terms, rows = _market_rows(conn, world, day, ids)
    if not order:
        return {}
    premium = [rows[i].premium or 0.0 for i in order]
    values = values_eur(world.defs.valuation, *terms, premium)
    return {i: int(v) for i, v in zip(order, values, strict=True)}


def initialize_value_premiums(conn: Connection, world: World, day: date) -> None:
    """Each player's market premium, once: a share of how far his Transfermarkt value (from the
    world build) sits from the model's value of him today, capped either way. Players without
    one get 0."""
    order, terms, rows = _market_rows(conn, world, day, None)
    pending = [i for i in order if rows[i].premium is None]
    if not pending:
        return
    model = world.defs.valuation
    plain = dict(zip(order, plain_values(model, *terms), strict=True))
    updates = []
    for i in pending:
        premium = 0.0
        if rows[i].listed_value:
            gap = float(np.log(rows[i].listed_value / 100 / plain[i]))
            premium = float(np.clip(model.premium_share * gap, -model.premium_cap,
                                    model.premium_cap))
        updates.append({"p": i, "premium": round(premium, 4)})
    conn.execute(text("UPDATE player SET value_premium = :premium WHERE person_id = :p"),
                 updates)

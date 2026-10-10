"""A world-wide look at the transfer market: this season's biggest moves, the most valuable players
and the best young prospects. Read-only; potential is only the public estimate (the range the
player page shows for a player at another club), never his hidden value."""

import numpy as np
from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from footsim.api.routes import Session
from footsim.api.schemas import ClubRef
from footsim.scouting.estimates import (
    OTHER_CLUB_KNOWLEDGE,
    OWN_CLUB_KNOWLEDGE,
    potential_label,
    potential_range,
)
from footsim.world.context import get_world
from footsim.world.market import FREE, _Market, season_calendar_end
from footsim.world.meta import read_meta
from footsim.world.squads import display_name

router = APIRouter(prefix="/api/market")
TOP_N = 20
PROSPECT_MAX_AGE = 21


class OverviewPlayer(BaseModel):
    player: ClubRef
    age: int
    position: str
    overall: int
    club: ClubRef | None
    value_eur: int


class OverviewTransfer(BaseModel):
    date: str
    player: ClubRef
    age: int | None
    position: str | None
    overall: int | None
    from_club: ClubRef | None
    to_club: ClubRef | None
    fee_eur: int
    yours: bool


class OverviewProspect(OverviewPlayer):
    potential_low: int
    potential_high: int
    potential_label: str


class MarketOverviewOut(BaseModel):
    season: str
    biggest_transfers: list[OverviewTransfer]
    most_valuable: list[OverviewPlayer]
    prospects: list[OverviewProspect]


@router.get("/overview")
def overview(session: Session) -> MarketOverviewOut:
    world = get_world()
    with session.read() as conn:
        meta = read_meta(conn)
        market = _Market(conn, world, meta, meta.current_date, season_calendar_end(world, meta))
        p = market.players
        season = conn.execute(text("SELECT label, start_date, end_date FROM season WHERE id = :s"),
                              {"s": meta.season_id}).one()
        clubs = {r.id: r.name for r in conn.execute(text("SELECT id, name FROM club"))}

        def ref(club_id: int) -> ClubRef | None:
            return ClubRef(id=club_id, name=clubs.get(club_id, "")) if club_id != FREE else None

        top_value = [int(k) for k in np.argsort(-market.value, kind="stable")[:TOP_N]]
        young = [k for k in range(len(p.ids)) if market.age[k] <= PROSPECT_MAX_AGE]
        moves = conn.execute(text(
            "SELECT t.*, pe.first_name, pe.last_name, pe.known_as FROM transfer t "
            "JOIN person pe ON pe.id = t.player_id WHERE t.kind = 'transfer' AND t.date >= :a "
            "AND t.date <= :b ORDER BY t.fee_cents DESC, t.id LIMIT :n"),
            {"a": season.start_date, "b": season.end_date, "n": TOP_N}).all()

        ids = {int(p.ids[k]) for k in top_value} | {int(p.ids[k]) for k in young}
        marks = ", ".join(str(i) for i in ids) or "0"
        people = {r.id: (display_name(r.first_name, r.last_name, r.known_as), r.pa_hidden)
                  for r in conn.execute(text(
                      "SELECT pe.id, pe.first_name, pe.last_name, pe.known_as, pl.pa_hidden "
                      "FROM person pe JOIN player pl ON pl.person_id = pe.id "
                      f"WHERE pe.id IN ({marks})"))}

        def line(k: int) -> OverviewPlayer:
            pid = int(p.ids[k])
            return OverviewPlayer(
                player=ClubRef(id=pid, name=people[pid][0]), age=int(market.age[k]),
                position=str(p.primary[k]), overall=int(p.overall[k]),
                club=ref(int(market.owner[k])), value_eur=int(market.value[k]))

        prospects = []
        for k in young:
            pid = int(p.ids[k])
            own = int(market.owner[k]) == meta.user_club_id
            low, high = potential_range(
                people[pid][1], float(p.overall[k]), int(market.age[k]),
                OWN_CLUB_KNOWLEDGE if own else OTHER_CLUB_KNOWLEDGE, meta.seed, pid)
            prospects.append((low + high, int(p.overall[k]), -pid, k, low, high))
        prospects.sort(reverse=True)

        transfers = []
        for r in moves:
            at = p.index.get(int(r.player_id))
            transfers.append(OverviewTransfer(
                date=r.date,
                player=ClubRef(id=r.player_id, name=display_name(
                    r.first_name, r.last_name, r.known_as)),
                age=int(market.age[at]) if at is not None else None,
                position=str(p.primary[at]) if at is not None else None,
                overall=int(p.overall[at]) if at is not None else None,
                from_club=ref(r.from_club_id) if r.from_club_id else None,
                to_club=ref(r.to_club_id) if r.to_club_id else None,
                fee_eur=r.fee_cents // 100,
                yours=meta.user_club_id in (r.from_club_id, r.to_club_id)))

        return MarketOverviewOut(
            season=season.label, biggest_transfers=transfers,
            most_valuable=[line(k) for k in top_value],
            prospects=[
                OverviewProspect(**line(k).model_dump(), potential_low=low, potential_high=high,
                                 potential_label=potential_label(high))
                for _, _, _, k, low, high in prospects[:TOP_N]])

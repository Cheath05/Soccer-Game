"""The user's transfer market (W4-6): searching for players, a player's terms, offers answered
at once, transfer-listing, AI clubs' bids for the user's players, and the history. Thin: the
rules are world/market.py's and world/transfers.py's, the same as every AI club's."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from footsim.api.routes import Session, _not_simulating
from footsim.api.schemas import ClubRef
from footsim.world.context import get_world
from footsim.world.market import (
    FREE,
    OfferResult,
    _Market,
    answer_bid,
    make_offer,
    player_terms,
    season_calendar_end,
)
from footsim.world.meta import read_meta
from footsim.world.squads import display_name
from footsim.world.transfers import MoveRefused, owner_contract

router = APIRouter(prefix="/api/transfers")
SEARCH_LIMIT = 60


class MarketPlayerOut(BaseModel):
    id: int
    name: str
    age: int
    position: str  # his position group
    overall: int
    club: ClubRef | None  # None: a free agent
    league: str | None
    value_eur: int
    contract_end: str | None
    listed: bool


class TermsOut(BaseModel):
    player_id: int
    value_eur: int
    wage_eur: int  # what he'd ask of your club, a week
    years: int
    listed: bool
    free_agent: bool
    window_open: bool


class OfferIn(BaseModel):
    player_id: int
    fee_eur: int = Field(ge=0)
    wage_eur: int | None = Field(default=None, ge=0)
    years: int | None = Field(default=None, ge=1, le=5)


class OfferOut(BaseModel):
    status: str  # accepted | countered | rejected | refused
    message: str
    fee_eur: int
    wage_eur: int
    years: int


class BidOut(BaseModel):
    """An AI club's bid for one of the user's players."""

    id: int
    player: ClubRef  # id and name of the player
    bidder: ClubRef
    fee_eur: int
    wage_eur: int
    years: int
    expires: str


class AnswerIn(BaseModel):
    action: str  # accept | reject | counter
    fee_eur: int | None = Field(default=None, ge=0)


class HistoryOut(BaseModel):
    date: str
    player: ClubRef
    from_club: ClubRef | None
    to_club: ClubRef | None
    kind: str
    fee_eur: int
    yours: bool


def _offer_out(result: OfferResult) -> OfferOut:
    return OfferOut(status=result.status, message=result.message, fee_eur=result.fee_eur,
                    wage_eur=result.wage_eur, years=result.years)


@router.get("/search")
def search(session: Session, position: str | None = None, min_overall: int = 0,
           max_overall: int = 99, max_age: int = 45, max_value_eur: int | None = None,
           league: str | None = None, free_agents: bool = False, listed_only: bool = False,
           name: Annotated[str | None, Query(max_length=40)] = None) -> list[MarketPlayerOut]:
    """Players anywhere but the user's club, best first: by position group, overall, age,
    value, league; free agents or listed players only; or by name."""
    world = get_world()
    with session.read() as conn:
        meta = read_meta(conn)
        market = _Market(conn, world, meta, meta.current_date, season_calendar_end(world, meta))
        p = market.players
        leagues = {r.club_id: (r.key, r.name) for r in conn.execute(text(
            "SELECT m.club_id, c.key, c.name FROM club_league_membership m JOIN competition c "
            "ON c.id = m.competition_id WHERE m.season_id = :s"), {"s": meta.season_id})}
        rows = []
        for k in range(len(p.ids)):
            owner = int(market.owner[k])
            if owner == meta.user_club_id or (free_agents and owner != FREE):
                continue
            if listed_only and not market.listed[k]:
                continue
            if position and str(p.primary[k]) != position:
                continue
            if not (min_overall <= p.overall[k] <= max_overall) or market.age[k] > max_age:
                continue
            if max_value_eur is not None and market.value[k] > max_value_eur:
                continue
            if league and leagues.get(owner, ("", ""))[0] != league:
                continue
            rows.append(k)
        if name:
            wanted = name.lower()
            people = {r.id: display_name(r.first_name, r.last_name, r.known_as) for r in
                      conn.execute(text("SELECT id, first_name, last_name, known_as FROM person "
                                        "WHERE lower(coalesce(known_as, '') || ' ' || "
                                        "first_name || ' ' || last_name) LIKE :q"),
                                   {"q": f"%{wanted}%"})}
            rows = [k for k in rows if int(p.ids[k]) in people]
        rows.sort(key=lambda k: (-p.overall[k], market.age[k], int(p.ids[k])))
        rows = rows[:SEARCH_LIMIT]
        ids = [int(p.ids[k]) for k in rows]
        if not ids:
            return []
        marks = ", ".join(str(i) for i in ids)
        info = {r.id: r for r in conn.execute(text(
            f"SELECT pe.id, pe.first_name, pe.last_name, pe.known_as, k.end_date, c.name AS club "
            f"FROM person pe LEFT JOIN contract k ON k.person_id = pe.id AND k.is_active = 1 "
            f"AND k.kind != 'loan' LEFT JOIN club c ON c.id = k.club_id WHERE pe.id IN ({marks})"
        ))}
        result = []
        for k, player_id in zip(rows, ids, strict=True):
            r = info[player_id]
            owner = int(market.owner[k])
            result.append(MarketPlayerOut(
                id=player_id, name=display_name(r.first_name, r.last_name, r.known_as),
                age=int(market.age[k]), position=str(p.primary[k]), overall=int(p.overall[k]),
                club=ClubRef(id=owner, name=r.club) if owner != FREE else None,
                league=leagues.get(owner, (None, None))[1], value_eur=int(market.value[k]),
                contract_end=r.end_date, listed=bool(market.listed[k])))
        return result


@router.get("/terms/{player_id}")
def terms(player_id: int, session: Session) -> TermsOut:
    with session.read() as conn:
        meta = read_meta(conn)
        try:
            t = player_terms(conn, get_world(), meta, meta.current_date, player_id)
        except MoveRefused as exc:
            raise HTTPException(404, str(exc)) from exc
    return TermsOut(player_id=t.player_id, value_eur=t.value_eur, wage_eur=t.wage_eur,
                    years=t.years, listed=t.listed, free_agent=t.club_id is None,
                    window_open=t.window_open)


@router.post("/offer")
def offer(body: OfferIn, session: Session) -> OfferOut:
    """An offer for a player, answered at once by his club and then by him."""
    _not_simulating(session)
    if session.live_matches:
        raise HTTPException(409, "finish the match being played first")
    with session.write() as conn:
        meta = read_meta(conn)
        try:
            result = make_offer(conn, get_world(), meta, meta.current_date, body.player_id,
                                body.fee_eur, body.wage_eur, body.years)
        except MoveRefused as exc:
            raise HTTPException(409, str(exc)) from exc
    if result.status == "accepted":
        session.autosave()
    return _offer_out(result)


@router.put("/listed/{player_id}")
def set_listed(player_id: int, session: Session, listed: bool = True) -> dict[str, bool]:
    """Put one of the user's players up for sale (AI clubs see him as available and cheaper),
    or take him off."""
    _not_simulating(session)
    with session.write() as conn:
        meta = read_meta(conn)
        owner = owner_contract(conn, player_id)
        if owner is None or owner.club_id != meta.user_club_id:
            raise HTTPException(400, "not one of your players")
        conn.execute(text("UPDATE contract SET listed = :l WHERE id = :id"),
                     {"l": int(listed), "id": owner.id})
    session.autosave()
    return {"listed": listed}


@router.get("/bids")
def bids(session: Session) -> list[BidOut]:
    """AI clubs' bids for the user's players, waiting for an answer."""
    with session.read() as conn:
        meta = read_meta(conn)
        rows = conn.execute(text(
            "SELECT o.*, pe.first_name, pe.last_name, pe.known_as, c.name AS bidder "
            "FROM transfer_offer o JOIN person pe ON pe.id = o.player_id "
            "JOIN club c ON c.id = o.bidder_club_id WHERE o.owner_club_id = :u "
            "AND o.status = 'pending' AND o.by_user = 0 AND o.expires >= :d ORDER BY o.id"),
            {"u": meta.user_club_id, "d": meta.current_date.isoformat()}).all()
    return [BidOut(id=r.id, player=ClubRef(id=r.player_id, name=display_name(
        r.first_name, r.last_name, r.known_as)), bidder=ClubRef(id=r.bidder_club_id,
                                                                  name=r.bidder),
        fee_eur=r.fee_cents // 100, wage_eur=r.wage_weekly_cents // 100, years=r.years or 1,
        expires=r.expires) for r in rows]


@router.post("/bids/{offer_id}")
def answer(offer_id: int, body: AnswerIn, session: Session) -> OfferOut:
    """Accept, reject or counter an AI club's bid for one of the user's players."""
    _not_simulating(session)
    if session.live_matches:
        raise HTTPException(409, "finish the match being played first")
    with session.write() as conn:
        meta = read_meta(conn)
        result = answer_bid(conn, get_world(), meta, meta.current_date, offer_id, body.action,
                            body.fee_eur)
    session.autosave()
    return _offer_out(result)


@router.get("/history")
def history(session: Session, mine: bool = False, limit: int = 50) -> list[HistoryOut]:
    """Completed moves, latest first: the whole world's, or just the user's club's."""
    with session.read() as conn:
        meta = read_meta(conn)
        where = "WHERE t.kind IN ('transfer', 'free')"
        params: dict[str, object] = {"n": max(1, min(limit, 200))}
        if mine:
            where = ("WHERE (t.from_club_id = :u OR t.to_club_id = :u) AND t.kind IN "
                     "('transfer', 'free', 'release')")
            params["u"] = meta.user_club_id
        rows = conn.execute(text(
            "SELECT t.*, pe.first_name, pe.last_name, pe.known_as, f.name AS from_name, "
            "o.name AS to_name FROM transfer t JOIN person pe ON pe.id = t.player_id "
            "LEFT JOIN club f ON f.id = t.from_club_id LEFT JOIN club o ON o.id = t.to_club_id "
            f"{where} ORDER BY t.date DESC, t.id DESC LIMIT :n"), params).all()
    return [HistoryOut(
        date=r.date, player=ClubRef(id=r.player_id, name=display_name(
            r.first_name, r.last_name, r.known_as)),
        from_club=ClubRef(id=r.from_club_id, name=r.from_name) if r.from_club_id else None,
        to_club=ClubRef(id=r.to_club_id, name=r.to_name) if r.to_club_id else None,
        kind=r.kind, fee_eur=r.fee_cents // 100,
        yours=meta.user_club_id in (r.from_club_id, r.to_club_id)) for r in rows]



@router.get("/listed")
def listed(session: Session) -> list[int]:
    """The user's players up for sale."""
    with session.read() as conn:
        meta = read_meta(conn)
        return [int(r.person_id) for r in conn.execute(text(
            "SELECT person_id FROM contract WHERE club_id = :u AND is_active = 1 AND listed = 1 "
            "ORDER BY person_id"), {"u": meta.user_club_id})]

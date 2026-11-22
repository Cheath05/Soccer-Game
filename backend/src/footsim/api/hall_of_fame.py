"""The user's club's history of players (20 Nov): everyone who has played for it in the career,
with his record there, where he is now, and the titles won while he was there; and its Hall of
fame, the players whose record reaches ``hall_of_fame`` in rules/lifecycle.yaml. The user can star
any of them as a favourite (22 Nov), kept in the career's meta."""

from collections import defaultdict
from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from footsim.api.routes import Session, _not_simulating
from footsim.api.schemas import ClubRef
from footsim.defs.lifecycle import HallOfFameDef
from footsim.importers.generate import age_on
from footsim.world.college.all_division import TITLE as ADT_TITLE
from footsim.world.college.season import NATIONAL_TITLE
from footsim.world.context import get_world
from footsim.world.meta import read_meta, write_meta
from footsim.world.squads import display_name

router = APIRouter(prefix="/api")


class FormerPlayerOut(BaseModel):
    player_id: int
    name: str
    position: str
    age: int
    first_season: str
    last_season: str
    seasons: int
    appearances: int
    starts: int
    minutes: int
    goals: int
    assists: int
    average_rating: float | None
    yellow: int
    red: int
    titles: list[str]  # the club's titles in his seasons there ("NCAA Championship 2026-27")
    now: str  # with_you | club | free_agent | retired
    club: ClubRef | None  # where he plays now, when it's another club
    hall_of_fame: bool
    favorite: bool  # starred by the user


class FavoriteIn(BaseModel):
    favorite: bool


class HallOfFameOut(BaseModel):
    club: ClubRef
    rule: str  # what it takes to get in, in words
    players: list[FormerPlayerOut]  # Hall of famers first, then by appearances
    favorites: list[int]  # the starred players' ids, in the order starred


_PLAYERS_SQL = """
    SELECT pm.player_id, COUNT(*) AS apps, SUM(pm.started) AS starts, SUM(pm.minutes) AS minutes,
           SUM(pm.goals) AS goals, SUM(pm.assists) AS assists, SUM(pm.rating) AS rating_sum,
           SUM(pm.yellow) AS yellow, SUM(pm.red) AS red, MIN(f.season_id) AS first_season,
           MAX(f.season_id) AS last_season, COUNT(DISTINCT f.season_id) AS seasons
    FROM player_match pm JOIN fixture f ON f.id = pm.fixture_id
    WHERE pm.club_id = :club
    GROUP BY pm.player_id
"""


@router.get("/club/hall-of-fame")
def hall_of_fame(session: Session) -> HallOfFameOut:
    """Everyone who has played for the user's club, with the Hall of famers marked."""
    world = get_world()
    rules = world.defs.lifecycle.hall_of_fame
    with session.read() as conn:
        meta = read_meta(conn)
        user = meta.user_club_id
        if user is None:
            raise HTTPException(409, "no club to manage")
        names = {int(r.id): str(r.name) for r in conn.execute(text("SELECT id, name FROM club"))}
        labels = {int(r.id): str(r.label)
                  for r in conn.execute(text("SELECT id, label FROM season"))}
        rows = conn.execute(text(_PLAYERS_SQL), {"club": user}).all()
        ids = [int(r.player_id) for r in rows]
        if not ids:
            return HallOfFameOut(club=ClubRef(id=user, name=names[user]), rule=_rule(rules),
                                 players=[], favorites=[])
        marks = ",".join(str(i) for i in ids)
        people = {int(r.id): r for r in conn.execute(text(
            f"SELECT pe.id, pe.first_name, pe.last_name, pe.known_as, pe.birth_date, "
            f"pl.retired_on FROM person pe JOIN player pl ON pl.person_id = pe.id "
            f"WHERE pe.id IN ({marks})"))}
        positions: dict[int, str] = {}
        for r in conn.execute(text(
                f"SELECT player_id, position FROM player_position WHERE player_id IN ({marks}) "
                f"ORDER BY player_id, familiarity DESC, position")):
            positions.setdefault(int(r.player_id), str(r.position))
        clubs = {int(r.person_id): int(r.club_id) for r in conn.execute(text(
            f"SELECT person_id, club_id FROM contract WHERE is_active = 1 AND kind != 'loan' "
            f"AND person_id IN ({marks})"))}
        seasons_of: dict[int, set[int]] = defaultdict(set)
        for r in conn.execute(text(
                "SELECT DISTINCT pm.player_id, f.season_id FROM player_match pm "
                "JOIN fixture f ON f.id = pm.fixture_id WHERE pm.club_id = :club"),
                {"club": user}):
            seasons_of[int(r.player_id)].add(int(r.season_id))
        titles: dict[int, list[tuple[str, bool]]] = defaultdict(list)  # season -> (title, national)
        for r in conn.execute(text(
                "SELECT t.season_id, t.title, t.kind, t.phase, c.type FROM league_title t "
                "JOIN competition c ON c.id = t.competition_id WHERE t.club_id = :club "
                "ORDER BY t.won_on, t.title"), {"club": user}):
            national = r.kind == "champion" and (
                (r.type == "league" and r.phase is None)
                or r.title in (NATIONAL_TITLE, ADT_TITLE))
            titles[int(r.season_id)].append((str(r.title), national))
        today: date = meta.current_date
        starred = set(meta.hall_of_fame_favorites)
        out = []
        for r in rows:
            pid = int(r.player_id)
            p = people.get(pid)
            if p is None:
                continue
            won = [(f"{t} {labels[s]}", national) for s in sorted(seasons_of[pid])
                   for t, national in titles.get(s, [])]
            apps = int(r.apps)
            rating = float(r.rating_sum) / apps if apps else None
            famous = apps >= rules.min_apps and (
                (rating is not None and rating >= rules.min_rating)
                or int(r.goals) >= rules.min_goals or int(r.assists) >= rules.min_assists
                or (rules.national_title and any(national for _, national in won)))
            club_id = clubs.get(pid)
            now = ("retired" if p.retired_on else "with_you" if club_id == user
                   else "club" if club_id is not None else "free_agent")
            out.append(FormerPlayerOut(
                player_id=pid, name=display_name(p.first_name, p.last_name, p.known_as),
                position=positions.get(pid, "CM"),
                age=age_on(date.fromisoformat(p.birth_date), today),
                first_season=labels[int(r.first_season)], last_season=labels[int(r.last_season)],
                seasons=int(r.seasons), appearances=apps, starts=int(r.starts or 0),
                minutes=int(r.minutes or 0), goals=int(r.goals or 0),
                assists=int(r.assists or 0),
                average_rating=round(rating, 2) if rating is not None else None,
                yellow=int(r.yellow or 0), red=int(r.red or 0), titles=[t for t, _ in won],
                now=now, club=ClubRef(id=club_id, name=names[club_id])
                if now == "club" and club_id is not None else None, hall_of_fame=famous,
                favorite=pid in starred))
        out.sort(key=lambda x: (not x.hall_of_fame, -x.appearances, -x.goals, x.name))
        shown = {p.player_id for p in out}
        return HallOfFameOut(club=ClubRef(id=user, name=names[user]), rule=_rule(rules),
                             players=out, favorites=[p for p in meta.hall_of_fame_favorites
                                                     if p in shown])


@router.put("/club/hall-of-fame/favorites/{player_id}")
def set_favorite(player_id: int, body: FavoriteIn, session: Session) -> HallOfFameOut:
    """Star (or unstar) a player who has played for the user's club."""
    _not_simulating(session)
    with session.write() as conn:
        meta = read_meta(conn)
        if meta.user_club_id is None:
            raise HTTPException(409, "no club to manage")
        played = conn.execute(text(
            "SELECT 1 FROM player_match WHERE club_id = :c AND player_id = :p LIMIT 1"),
            {"c": meta.user_club_id, "p": player_id}).first()
        if played is None:
            raise HTTPException(404, "he hasn't played for your club")
        favorites = [p for p in meta.hall_of_fame_favorites if p != player_id]
        if body.favorite:
            favorites.append(player_id)
        meta.hall_of_fame_favorites = favorites
        write_meta(conn, meta)
    session.autosave()
    return hall_of_fame(session)


def _rule(rules: HallOfFameDef) -> str:
    others = [f"a {rules.min_rating:.1f} average rating", f"{rules.min_goals} goals",
              f"{rules.min_assists} assists"]
    if rules.national_title:
        others.append("a national title")
    return (f"{rules.min_apps} appearances for the club, and " + ", ".join(others[:-1])
            + f" or {others[-1]}")

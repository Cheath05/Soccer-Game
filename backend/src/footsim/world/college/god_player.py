"""The OP player (college fixes, 20 Nov; first called the GOD player): once every few seasons
a college coach may sign a freshman with a professional's ratings, at a random position.

He joins at once as a freshman on no scholarship, with about ``god_player.overall``
(recruiting.yaml) and a potential only a little above it. He never declares early for the draft
(``draft.declare_prospects`` leaves him out), so he plays all four years. The career's meta keeps
who was signed and when; the next one is allowed ``every_seasons`` later."""

from dataclasses import dataclass
from datetime import date

from sqlalchemy import Connection, select, text

from footsim.core.rng import derive_rng
from footsim.persistence.schema import club, season
from footsim.world.college.common import ENROLLED, is_college_club
from footsim.world.college.roster import RecruitPerson, _Maker
from footsim.world.context import World
from footsim.world.meta import CareerMeta, bump_players_epoch, write_meta


class GodPlayerRefused(ValueError):
    """Why a OP player can't be signed now, for the user."""


@dataclass(frozen=True)
class GodPlayerStatus:
    available: bool
    next_season: str | None  # the season one is allowed again, when not now
    every_seasons: int
    overall: int
    signed: list[tuple[int, int]]  # (player id, season id), latest first


def _label(conn: Connection, season_id: int) -> str:
    """A season's label ("2030-31"), for seasons the save hasn't reached too."""
    row = conn.execute(select(season.c.label, season.c.id).order_by(season.c.id.desc())
                       .limit(1)).one()
    if season_id <= int(row.id):
        return str(conn.execute(select(season.c.label).where(season.c.id == season_id))
                   .scalar_one())
    first = int(str(row.label)[:4]) + season_id - int(row.id)
    return f"{first}-{str(first + 1)[2:]}"


def status(conn: Connection, world: World, meta: CareerMeta) -> GodPlayerStatus:
    rules = world.defs.college.recruiting.user.god_player
    last = max(meta.god_players.values(), default=None)
    ready = last is None or meta.season_id - last >= rules.every_seasons
    return GodPlayerStatus(
        available=ready,
        next_season=None if ready or last is None else _label(conn, last + rules.every_seasons),
        every_seasons=rules.every_seasons, overall=round(rules.overall),
        signed=sorted(meta.god_players.items(), key=lambda kv: (-kv[1], -kv[0])))


def sign(conn: Connection, world: World, meta: CareerMeta, day: date) -> int:
    """Sign this season's OP player for the user's program; his player id."""
    club_id = meta.user_club_id
    if club_id is None or not is_college_club(conn, club_id):
        raise GodPlayerRefused("The OP player is for a college coach.")
    found = status(conn, world, meta)
    if not found.available:
        raise GodPlayerRefused(f"You've had your OP player: the next one is in "
                               f"{found.next_season}.")
    roster = int(conn.execute(text("SELECT COUNT(*) FROM college_player WHERE club_id = :c "
                                   "AND status = :e"), {"c": club_id, "e": ENROLLED}).scalar_one())
    if roster >= world.defs.college.recruiting.programs.roster_max:
        raise GodPlayerRefused("Your roster is full: let a player go first.")
    rules = world.defs.college.recruiting.user.god_player
    college = world.defs.college.rules
    rng = derive_rng(meta.seed, "god-player", meta.season_id, club_id)
    positions = sorted(set(college.roster.shape))
    position = positions[int(rng.integers(len(positions)))]
    maker = _Maker(conn, world, meta, day)
    first, last = maker._names(maker.home, rng)
    born = date.fromordinal(day.toordinal() - int(rules.age * 365.25))
    reputation = int(conn.execute(select(club.c.reputation).where(club.c.id == club_id))
                     .scalar_one())
    pid = maker.make(club_id, reputation, position, 1, rules.age, rules.overall,
                     meta.season_id,
                     signed=RecruitPerson(first, last, maker.home, born,
                                          round(rules.overall) + rules.potential_room))
    maker.rows.write(conn, with_state=True)
    bump_players_epoch(conn)
    meta.god_players[pid] = meta.season_id
    write_meta(conn, meta)
    return pid

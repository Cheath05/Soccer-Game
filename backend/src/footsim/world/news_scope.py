"""Which news the user follows (college fixes, 20 Nov).

A league the user switched to fast results (world/fast_sim.py) is one they've said they don't
follow: its titles, play-offs, promotions and relegations stay out of the news, and so do the
cups of a country whose every league is fast. A user who follows no professional league at all (a
college coach who fast-simulates the rest of the world) hears nothing of the continental club
competitions, the Club World Cup or the retirements of other clubs' players either. The
competitions still play out; only their news is left out."""

from dataclasses import dataclass

from sqlalchemy import Connection, text

from footsim.world.college.common import is_college_club
from footsim.world.context import World
from footsim.world.meta import CareerMeta


def user_league(conn: Connection, meta: CareerMeta) -> str | None:
    """The key of the user's club's league this season (always fully simulated)."""
    if meta.user_club_id is None:
        return None
    if is_college_club(conn, meta.user_club_id):  # a college coach: the NCAA (W9c)
        return str(conn.execute(text("SELECT key FROM competition WHERE type = 'college'"))
                   .scalar_one())
    value = conn.execute(text(
        "SELECT c.key FROM club_league_membership m JOIN competition c ON c.id = m.competition_id "
        "WHERE m.club_id = :club AND m.season_id = :s"),
        {"club": meta.user_club_id, "s": meta.season_id}).scalar()
    return str(value) if value is not None else None


def effective_fast(conn: Connection, meta: CareerMeta) -> set[str]:
    """The competitions given fast results today: the setting, less the user's own league."""
    fast = set(meta.fast_leagues)
    if fast:
        fast.discard(user_league(conn, meta) or "")
    return fast


@dataclass(frozen=True)
class NewsScope:
    quiet_leagues: frozenset[str]  # the leagues on fast results (never the user's own)
    quiet_nations: frozenset[str]  # countries whose every league is on fast results
    league_nations: frozenset[str]  # countries with a league in the game
    quiet_world: bool  # every professional league is on fast results

    def follows_league(self, key: str) -> bool:
        return key not in self.quiet_leagues

    def follows_nation(self, nation: str) -> bool:
        """A country's cups: followed with one of its leagues, or, for a country without a
        league of its own (Canada's clubs play in MLS), with any professional league."""
        if nation in self.league_nations:
            return nation not in self.quiet_nations
        return not self.quiet_world


def news_scope(conn: Connection, world: World, meta: CareerMeta) -> NewsScope:
    fast = effective_fast(conn, meta)
    leagues = world.defs.leagues
    quiet = frozenset(k for k in leagues if k in fast)
    by_nation: dict[str, list[str]] = {}
    for key, league in leagues.items():
        by_nation.setdefault(league.nation, []).append(key)
    return NewsScope(
        quiet_leagues=quiet,
        quiet_nations=frozenset(n for n, keys in by_nation.items()
                                if all(k in quiet for k in keys)),
        league_nations=frozenset(by_nation),
        quiet_world=bool(leagues) and all(k in quiet for k in leagues))

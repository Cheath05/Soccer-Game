"""FIFA's international windows (W8 I2): call-ups, friendlies and Elo.

The day before a window starts, every AI-managed national team picks its squad
(``pick_squads``), and the called-up players are away from their clubs until the window ends
(``away_players``: unavailable to their clubs' line-ups). Each team plays a friendly on each of
the window's matchdays it has no other match on, against a nation of similar Elo. After every
international match, both teams' Elo moves by World Football Elo's formula. International
fixtures don't hold up the season's rollover (``season.season_complete``).
"""

import json
from datetime import date, timedelta

import numpy as np
from sqlalchemy import Connection, text

from footsim.core.rng import derive_rng
from footsim.defs.calendar import DateRange
from footsim.persistence.schema import competition, fixture
from footsim.world.context import World
from footsim.world.international.common import AWAY_KEY, TYPE
from footsim.world.international.finals import finals_day
from footsim.world.international.manager import ensure_squad
from footsim.world.international.pools import top_up_pools
from footsim.world.international.qualifiers import qualifiers_day
from footsim.world.international.teams import ensure_international, pick_squads
from footsim.world.meta import CareerMeta

FRIENDLY = "INTL_FRIENDLY"  # the friendlies' competition key, and their fixtures' stage
FINALS = "WCF:"  # the World Cup finals' fixtures' stages (I4)
ELO_KEY = "intl_elo_day"  # game_meta: the last day whose results moved Elo


def _meta_get(conn: Connection, key: str) -> object:
    value = conn.execute(text("SELECT value FROM game_meta WHERE key = :k"), {"k": key}).scalar()
    return json.loads(value) if value is not None else None


def _meta_set(conn: Connection, key: str, value: object) -> None:
    conn.execute(text("INSERT INTO game_meta (key, value) VALUES (:k, :v) "
                      "ON CONFLICT(key) DO UPDATE SET value = excluded.value"),
                 {"k": key, "v": json.dumps(value)})


def windows(world: World, meta: CareerMeta) -> list[DateRange]:
    from footsim.world.season import season_calendar  # season imports this module

    return list(season_calendar(world, meta, meta.season_id).international_windows)


def matchdays(world: World, window: DateRange) -> list[date]:
    rules = world.defs.international.rules.windows
    days: list[date] = []
    day = window.start + timedelta(days=rules.first_after_days)
    while day <= window.end and len(days) < rules.max_matchdays:
        days.append(day)
        day += timedelta(days=rules.spacing_days)
    return days


def competition_id(conn: Connection, key: str, name: str, short: str) -> int:
    """A national-team competition's row, added the first time it's needed."""
    found = conn.execute(text("SELECT id FROM competition WHERE key = :k"), {"k": key}).scalar()
    if found is not None:
        return int(found)
    return int(conn.execute(competition.insert().values(
        key=key, name=name, short_name=short, nation_id=None, type=TYPE, tier=None,
        sim_level="simulated")).lastrowid)


def international_day(conn: Connection, world: World, meta: CareerMeta, day: date) -> list[str]:
    """After ``day``'s matches: Elo for its international results; the end of a window; and, the
    day before one starts, the call-ups and the friendlies. Returns news for the user."""
    news: list[str] = []
    update_elo(conn, world, day)
    window = _meta_get(conn, AWAY_KEY)
    if isinstance(window, dict) and window["end"] <= day.isoformat():
        conn.execute(text("DELETE FROM game_meta WHERE key = :k"), {"k": AWAY_KEY})
    news += qualifiers_day(conn, world, meta, day)  # before the friendlies fill the gaps
    news += finals_day(conn, world, meta, day)
    tomorrow = day + timedelta(days=1)
    for w in windows(world, meta):
        if w.start == tomorrow:
            news += start_window(conn, world, meta, w)
    return news


def start_window(conn: Connection, world: World, meta: CareerMeta, window: DateRange
                 ) -> list[str]:
    """The call-ups for ``window`` and the friendlies on its free matchdays."""
    day = window.start - timedelta(days=1)
    ensure_international(conn, world, meta, day)
    _top_up(conn, world, meta, day)
    pick_squads(conn, world, meta, day)
    ensure_squad(conn, world, meta, day)  # the user's own, when he hasn't picked one
    _meta_set(conn, AWAY_KEY, {"start": window.start.isoformat(), "end": window.end.isoformat()})
    _schedule_friendlies(conn, world, meta, window)
    return _called_up_news(conn, meta)


def _top_up(conn: Connection, world: World, meta: CareerMeta, day: date) -> None:
    """Made-up home-based players for the places retirements have emptied (at each nation's
    current Elo)."""
    rules = world.defs.international.rules
    elo = {str(r.code): float(r.elo) for r in conn.execute(text(
        "SELECT code, elo FROM national_team"))}
    top_up_pools(conn, world, meta, day, elo,
                 {code: rules.reputation.of(value) for code, value in elo.items()})


def _schedule_friendlies(conn: Connection, world: World, meta: CareerMeta,
                         window: DateRange) -> None:
    rules = world.defs.international.rules.friendlies
    teams = conn.execute(text("SELECT club_id, code, confederation, elo FROM national_team "
                              "ORDER BY club_id")).all()
    comp = competition_id(conn, FRIENDLY, "International friendlies", "Friendlies")
    rows = []
    for k, day in enumerate(matchdays(world, window), start=1):
        busy = {int(c) for r in conn.execute(text(
            "SELECT home_club_id, away_club_id FROM fixture WHERE date = :d"),
            {"d": day.isoformat()}) for c in r}
        rng = derive_rng(meta.seed, "friendlies", day.isoformat())
        free = [t for t in teams if t.club_id not in busy]
        groups: dict[str, list[tuple[float, int]]] = {}
        for t in free:
            region = "WORLD" if rng.random() < rules.cross_confederation else t.confederation
            groups.setdefault(region, []).append(
                (float(t.elo) + float(rng.normal(0, rules.elo_noise)), int(t.club_id)))
        for region in sorted(groups):
            ordered = [cid for _, cid in sorted(groups[region], reverse=True)]
            for i in range(0, len(ordered) - 1, 2):
                home, away = ordered[i], ordered[i + 1]
                if rng.random() < 0.5:
                    home, away = away, home
                rows.append({"season_id": meta.season_id, "competition_id": comp,
                             "stage": FRIENDLY, "round": k, "tie": None, "leg": None,
                             "date": day.isoformat(), "home_club_id": home,
                             "away_club_id": away, "neutral": 0, "status": "scheduled"})
    if rows:
        conn.execute(fixture.insert(), rows)


def _called_up_news(conn: Connection, meta: CareerMeta) -> list[str]:
    if meta.user_club_id is None:
        return []
    rows = conn.execute(text(
        "SELECT p.first_name, p.last_name, p.known_as, c.name AS team FROM national_squad s "
        "JOIN person p ON p.id = s.player_id JOIN club c ON c.id = s.club_id "
        "JOIN playing k ON k.person_id = s.player_id WHERE k.club_id = :u "
        "ORDER BY c.name, p.last_name"), {"u": meta.user_club_id}).all()
    if not rows:
        return []
    from footsim.world.squads import display_name

    named = ", ".join(f"{display_name(r.first_name, r.last_name, r.known_as)} ({r.team})"
                      for r in rows)
    return [f"International duty: {named} {'is' if len(rows) == 1 else 'are'} away with "
            f"{'his' if len(rows) == 1 else 'their'} national "
            f"{'team' if len(rows) == 1 else 'teams'} for the window."]


# --- Elo ---------------------------------------------------------------------------------


def elo_change(world: World, home: float, away: float, home_goals: int, away_goals: int,
               neutral: bool, kind: str) -> float:
    """How much the home side's Elo moves (the away side's moves by the opposite)."""
    rules = world.defs.international.rules.elo
    gap = home + (0.0 if neutral else rules.home_advantage) - away
    expected = 1.0 / (10 ** (-gap / 400) + 1)
    result = 1.0 if home_goals > away_goals else 0.5 if home_goals == away_goals else 0.0
    n = abs(home_goals - away_goals)
    g = 1.0 if n <= 1 else 1.5 if n == 2 else (11 + n) / 8
    return float(rules.k[kind] * g * (result - expected))


def match_kind(stage: str) -> str:
    """Which K a national-team fixture's stage moves Elo by."""
    if stage == FRIENDLY:
        return "friendly"
    return "finals" if stage.startswith(FINALS) else "qualifier"


def update_elo(conn: Connection, world: World, day: date) -> None:
    """Move both teams' Elo for every international match played on ``day`` (once a day: the
    day is recorded, as after_day may run twice)."""
    if _meta_get(conn, ELO_KEY) == day.isoformat():
        return
    rows = conn.execute(text(
        "SELECT f.home_club_id, f.away_club_id, f.home_goals, f.away_goals, f.neutral, f.stage "
        "FROM fixture f JOIN competition c ON c.id = f.competition_id "
        "WHERE f.date = :d AND f.status = 'played' AND c.type = :t ORDER BY f.id"),
        {"d": day.isoformat(), "t": TYPE}).all()
    _meta_set(conn, ELO_KEY, day.isoformat())
    if not rows:
        return
    elo = {int(r.club_id): float(r.elo) for r in conn.execute(text(
        "SELECT club_id, elo FROM national_team"))}
    for r in rows:
        change = elo_change(world, elo[r.home_club_id], elo[r.away_club_id], r.home_goals,
                            r.away_goals, bool(r.neutral), match_kind(r.stage))
        elo[r.home_club_id] += change
        elo[r.away_club_id] -= change
    conn.execute(text("UPDATE national_team SET elo = :e WHERE club_id = :c"),
                 [{"c": c, "e": round(float(np.round(e, 1)), 1)} for c, e in elo.items()])

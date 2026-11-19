"""Leaving college: the draft pool, turning pro, the undrafted, and the college cycle at each
season's rollover (data/config/college/rules.yaml ``draft``).

After the College Cup every senior declares for MLS's SuperDraft, with the best underclassmen
(Generation adidas-style top prospects, flagged ``ga``). They stay on their college rosters, and
out of the market, until the draft (another step: W9a B5) turns the picks pro with ``turn_pro``.
Those nobody drafted become free agents in the spring (``release_undrafted``); one still unsigned
``grace_seasons`` later retires. At each rollover the classes move up and every program signs
its freshmen (world/college/roster.py)."""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import numpy as np
from sqlalchemy import Connection, Row, text

from footsim.defs.college import CLASS_NAMES
from footsim.domain.attributes import ATTRIBUTES
from footsim.importers.generate import age_on
from footsim.world.college.common import (
    COLLEGE_CONTRACT,
    ENROLLED,
    IN_COLLEGE,
    PRO,
    PROSPECT,
    UNDRAFTED,
    is_college_club,
)
from footsim.world.college.recruiting import enroll_class, had_class, update_prestige
from footsim.world.college.roster import recruit
from footsim.world.context import World
from footsim.world.meta import CareerMeta, bump_players_epoch
from footsim.world.squads import display_name


@dataclass(frozen=True)
class DraftProspect:
    """A college player in a season's draft pool."""

    player_id: int
    name: str
    college_id: int  # his college club
    college: str
    class_year: str  # Fr, So, Jr or Sr
    age: int
    position: str  # his best position
    overall: int
    potential: int  # his hidden potential (the draft's scouting is the drafting step's)
    ga: bool  # an underclassman who declared (Generation adidas)


def _players(conn: Connection, world: World, where: str, params: dict[str, object]
             ) -> list[tuple[Row[Any], str, int]]:
    """College players matching ``where`` (on ``cp``), with their best position and overall."""
    rows = conn.execute(text(f"""
        SELECT cp.player_id, cp.club_id, cp.class_year, cp.ga, p.first_name, p.last_name,
               p.known_as, p.birth_date, pl.pa_hidden, c.name AS college, a.*,
               (SELECT position FROM player_position pp WHERE pp.player_id = cp.player_id
                ORDER BY familiarity DESC, position LIMIT 1) AS position
        FROM college_player cp JOIN person p ON p.id = cp.player_id
        JOIN player pl ON pl.person_id = cp.player_id
        JOIN player_attr a ON a.player_id = cp.player_id
        JOIN club c ON c.id = cp.club_id
        WHERE {where} ORDER BY cp.player_id"""), params).all()
    if not rows:
        return []
    groups = world.model.group_overalls(
        np.array([[getattr(r, a) for a in ATTRIBUTES] for r in rows], dtype=float))
    out = []
    for i, r in enumerate(rows):
        position = str(r.position or "CM")
        out.append((r, position, round(float(groups[world.defs.positions[position].group][i]))))
    return out


def declare_prospects(conn: Connection, world: World, meta: CareerMeta, season_id: int,
                      day: date) -> list[str]:
    """The season's draft pool, after the College Cup: every senior, and the best underclassmen
    with enough potential. Returns news."""
    rules = world.defs.college.rules.draft
    seniors = conn.execute(text(
        "UPDATE college_player SET status = :prospect, declared_season = :s "
        "WHERE status = :enrolled AND class_year >= 4"),
        {"prospect": PROSPECT, "s": season_id, "enrolled": ENROLLED}).rowcount
    candidates = _players(conn, world, "cp.status = :enrolled AND cp.class_year < 4 "
                          "AND pl.pa_hidden >= :least",
                          {"enrolled": ENROLLED, "least": rules.min_potential})
    best = sorted(candidates, key=lambda c: (-int(c[0].pa_hidden), -c[2],
                                             int(c[0].player_id)))[:rules.underclassmen]
    if best:
        conn.execute(text("UPDATE college_player SET status = :prospect, declared_season = :s, "
                          "ga = 1 WHERE player_id = :p"),
                     [{"prospect": PROSPECT, "s": season_id, "p": int(c[0].player_id)}
                      for c in best])
    return [f"The draft pool: {seniors} college seniors and {len(best)} underclassmen "
            "(Generation adidas) declare for MLS's SuperDraft."]


def draft_pool(conn: Connection, world: World, meta: CareerMeta, season_id: int
               ) -> list[DraftProspect]:
    """The prospects of ``season_id``'s draft still to be picked, best first (overall and
    potential together)."""
    found = _players(conn, world, "cp.status = :prospect AND cp.declared_season = :s",
                     {"prospect": PROSPECT, "s": season_id})
    pool = []
    for row, position, overall in found:
        pool.append(DraftProspect(
            player_id=int(row.player_id),
            name=display_name(row.first_name, row.last_name, row.known_as),
            college_id=int(row.club_id), college=str(row.college),
            class_year=CLASS_NAMES[min(4, int(row.class_year))],
            age=age_on(date.fromisoformat(row.birth_date), meta.current_date),
            position=position, overall=overall, potential=int(row.pa_hidden),
            ga=bool(row.ga)))
    return sorted(pool, key=lambda p: (-(p.overall + p.potential), p.player_id))


def _leave(conn: Connection, player_ids: list[int], status: str, day: date) -> None:
    if not player_ids:
        return
    params = [{"p": p, "d": day.isoformat(), "status": status} for p in player_ids]
    conn.execute(text("UPDATE contract SET is_active = 0, end_date = :d WHERE person_id = :p "
                      f"AND kind = '{COLLEGE_CONTRACT}' AND is_active = 1"), params)
    conn.execute(text("UPDATE college_player SET status = :status, left_on = :d "
                      "WHERE player_id = :p"), params)
    bump_players_epoch(conn)  # he joins the market's players


def turn_pro(conn: Connection, meta: CareerMeta, player_id: int, day: date) -> None:
    """A college player turns pro (drafted, or signed by a club): his college contract ends and
    he is a free agent, whom a club can now sign. Raises ValueError if he isn't in college."""
    status = conn.execute(text("SELECT status FROM college_player WHERE player_id = :p"),
                          {"p": player_id}).scalar()
    if status not in IN_COLLEGE:
        raise ValueError(f"player {player_id} isn't a college player")
    _leave(conn, [player_id], PRO, day)


def leave_program(conn: Connection, world: World, player_id: int, day: date) -> None:
    """A college coach lets a player go (W9c): he leaves college as a free agent. Refused
    (ValueError) when it would leave the program fewer players or keepers than the squad rules'
    floor, or he isn't in college."""
    from footsim.world.overall_history import primary_positions

    club_id = conn.execute(text("SELECT club_id FROM college_player WHERE player_id = :p AND "
                                "status IN ('enrolled', 'prospect')"), {"p": player_id}).scalar()
    if club_id is None:
        raise ValueError(f"player {player_id} isn't a college player")
    rules = world.defs.lifecycle.squads
    roster = [int(r[0]) for r in conn.execute(text(
        "SELECT player_id FROM college_player WHERE club_id = :c AND status IN "
        "('enrolled', 'prospect')"), {"c": club_id})]
    if len(roster) - 1 < rules.user_min_players:
        raise ValueError(f"You need at least {rules.user_min_players} players.")
    positions = primary_positions(conn, roster)
    if positions.get(player_id) == "GK" and sum(
            1 for p in roster if positions.get(p) == "GK") - 1 < rules.user_min_keepers:
        raise ValueError(f"You need at least {rules.user_min_keepers} keepers.")
    _leave(conn, [player_id], UNDRAFTED, day)


def release_undrafted(conn: Connection, meta: CareerMeta, day: date) -> list[str]:
    """Prospects nobody drafted leave college as free agents. Returns news."""
    ids = [int(r.player_id) for r in conn.execute(text(
        "SELECT player_id FROM college_player WHERE status = :s ORDER BY player_id"),
        {"s": PROSPECT})]
    _leave(conn, ids, UNDRAFTED, day)
    if not ids:
        return []
    return [f"{len(ids)} college prospects nobody drafted are free agents."]


def college_turnover(conn: Connection, world: World, meta: CareerMeta, new_season: int,
                     day: date) -> list[str]:
    """The college cycle as a season ends: the last undrafted prospects and seniors leave, the
    undrafted still unsigned after the grace period retire, the classes move up, and every
    program signs its freshmen. Returns news."""
    rules = world.defs.college.rules.draft
    news = release_undrafted(conn, meta, day)
    seniors = [int(r.player_id) for r in conn.execute(text(
        "SELECT player_id FROM college_player WHERE status = :e AND class_year >= 4 "
        "ORDER BY player_id"), {"e": ENROLLED})]
    _leave(conn, seniors, UNDRAFTED, day)
    stale = (day - timedelta(days=round(365.25 * rules.grace_seasons))).isoformat()
    retiring = [{"p": int(r.player_id), "d": day.isoformat()} for r in conn.execute(text(
        "SELECT cp.player_id FROM college_player cp JOIN player pl ON pl.person_id = "
        "cp.player_id WHERE cp.status = :u AND cp.left_on <= :stale AND pl.retired_on IS NULL "
        "AND NOT EXISTS (SELECT 1 FROM contract k WHERE k.person_id = cp.player_id "
        "AND k.is_active = 1) ORDER BY cp.player_id"), {"u": UNDRAFTED, "stale": stale})]
    if retiring:
        conn.execute(text("UPDATE player SET retired_on = :d WHERE person_id = :p"), retiring)
        bump_players_epoch(conn)
    conn.execute(text("UPDATE college_player SET class_year = class_year + 1 "
                      "WHERE status = :e"), {"e": ENROLLED})
    # Programs' prestige moves with their results; the class they recruited (W9c) enrolls, and
    # generated freshmen fill any program still short (all of them, in a save's first season
    # with the college game, before it had a recruiting class).
    update_prestige(conn, world, meta, new_season - 1)
    recruited = had_class(conn, new_season)
    signed = enroll_class(conn, world, meta, new_season, day)
    # A college coach's program gets generated walk-ons only to a playable roster.
    coach = ({meta.user_club_id: world.defs.college.recruiting.user.min_roster}
             if recruited and meta.user_club_id is not None
             and is_college_club(conn, meta.user_club_id) else None)
    filled = recruit(conn, world, meta, new_season, day, minimum=0 if recruited else None,
                     targets=coach)
    if signed:
        news.append(f"College soccer: {signed} recruits enroll as freshmen at the NCAA's "
                    "programs.")
    if filled:
        news.append(f"College soccer: {filled} more freshmen join the NCAA's programs.")
    return news

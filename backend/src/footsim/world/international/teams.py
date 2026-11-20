"""National teams in a career (W8): their club rows, Elo, pools of made-up home-based players,
and the squads an AI manager picks."""

import json
from datetime import date

from sqlalchemy import Connection, text, update

from footsim.persistence.schema import club, nation, national_squad, national_team, tactic
from footsim.world.context import AI_FORMATIONS, World, default_instructions
from footsim.world.international.common import nation_ids
from footsim.world.international.pools import pool_players, top_up_pools
from footsim.world.meta import CareerMeta
from footsim.world.squads import load_squad


def ensure_international(conn: Connection, world: World, meta: CareerMeta, day: date
                         ) -> list[str]:
    """Every FIFA member's national team, if the save hasn't got them: its club row, Elo, the
    made-up players its squad needs, and a first squad; then the Club World Cup's guest clubs
    (W10), if it hasn't got those. Returns news (none)."""
    if conn.execute(text("SELECT 1 FROM national_team LIMIT 1")).first() is not None:
        _guests(conn, world, meta, day)
        return []
    teams = world.defs.international.teams
    rules = world.defs.international.rules
    ids = nation_ids(conn, world)
    for code, team in sorted(teams.items()):
        nation_id = min(ids[code]) if ids[code] else None
        if nation_id is None:
            nation_id = int(conn.execute(nation.insert().values(name=team.name, code=code)
                                         ).lastrowid)
            ids[code] = {nation_id}
        club_id = int(conn.execute(club.insert().values(
            name=team.name, nation_id=nation_id, source_league=None,
            reputation=rules.reputation.of(team.elo), stadium_name=None,
            stadium_capacity=None)).lastrowid)
        conn.execute(national_team.insert().values(club_id=club_id, code=code,
                                                   confederation=team.confederation,
                                                   elo=float(team.elo)))
    elo = {code: float(team.elo) for code, team in teams.items()}
    reputation = {code: rules.reputation.of(team.elo) for code, team in teams.items()}
    top_up_pools(conn, world, meta, day, elo, reputation)
    pick_squads(conn, world, meta, day)
    _guests(conn, world, meta, day)
    return []


def _guests(conn: Connection, world: World, meta: CareerMeta, day: date) -> None:
    """The guest clubs, once (world/international/guests.py), with their formations."""
    from footsim.world.international.guests import ensure_guests, guest_club_ids

    if conn.execute(text("SELECT 1 FROM guest_club LIMIT 1")).first() is not None:
        return
    ensure_guests(conn, world, meta, day)
    _formations(conn, world, day, sorted(guest_club_ids(conn)))


def pick_squads(conn: Connection, world: World, meta: CareerMeta, day: date,
                codes: set[str] | None = None) -> None:
    """Each national team's squad, as an AI manager picks it from the nation's players available
    on ``day`` (not injured): for each place of rules.yaml ``places`` (a 4-3-3 and its cover),
    the best players whose main position it is, by their rating there; a place nobody fills goes
    to the best left in the same group of positions, then to the best left at all. Then the
    team's formation is the one its squad suits best, as AI clubs choose theirs."""
    rules = world.defs.international.rules
    ids = nation_ids(conn, world)
    teams = {str(r.code): int(r.club_id) for r in conn.execute(text(
        "SELECT code, club_id FROM national_team ORDER BY code"))}
    if codes is not None:
        teams = {c: v for c, v in teams.items() if c in codes}
    teams = {c: v for c, v in teams.items() if v != meta.user_nation_id}  # the user picks theirs
    code_of_nation = {nid: code for code, s in ids.items() for nid in s}
    pooled = {int(r.player_id): str(r.code) for r in conn.execute(text(
        "SELECT player_id, code FROM national_pool"))}
    injured = {int(r.player_id) for r in conn.execute(text(
        "SELECT player_id FROM player_state WHERE injured_until > :d"), {"d": day.isoformat()})}
    candidates: dict[str, list[tuple[int, str, float]]] = {code: [] for code in teams}
    for pid, nid, position, overall in pool_players(conn, world):
        code = pooled.get(pid) or (code_of_nation.get(nid) if nid is not None else None)
        if code in candidates and pid not in injured:
            candidates[code].append((pid, position, overall))
    positions = world.defs.positions
    picks: list[dict[str, int]] = []
    chosen: dict[int, list[int]] = {}
    for code, club_id in teams.items():
        ranked = sorted(candidates[code], key=lambda c: (-c[2], c[0]))
        taken: list[int] = []
        short: list[str] = []
        for position, (starters, reserves) in sorted(rules.places.items()):
            mine = [c for c in ranked if c[1] == position and c[0] not in taken]
            taken += [c[0] for c in mine[:starters + reserves]]
            short += [position] * max(0, starters + reserves - len(mine))
        for position in short:
            group = positions[position].group
            near = [c for c in ranked if c[0] not in taken
                    and positions[c[1]].group is group] or [c for c in ranked if c[0] not in taken]
            if near:
                taken.append(near[0][0])
        chosen[club_id] = taken
        picks += [{"club_id": club_id, "player_id": pid} for pid in taken]
    if teams:
        conn.execute(national_squad.delete().where(
            national_squad.c.club_id.in_(list(teams.values()))))
    if picks:
        conn.execute(national_squad.insert(), picks)
    _formations(conn, world, day, list(chosen))


def _formations(conn: Connection, world: World, day: date, club_ids: list[int]) -> None:
    """The formation each national team's squad suits best (as AI clubs choose theirs)."""
    instructions = json.dumps(default_instructions(world.defs))
    existing = {int(r.club_id) for r in conn.execute(text("SELECT club_id FROM tactic"))}
    for club_id in club_ids:
        squad = load_squad(conn, club_id, day)
        if not squad:
            continue
        formation = world.picker.best_formation(club_id, "", squad, AI_FORMATIONS)
        values = {"formation": formation, "roles": json.dumps({}), "lineup": None,
                  "instructions": instructions}
        if club_id in existing:
            conn.execute(update(tactic).where(tactic.c.club_id == club_id).values(**values))
        else:
            conn.execute(tactic.insert().values(club_id=club_id, **values))

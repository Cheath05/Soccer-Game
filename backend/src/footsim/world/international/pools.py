"""Made-up home-based players (W8): every nation can field a squad at its real strength.

Many nations' players play at home, in leagues the game doesn't simulate (Egypt has 15 players
in the base world, Qatar one). For each nation, each place in a 4-3-3 and its cover
(rules.yaml ``places``) is wanted at the nation's level (its Elo as a best-XI overall; a
reserve a little lower). Where the nation's own players whose main position it is fall short, a
made-up player is added at the place's level. A nation whose own league is in the game has its
home-based players already: it only gets made-up players for places it has nobody for, at no
more than its own players' level. Made-up players have no club: they are listed in
``national_pool`` and kept out of the market. They develop, age and retire like everyone else,
and the pool is topped up the same way whenever it's checked again.
"""

from collections import defaultdict
from datetime import date, timedelta
from typing import Any

import numpy as np
from sqlalchemy import Connection, text

from footsim.core.rng import derive_rng
from footsim.domain.attributes import ATTRIBUTES
from footsim.importers.generate import (
    draw_personality,
    estimate_height,
    estimate_weight,
    player_reputation,
)
from footsim.match.synthetic import synthetic_player
from footsim.persistence.schema import (
    national_pool,
    person,
    player,
    player_attr,
    player_personality,
    player_position,
    player_state,
)
from footsim.world.context import World
from footsim.world.international.common import nation_ids
from footsim.world.lifecycle import NATURAL, _own_overalls
from footsim.world.meta import CareerMeta, bump_players_epoch


def pool_players(conn: Connection, world: World) -> list[tuple[int, int | None, str, float]]:
    """Every active player as (id, nation id, main position, overall there)."""
    rows = conn.execute(text(f"""
        SELECT p.id, p.nation_id, {", ".join("a." + a for a in ATTRIBUTES)},
            (SELECT position FROM player_position pp WHERE pp.player_id = p.id
             ORDER BY familiarity DESC, position LIMIT 1) AS position
        FROM person p JOIN player pl ON pl.person_id = p.id
        JOIN player_attr a ON a.player_id = p.id
        WHERE pl.retired_on IS NULL ORDER BY p.id""")).all()
    if not rows:
        return []
    attrs = np.array([[getattr(r, a) for a in ATTRIBUTES] for r in rows], dtype=float)
    positions = [str(r.position or "CM") for r in rows]
    overalls = _own_overalls(world, attrs, positions)
    return [(int(r.id), r.nation_id, positions[k], float(overalls[k]))
            for k, r in enumerate(rows)]


def _names(conn: Connection, world: World, by_code: dict[str, set[int]]
           ) -> dict[str, tuple[list[str], list[str]]]:
    """First and last names for each nation's made-up players (names.yaml)."""
    firsts: dict[int, list[str]] = defaultdict(list)
    lasts: dict[int, list[str]] = defaultdict(list)
    every: tuple[list[str], list[str]] = ([], [])
    for r in conn.execute(text("SELECT first_name, last_name, nation_id FROM person "
                               "WHERE first_name != '' AND last_name != '' ORDER BY id")):
        if r.nation_id is not None:
            firsts[r.nation_id].append(r.first_name)
            lasts[r.nation_id].append(r.last_name)
        every[0].append(r.first_name)
        every[1].append(r.last_name)

    def own(code: str) -> tuple[list[str], list[str]]:
        ids = sorted(by_code.get(code, set()))
        return ([n for i in ids for n in firsts[i]], [n for i in ids for n in lasts[i]])

    names = world.defs.international.names
    region_of = {code: region for region in names.regions.values() for code in region.nations}
    result = {}
    for code in world.defs.international.teams:
        first, last = own(code)
        if len(first) >= names.own_names_min:
            result[code] = (first, last)
            continue
        region = region_of.get(code)
        if region is None:
            result[code] = every
            continue
        for donor in region.donors:
            more = own(donor)
            first, last = first + more[0], last + more[1]
        first, last = first + region.first * 3, last + region.last * 3
        result[code] = (first, last) if first and last else every
    return result


def top_up_pools(conn: Connection, world: World, meta: CareerMeta, day: date,
                 elo: dict[str, float], reputation: dict[str, int]) -> int:
    """Add made-up players wherever a nation's places fall short. Returns how many."""
    rules = world.defs.international.rules
    by_code = nation_ids(conn, world)
    code_of_nation = {nid: code for code, ids in by_code.items() for nid in ids}
    pooled = {int(r.player_id): str(r.code) for r in conn.execute(text(
        "SELECT player_id, code FROM national_pool"))}
    have: dict[tuple[str, str], list[float]] = defaultdict(list)
    for pid, nid, position, overall in pool_players(conn, world):
        code = pooled.get(pid) or (code_of_nation.get(nid) if nid is not None else None)
        if code is not None:
            have[(code, position)].append(overall)
    names = _names(conn, world, by_code)
    next_id = int(conn.execute(text("SELECT COALESCE(MAX(id), 0) FROM person")).scalar_one()) + 1
    rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    # A nation whose own league is in the game already has its home-based players: made-up ones
    # only fill places it has nobody for, at no more than its own players' level.
    covered = {lg.nation for lg in world.defs.leagues.values()}
    for code in sorted(world.defs.international.teams):
        level = rules.level.of(elo[code])
        if code in covered:
            mine = sorted((v for (c, _), vs in have.items() if c == code for v in vs),
                          reverse=True)[:11]
            if mine:
                level = min(level, float(np.mean(mine)))
        rng = derive_rng(meta.seed, "national-pool", code, day.isoformat())
        first, last = names[code]
        nation = min(by_code[code]) if by_code.get(code) else None
        for position, (starters, reserves) in sorted(rules.places.items()):
            own = sorted(have[(code, position)], reverse=True)
            for k in range(starters + reserves):
                want = level - (0.0 if k < starters else rules.depth_drop)
                if k < len(own) and (code in covered or own[k] >= want - rules.margin):
                    continue
                pid = next_id
                next_id += 1
                _make(rows, world, rng, pid, code, nation, position,
                      want + float(rng.normal(0, rules.quality_sd)), day,
                      str(rng.choice(first)), str(rng.choice(last)), reputation[code])
    for table, key in ((person, "person"), (player, "player"), (player_attr, "attr"),
                       (player_position, "position"), (player_personality, "personality"),
                       (player_state, "state"), (national_pool, "pool")):
        if rows[key]:
            conn.execute(table.insert(), rows[key])
    if rows["player"]:
        bump_players_epoch(conn)
    return len(rows["player"])


def _make(rows: dict[str, list[dict[str, Any]]], world: World, rng: np.random.Generator,
          pid: int, code: str, nation: int | None, position: str, quality: float, day: date,
          first: str, last: str, club_reputation: int) -> None:
    """One made-up home-based player, rows for every table he needs."""
    rules = world.defs.international.rules
    build = world.defs.world_build
    attrs = synthetic_player(world.defs, pid, position, quality, rng).attrs
    values = {a: int(v) for a, v in zip(ATTRIBUTES, attrs, strict=True)}
    overall = float(_own_overalls(world, attrs[None, :], [position])[0])
    age = int(rng.integers(rules.ages[0], rules.ages[1] + 1))
    born = day - timedelta(days=int(np.ceil(age * 365.25)) + int(rng.integers(0, 364)))
    room = max(0.0, (27 - age) * 1.5)
    potential = int(min(99, round(overall + rules.potential_room + room * float(rng.random()))))
    side = "left" if position in ("LB", "LW", "LM", "LWB") else "other"
    foot = "Left" if rng.random() < world.defs.lifecycle.youth.left_footed[side] else "Right"
    height = estimate_height(position, values, build.physique, rng)
    rows["person"].append({"id": pid, "first_name": first, "last_name": last, "known_as": None,
                           "birth_date": born.isoformat(), "nation_id": nation,
                           "birth_city": None})
    rows["player"].append({
        "person_id": pid, "height_cm": height,
        "weight_kg": estimate_weight(height, values, build.physique, rng),
        "preferred_foot": foot, "weak_foot": int(rng.integers(2, 5)),
        "skill_moves": int(rng.integers(2, 5)), "pa_hidden": potential,
        "reputation": player_reputation(overall, club_reputation, build.reputation),
        "value_eur_cents": None, "retired_on": None})
    rows["attr"].append({"player_id": pid, **values})
    familiarity = {position: NATURAL}
    for adj in world.defs.adjacency:
        if adj.from_ == position and familiarity.get(adj.to, 0) < adj.familiarity:
            familiarity[adj.to] = adj.familiarity
    rows["position"] += [{"player_id": pid, "position": p, "familiarity": f}
                         for p, f in sorted(familiarity.items())]
    rows["personality"].append({"player_id": pid,
                                **draw_personality(overall, build.personality, rng)})
    rows["state"].append({"player_id": pid, "condition": 100.0, "form": 6.5,
                          "suspended_matches": 0, "season_yellows": 0})
    rows["pool"].append({"player_id": pid, "code": code})

"""Careers ending and starting, at each season's end (data/config/rules/lifecycle.yaml).

Players retire, mostly from their mid-thirties: keepers, the ageless and the still good later,
the poor sooner, and free agents nobody has signed leave the professional game. Every club
takes in a few youngsters from its academy, more and better at bigger clubs (its reputation
stands in for its academy until academies are built), named from the save's own players of
their country. Computer-run clubs whose squads have grown too big release their weakest."""

from collections import Counter, defaultdict
from datetime import date, timedelta
from typing import Any

import numpy as np
from sqlalchemy import Connection, select, text, update

from footsim.core.rng import derive_rng
from footsim.domain.attributes import ATTRIBUTES
from footsim.importers.generate import (
    age_on,
    draw_personality,
    estimate_height,
    estimate_weight,
    player_reputation,
)
from footsim.match.synthetic import synthetic_player
from footsim.persistence.schema import (
    club,
    contract,
    person,
    player,
    player_attr,
    player_personality,
    player_position,
    player_state,
)
from footsim.scouting.estimates import potential_label
from footsim.world.context import World
from footsim.world.meta import CareerMeta
from footsim.world.squads import display_name

NATURAL = 20  # familiarity in a player's own position


def _lookup(table: list[tuple[int, Any]], value: float) -> Any:
    """The entry for the highest threshold ``value`` reaches (the first one below them all)."""
    result = table[0][1]
    for threshold, entry in table:
        if value >= threshold:
            result = entry
    return result


def _own_overalls(world: World, attrs: np.ndarray, positions: list[str]) -> np.ndarray:
    overalls = world.model.group_overalls(attrs)
    groups = [world.defs.positions[p].group for p in positions]
    return np.array([overalls[g][i] for i, g in enumerate(groups)])


def retirement_chance(world: World, age: float, keeper: bool, overall: float, ageless: bool,
                      free_agent: bool) -> float:
    rules = world.defs.lifecycle.retirement
    later = rules.keeper_years if keeper else 0
    chance = 0.0
    for from_age, at_age in rules.by_age:
        if age >= from_age + later:
            chance = at_age
    if ageless:
        chance *= rules.ageless_factor
    if overall >= rules.good_from:
        chance *= rules.good_factor
    elif overall < rules.poor_below:
        chance *= rules.poor_factor
    if free_agent:
        chance = max(chance * rules.free_agent_factor, rules.free_agent_leave)
    return min(1.0, chance)


def _players(conn: Connection) -> list[Any]:
    return list(conn.execute(text("""
        SELECT p.id, p.first_name, p.last_name, p.known_as, p.birth_date, k.club_id,
               k.kind AS contract_kind, a.*,
               (SELECT position FROM player_position pp WHERE pp.player_id = p.id
                ORDER BY familiarity DESC LIMIT 1) AS primary_position,
               COALESCE(d.ageless, 0) AS ageless, pl.pa_hidden
        FROM person p JOIN player pl ON pl.person_id = p.id
        JOIN player_attr a ON a.player_id = p.id
        LEFT JOIN contract k ON k.person_id = p.id AND k.is_active = 1
        LEFT JOIN player_development d ON d.player_id = p.id
        WHERE pl.retired_on IS NULL
        ORDER BY p.id
    """)).all())


def retire_players(conn: Connection, world: World, meta: CareerMeta, day: date) -> list[str]:
    """Players who retire as the season ends; returns news of the user's and notable ones."""
    rules = world.defs.lifecycle.retirement
    rows = _players(conn)
    if not rows:
        return []
    positions = [r.primary_position or "CM" for r in rows]
    attrs = np.array([[getattr(r, a) for a in ATTRIBUTES] for r in rows], dtype=float)
    overalls = _own_overalls(world, attrs, positions)
    rng = derive_rng(meta.seed, "retirement", day.isoformat())
    names = {r.id: name for r, name in zip(rows, (
        display_name(r.first_name, r.last_name, r.known_as) for r in rows), strict=True)}
    retiring = []
    for r, position, overall, draw in zip(rows, positions, overalls, rng.random(len(rows)),
                                          strict=True):
        age = (day - date.fromisoformat(r.birth_date)).days / 365.25
        chance = retirement_chance(world, age, position == "GK", float(overall),
                                   bool(r.ageless), r.club_id is None)
        if draw < chance:
            retiring.append((r, int(age), float(overall)))
    for r, _, _ in retiring:
        conn.execute(update(player).where(player.c.person_id == r.id)
                     .values(retired_on=day.isoformat()))
        conn.execute(update(contract).where(contract.c.person_id == r.id,
                                            contract.c.is_active == 1)
                     .values(is_active=0, end_date=day.isoformat()))
    club_names = {c.id: c.name for c in conn.execute(select(club.c.id, club.c.name))}
    news = []
    for r, age, overall in sorted(retiring, key=lambda x: -x[2]):
        if r.club_id is not None and r.club_id == meta.user_club_id:
            news.append(f"{names[r.id]} retires at {age}.")
        elif r.club_id is not None and overall >= rules.news_from:
            news.append(f"{names[r.id]} ({club_names[r.club_id]}) retires at {age}.")
    return news


def _name_pools(conn: Connection) -> dict[int | None, tuple[list[str], list[str]]]:
    """First and last names by nation, from the save's own people."""
    firsts: dict[int | None, list[str]] = defaultdict(list)
    lasts: dict[int | None, list[str]] = defaultdict(list)
    for r in conn.execute(select(person.c.first_name, person.c.last_name, person.c.nation_id)):
        if r.first_name and r.last_name:
            firsts[r.nation_id].append(r.first_name)
            lasts[r.nation_id].append(r.last_name)
            firsts[None].append(r.first_name)
            lasts[None].append(r.last_name)
    return {nation: (firsts[nation], lasts[nation]) for nation in firsts}


def youth_intake(conn: Connection, world: World, meta: CareerMeta, day: date) -> list[str]:
    """Every club's youngsters from its academy; returns news of the user's."""
    rules = world.defs.lifecycle.youth
    clubs = conn.execute(text("""
        SELECT c.id, c.reputation, c.nation_id FROM club c
        WHERE EXISTS (SELECT 1 FROM contract k WHERE k.club_id = c.id AND k.is_active = 1)
        ORDER BY c.id""")).all()
    squad_nations: dict[int, Counter[int]] = defaultdict(Counter)
    for r in conn.execute(text("""SELECT k.club_id, p.nation_id FROM contract k
                                  JOIN person p ON p.id = k.person_id WHERE k.is_active = 1""")):
        if r.nation_id is not None:
            squad_nations[r.club_id][r.nation_id] += 1
    pools = _name_pools(conn)
    next_id = int(conn.execute(text("SELECT COALESCE(MAX(id), 0) FROM person")).scalar_one()) + 1
    codes = list(rules.positions)
    shares = np.array([rules.positions[c] for c in codes])
    shares = shares / shares.sum()
    build = world.defs.world_build
    minimum = int(world.defs.wage_levels.minimum_weekly_wage * 100)
    rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    ours = []
    for c in clubs:
        rng = derive_rng(meta.seed, "youth", day.isoformat(), c.id)
        count = max(1, int(round(rng.normal(_lookup(rules.intake, c.reputation),
                                            rules.intake_sd))))
        for _ in range(count):
            pid = next_id
            next_id += 1
            position = str(codes[int(rng.choice(len(codes), p=shares))])
            nation = c.nation_id
            if rng.random() > rules.home_nation and squad_nations[c.id]:
                options = sorted(squad_nations[c.id].items())
                weights = np.array([n for _, n in options], dtype=float)
                nation = options[int(rng.choice(len(options), p=weights / weights.sum()))][0]
            firsts, lasts = pools.get(nation) or pools[None]
            if len(firsts) < 30:
                firsts, lasts = pools[None]
            first, last = str(rng.choice(firsts)), str(rng.choice(lasts))
            age = int(rng.integers(rules.ages[0], rules.ages[1] + 1))
            born = day - timedelta(days=int(np.ceil(age * 365.25)) + int(rng.integers(0, 364)))
            quality = float(rng.normal(_lookup(rules.overall, c.reputation), rules.overall_sd))
            attrs = synthetic_player(world.defs, pid, position, quality, rng).attrs
            values = {a: int(v) for a, v in zip(ATTRIBUTES, attrs, strict=True)}
            overall = float(_own_overalls(world, attrs[None, :], [position])[0])
            potential = int(np.clip(rng.normal(_lookup(rules.potential, c.reputation),
                                               rules.potential_sd),
                                    overall + rules.potential_room, rules.max_potential))
            side = "left" if position in ("LB", "LW", "LM", "LWB") else "other"
            foot = "Left" if rng.random() < rules.left_footed[side] else "Right"
            height = estimate_height(position, values, build.physique, rng)
            rows["person"].append({"id": pid, "first_name": first, "last_name": last,
                                   "known_as": None, "birth_date": born.isoformat(),
                                   "nation_id": nation, "birth_city": None})
            rows["player"].append({
                "person_id": pid, "height_cm": height,
                "weight_kg": estimate_weight(height, values, build.physique, rng),
                "preferred_foot": foot,
                "weak_foot": int(rng.integers(rules.weak_foot[0], rules.weak_foot[1] + 1)),
                "skill_moves": int(rng.integers(rules.skill_moves[0], rules.skill_moves[1] + 1)),
                "pa_hidden": potential,
                "reputation": player_reputation(overall, c.reputation, build.reputation),
                "value_eur_cents": None, "retired_on": None})
            rows["attr"].append({"player_id": pid, **values})
            familiarity = {position: NATURAL}
            for adj in world.defs.adjacency:
                if adj.from_ == position and familiarity.get(adj.to, 0) < adj.familiarity:
                    familiarity[adj.to] = adj.familiarity
            rows["position"] += [{"player_id": pid, "position": p, "familiarity": f}
                                 for p, f in sorted(familiarity.items())]
            rows["personality"].append({
                "player_id": pid, **draw_personality(overall, build.personality, rng)})
            end = date(born.year + rules.contract_age + (1 if born.month > 6 else 0), 6, 30)
            rows["contract"].append({
                "person_id": pid, "club_id": c.id, "kind": "youth",
                "start_date": day.isoformat(), "end_date": max(end, day).isoformat(),
                "wage_weekly_cents": minimum, "release_clause_cents": None, "is_active": 1})
            rows["state"].append({"player_id": pid, "condition": 100.0, "form": 6.5,
                                  "suspended_matches": 0, "season_yellows": 0})
            if c.id == meta.user_club_id:
                ours.append((display_name(first, last, None), position, age_on(born, day),
                             potential))
    for table, key in ((person, "person"), (player, "player"), (player_attr, "attr"),
                       (player_position, "position"), (player_personality, "personality"),
                       (contract, "contract"), (player_state, "state")):
        if rows[key]:
            conn.execute(table.insert(), rows[key])
    if not ours:
        return []
    listed = ", ".join(f"{name} ({position}, {age})" for name, position, age, _ in ours)
    best = max(ours, key=lambda o: o[3])
    return [f"Youth intake: {listed} join from the academy. The coaches rate {best[0]} the "
            f"pick of them: {potential_label(best[3]).lower()}."]


def trim_squads(conn: Connection, world: World, meta: CareerMeta, day: date) -> None:
    """Computer-run clubs over their squad limit release their weakest: worst first, a young
    player counting half the potential he has yet to reach. Youngsters on youth contracts are
    in the youth squad, which doesn't count, until they're old enough for a first contract."""
    rules = world.defs.lifecycle.squads
    adult = world.defs.lifecycle.youth.contract_age
    rows = [r for r in _players(conn) if r.club_id is not None and r.club_id != meta.user_club_id
            and not (r.contract_kind == "youth"
                     and age_on(date.fromisoformat(r.birth_date), day) < adult)]
    by_club: dict[int, list[Any]] = defaultdict(list)
    for r in rows:
        by_club[r.club_id].append(r)
    for _, squad in sorted(by_club.items()):
        if len(squad) <= rules.max_players:
            continue
        positions = [r.primary_position or "CM" for r in squad]
        attrs = np.array([[getattr(r, a) for a in ATTRIBUTES] for r in squad], dtype=float)
        overalls = _own_overalls(world, attrs, positions)
        keepers = sorted((k for k, p in enumerate(positions) if p == "GK"),
                         key=lambda k: -float(overalls[k]))[:rules.keepers_kept]
        scores = []
        for k, r in enumerate(squad):
            age = age_on(date.fromisoformat(r.birth_date), day)
            room = (max(0.0, r.pa_hidden - float(overalls[k])) if age <= rules.young_until
                    else 0.0)
            scores.append((float(overalls[k]) + rules.potential_weight * room, -age, r.id, k))
        releasable = sorted(entry for entry in scores if entry[3] not in keepers)
        for _, _, pid, _ in releasable[:max(0, len(squad) - rules.keep)]:
            conn.execute(update(contract).where(contract.c.person_id == pid,
                                                contract.c.is_active == 1)
                         .values(is_active=0, end_date=day.isoformat()))


def season_turnover(conn: Connection, world: World, meta: CareerMeta, day: date) -> list[str]:
    """Retirements, then youth intakes, then over-full squads trimmed: at a season's end."""
    news = retire_players(conn, world, meta, day)
    news += youth_intake(conn, world, meta, day)
    trim_squads(conn, world, meta, day)
    return news


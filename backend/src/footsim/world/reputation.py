"""Clubs' reputations move (data/config/rules/reputation.yaml).

A club's reputation (1-99) is its stature. It's the market its players are priced in
(transfers/valuation.py), it decides which players will come (transfers/decisions.py), and it
sets the youth intake and cup seeding. It began at the world build, from its best 18 players. At
each season's turn it now drifts ``drift`` of the way towards a target:
- what its squad is worth now, by the build's own formula (the best 18 players' mean overall);
- blended with its league's standing (the mean reputation of the league it plays in next season),
  ``league_weight`` of it;
- plus a little for a title or a cup won in the season just ended.

So a club that builds a better side and climbs gains stature over a few seasons, and one that
sells its best players and drops loses it, without one good season making a giant. Nothing here
is random.
"""

from collections import defaultdict

import numpy as np
from sqlalchemy import Connection, text

from footsim.world.context import World
from footsim.world.meta import CareerMeta
from footsim.world.overall_history import player_overalls

TOP_PLAYERS = 18  # as the world build rates a club (world_build.yaml reputation.club_top_players)


def _squad_targets(conn: Connection, world: World) -> dict[int, float]:
    """The reputation each club's squad is worth now, by the world build's formula."""
    rules = world.defs.world_build.reputation
    overalls = player_overalls(conn, world)
    by_club: dict[int, list[int]] = defaultdict(list)
    for r in conn.execute(text("SELECT person_id, club_id FROM playing")):
        if r.person_id in overalls:
            by_club[int(r.club_id)].append(overalls[r.person_id])
    targets = {}
    for club_id, values in by_club.items():
        best = sorted(values, reverse=True)[:rules.club_top_players or TOP_PLAYERS]
        mean = float(np.mean(best))
        targets[club_id] = rules.club_base + rules.club_per_point * (
            mean - rules.club_reference_overall)
    return targets


def _honours(conn: Connection, world: World, season_id: int) -> dict[int, float]:
    """Silverware from ``season_id``: titles (a top flight's in full, lower ones' half) and cups."""
    rules = world.defs.reputation_drift
    bonus: dict[int, float] = defaultdict(float)
    for r in conn.execute(text(
            "SELECT f.club_id, c.key FROM league_final f JOIN competition c ON c.id = "
            "f.competition_id WHERE f.season_id = :s AND f.position = 1"), {"s": season_id}):
        league = world.defs.leagues.get(r.key)
        if league is not None:
            bonus[int(r.club_id)] += rules.title_bonus * (1.0 if league.tier == 1 else 0.5)
    for key, cup in world.defs.cups.items():
        winner = conn.execute(text(
            "SELECT t.winner_club_id FROM cup_tie t JOIN competition c ON c.id = t.competition_id "
            "WHERE c.key = :k AND t.season_id = :s AND t.round = :r AND t.winner_club_id IS NOT "
            "NULL"), {"k": key, "s": season_id, "r": len(cup.rounds) - 1}).scalar()
        if winner is not None:
            bonus[int(winner)] += rules.cup_bonus
    return bonus


def drift_reputations(conn: Connection, world: World, meta: CareerMeta, old_season: int,
                      new_season: int) -> list[str]:
    """Every club's reputation moves for the new season. Returns news of the user's club when
    its reputation moves by ``news_change`` or more."""
    rules = world.defs.reputation_drift
    squads = _squad_targets(conn, world)
    honours = _honours(conn, world, old_season)
    current = {int(r.id): float(r.reputation) for r in conn.execute(
        text("SELECT id, reputation FROM club"))}
    league_of = {int(r.club_id): int(r.competition_id) for r in conn.execute(text(
        "SELECT club_id, competition_id FROM club_league_membership WHERE season_id = :s"),
        {"s": new_season})}
    members: dict[int, list[float]] = defaultdict(list)
    for club_id, comp in league_of.items():
        members[comp].append(current[club_id])
    standing = {comp: float(np.mean(reps)) for comp, reps in members.items()}
    updates, news = [], []
    for club_id, rep in sorted(current.items()):
        squad = squads.get(club_id)
        if squad is None:
            continue  # a club without players keeps its name, and its standing
        target = squad
        if club_id in league_of:
            target = ((1 - rules.league_weight) * squad
                      + rules.league_weight * standing[league_of[club_id]])
        new = rep + rules.drift * (target - rep) + honours.get(club_id, 0.0)
        new_int = int(round(min(99.0, max(1.0, new))))
        if new_int != int(rep):
            updates.append({"c": club_id, "r": new_int})
            if club_id == meta.user_club_id and abs(new_int - rep) >= rules.news_change:
                word = "rises" if new_int > rep else "falls"
                change = new_int - int(rep)
                news.append(f"Your club's reputation {word} to {new_int} ({change:+d}).")
    if updates:
        conn.execute(text("UPDATE club SET reputation = :r WHERE id = :c"), updates)
    return news

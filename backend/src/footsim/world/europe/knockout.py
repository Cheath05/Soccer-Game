"""The European knockouts (W6 E4): the play-off, the round of 16, the quarter- and semi-finals
over two legs, and the final; their prize money; and the season's coefficient points.

Seeding comes from the league phase, with no draw: in the knockout play-off 9th meets 24th,
10th 23rd, and so on; in the round of 16 1st meets the winner of 16th v 17th, 2nd of 15th v
18th, down to 8th and the winner of 9th v 24th. From there a fixed bracket keeps the top
places apart (1st and 2nd can meet only in the final: the bracket order is 1, 8, 4, 5, 2, 7,
3, 6). The better-placed club plays the second leg at home; the final is at a neutral ground."""

from datetime import date
from typing import Any

from sqlalchemy import Connection, Row, select, update

from footsim.defs.europe import ContinentalDef
from footsim.persistence.schema import club_coefficient, continental_entry, cup_tie, fixture
from footsim.world.context import World
from footsim.world.cups import moved_ties_news
from footsim.world.europe.common import KNOCKOUT, competition_id, europe_calendar
from footsim.world.europe.ties import insert_ties, tie_winner
from footsim.world.finance import Entry, post
from footsim.world.meta import CareerMeta
from footsim.world.squads import club_name

BRACKET = [1, 8, 4, 5, 2, 7, 3, 6]  # round-of-16 ties by their seed, in bracket order


def _positions(conn: Connection, season_id: int, comp_id: int) -> dict[int, int]:
    """Each league-phase club's final position."""
    return {r.club_id: r.position for r in conn.execute(select(continental_entry).where(
        continental_entry.c.season_id == season_id,
        continental_entry.c.competition_id == comp_id,
        continental_entry.c.position.is_not(None)))}


def _ties(conn: Connection, season_id: int, comp_id: int, round_number: int) -> list[Row[Any]]:
    return list(conn.execute(select(cup_tie).where(
        cup_tie.c.season_id == season_id, cup_tie.c.competition_id == comp_id,
        cup_tie.c.round == round_number).order_by(cup_tie.c.id)).all())


def _pairs(comp: ContinentalDef, index: int, position: dict[int, int],
           previous: list[Row[Any]]) -> list[tuple[int, int]]:
    """Knockout round ``index``'s ties, each (first-leg host, second-leg host): the better
    placed club second. The play-off from the league phase; the round of 16 from the top
    places and the play-off's winners; later rounds along the bracket."""
    phase = comp.league_phase
    by_seed = {pos: c for c, pos in position.items()}
    if index == 0:
        first, last = phase.to_playoff
        pairs = [(by_seed[last - k], by_seed[first + k]) for k in range((last - first + 1) // 2)]
    elif index == 1:
        winners = [t.winner_club_id for t in previous]  # play-off ties in seed order
        pairs = [(winners[len(winners) - p], by_seed[p])
                 for p in range(1, phase.to_round_of_16 + 1)]
        pairs = [pairs[seed - 1] for seed in BRACKET]  # bracket order from here on
    else:
        winners = [t.winner_club_id for t in previous]
        pairs = [(winners[k], winners[k + 1]) for k in range(0, len(winners), 2)]
    return [(a, b) if position.get(b, 99) < position.get(a, 99) else (b, a) for a, b in pairs]


def _insert(conn: Connection, world: World, season_id: int, comp: ContinentalDef, comp_id: int,
            index: int, ties: list[tuple[int, int]], today: date) -> list[int]:
    days = europe_calendar(world, season_id).competitions[comp.key].knockout[index]
    return insert_ties(conn, world, season_id, comp_id, comp.key, KNOCKOUT + index, ties, days,
                       neutral=comp.knockout[index].neutral, today=today)


def progress_knockout(conn: Connection, world: World, meta: CareerMeta, comp: ContinentalDef,
                      today: date) -> list[str]:
    """Settle the knockout ties played so far and draw the next round once a round is over:
    the play-off once the league phase has its positions, the final's winner last."""
    season_id = meta.season_id
    comp_id = competition_id(conn, comp)
    position = _positions(conn, season_id, comp_id)
    if not position:
        return []  # the league phase isn't over
    prize = world.defs.finance.europe_prizes[comp.key]
    messages: list[str] = []
    for index in range(len(comp.knockout)):
        ties = _ties(conn, season_id, comp_id, KNOCKOUT + index)
        if not ties:
            previous = _ties(conn, season_id, comp_id, KNOCKOUT + index - 1) if index else []
            if index and (not previous or any(t.winner_club_id is None for t in previous)):
                return messages
            pairs = _pairs(comp, index, position, previous)
            moved = _insert(conn, world, season_id, comp, comp_id, index, pairs, today)
            post(conn, today, season_id, [Entry(c, "prize", round(prize.rounds[index] * 100),
                                                comp_id) for pair in pairs for c in pair])
            messages += _draw_news(conn, meta, comp, index, pairs)
            messages += moved_ties_news(conn, world, meta, moved)
            return messages
        decided = []
        for tie in ties:
            if tie.winner_club_id is None:
                winner = tie_winner(conn, season_id, comp.key, tie)
                if winner is not None:
                    conn.execute(update(cup_tie).where(cup_tie.c.id == tie.id)
                                 .values(winner_club_id=winner))
                    decided.append((tie, winner))
        messages += _result_news(conn, meta, comp, index, decided)
        if any(t.winner_club_id is None for t in _ties(conn, season_id, comp_id,
                                                      KNOCKOUT + index)):
            return messages
        if index == len(comp.knockout) - 1 and decided:
            champion = decided[0][1]
            post(conn, today, season_id, [Entry(champion, "prize", round(prize.winner * 100),
                                                comp_id)])
            messages.append(f"{club_name(conn, champion)} win the {comp.name}.")
            if all(_final_decided(conn, world, season_id, other)
                   for other in world.defs.continental.values()):
                record_coefficients(conn, world, season_id)
    return messages


def _final_decided(conn: Connection, world: World, season_id: int,
                   comp: ContinentalDef) -> bool:
    final = _ties(conn, season_id, competition_id(conn, comp),
                  KNOCKOUT + len(comp.knockout) - 1)
    return bool(final) and final[0].winner_club_id is not None


def record_coefficients(conn: Connection, world: World, season_id: int) -> None:
    """The season's coefficient points for every club that played in Europe: per win and
    draw (the summer play-off round included), and a bonus for each knockout round reached
    (europe/settings.yaml coefficient). Once, when the last final is decided."""
    if conn.execute(select(club_coefficient.c.club_id).where(
            club_coefficient.c.season_id == season_id)).first() is not None:
        return
    rules = world.defs.europe.coefficient
    points: dict[int, float] = {}
    for comp in world.defs.continental.values():
        comp_id = competition_id(conn, comp)
        for g in conn.execute(select(fixture).where(
                fixture.c.season_id == season_id, fixture.c.stage == comp.key,
                fixture.c.status == "played")):
            for club_id, ours, theirs in ((g.home_club_id, g.home_goals, g.away_goals),
                                          (g.away_club_id, g.away_goals, g.home_goals)):
                earned = rules.win if ours > theirs else rules.draw if ours == theirs else 0.0
                points[club_id] = points.get(club_id, 0.0) + earned
        bonus = rules.round_bonus[comp.key]
        for index in range(len(comp.knockout)):
            for tie in _ties(conn, season_id, comp_id, KNOCKOUT + index):
                for club_id in (tie.club_a_id, tie.club_b_id):
                    if club_id is not None:
                        points[club_id] = points.get(club_id, 0.0) + bonus[index]
            if index == len(comp.knockout) - 1:
                for tie in _ties(conn, season_id, comp_id, KNOCKOUT + index):
                    if tie.winner_club_id is not None:
                        points[tie.winner_club_id] += bonus[index]  # winning it, on top
    if points:
        conn.execute(club_coefficient.insert(), [
            {"club_id": c, "season_id": season_id, "points": p} for c, p in sorted(points.items())])


def _draw_news(conn: Connection, meta: CareerMeta, comp: ContinentalDef, index: int,
               pairs: list[tuple[int, int]]) -> list[str]:
    user = meta.user_club_id
    for a, b in pairs:
        if user in (a, b):
            other = b if user == a else a
            return [f"{comp.name} {comp.knockout[index].name.lower()}: "
                    f"{club_name(conn, user)} v {club_name(conn, other)}."]
    return []


def _result_news(conn: Connection, meta: CareerMeta, comp: ContinentalDef, index: int,
                 decided: list[tuple[Row[Any], int]]) -> list[str]:
    user = meta.user_club_id
    if user is None:
        return []
    for tie, winner in decided:
        if user in (tie.club_a_id, tie.club_b_id):
            name = comp.knockout[index].name.lower()
            if winner == user:
                if index == len(comp.knockout) - 1:
                    return []  # the winner's own line says it
                return [f"{club_name(conn, user)} are through the {comp.name} {name}."]
            return [f"{club_name(conn, user)} are out of the {comp.name}, beaten by "
                    f"{club_name(conn, winner)} in the {name}."]
    return []

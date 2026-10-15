"""The European qualifying rounds (W7 A4, docs/plans/w7-all-of-uefa.md): the first, second and
third qualifying rounds and the play-off round, in each competition's paths (europe/
access_list.yaml `nodes`), the losers of one competition's rounds dropping into a lower one's.

At the season's start the entries are planned (``plan_season``): an empty place is filled by the
best club by coefficient entering lower down the same path, a round left odd takes two more clubs
from the round below (or gives its best club a bye when it's drawn), and each league phase comes
out at exactly its size. Then each round is drawn as soon as every round feeding it is decided
(``draw_ready``), and its ties settled as they're played (``settle``): winners up a round, losers
down into another competition, or out.

A round's fixtures use the round numbers -3 (Q1), -2 (Q2), -1 (Q3) and 0 (PO); its path is in
``cup_tie.path`` and its ties' labels (C1, L1, M1...; a bye CB1...). A club's ``continental_entry``
row says where it is: its competition, ``entry_round`` and ``path``, ``stage`` qualifying until it
reaches a league phase (league_phase) or is out (out); ``entered`` where it started, and
``came_from`` the round it dropped from."""

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from sqlalchemy import Connection, Row, select, update

from footsim.core.rng import derive_rng
from footsim.persistence.schema import club, continental_entry, cup_tie, nation
from footsim.world.context import World
from footsim.world.cups import moved_ties_news
from footsim.world.europe.access import nation_order
from footsim.world.europe.coefficients import coefficients
from footsim.world.europe.common import (
    LEAGUE_PHASE,
    QUALIFYING_ROUNDS,
    competition_id,
    competitions_by_rank,
    europe_calendar,
    round_key,
    round_number,
)
from footsim.world.europe.places import Vacancy, qualify
from footsim.world.europe.ranking import access_ranking
from footsim.world.europe.ties import insert_ties, tie_winner
from footsim.world.finance import Entry as LedgerEntry
from footsim.world.finance import post
from footsim.world.meta import CareerMeta
from footsim.world.squads import club_name

PATH_LETTER = {"champions": "C", "league": "L", "main": "M"}
PATH_NAME = {"champions": "Champions Path", "league": "League Path", "main": "Main Path"}
BALANCE_PASSES = 200  # the balancing loop settles in far fewer


@dataclass(frozen=True)
class Node:
    """One path of one qualifying round of a competition, or its league phase (round LP)."""

    competition: str
    round: str  # Q1, Q2, Q3, PO or LP
    path: str | None  # champions, league or main; None for a league phase


@dataclass
class Entrant:
    club_id: int
    route: str
    association: str | None
    coefficient: float


@dataclass
class Plan:
    """Each round's direct entrants, after the places are filled and the rounds balanced."""

    direct: dict[Node, list[Entrant]] = field(default_factory=lambda: defaultdict(list))


# --- the rounds and paths -------------------------------------------------------------------------

@dataclass(frozen=True)
class Structure:
    """The qualifying rounds' structure, worked out once from the access list."""

    order: list[Node]  # every round and path, in the order they're settled
    winners: dict[Node, Node]
    losers: dict[Node, Node | None]
    feeders: dict[Node, list[Node]]


_STRUCTURES: dict[int, Structure] = {}


def structure(world: World) -> Structure:
    access = world.defs.europe_access
    found = _STRUCTURES.get(id(access))
    if found is not None:
        return found
    order: list[Node] = []
    for comp in competitions_by_rank(world):
        order += sorted((Node(comp.key, n.round, n.path)
                         for n in access.competitions[comp.key].nodes),
                        key=lambda n: (QUALIFYING_ROUNDS.index(n.round), n.path or ""))
    winners: dict[Node, Node] = {}
    losers: dict[Node, Node | None] = {}
    for node in order:
        rule = next(n for n in access.competitions[node.competition].nodes
                    if (n.round, n.path) == (node.round, node.path))
        if rule.winners is not None:
            winners[node] = Node(rule.winners.competition or node.competition,
                                 rule.winners.round,
                                 None if rule.winners.round == LEAGUE_PHASE else rule.winners.path)
        else:
            k = QUALIFYING_ROUNDS.index(node.round)
            winners[node] = (Node(node.competition, QUALIFYING_ROUNDS[k + 1], node.path)
                             if k + 1 < len(QUALIFYING_ROUNDS)
                             else Node(node.competition, LEAGUE_PHASE, None))
        losers[node] = (None if rule.losers is None else Node(
            rule.losers.competition or node.competition, rule.losers.round,
            None if rule.losers.round == LEAGUE_PHASE else rule.losers.path))
    feeding = {node: [n for n in order if winners[n] == node or losers[n] == node]
               for node in order}
    found = Structure(order, winners, losers, feeding)
    _STRUCTURES[id(access)] = found
    return found


def nodes(world: World) -> list[Node]:
    """Every qualifying round and path, in the order they're settled: the top competition first
    (its losers drop into the others), each from its first round up."""
    return structure(world).order


def winners_to(world: World, node: Node) -> Node:
    """Where a round's winners go: as its `winners` says, else the same path's next round, the
    play-off's into the league phase."""
    return structure(world).winners[node]


def losers_to(world: World, node: Node) -> Node | None:
    """Where a round's losers go (a lower competition's round or league phase), or None: out."""
    return structure(world).losers[node]


def feeders(world: World, node: Node) -> list[Node]:
    """The rounds whose winners or losers come into ``node``."""
    return structure(world).feeders.get(node, [])


def round_name(world: World, node: Node) -> str:
    """A round in words: "Second qualifying round (Champions Path)"; the path only where the
    round has more than one."""
    if node.round == LEAGUE_PHASE:
        return "League phase"
    comp = world.defs.continental[node.competition]
    name = next(r.name for r in comp.qualifying if r.key == node.round)
    paths = {n.path for n in nodes(world)
             if n.competition == node.competition and n.round == node.round}
    return f"{name} ({PATH_NAME[node.path or 'main']})" if len(paths) > 1 else name


# --- the season's plan ----------------------------------------------------------------------------

def _below(world: World, competition: str, round_key: str, path: str | None) -> list[Node]:
    """The rounds of a competition's path below ``round_key`` (LP: all of them), highest first."""
    top = (len(QUALIFYING_ROUNDS) if round_key == LEAGUE_PHASE
           else QUALIFYING_ROUNDS.index(round_key))
    return [n for n in reversed(nodes(world)) if n.competition == competition and n.path == path
            and QUALIFYING_ROUNDS.index(n.round) < top]


def _take_best(plan: Plan, source: list[Node]) -> tuple[Entrant, Node] | None:
    """Remove and return the best direct entrant by coefficient in the ``source`` rounds."""
    pool = [(e, n) for n in source for e in plan.direct[n]]
    if not pool:
        return None
    best, home = max(pool, key=lambda p: (p[0].coefficient, -p[0].club_id))
    plan.direct[home].remove(best)
    return best, home


def fill_vacancies(world: World, plan: Plan, vacancies: list[Vacancy]) -> None:
    """Fill each empty place with the best club by coefficient entering lower down its path
    (UEFA's rule since 2024), from the top rounds down; the place that club leaves is filled the
    same way, so the gaps end up in a path's first round."""
    rank = {key: k for k, key in enumerate([LEAGUE_PHASE, *reversed(QUALIFYING_ROUNDS)])}
    pending = [(Node(v.competition, v.round, v.path), v.fill_from) for v in vacancies]
    while pending:
        pending.sort(key=lambda p: (world.defs.continental[p[0].competition].rank,
                                    rank[p[0].round]))
        node, fill_from = pending.pop(0)
        path = fill_from if node.round == LEAGUE_PHASE else node.path
        taken = _take_best(plan, _below(world, node.competition, node.round, path))
        if taken is None:
            continue
        best, home = taken
        plan.direct[node].append(best)
        pending.append((home, None))


def sizes(world: World, plan: Plan) -> dict[Node, int]:
    """How many clubs each round will have: its direct entrants, the winners of the rounds feeding
    it and the losers dropping into it (a round with an odd number gives its best club a bye, so
    its winners are rounded up); and each league phase's."""
    size: dict[Node, int] = {}
    coming: dict[Node, int] = defaultdict(int)
    for node in nodes(world):
        n = len(plan.direct[node]) + coming[node]
        size[node] = n
        coming[winners_to(world, node)] += (n + 1) // 2
        drop = losers_to(world, node)
        if drop is not None:
            coming[drop] += n // 2
    for key in world.defs.continental:
        lp = Node(key, LEAGUE_PHASE, None)
        size[lp] = len(plan.direct[lp]) + coming[lp]
    return size


def balance(world: World, plan: Plan) -> None:
    """Even rounds and full league phases, as UEFA re-balances. A round with an odd number of
    clubs sends its best direct entrant a round higher (which keeps that round's number), or,
    with no direct entrant to send, takes two more from the round below when that round has two
    to spare; a league phase short of its size takes the best direct entrant of its play-off
    rounds; until nothing changes. A round still odd gives its best club a bye when it's
    drawn."""
    for _ in range(BALANCE_PASSES):
        size = sizes(world, plan)
        changed = False
        for node in nodes(world):
            if size[node] % 2 == 0:
                continue
            above = winners_to(world, node)
            if plan.direct[node] and above.competition == node.competition:
                taken = _take_best(plan, [node])
                assert taken is not None
                plan.direct[above].append(taken[0])
                changed = True
                break
            below = _below(world, node.competition, node.round, node.path)[:1]
            if below and len(plan.direct[below[0]]) >= 2 and size[below[0]] % 2 == 0 \
                    and size[below[0]] >= 4:
                for _ in range(2):
                    taken = _take_best(plan, below)
                    assert taken is not None
                    plan.direct[node].append(taken[0])
                changed = True
                break
        if changed:
            continue
        for key, comp in world.defs.continental.items():
            lp = Node(key, LEAGUE_PHASE, None)
            if size[lp] < comp.league_phase.clubs:
                playoffs = [n for n in nodes(world) if n.competition == key and n.round == "PO"]
                taken = _take_best(plan, playoffs)
                if taken is not None:
                    plan.direct[lp].append(taken[0])
                    changed = True
                    break
            elif size[lp] > comp.league_phase.clubs:
                raise ValueError(f"{key}: {size[lp]} clubs for a league phase of "
                                 f"{comp.league_phase.clubs}")
        if not changed:
            return
    raise ValueError("the European qualifying didn't balance")


def plan_season(conn: Connection, world: World, meta: CareerMeta, season_id: int) -> Plan:
    """The season's entries, places filled and rounds balanced. A league phase still short (a
    world missing some countries' clubs, an old save) takes the next clubs not yet in Europe of
    the best-ranked countries, in turn."""
    entries, vacancies = qualify(conn, world, meta, season_id)
    coeff = coefficients(conn, world, [e.club_id for e in entries], season_id)
    plan = Plan()
    for e in entries:
        plan.direct[Node(e.competition, e.round, e.path)].append(
            Entrant(e.club_id, e.route, e.association, coeff[e.club_id]))
    fill_vacancies(world, plan, vacancies)
    balance(world, plan)
    size = sizes(world, plan)
    short = {key: comp.league_phase.clubs - size[Node(key, LEAGUE_PHASE, None)]
             for key, comp in world.defs.continental.items()}
    if any(n > 0 for n in short.values()):
        _fill_league_phases(conn, world, meta, season_id, plan, short)
        balance(world, plan)
    return plan


def _fill_league_phases(conn: Connection, world: World, meta: CareerMeta, season_id: int,
                        plan: Plan, short: dict[str, int]) -> None:
    """Fill each league phase's missing places, the top competition first, with the next club
    not yet in Europe of each country in ranking order, taking the countries in turn."""
    taken = {e.club_id for entrants in plan.direct.values() for e in entrants}
    countries = [r.nation for r in access_ranking(conn, world, season_id)]
    orders = {code: nation_order(conn, world, meta, season_id, code) for code in countries}
    turn = 0
    for comp in competitions_by_rank(world):
        for _ in range(max(0, short[comp.key])):
            for _ in range(len(countries)):
                code = countries[turn % len(countries)]
                turn += 1
                club_id = next((c for c in orders[code] if c not in taken), None)
                if club_id is not None:
                    taken.add(club_id)
                    plan.direct[Node(comp.key, LEAGUE_PHASE, None)].append(
                        Entrant(club_id, f"fill:{code}", code, 0.0))
                    break


def start_qualifying(conn: Connection, world: World, meta: CareerMeta, season_id: int,
                     today: date) -> list[str]:
    """The season's entries (``continental_entry``), their payments for the rounds they enter,
    and the first rounds' draws."""
    plan = plan_season(conn, world, meta, season_id)
    rows = []
    for node, entrants in plan.direct.items():
        comp_id = competition_id(conn, world.defs.continental[node.competition])
        for e in entrants:
            rows.append({
                "season_id": season_id, "competition_id": comp_id, "club_id": e.club_id,
                "stage": "league_phase" if node.round == LEAGUE_PHASE else "qualifying",
                "route": e.route, "pot": None, "position": None, "association": e.association,
                "entry_round": round_number(node.round), "path": node.path,
                "entered": _node_text(node), "came_from": None})
    if rows:
        conn.execute(continental_entry.insert(), rows)
    messages = _entry_news(conn, world, meta, plan)
    return messages + draw_ready(conn, world, meta, today)


# --- draws ----------------------------------------------------------------------------------------

def pair_up(seeded: list[int], order: list[int], allowed: Callable[[int, int], bool]
            ) -> list[tuple[int, int]] | None:
    """Every seeded club paired with an unseeded one that ``allowed`` permits, trying unseeded
    clubs in ``order`` (a shuffle): augmenting paths (Kuhn's). None if no full pairing exists.
    Pairs are (unseeded, seeded): the unseeded club at home first."""
    match: dict[int, int] = {}  # unseeded -> seeded

    def place(s: int, seen: set[int]) -> bool:
        for u in order:
            if u in seen or not allowed(s, u):
                continue
            seen.add(u)
            if u not in match or place(match[u], seen):
                match[u] = s
                return True
        return False

    for s in seeded:
        if not place(s, set()):
            return None
    by_seeded = {s: u for u, s in match.items()}
    return [(by_seeded[s], s) for s in seeded]


def draw_pairs(conn: Connection, world: World, meta: CareerMeta, node: Node,
               clubs: list[int], coeff: dict[int, float]
               ) -> tuple[list[tuple[int, int]], list[int]]:
    """A round's ties, and its bye: the best club by coefficient gets one if the number is odd;
    the top half of the rest is seeded against the bottom half; no two clubs of a country and no
    prohibited pair of countries (europe/settings.yaml) meet where a draw allows."""
    ranked = sorted(clubs, key=lambda c: (-coeff.get(c, 0.0), c))
    byes = ranked[:1] if len(ranked) % 2 else []
    playing = ranked[len(byes):]
    seeded, unseeded = playing[:len(playing) // 2], playing[len(playing) // 2:]
    country = {r.id: r.code for r in conn.execute(select(club.c.id, nation.c.code).join(
        nation, nation.c.id == club.c.nation_id).where(club.c.id.in_(playing)))}
    prohibited = {frozenset(pair) for pair in world.defs.europe.prohibited}
    rng = derive_rng(meta.seed, "europe-qualifying-draw", meta.season_id, node.competition,
                     node.round, node.path or "")
    order = [unseeded[k] for k in rng.permutation(len(unseeded))]

    def apart(a: int, b: int) -> bool:
        return frozenset((country.get(a), country.get(b))) not in prohibited

    rules: list[Callable[[int, int], bool]] = [
        lambda a, b: country.get(a) != country.get(b) and apart(a, b), apart, lambda a, b: True]
    for allowed in rules:
        pairs = pair_up(seeded, order, allowed)
        if pairs is not None:
            return pairs, byes
    raise AssertionError("an unconstrained pairing always exists")


@dataclass
class State:
    """Where every qualifying round stands: its ties, and the clubs in it not yet in a tie."""

    comp_ids: dict[str, int]
    ties: dict[Node, list[Row[Any]]]
    waiting: dict[Node, list[int]]


def state(conn: Connection, world: World, season_id: int) -> State:
    comp_ids = {key: competition_id(conn, comp) for key, comp in world.defs.continental.items()}
    by_id = {v: k for k, v in comp_ids.items()}
    ties: dict[Node, list[Row[Any]]] = defaultdict(list)
    for t in conn.execute(select(cup_tie).where(
            cup_tie.c.season_id == season_id, cup_tie.c.round <= round_number("PO"),
            cup_tie.c.competition_id.in_(list(comp_ids.values()))).order_by(cup_tie.c.id)):
        ties[Node(by_id[t.competition_id], round_key(t.round), t.path)].append(t)
    tied = {(node, c) for node, rows in ties.items() for t in rows
            for c in (t.club_a_id, t.club_b_id) if c is not None}
    waiting: dict[Node, list[int]] = defaultdict(list)
    for e in conn.execute(select(continental_entry.c.club_id, continental_entry.c.competition_id,
                                 continental_entry.c.entry_round, continental_entry.c.path)
                          .where(continental_entry.c.season_id == season_id,
                                 continental_entry.c.stage == "qualifying")
                          .order_by(continental_entry.c.club_id)):
        node = Node(by_id[e.competition_id], round_key(e.entry_round), e.path)
        if (node, e.club_id) not in tied:
            waiting[node].append(e.club_id)
    return State(comp_ids, ties, waiting)


def decided(world: World, now: State, node: Node, memo: dict[Node, bool]) -> bool:
    """Whether a round is over: every round feeding it is, nobody is waiting in it, and every
    one of its ties has a winner."""
    if node not in memo:
        memo[node] = (all(decided(world, now, f, memo) for f in feeders(world, node))
                      and not now.waiting.get(node)
                      and all(t.winner_club_id is not None for t in now.ties.get(node, [])))
    return memo[node]


def qualifying_done(conn: Connection, world: World, season_id: int) -> bool:
    """Whether every qualifying round is over: nobody left in one, and no tie undecided."""
    in_play = conn.execute(select(continental_entry.c.id).where(
        continental_entry.c.season_id == season_id,
        continental_entry.c.stage == "qualifying")).first()
    comp_ids = [competition_id(conn, comp) for comp in world.defs.continental.values()]
    undecided = conn.execute(select(cup_tie.c.id).where(
        cup_tie.c.season_id == season_id, cup_tie.c.round <= round_number("PO"),
        cup_tie.c.competition_id.in_(comp_ids), cup_tie.c.winner_club_id.is_(None))).first()
    return in_play is None and undecided is None


def draw_ready(conn: Connection, world: World, meta: CareerMeta, today: date) -> list[str]:
    """Draw every round whose feeding rounds are all decided and that has clubs waiting: its
    bye first (straight into the next round), then its ties on the round's dates."""
    season_id = meta.season_id
    messages: list[str] = []
    now = state(conn, world, season_id)
    for node in nodes(world):
        if now.ties.get(node):
            continue  # drawn already
        memo: dict[Node, bool] = {}
        if not all(decided(world, now, f, memo) for f in feeders(world, node)):
            continue
        clubs = now.waiting.get(node, [])
        if not clubs:
            continue
        comp = world.defs.continental[node.competition]
        comp_id = now.comp_ids[node.competition]
        coeff = coefficients(conn, world, clubs, season_id)
        pairs, byes = draw_pairs(conn, world, meta, node, clubs, coeff)
        letter = PATH_LETTER[node.path or "main"]
        if byes:
            conn.execute(cup_tie.insert(), [
                {"season_id": season_id, "competition_id": comp_id,
                 "round": round_number(node.round), "tie": f"{letter}B{k}", "club_a_id": c,
                 "club_b_id": None, "winner_club_id": c, "path": node.path}
                for k, c in enumerate(byes, start=1)])
            for c in byes:
                _advance(conn, world, today, season_id, node, c)
        days = _dates(europe_calendar(world, season_id).competitions[comp.key]
                      .qualifying[node.round], today)
        moved = insert_ties(conn, world, season_id, comp_id, comp.key, round_number(node.round),
                            pairs, days, neutral=False, today=today, path=node.path,
                            prefix=letter)
        messages += _draw_news(conn, world, meta, node, pairs, byes, days)
        messages += moved_ties_news(conn, world, meta, moved)
        now = state(conn, world, season_id)
    return messages


def _dates(days: list[list[date]], today: date) -> list[list[date]]:
    """A round's legs' days, all moved on together if the first leg would come before tomorrow
    (a draw later than the calendar planned)."""
    first = min(days[0])
    late = (today + timedelta(days=1) - first).days
    if late <= 0:
        return days
    return [[day + timedelta(days=late) for day in leg] for leg in days]


# --- results --------------------------------------------------------------------------------------

def settle(conn: Connection, world: World, meta: CareerMeta, today: date) -> list[str]:
    """Settle the qualifying ties played so far (winners up a round, losers down or out), then
    draw whatever rounds that makes ready."""
    season_id = meta.season_id
    comp_ids = {key: competition_id(conn, comp) for key, comp in world.defs.continental.items()}
    by_id = {v: k for k, v in comp_ids.items()}
    open_ties = conn.execute(select(cup_tie).where(
        cup_tie.c.season_id == season_id, cup_tie.c.round <= round_number("PO"),
        cup_tie.c.winner_club_id.is_(None), cup_tie.c.club_b_id.is_not(None),
        cup_tie.c.competition_id.in_(list(comp_ids.values()))).order_by(cup_tie.c.id)).all()
    messages: list[str] = []
    decided_any = False
    for tie in open_ties:
        key = by_id[tie.competition_id]
        winner = tie_winner(conn, season_id, key, tie)
        if winner is None:
            continue
        node = Node(key, round_key(tie.round), tie.path)
        loser = tie.club_b_id if winner == tie.club_a_id else tie.club_a_id
        conn.execute(update(cup_tie).where(cup_tie.c.id == tie.id).values(winner_club_id=winner))
        _pay(conn, world, today, season_id, node, [winner, loser])
        _advance(conn, world, today, season_id, node, winner)
        _drop(conn, world, today, season_id, node, loser)
        messages += _result_news(conn, world, meta, node, winner, loser)
        decided_any = True
    if decided_any:
        messages += draw_ready(conn, world, meta, today)
    return messages


def _move(conn: Connection, world: World, season_id: int, club_id: int, target: Node,
          **extra: Any) -> None:
    comp_id = competition_id(conn, world.defs.continental[target.competition])
    conn.execute(update(continental_entry).where(
        continental_entry.c.season_id == season_id, continental_entry.c.club_id == club_id)
        .values(competition_id=comp_id, entry_round=round_number(target.round),
                path=target.path,
                stage="league_phase" if target.round == LEAGUE_PHASE else "qualifying", **extra))


def _advance(conn: Connection, world: World, today: date, season_id: int, node: Node,
             club_id: int) -> None:
    _move(conn, world, season_id, club_id, winners_to(world, node))


def _drop(conn: Connection, world: World, today: date, season_id: int, node: Node,
          club_id: int) -> None:
    target = losers_to(world, node)
    if target is None:
        conn.execute(update(continental_entry).where(
            continental_entry.c.season_id == season_id, continental_entry.c.club_id == club_id)
            .values(stage="out"))
        return
    _move(conn, world, season_id, club_id, target, came_from=_node_text(node))


def _pay(conn: Connection, world: World, today: date, season_id: int, node: Node,
         club_ids: list[int]) -> None:
    """The money for playing in a qualifying round (europe_prizes `qualifying`), paid to both
    clubs once their tie is decided (a bye earns none). A league phase's is paid when it's
    drawn."""
    if node.round == LEAGUE_PHASE:
        return
    amount = world.defs.finance.europe_prizes[node.competition].qualifying[
        QUALIFYING_ROUNDS.index(node.round)]
    if amount <= 0:
        return
    comp_id = competition_id(conn, world.defs.continental[node.competition])
    post(conn, today, season_id, [LedgerEntry(c, "prize", round(amount * 100), comp_id)
                                  for c in club_ids])


def _node_text(node: Node) -> str:
    """A round as stored: UCL:Q2:champions, UEL:LP."""
    return ":".join(p for p in (node.competition, node.round, node.path) if p)


def node_of(text: str) -> Node:
    competition, round_key, *path = text.split(":")
    return Node(competition, round_key, path[0] if path else None)


# --- news -----------------------------------------------------------------------------------------

def _entry_news(conn: Connection, world: World, meta: CareerMeta, plan: Plan) -> list[str]:
    user = meta.user_club_id
    if user is None:
        return []
    for node, entrants in plan.direct.items():
        if any(e.club_id == user for e in entrants):
            comp = world.defs.continental[node.competition]
            where = ("the league phase" if node.round == LEAGUE_PHASE
                     else f"the {round_name(world, node).lower()}")
            return [f"{club_name(conn, user)} are in the {comp.name}: {where}."]
    return []


def _draw_news(conn: Connection, world: World, meta: CareerMeta, node: Node,
               pairs: list[tuple[int, int]], byes: list[int], days: list[list[date]]
               ) -> list[str]:
    user = meta.user_club_id
    comp = world.defs.continental[node.competition]
    if user in byes:
        return [f"{club_name(conn, user)} have a bye in the {comp.name} "
                f"{round_name(world, node).lower()}."]
    for n, (a, b) in enumerate(pairs, start=1):
        if user in (a, b):
            when = " and ".join(f"{d:%a} {d.day} {d:%b}"
                                for d in (leg[(n - 1) % len(leg)] for leg in days))
            return [f"{comp.name} {round_name(world, node).lower()} draw: "
                    f"{club_name(conn, a)} v {club_name(conn, b)} ({when})."]
    return []


def _result_news(conn: Connection, world: World, meta: CareerMeta, node: Node, winner: int,
                 loser: int) -> list[str]:
    user = meta.user_club_id
    comp = world.defs.continental[node.competition]
    if user == winner:
        nxt = winners_to(world, node)
        where = ("league phase" if nxt.round == LEAGUE_PHASE
                 else round_name(world, nxt).lower())
        return [f"{club_name(conn, user)} are through to the {comp.name} {where}."]
    if user == loser:
        drop = losers_to(world, node)
        then = ""
        if drop is not None:
            other = world.defs.continental[drop.competition]
            where = ("league phase" if drop.round == LEAGUE_PHASE
                     else round_name(world, drop).lower())
            then = f" They go into the {other.name} {where}."
        return [f"{club_name(conn, user)} are out of the {comp.name}, beaten by "
                f"{club_name(conn, winner)}.{then}"]
    return []

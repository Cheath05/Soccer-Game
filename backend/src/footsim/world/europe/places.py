"""Who gets which European place each season (W7 A3, docs/plans/w7-all-of-uefa.md): UEFA's
2024-27 access list (europe/access_list.yaml) read against the ranking that applies to the season
(the one from two seasons back) and its two European Performance Spots.

A country's clubs are in the order its places go (``nation_order``: last season's table, or its
clubs by reputation before there is one). Places are handed out from the top competition down,
each competition's from the league phase down: a club takes the first place it earns, and a place
whose club is already in passes to the next club of the country not yet in (a cup's place to the
best-placed such club of its league).

The holders come first. A holder already in the Champions League's league phase through its league
(for the Conference League holders, anywhere in the Champions League or in the Europa League's
league phase) leaves its holder's place empty, for the best club by coefficient in the path the
access list names (UEFA's rule since 2024); otherwise it takes the holder's place, and the place
its league would have given it passes down. Places nobody can take are returned as vacancies for
qualifying.py to fill."""

from dataclasses import dataclass

from sqlalchemy import Connection, select

from footsim.defs.europe import AccessPlaceDef
from footsim.persistence.schema import club_league_membership, competition, nation
from footsim.world.context import World
from footsim.world.europe.access import cup_winner, holder, nation_order
from footsim.world.europe.common import LEAGUE_PHASE, competitions_by_rank
from footsim.world.europe.ranking import access_ranking, performance_spots, season_coefficients
from footsim.world.meta import CareerMeta

ROUND_ORDER = {"LP": 0, "PO": 1, "Q3": 2, "Q2": 3, "Q1": 4}


@dataclass(frozen=True)
class Entry:
    competition: str
    club_id: int
    round: str  # LP, PO, Q3, Q2 or Q1
    path: str | None  # champions, league or main (None in the league phase)
    route: str  # league:ENG:4, cup:FA_CUP, holder:UCL, eps:ENG:5
    association: str | None  # the country whose place it is (None for a holder)


@dataclass(frozen=True)
class Vacancy:
    competition: str
    round: str
    path: str | None
    fill_from: str | None  # for a league-phase place, the path its club is to come from


def country_cup(world: World, code: str) -> str | None:
    """The cup whose winners take a country's cup place."""
    chosen = world.defs.europe_access.cups.get(code)
    if chosen is not None:
        return chosen
    cups = [key for key, cup in world.defs.cups.items() if cup.nation == code]
    return cups[0] if len(cups) == 1 else None


def ordered_places(world: World, competition_key: str) -> list[AccessPlaceDef]:
    """A competition's places in the order they're handed out: the holders first, then the
    league phase's (the Performance Spots last), then each round's from the play-off down."""
    places = world.defs.europe_access.competitions[competition_key].places
    return sorted(places, key=lambda p: (ROUND_ORDER[p.round], p.holder is None,
                                         p.performance_spot))


def lp_fill_path(competition_key: str, place: AccessPlaceDef, position: int | None) -> str:
    """The path whose best club fills an empty league-phase place: as the place says (the
    holders'); in the Champions League the Champions Path for a champion's place and the League
    Path for the rest; the main path in the others."""
    if place.fill_from is not None:
        return place.fill_from
    if competition_key == "UCL":
        return "champions" if position == 1 else "league"
    return "main"


def places_for(world: World, rank: int) -> list[tuple[str, AccessPlaceDef]]:
    """The places a country in ``rank`` gets, by competition, in the order they're handed out
    (not the holders' or the Performance Spots')."""
    return [(comp.key, place) for comp in competitions_by_rank(world)
            for place in ordered_places(world, comp.key)
            if place.ranks is not None and place.ranks[0] <= rank <= place.ranks[1]]


def _league_nation(conn: Connection, club_id: int, season_id: int) -> str | None:
    """The country of the league a club played in in season ``season_id``."""
    row = conn.execute(select(nation.c.code).select_from(club_league_membership).join(
        competition, competition.c.id == club_league_membership.c.competition_id).join(
        nation, nation.c.id == competition.c.nation_id).where(
        club_league_membership.c.club_id == club_id,
        club_league_membership.c.season_id == season_id)).first()
    return str(row.code) if row is not None else None


def qualify(conn: Connection, world: World, meta: CareerMeta, season_id: int
            ) -> tuple[list[Entry], list[Vacancy]]:
    """Every European place for season ``season_id``: the clubs in, with their competition,
    round and path, and the places nobody could take."""
    access = world.defs.europe_access
    rank_of = {r.nation: r.rank for r in access_ranking(conn, world, season_id)}
    code_at = {rank: code for code, rank in rank_of.items()}
    spots = performance_spots(conn, world, season_id)
    overrides = {(o.nation, o.competition, o.position): o.cup for o in access.overrides}
    orders: dict[str, list[int]] = {}
    placed: dict[int, Entry] = {}
    vacancies: list[Vacancy] = []

    def order(code: str) -> list[int]:
        if code not in orders:
            orders[code] = nation_order(conn, world, meta, season_id, code)
        return orders[code]

    def free(code: str, position: int) -> tuple[int, int] | None:
        """The first club of the country not yet in, from ``position`` down, and its place."""
        clubs = order(code)
        for index in range(position - 1, len(clubs)):
            if clubs[index] not in placed:
                return clubs[index], index + 1
        return None

    def league_place(comp_key: str, place: AccessPlaceDef, code: str, position: int) -> None:
        path = None if place.round == LEAGUE_PHASE else place.path
        found = free(code, position)
        if found is None:
            vacancies.append(Vacancy(comp_key, place.round, path,
                                     lp_fill_path(comp_key, place, position)))
        else:
            placed[found[0]] = Entry(comp_key, found[0], place.round, path,
                                     f"league:{code}:{found[1]}", code)

    def cup_place(comp_key: str, place: AccessPlaceDef, code: str, cup: str | None,
                  position: int | None) -> None:
        """A cup's place: last season's winners if they aren't in already, else the best-placed
        club of the country not yet in."""
        path = None if place.round == LEAGUE_PHASE else place.path
        winner = cup_winner(conn, world, season_id - 1, cup) if cup is not None else None
        if winner is not None and winner not in placed:
            placed[winner] = Entry(comp_key, winner, place.round, path, f"cup:{cup}", code)
        else:
            league_place(comp_key, place, code, 1)

    def in_through_league(holder_of: str, club_id: int) -> bool:
        """Whether a holder has a place through its own country that keeps it from the holder's
        place: the Champions League's league phase (a Performance Spot included), or for the
        Conference League holders any Champions League place or the Europa League's league
        phase."""
        code = (_league_nation(conn, club_id, season_id - 1)
                or _league_nation(conn, club_id, season_id))  # a first season: no last one
        if code is None or code not in rank_of or club_id not in order(code):
            return False
        position = order(code).index(club_id) + 1
        cup = country_cup(world, code)
        won = cup is not None and cup_winner(conn, world, season_id - 1, cup) == club_id
        earned: set[tuple[str, str]] = set()
        for comp_key, place in places_for(world, rank_of[code]):
            if (place.cup and won) or (place.positions is not None
                                       and place.positions[0] <= position
                                       <= place.positions[1]):
                earned.add((comp_key, place.round))
        lp_positions = max((p.positions[1] for c, p in places_for(world, rank_of[code])
                            if c == "UCL" and p.round == LEAGUE_PHASE and p.positions), default=0)
        if code in spots and position == lp_positions + 1:
            earned.add(("UCL", LEAGUE_PHASE))
        if holder_of == "UECL":
            return any(c == "UCL" for c, _ in earned) or ("UEL", LEAGUE_PHASE) in earned
        return ("UCL", LEAGUE_PHASE) in earned

    for comp in competitions_by_rank(world):
        for place in ordered_places(world, comp.key):
            path = None if place.round == LEAGUE_PHASE else place.path
            if place.holder is not None:
                won: int | None = holder(conn, world, season_id - 1, place.holder)
                if won is None or won in placed or in_through_league(place.holder, won):
                    vacancies.append(Vacancy(comp.key, place.round, path,
                                             lp_fill_path(comp.key, place, None)))
                else:
                    placed[won] = Entry(comp.key, won, place.round, path,
                                        f"holder:{place.holder}", None)
                continue
            if place.performance_spot:
                for code in spots:
                    found = free(code, 1)
                    if found is None:
                        vacancies.append(Vacancy(comp.key, place.round, path, "league"))
                    else:
                        placed[found[0]] = Entry(comp.key, found[0], place.round, path,
                                                 f"eps:{code}:{found[1]}", code)
                continue
            assert place.ranks is not None
            for rank in range(place.ranks[0], place.ranks[1] + 1):
                country = code_at.get(rank)
                if country is None:
                    continue  # a position beyond the countries ranked
                if place.cup:
                    cup_place(comp.key, place, country, country_cup(world, country), None)
                    continue
                assert place.positions is not None
                for position in range(place.positions[0], place.positions[1] + 1):
                    override = overrides.get((country, comp.key, position))
                    if override is not None:
                        cup_place(comp.key, place, country, override, position)
                    else:
                        league_place(comp.key, place, country, position)
    return list(placed.values()), vacancies


@dataclass(frozen=True)
class CountryPlace:
    """A place a country's clubs can earn: league finishes or a cup's winners, entering a
    competition at a round (and path)."""

    competition: str
    round: str  # LP, PO, Q3, Q2 or Q1
    path: str | None
    positions: tuple[int, int] | None  # league finishes; None for a cup's winners
    cup: str | None  # the cup, for a cup's place
    performance_spot: bool = False


def country_places(conn: Connection | None, world: World, code: str, season_id: int
                   ) -> list[CountryPlace]:
    """The places a country's clubs can earn for season ``season_id`` by its position in that
    season's ranking (and its Performance Spot, once the season before it is over), in the order
    they're handed out, as written: before anything passes down the table."""
    rank = {r.nation: r.rank for r in access_ranking(conn, world, season_id)}.get(code)
    if rank is None:
        return []
    overrides = {(o.nation, o.competition, o.position): o.cup
                 for o in world.defs.europe_access.overrides}
    out: list[CountryPlace] = []
    for comp_key, place in places_for(world, rank):
        path = None if place.round == LEAGUE_PHASE else place.path
        if place.cup:
            out.append(CountryPlace(comp_key, place.round, path, None, country_cup(world, code)))
            continue
        assert place.positions is not None
        run: list[int] = []
        for position in range(place.positions[0], place.positions[1] + 1):
            cup = overrides.get((code, comp_key, position))
            if cup is None:
                run.append(position)
                continue
            if run:
                out.append(CountryPlace(comp_key, place.round, path, (run[0], run[-1]), None))
                run = []
            out.append(CountryPlace(comp_key, place.round, path, None, cup))
        if run:
            out.append(CountryPlace(comp_key, place.round, path, (run[0], run[-1]), None))
    if _season_known(conn, world, season_id - 1) and code in performance_spots(conn, world,
                                                                              season_id):
        last = max((p.positions[1] for p in out if p.competition == "UCL"
                    and p.round == LEAGUE_PHASE and p.positions), default=0)
        spot = CountryPlace("UCL", LEAGUE_PHASE, None, (last + 1, last + 1), None, True)
        at = next((k for k, p in enumerate(out) if not (p.competition == "UCL"
                                                       and p.round == LEAGUE_PHASE)), len(out))
        out.insert(at, spot)
    return out


def _season_known(conn: Connection | None, world: World, season_id: int) -> bool:
    """Whether a season's country coefficients are in: a real one, or one played and over."""
    return bool(season_coefficients(conn, world).get(season_id))

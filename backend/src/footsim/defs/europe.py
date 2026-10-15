"""The European club competitions (data/config/europe/, docs/plans/w6-european-competitions.md
and w7-all-of-uefa.md): each competition's format, who qualifies (UEFA's access list by ranking
position), the season's dates, prize money (finance.yaml), coefficients, and the countries' real
coefficients before the career."""

from datetime import date
from typing import Literal, Self

from pydantic import Field, model_validator

from footsim.defs.common import DefModel

QUALIFYING_KEYS = ("Q1", "Q2", "Q3", "PO")
PATHS = ("champions", "league", "main")


class KnockoutRoundDef(DefModel):
    name: str
    legs: Literal[1, 2] = 2
    neutral: bool = False  # a final at a ground chosen beforehand


class LeaguePhaseDef(DefModel):
    """One table of every club, each playing ``matches`` others: as many from each pot (half
    of them at home when that's two)."""

    clubs: int = Field(gt=0)
    matches: int = Field(gt=0)
    pots: int = Field(gt=0)
    to_round_of_16: int = Field(ge=0)  # the top clubs skip the knockout play-off
    to_playoff: tuple[int, int]  # the places that go into it, first and last

    @property
    def per_pot(self) -> int:
        return self.matches // self.pots

    @property
    def pot_size(self) -> int:
        return self.clubs // self.pots

    @model_validator(mode="after")
    def _shape(self) -> Self:
        if self.clubs % self.pots or self.matches % self.pots:
            raise ValueError("league_phase: clubs and matches must divide into the pots")
        if self.per_pot not in (1, 2):
            raise ValueError("league_phase: one or two opponents from each pot")
        if self.per_pot == 1 and self.pots % 2:
            raise ValueError("league_phase: one opponent from each pot needs an even number of "
                             "pots, for as many home matches as away")
        first, last = self.to_playoff
        if not self.to_round_of_16 < first <= last <= self.clubs or (last - first + 1) % 2:
            raise ValueError("league_phase: to_playoff must be an even run of places after "
                             "those going straight to the round of 16")
        if self.to_round_of_16 != (last - first + 1) // 2:
            raise ValueError("league_phase: the play-off's winners must make up the round of 16 "
                             "with the clubs who skip it")
        return self


class QualifyingRoundDef(DefModel):
    """One of the qualifying rounds before the league phase: Q1, Q2, Q3 or PO (the play-off)."""

    key: Literal["Q1", "Q2", "Q3", "PO"]
    name: str
    legs: Literal[1, 2] = 2


class ContinentalDef(DefModel):
    key: str
    name: str
    short_name: str
    rank: int = Field(ge=1)  # 1: the top competition; a club plays in the highest it earns
    league_phase: LeaguePhaseDef
    knockout: list[KnockoutRoundDef]  # the play-off first, the final last
    qualifying: list[QualifyingRoundDef]  # Q1, Q2, Q3, PO, in order

    @model_validator(mode="after")
    def _rounds(self) -> Self:
        if len(self.knockout) < 2 or self.knockout[-1].legs != 1:
            raise ValueError(f"{self.key}: the knockout ends in a one-match final")
        if [r.key for r in self.qualifying] != list(QUALIFYING_KEYS):
            raise ValueError(f"{self.key}: the qualifying rounds are Q1, Q2, Q3 and PO, in order")
        return self


# --- the access list (europe/access_list.yaml) ---------------------------------------------------

class NodeTargetDef(DefModel):
    """Where a round's winners or losers go: a round (Q1..PO, or LP for the league phase) of a
    competition (this one when left out) and its path."""

    competition: str | None = None
    round: Literal["Q1", "Q2", "Q3", "PO", "LP"]
    path: Literal["champions", "league", "main"] | None = None


class NodeDef(DefModel):
    """One path of one qualifying round of a competition."""

    round: Literal["Q1", "Q2", "Q3", "PO"]
    path: Literal["champions", "league", "main"]
    winners: NodeTargetDef | None = None  # default: the path's next round (PO: the league phase)
    losers: NodeTargetDef | None = None  # default: out


class AccessPlaceDef(DefModel):
    """A run of places: for ranking positions ``ranks``, league finishes ``positions`` or the cup
    winners (``cup``), entering ``round`` (and ``path`` before the league phase); or the holders
    of a competition (``holder``, an empty place filled from ``fill_from``), or the two European
    Performance Spots."""

    round: Literal["Q1", "Q2", "Q3", "PO", "LP"]
    path: Literal["champions", "league", "main"] | None = None
    ranks: tuple[int, int] | None = None
    positions: tuple[int, int] | None = None
    cup: bool = False
    holder: str | None = None
    fill_from: Literal["champions", "league", "main"] | None = None
    performance_spot: bool = False

    @model_validator(mode="after")
    def _one_kind(self) -> Self:
        kinds = [self.holder is not None, self.performance_spot,
                 self.ranks is not None]
        if sum(kinds) != 1:
            raise ValueError(f"a place is a holder's, a Performance Spot or a run of ranks: {self}")
        if self.ranks is not None:
            if not 1 <= self.ranks[0] <= self.ranks[1]:
                raise ValueError(f"ranks first <= last: {self}")
            if self.cup == (self.positions is not None):
                raise ValueError(f"a run of ranks gives league positions or the cup: {self}")
            if self.positions is not None and not 1 <= self.positions[0] <= self.positions[1]:
                raise ValueError(f"positions first <= last: {self}")
        if (self.round == "LP") != (self.path is None):
            raise ValueError(f"a qualifying place has a path, a league-phase place none: {self}")
        return self

    @property
    def count(self) -> int:
        """Places per country in ``ranks`` (a holder's or Performance Spot: 1 and 2)."""
        if self.holder is not None:
            return 1
        if self.performance_spot:
            return 2
        if self.cup or self.positions is None:
            return 1
        return self.positions[1] - self.positions[0] + 1


class CompetitionAccessListDef(DefModel):
    nodes: list[NodeDef]
    places: list[AccessPlaceDef]


class OverrideDef(DefModel):
    """A league place given to a cup's winners instead (England's sixth: the EFL Cup's)."""

    nation: str
    competition: str
    position: int = Field(ge=1)
    cup: str


class AccessListFile(DefModel):
    cups: dict[str, str] = {}  # a country's cup for its cup place, where it has several
    overrides: list[OverrideDef] = []
    competitions: dict[str, CompetitionAccessListDef]


# --- coefficients -------------------------------------------------------------------------------

class RankingBonusDef(DefModel):
    """A league-phase place bonus: ``step`` for each place climbed from 24th (24th earns one
    step, 9th sixteen), and ``top8_step`` for each place above 9th (1st earns eight more)."""

    step: float = Field(ge=0)
    top8_step: float = Field(ge=0)

    def points(self, position: int) -> float:
        if position > 24:
            return 0.0
        if position >= 9:
            return (25 - position) * self.step
        return 16 * self.step + (9 - position) * self.top8_step


class CoefficientDef(DefModel):
    """UEFA's coefficient points (2024-27): per match (halved in qualifying and play-off
    rounds), a league-phase bonus, a league-phase place bonus, and a bonus for each knockout
    round reached from the round of 16. A club's season points are these; a country's season
    coefficient is its clubs' points divided by how many it entered. Rankings sum ``seasons``."""

    win: float = Field(ge=0)
    draw: float = Field(ge=0)
    qualifying_factor: float = Field(gt=0, le=1)  # qualifying and play-off rounds
    league_phase_bonus: dict[str, float]  # for taking part, by competition (UCL only, in fact)
    ranking_bonus: dict[str, RankingBonusDef]
    knockout_bonus: dict[str, float]  # each round reached from the round of 16 on
    seasons: int = Field(ge=1)
    # A club's coefficient is at least this share of its country's (UEFA's floor: 20%).
    association_share: float = Field(ge=0, le=1)
    # Before a club has European results: a coefficient from its reputation,
    # ``(reputation - floor) * per_point``, never below 0.
    reputation_floor: float
    reputation_per_point: float = Field(ge=0)


class AssociationCoefficientsFile(DefModel):
    """Countries' real season coefficients before the career (europe/association_coefficients.yaml):
    by season label ("2024-25"), each country's coefficient by nation code."""

    seasons: dict[str, dict[str, float]]

    @model_validator(mode="after")
    def _labels(self) -> Self:
        for label, values in self.seasons.items():
            start, _, end = label.partition("-")
            if not (start.isdigit() and end.isdigit() and len(start) == 4 and len(end) == 2
                    and int(end) == (int(start) + 1) % 100):
                raise ValueError(f"association coefficients: bad season label {label!r}")
            if any(v < 0 for v in values.values()):
                raise ValueError(f"association coefficients {label}: a negative coefficient")
        return self


class HolderBeforeDef(DefModel):
    nation: str
    club: str  # the game's name for it


class CountryBeforeDef(DefModel):
    table: list[str] = []  # its top league's final table, best first (the game's club names)
    cups: dict[str, str] = {}  # each cup's winners, by cup key


class SeasonBeforeFile(DefModel):
    """The season before the career, as it really finished (europe/season_before.yaml): a
    first season's European places come from it."""

    season: str
    holders: dict[str, HolderBeforeDef] = {}
    countries: dict[str, CountryBeforeDef] = {}


class EuropeSettingsDef(DefModel):
    enabled: bool = True  # whether new seasons have European competitions
    calendar: str  # the key of the calendar in data/config/europe/calendars
    # A country without a league in the game: its clubs' order each season is a lottery,
    # each club's chance weighted by reputation ** lottery_power.
    lottery_power: float = Field(ge=0)
    coefficient: CoefficientDef
    # Pairs of countries whose clubs aren't drawn together (UEFA's prohibited clashes).
    prohibited: list[tuple[str, str]] = []


class ContinentalDatesDef(DefModel):
    """One competition's dates in a season: each leg or matchday is a list of days its matches
    are spread over (Tuesday and Wednesday, say)."""

    qualifying: dict[str, list[list[date]]]  # each round's (Q1..PO), one per leg
    league_phase: list[list[date]]  # one per matchday
    knockout: list[list[list[date]]]  # one per round, one per leg

    @model_validator(mode="after")
    def _days(self) -> Self:
        stages = [*(leg for key in QUALIFYING_KEYS for leg in self.qualifying.get(key, [])),
                  *self.league_phase, *(leg for rnd in self.knockout for leg in rnd)]
        if any(not days for days in stages):
            raise ValueError("every leg and matchday needs at least one day")
        firsts = [min(days) for days in stages]
        if firsts != sorted(firsts):
            raise ValueError("the stages' dates must run in order")
        return self


class EuropeCalendarDef(DefModel):
    key: str
    season: str
    season_start: date
    competitions: dict[str, ContinentalDatesDef]


class EuropePrizeDef(DefModel):
    """Prize money (EUR) for one competition: for playing in each qualifying round (Q1..PO), on
    entering the league phase, per league-phase win and draw, for reaching each knockout round
    (as in its knockout list), and on top for winning the final."""

    qualifying: list[float] = Field(min_length=4, max_length=4)
    participation: float = Field(ge=0)
    win: float = Field(ge=0)
    draw: float = Field(ge=0)
    rounds: list[float]
    winner: float = Field(ge=0)

    @model_validator(mode="after")
    def _rising(self) -> Self:
        for amounts in (self.qualifying, self.rounds):
            if min(amounts, default=0) < 0 or any(
                    later < earlier for earlier, later in zip(amounts, amounts[1:],
                                                              strict=False)):
                raise ValueError("europe_prizes: a later round never pays less than an earlier "
                                 "one")
        return self


def check_europe(continental: dict[str, ContinentalDef], access: AccessListFile,
                 calendars: dict[str, EuropeCalendarDef], settings: EuropeSettingsDef,
                 prizes: dict[str, EuropePrizeDef], nations: set[str],
                 cups: dict[str, str]) -> list[str]:
    """Errors in the European definitions, taken together: every competition has its access
    list, dates and prizes; each round its rules; where winners and losers go exists; every
    country and cup named exists. ``cups``: each domestic cup's nation, by key."""
    errors: list[str] = []
    calendar = calendars.get(settings.calendar)
    if calendar is None:
        errors.append(f"europe settings: unknown calendar {settings.calendar}")
    for code, cup in access.cups.items():
        if code not in nations or cups.get(cup) != code:
            errors.append(f"access list cups: {cup} isn't a cup of {code}")
    for o in access.overrides:
        if o.nation not in nations or cups.get(o.cup) != o.nation:
            errors.append(f"access list override: {o.cup} isn't a cup of {o.nation}")
        if o.competition not in continental:
            errors.append(f"access list override: unknown competition {o.competition}")
    for a, b in settings.prohibited:
        if a not in nations or b not in nations:
            errors.append(f"europe settings: prohibited pair {a}-{b} names an unknown country")
    for key, comp in continental.items():
        rules = access.competitions.get(key)
        if rules is None:
            errors.append(f"{key}: no access list in europe/access_list.yaml")
            continue
        own = {(n.round, n.path) for n in rules.nodes}
        for node in rules.nodes:
            for target in (node.winners, node.losers):
                if target is None:
                    continue
                other = target.competition or key
                if other not in continental:
                    errors.append(f"{key} {node.round}: unknown competition {other}")
                    continue
                if target.round != "LP" and (target.round, target.path) not in {
                        (n.round, n.path) for n in access.competitions[other].nodes}:
                    errors.append(f"{key} {node.round} {node.path}: no round {target.round} "
                                  f"{target.path} in {other}")
        for place in rules.places:
            if place.round != "LP" and (place.round, place.path) not in own:
                errors.append(f"{key}: a place in {place.round} {place.path}, which it hasn't")
            if place.holder is not None and place.holder not in continental:
                errors.append(f"{key}: holder of unknown competition {place.holder}")
        if calendar is not None:
            dates = calendar.competitions.get(key)
            if dates is None:
                errors.append(f"{key}: no dates in the {calendar.key} calendar")
            else:
                for r in comp.qualifying:
                    if len(dates.qualifying.get(r.key, [])) != r.legs:
                        errors.append(f"{key}: {r.key} has {r.legs} legs but "
                                      f"{len(dates.qualifying.get(r.key, []))} dates")
                if len(dates.league_phase) != comp.league_phase.matches:
                    errors.append(f"{key}: {comp.league_phase.matches} matchdays but "
                                  f"{len(dates.league_phase)} dates")
                if [len(r) for r in dates.knockout] != [r.legs for r in comp.knockout]:
                    errors.append(f"{key}: the knockout dates don't match its rounds' legs")
        prize = prizes.get(key)
        if prize is None:
            errors.append(f"{key}: no europe_prizes in finance.yaml")
        elif len(prize.rounds) != len(comp.knockout):
            errors.append(f"{key}: europe_prizes needs one amount per knockout round")
        points = settings.coefficient
        if key not in points.ranking_bonus or key not in points.knockout_bonus:
            errors.append(f"{key}: coefficient needs a ranking_bonus and a knockout_bonus")
    for key in set(access.competitions) - set(continental):
        errors.append(f"europe/access_list.yaml: unknown competition {key}")
    return errors

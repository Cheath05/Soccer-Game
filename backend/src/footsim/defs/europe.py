"""The European club competitions (data/config/europe/, docs/plans/w6-european-competitions.md):
each competition's format, who qualifies (the access list), the season's dates, prize money
(finance.yaml) and the settings for coefficients and for countries without a league."""

from datetime import date
from typing import Literal, Self

from pydantic import Field, model_validator

from footsim.defs.common import DefModel


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


class QualifyingDef(DefModel):
    """The summer play-off round before the league phase."""

    name: str
    legs: Literal[1, 2] = 2
    losers_to: str | None = None  # the competition whose league phase takes the losers


class ContinentalDef(DefModel):
    key: str
    name: str
    short_name: str
    rank: int = Field(ge=1)  # 1: the top competition; a club plays in the highest it earns
    league_phase: LeaguePhaseDef
    knockout: list[KnockoutRoundDef]  # the play-off first, the final last
    qualifying: QualifyingDef
    winner_to: str | None = None  # next season's competition its winner enters directly

    @model_validator(mode="after")
    def _final(self) -> Self:
        if len(self.knockout) < 2 or self.knockout[-1].legs != 1:
            raise ValueError(f"{self.key}: the knockout ends in a one-match final")
        return self


class PlaceDef(DefModel):
    """One place, or a run of them: a league finish (``nation`` and ``ranks``: the nation's top
    league, or for a country without a league in the game its clubs in a lottery order), a
    domestic cup's winner (``cup``), or a competition's last winner (``holder``)."""

    nation: str | None = None
    ranks: tuple[int, int] | None = None
    cup: str | None = None
    holder: str | None = None

    @model_validator(mode="after")
    def _one_kind(self) -> Self:
        kinds = [self.ranks is not None, self.cup is not None, self.holder is not None]
        if sum(kinds) != 1:
            raise ValueError("a place is a league finish (nation, ranks), a cup or a holder")
        if self.ranks is not None and (self.nation is None
                                       or not 1 <= self.ranks[0] <= self.ranks[1]):
            raise ValueError(f"a league place needs a nation and ranks first <= last: {self}")
        return self

    @property
    def count(self) -> int:
        return self.ranks[1] - self.ranks[0] + 1 if self.ranks is not None else 1


class CompetitionAccessDef(DefModel):
    league_phase: list[PlaceDef]  # straight into the league phase
    qualifying: list[PlaceDef]  # into the summer play-off round
    # Countries whose next club takes a place nobody else can (no holder yet, a league not in
    # the career): the first of them with a club left, in this order.
    fill: list[str]

    def direct(self) -> int:
        return sum(p.count for p in self.league_phase)

    def qualifiers(self) -> int:
        return sum(p.count for p in self.qualifying)


class AccessFile(DefModel):
    competitions: dict[str, CompetitionAccessDef]


class CoefficientDef(DefModel):
    """Club coefficients (simplified UEFA): points for each European match and for reaching
    each knockout round, summed over the last ``seasons`` seasons."""

    win: float = Field(ge=0)
    draw: float = Field(ge=0)
    # Bonus points for reaching each knockout round (the play-off, the round of 16, ...), by
    # competition, one per round as in its knockout list (the last for winning the final).
    round_bonus: dict[str, list[float]]
    seasons: int = Field(ge=1)
    # Before a club has European results: a coefficient from its reputation,
    # ``(reputation - floor) * per_point``, never below 0.
    reputation_floor: float
    reputation_per_point: float = Field(ge=0)


class EuropeSettingsDef(DefModel):
    calendar: str  # the key of the calendar in data/config/europe/calendars
    # A country without a league in the game: its clubs' order each season is a lottery,
    # each club's chance weighted by reputation ** lottery_power.
    lottery_power: float = Field(ge=0)
    coefficient: CoefficientDef


class ContinentalDatesDef(DefModel):
    """One competition's dates in a season: each leg or matchday is a list of days its matches
    are spread over (Tuesday and Wednesday, say)."""

    qualifying: list[list[date]]  # one per leg
    league_phase: list[list[date]]  # one per matchday
    knockout: list[list[list[date]]]  # one per round, one per leg

    @model_validator(mode="after")
    def _days(self) -> Self:
        for days in [*self.qualifying, *self.league_phase,
                     *(leg for rnd in self.knockout for leg in rnd)]:
            if not days:
                raise ValueError("every leg and matchday needs at least one day")
        stages = [*self.qualifying, *self.league_phase,
                  *(leg for rnd in self.knockout for leg in rnd)]
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
    """Prize money (EUR) for one competition: on entering the league phase, per league-phase
    win and draw, for reaching each knockout round (as in its knockout list), and on top for
    winning the final."""

    participation: float = Field(ge=0)
    win: float = Field(ge=0)
    draw: float = Field(ge=0)
    rounds: list[float]
    winner: float = Field(ge=0)

    @model_validator(mode="after")
    def _rising(self) -> Self:
        if min(self.rounds, default=0) < 0 or any(
                later < earlier for earlier, later in zip(self.rounds, self.rounds[1:],
                                                          strict=False)):
            raise ValueError("europe_prizes: a later round never pays less than an earlier one")
        return self


def check_europe(continental: dict[str, ContinentalDef], access: AccessFile,
                 calendars: dict[str, EuropeCalendarDef], settings: EuropeSettingsDef,
                 prizes: dict[str, EuropePrizeDef], nations: set[str],
                 top_league_nations: set[str], cups: dict[str, str]) -> list[str]:
    """Errors in the European definitions, taken together: every competition has its access,
    dates and prizes, the places come to exactly the league phase's size, and every country,
    cup and competition named exists. ``cups``: each domestic cup's nation, by key."""
    errors: list[str] = []
    calendar = calendars.get(settings.calendar)
    if calendar is None:
        errors.append(f"europe settings: unknown calendar {settings.calendar}")
    for key, comp in continental.items():
        rules = access.competitions.get(key)
        if rules is None:
            errors.append(f"{key}: no access list in europe/access.yaml")
            continue
        if comp.qualifying.losers_to and comp.qualifying.losers_to not in continental:
            errors.append(f"{key}: qualifying losers to unknown {comp.qualifying.losers_to}")
        if comp.winner_to and comp.winner_to not in continental:
            errors.append(f"{key}: winner to unknown {comp.winner_to}")
        if rules.qualifiers() % 2:
            errors.append(f"{key}: an odd number of clubs in qualifying ({rules.qualifiers()})")
        dropping = sum(access.competitions[other].qualifiers() // 2
                       for other, c in continental.items()
                       if c.qualifying.losers_to == key and other in access.competitions)
        total = rules.direct() + rules.qualifiers() // 2 + dropping
        if total != comp.league_phase.clubs:
            errors.append(f"{key}: the access list makes {total} league-phase clubs "
                          f"({rules.direct()} direct, {rules.qualifiers() // 2} through "
                          f"qualifying, {dropping} dropping in), not {comp.league_phase.clubs}")
        for place in [*rules.league_phase, *rules.qualifying]:
            if place.nation is not None and place.nation not in nations:
                errors.append(f"{key}: unknown nation {place.nation}")
            if place.cup is not None and place.cup not in cups:
                errors.append(f"{key}: unknown cup {place.cup}")
            if place.cup is not None and place.nation not in (None, cups.get(place.cup)):
                errors.append(f"{key}: cup {place.cup} isn't {place.nation}'s")
            if place.holder is not None and place.holder not in continental:
                errors.append(f"{key}: holder of unknown competition {place.holder}")
        for nation in rules.fill:
            if nation not in top_league_nations:
                errors.append(f"{key}: fill from {nation}, which has no league in the game")
        if calendar is not None:
            dates = calendar.competitions.get(key)
            if dates is None:
                errors.append(f"{key}: no dates in the {calendar.key} calendar")
            else:
                if len(dates.qualifying) != comp.qualifying.legs:
                    errors.append(f"{key}: qualifying has {comp.qualifying.legs} legs but "
                                  f"{len(dates.qualifying)} dates")
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
        bonus = settings.coefficient.round_bonus.get(key)
        if bonus is None or len(bonus) != len(comp.knockout):
            errors.append(f"{key}: coefficient round_bonus needs one per knockout round")
    for key in set(access.competitions) - set(continental):
        errors.append(f"europe/access.yaml: unknown competition {key}")
    return errors

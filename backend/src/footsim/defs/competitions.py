"""League rules, promotion/relegation and play-off brackets (data/config/competitions/**)."""

from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from footsim.defs.common import DefModel


class SimLevel(StrEnum):
    PLAYABLE = "playable"  # fast engine for every match, full player stats
    SIMULATED = "simulated"  # results-only engine
    DORMANT = "dormant"  # no fixtures; players still exist, age and move


class Tiebreaker(StrEnum):
    POINTS = "points"
    GOAL_DIFFERENCE = "goal_difference"
    GOALS_FOR = "goals_for"
    WINS = "wins"
    AWAY_GOALS_FOR = "away_goals_for"
    H2H_POINTS = "h2h_points"
    H2H_GOAL_DIFFERENCE = "h2h_goal_difference"
    H2H_GOALS_FOR = "h2h_goals_for"
    H2H_AWAY_GOALS_FOR = "h2h_away_goals_for"
    DRAWING_OF_LOTS = "drawing_of_lots"


class MovementKind(StrEnum):
    PROMOTION = "promotion"
    RELEGATION = "relegation"


class PointsRule(DefModel):
    win: int = 3
    draw: int = 1
    loss: int = 0


class RoundRobinFormat(DefModel):
    type: Literal["round_robin"] = "round_robin"
    legs: int = Field(default=2, ge=1, le=4)


class GroupsFormat(DefModel):
    """Conferences or zones (``LeagueDef.groups``): each group a round robin of ``legs``, plus
    ``cross_rounds`` rounds in which every club meets one of the other group's (two groups of
    one size). The first cross round pairs the ``rivals`` when there are any. Rounds with an odd
    group leave a club of each group free (a bye)."""

    type: Literal["groups"] = "groups"
    legs: int = Field(default=2, ge=1, le=2)
    cross_rounds: int = Field(default=0, ge=0)
    rivals: list[tuple[str, str]] = []  # by club name, one of each group


class GroupDef(DefModel):
    """A conference or zone: its clubs, by name as the world has them."""

    key: str
    name: str
    clubs: list[str]


class PhaseDef(DefModel):
    """A tournament within the season (Apertura, Clausura): the league's format played once
    more, the venues swapped from the one before, with its own table and champion. Its dates
    are the calendar's ``<league key>:<phase key>``."""

    key: str
    name: str


class MovementDef(DefModel):
    kind: MovementKind
    ranks: tuple[int, int]
    to: str

    @model_validator(mode="after")
    def _ordered(self) -> "MovementDef":
        first, last = self.ranks
        if not 1 <= first <= last:
            raise ValueError(f"invalid rank range {self.ranks}")
        return self

    @property
    def count(self) -> int:
        return self.ranks[1] - self.ranks[0] + 1


class EntrantRef(DefModel):
    """A play-off participant: a final league rank, or the winner of earlier tie(s).

    With several ``winner_of`` ties, ``pick`` selects by original league rank, e.g. the
    Championship semi where 3rd plays the lowest-ranked eliminator winner.
    """

    rank: int | None = Field(default=None, ge=1)
    group: str | None = None  # the rank is within this conference or zone
    winner_of: list[str] = []
    # Among several ties' winners, by their seeding rank: the best, the worst, or the second
    # best or worst (a reseeded semi-final: best v worst, second best v second worst).
    pick: Literal["only", "highest_ranked", "lowest_ranked", "second_highest",
                  "second_lowest"] = "only"

    @model_validator(mode="after")
    def _one_source(self) -> "EntrantRef":
        if (self.rank is None) == (not self.winner_of):
            raise ValueError("entrant needs exactly one of 'rank' or 'winner_of'")
        if self.winner_of and self.pick == "only" and len(self.winner_of) != 1:
            raise ValueError("'pick' is required when choosing among several ties")
        if self.group is not None and self.rank is None:
            raise ValueError("'group' goes with a 'rank'")
        return self


class TieDef(DefModel):
    id: str
    a: EntrantRef
    b: EntrantRef


class PlayoffRoundDef(DefModel):
    name: str
    legs: Literal[1, 2] = 1
    # A series: best of ``games`` single matches, each decided on the day (MLS Round One). The
    # better seed hosts the odd games. Games beyond the first to win a majority aren't played.
    games: Literal[1, 3, 5] = 1
    # Single leg: who hosts. Two legs: who hosts the second leg.
    host: Literal["higher_ranked", "lower_ranked", "neutral"] = "higher_ranked"
    extra_time: bool = True
    penalties: bool = True
    # A level aggregate sends the better seed through, with no extra time or penalties
    # (Liga MX's Liguilla).
    higher_seed_on_level: bool = False
    ties: list[TieDef]

    @model_validator(mode="after")
    def _series(self) -> "PlayoffRoundDef":
        if self.games > 1 and (self.legs != 1 or self.host == "neutral"):
            raise ValueError(f"{self.name}: a series is of single matches at the clubs' grounds")
        if self.higher_seed_on_level and (self.extra_time or self.penalties):
            raise ValueError(f"{self.name}: a level tie can't go both to the better seed and to "
                             "extra time or penalties")
        return self

    @property
    def matches(self) -> int:
        """The most matches a tie can take: its legs, or a series' games."""
        return self.games if self.games > 1 else self.legs


class PlayoffDef(DefModel):
    key: str
    name: str
    winner_to: str | None = None
    # The winner is the champion (MLS Cup, the Liguilla), not the table's top club.
    title: bool = False
    # Seeded from this phase's table (Apertura, Clausura) and played straight after it; None:
    # the season's table, after the season.
    phase: str | None = None
    rounds: list[PlayoffRoundDef]

    @model_validator(mode="after")
    def _bracket(self) -> "PlayoffDef":
        seen: set[str] = set()
        for rnd in self.rounds:
            for tie in rnd.ties:
                if tie.id in seen:
                    raise ValueError(f"{self.key}: duplicate tie id {tie.id!r}")
                for ref in (tie.a, tie.b):
                    unknown = set(ref.winner_of) - seen
                    if unknown:
                        raise ValueError(
                            f"{self.key}: tie {tie.id} refers to later/unknown ties {unknown}"
                        )
            seen.update(t.id for t in rnd.ties)
        if not self.rounds or len(self.rounds[-1].ties) != 1:
            raise ValueError(f"{self.key}: the last round must be a single final tie")
        return self

    def entrant_ranks(self) -> set[int]:
        """The league ranks that enter (not those ranked within a group)."""
        return {
            ref.rank
            for rnd in self.rounds
            for tie in rnd.ties
            for ref in (tie.a, tie.b)
            if ref.rank is not None and ref.group is None
        }

    def group_ranks(self) -> set[tuple[str, int]]:
        """The (group, rank within it) that enter."""
        return {
            (ref.group, ref.rank)
            for rnd in self.rounds
            for tie in rnd.ties
            for ref in (tie.a, tie.b)
            if ref.rank is not None and ref.group is not None
        }


class SquadRulesDef(DefModel):
    max_registered: int | None = None
    min_homegrown: int | None = None
    exempt_under_age: int | None = None


class LeagueDef(DefModel):
    key: str
    name: str
    short_name: str
    nation: str
    tier: int = Field(ge=1)
    clubs: int = Field(ge=2)
    sim_level: SimLevel = SimLevel.PLAYABLE
    calendar: str
    # The ratings source's names for this league: its clubs are found by them when the league
    # is first played (a world built before the league existed, or a save from before it).
    source_leagues: list[str] = []
    format: RoundRobinFormat | GroupsFormat = Field(default_factory=RoundRobinFormat,
                                                    discriminator="type")
    groups: list[GroupDef] = []
    phases: list[PhaseDef] = []
    points: PointsRule = PointsRule()
    tiebreakers: list[Tiebreaker]
    movements: list[MovementDef] = []
    playoffs: list[PlayoffDef] = []
    squad_rules: SquadRulesDef | None = None
    # A title for the season table's top club when the champion is decided otherwise (the
    # Supporters' Shield; Argentina's annual table, the "Campeón de Liga"). None: the table's top
    # club is the champion, unless a play-off or the phases decide it.
    table_title: str | None = None

    @model_validator(mode="after")
    def _groups_and_phases(self) -> "LeagueDef":
        grouped = isinstance(self.format, GroupsFormat)
        if grouped != bool(self.groups):
            raise ValueError(f"{self.key}: a groups format needs groups, and groups need it")
        if self.groups:
            named = [c for g in self.groups for c in g.clubs]
            if len(named) != self.clubs or len(set(named)) != len(named):
                raise ValueError(f"{self.key}: the groups must hold each of the {self.clubs} "
                                 "clubs once")
            assert isinstance(self.format, GroupsFormat)
            sizes = {len(g.clubs) for g in self.groups}
            if self.format.cross_rounds and (len(self.groups) != 2 or len(sizes) != 1):
                raise ValueError(f"{self.key}: cross rounds need two groups of one size")
            if self.format.cross_rounds > len(self.groups[0].clubs):
                raise ValueError(f"{self.key}: more cross rounds than opponents")
            first, second = (set(g.clubs) for g in self.groups[:2])
            for a, b in self.format.rivals:
                if not ((a in first and b in second) or (a in second and b in first)):
                    raise ValueError(f"{self.key}: rivals {a} and {b} aren't one of each group")
            if self.format.rivals and not self.format.cross_rounds:
                raise ValueError(f"{self.key}: rivals need a cross round to meet in")
            if len({c for pair in self.format.rivals for c in pair}) != 2 * len(
                    self.format.rivals):
                raise ValueError(f"{self.key}: a club has two rivals")
        keys = {g.key for g in self.groups}
        phases = {p.key for p in self.phases}
        for po in self.playoffs:
            unknown = {g for g, _ in po.group_ranks()} - keys
            if unknown:
                raise ValueError(f"{self.key}: play-off {po.key} ranks in unknown groups {unknown}")
            for group, rank in po.group_ranks():
                size = len(next(g for g in self.groups if g.key == group).clubs)
                if rank > size:
                    raise ValueError(f"{self.key}: play-off {po.key} rank {rank} of {group}")
            if (po.phase is None) != (not self.phases):
                raise ValueError(f"{self.key}: play-off {po.key} must name a phase exactly "
                                 "when the league has phases")
            if po.phase is not None and po.phase not in phases:
                raise ValueError(f"{self.key}: play-off {po.key} for unknown phase {po.phase}")
            if po.title and po.winner_to:
                raise ValueError(f"{self.key}: play-off {po.key} crowns a champion; it can't "
                                 "also move its winner")
        titles = [po.phase for po in self.playoffs if po.title]
        if len(titles) != len(set(titles)):
            raise ValueError(f"{self.key}: two title play-offs for one table")
        if self.phases and self.movements:
            raise ValueError(f"{self.key}: promotion and relegation aren't supported with phases")
        return self

    @property
    def title_playoff(self) -> "PlayoffDef | None":
        """The season's title play-off (not a phase's)."""
        return next((p for p in self.playoffs if p.title and p.phase is None), None)

    def calendar_key(self, phase: str | None = None) -> str:
        """The calendar entry with this league's (or one of its phases') dates."""
        return self.key if phase is None else f"{self.key}:{phase}"

    @model_validator(mode="after")
    def _ranks_in_range(self) -> "LeagueDef":
        used: set[int] = set()
        for mv in self.movements:
            ranks = set(range(mv.ranks[0], mv.ranks[1] + 1))
            if mv.ranks[1] > self.clubs:
                raise ValueError(f"{self.key}: movement ranks {mv.ranks} exceed {self.clubs} clubs")
            if ranks & used:
                raise ValueError(f"{self.key}: overlapping movement/play-off ranks")
            used |= ranks
        for po in self.playoffs:
            if po.phase is not None:
                continue  # a phase's play-offs seed from its own table
            ranks = po.entrant_ranks()
            if max(ranks, default=0) > self.clubs:
                raise ValueError(f"{self.key}: play-off ranks exceed {self.clubs} clubs")
            if ranks & used:
                raise ValueError(f"{self.key}: play-off ranks overlap other movements")
            used |= ranks
        return self

    def promotions_to(self, target: str) -> int:
        """How many clubs this league sends up to ``target`` each season."""
        auto = sum(
            m.count for m in self.movements if m.kind is MovementKind.PROMOTION and m.to == target
        )
        return auto + sum(1 for p in self.playoffs if p.winner_to == target)

    def relegations_to(self, target: str) -> int:
        return sum(
            m.count for m in self.movements if m.kind is MovementKind.RELEGATION and m.to == target
        )

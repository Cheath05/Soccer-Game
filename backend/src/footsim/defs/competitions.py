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
    winner_of: list[str] = []
    pick: Literal["only", "highest_ranked", "lowest_ranked"] = "only"

    @model_validator(mode="after")
    def _one_source(self) -> "EntrantRef":
        if (self.rank is None) == (not self.winner_of):
            raise ValueError("entrant needs exactly one of 'rank' or 'winner_of'")
        if self.winner_of and self.pick == "only" and len(self.winner_of) != 1:
            raise ValueError("'pick' is required when choosing among several ties")
        return self


class TieDef(DefModel):
    id: str
    a: EntrantRef
    b: EntrantRef


class PlayoffRoundDef(DefModel):
    name: str
    legs: Literal[1, 2] = 1
    # Single leg: who hosts. Two legs: who hosts the second leg.
    host: Literal["higher_ranked", "lower_ranked", "neutral"] = "higher_ranked"
    extra_time: bool = True
    penalties: bool = True
    ties: list[TieDef]


class PlayoffDef(DefModel):
    key: str
    name: str
    winner_to: str | None = None
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
        return {
            ref.rank
            for rnd in self.rounds
            for tie in rnd.ties
            for ref in (tie.a, tie.b)
            if ref.rank is not None
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
    format: RoundRobinFormat = RoundRobinFormat()
    points: PointsRule = PointsRule()
    tiebreakers: list[Tiebreaker]
    movements: list[MovementDef] = []
    playoffs: list[PlayoffDef] = []
    squad_rules: SquadRulesDef | None = None

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

"""Knockout cups (data/config/cups/*.yaml): who enters when, and each round's rules. The draw,
byes and ties are played out in world/cups.py."""

from typing import Literal

from pydantic import Field, model_validator

from footsim.defs.common import DefModel


class CupEntryDef(DefModel):
    """Clubs of one league entering in one round: all of them, or a range of their ranks
    (last season's finish, promoted clubs below those who stayed up)."""

    league: str
    round: int = Field(ge=1)
    ranks: tuple[int, int] | None = None

    @model_validator(mode="after")
    def _ordered(self) -> "CupEntryDef":
        if self.ranks is not None and not 1 <= self.ranks[0] <= self.ranks[1]:
            raise ValueError(f"invalid ranks {self.ranks}")
        return self


class CupRoundDef(DefModel):
    name: str
    # How many clubs go through. Fewer than half the clubs in the round can't be; more means
    # the highest-ranked are exempt (a bye). Default: half, every club plays.
    qualifiers: int | None = None
    legs: Literal[1, 2] = 1
    neutral: bool = False  # at a neutral ground (Wembley) rather than the first-drawn club's
    extra_time: bool = True
    penalties: bool = True
    blocks: list[str] = []  # leagues that play no matches on this round's date(s)


class CupDef(DefModel):
    key: str
    name: str
    short_name: str
    nation: str
    entrants: list[CupEntryDef]
    rounds: list[CupRoundDef]

    @model_validator(mode="after")
    def _rounds(self) -> "CupDef":
        if not self.rounds:
            raise ValueError(f"{self.key}: no rounds")
        if any(e.round > len(self.rounds) for e in self.entrants):
            raise ValueError(f"{self.key}: entrants join a round that doesn't exist")
        return self

    def entering(self, round_index: int) -> list[CupEntryDef]:
        """Entries joining round ``round_index`` (0-based)."""
        return [e for e in self.entrants if e.round == round_index + 1]

    def sizes(self, league_sizes: dict[str, int]) -> list[tuple[int, int]]:
        """(clubs in it, clubs going through) for each round, given each league's size."""
        result = []
        carried = 0
        for index, rnd in enumerate(self.rounds):
            clubs = carried + sum(
                (e.ranks[1] - e.ranks[0] + 1) if e.ranks else league_sizes[e.league]
                for e in self.entering(index))
            through = rnd.qualifiers if rnd.qualifiers is not None else clubs // 2
            result.append((clubs, through))
            carried = through
        return result

"""What a finished match produces, whichever engine played it."""

from dataclasses import dataclass, field


@dataclass
class PlayerLine:
    player_id: int
    club_id: int
    started: bool
    minutes: int = 0
    goals: int = 0
    assists: int = 0
    shots: int = 0
    shots_on_target: int = 0
    passes: int = 0
    passes_completed: int = 0
    tackles: int = 0
    interceptions: int = 0
    saves: int = 0
    yellow: int = 0
    red: int = 0
    rating: float = 6.0


@dataclass
class MatchEvent:
    minute: int  # the football minute, counting on through added time (45+2 is 47)
    type: str  # goal | own_goal | penalty_goal | penalty_miss | yellow | red | sub | injury
    club_id: int
    player_id: int | None = None
    other_player_id: int | None = None  # assist provider, or the player coming on
    detail: str | None = None
    period: int | None = None  # 1-4, when the engine knows it to the second
    second: int | None = None  # seconds into ``period``


@dataclass
class TeamStats:
    goals: int = 0
    shots: int = 0
    shots_on_target: int = 0
    xg: float = 0.0
    possession: float = 50.0
    passes: int = 0
    passes_completed: int = 0
    corners: int = 0
    fouls: int = 0
    offsides: int = 0
    yellow: int = 0
    red: int = 0


@dataclass
class Injury:
    player_id: int
    club_id: int
    days: int
    name: str


@dataclass
class Decider:
    """Knockout rules for a match that must produce a winner."""

    extra_time: bool = True
    penalties: bool = True
    # Goals from the first leg, as (this match's home club, this match's away club).
    first_leg: tuple[int, int] | None = None

    def level(self, home_goals: int, away_goals: int) -> bool:
        prior_home, prior_away = self.first_leg or (0, 0)
        return home_goals + prior_home == away_goals + prior_away


@dataclass
class MatchReport:
    home_club_id: int
    away_club_id: int
    home_goals: int = 0
    away_goals: int = 0
    extra_time: bool = False
    home_pens: int | None = None
    away_pens: int | None = None
    events: list[MatchEvent] = field(default_factory=list)
    players: dict[int, PlayerLine] = field(default_factory=dict)
    home_stats: TeamStats = field(default_factory=TeamStats)
    away_stats: TeamStats = field(default_factory=TeamStats)
    injuries: list[Injury] = field(default_factory=list)
    fitness: dict[int, float] = field(default_factory=dict)  # player -> condition at full time

    def winner(self, decider: Decider | None = None) -> int | None:
        """Winning club over this match (and the first leg, if any). None for a draw."""
        prior_home, prior_away = (decider.first_leg if decider and decider.first_leg else (0, 0))
        home, away = self.home_goals + prior_home, self.away_goals + prior_away
        if home == away and self.home_pens is not None and self.away_pens is not None:
            home, away = self.home_pens, self.away_pens
        if home == away:
            return None
        return self.home_club_id if home > away else self.away_club_id

"""The football clock: periods, half-time and added time.

Three kinds of time are kept apart in the match:
  simulation time  ``MatchEngine.t``, advanced 0.1 s per tick; the only time the engine uses
  football clock   this module: the minutes and seconds of the current period, running
                   through dead balls just as a real match clock does
  playback time    how fast a viewer watches (match.live.session); the match never sees it

Added time follows IFAB Law 7: a StoppageLedger collects time lost to goals, substitutions,
injuries, cards and penalties, and at the end of each period the minimum added time is
announced. The announcement is capped so added time can't dominate a match.
"""

from dataclasses import dataclass, field
from enum import StrEnum

from footsim.defs.match import ClockDef

PERIOD_SECONDS = {1: 45 * 60, 2: 45 * 60, 3: 15 * 60, 4: 15 * 60}
PERIOD_START_MINUTE = {1: 0, 2: 45, 3: 90, 4: 105}


class ClockState(StrEnum):
    PLAYING = "playing"
    BREAK = "break"  # half-time, or the pause before or during extra time
    FINISHED = "finished"


@dataclass
class StoppageLedger:
    """Time lost in the current period, by cause (allowances: data/config/match/clock.yaml)."""

    allowance: dict[str, float]
    seconds: float = 0.0
    items: list[tuple[str, float]] = field(default_factory=list)

    def add(self, cause: str, seconds: float | None = None) -> None:
        amount = self.allowance.get(cause, 0.0) if seconds is None else seconds
        self.seconds += amount
        self.items.append((cause, amount))


@dataclass
class MatchClock:
    rules: ClockDef
    period: int = 1
    elapsed: float = 0.0  # seconds played in this period, advanced only by ticks
    state: ClockState = ClockState.PLAYING
    announced: int | None = None  # minutes of added time shown, once regulation is over
    ledger: StoppageLedger = field(init=False)

    def __post_init__(self) -> None:
        self.ledger = StoppageLedger(self.rules.allowance)

    @property
    def regulation(self) -> float:
        return float(PERIOD_SECONDS[self.period])

    @property
    def in_added_time(self) -> bool:
        return self.elapsed >= self.regulation

    @property
    def minute(self) -> int:
        """The football minute being played (1-based), counting on through added time, so
        the second minute of first-half added time is 47."""
        return PERIOD_START_MINUTE[self.period] + int(self.elapsed // 60) + 1

    def announce(self) -> int:
        low, high = self.rules.limits[self.period]
        lost = self.rules.base_seconds[self.period] + self.ledger.seconds
        self.announced = int(min(high, max(low, round(lost / 60))))
        return self.announced

    def due_to_end(self) -> bool:
        return (self.announced is not None
                and self.elapsed >= self.regulation + 60 * self.announced)

    def overrun(self) -> bool:
        return (self.announced is not None
                and self.elapsed >= self.regulation + 60 * self.announced
                + self.rules.max_overrun_seconds)

    def start_period(self, period: int) -> None:
        self.period = period
        self.elapsed = 0.0
        self.announced = None
        self.ledger = StoppageLedger(self.rules.allowance)
        self.state = ClockState.PLAYING

    def display(self) -> str:
        """The scoreboard clock: ``MM:SS``, with added time shown after the period's end
        (``45:00 +1:37``)."""
        start = PERIOD_START_MINUTE[self.period] * 60
        if self.state is ClockState.BREAK and self.elapsed == 0:
            return _mmss(start)
        if not self.in_added_time:
            return _mmss(start + self.elapsed)
        return f"{_mmss(start + self.regulation)} +{_mmss(self.elapsed - self.regulation)}"

    def label(self) -> str:
        """How an event's time is written: ``23'``, or ``45+2'`` in added time."""
        end = PERIOD_START_MINUTE[self.period] + int(self.regulation // 60)
        if self.in_added_time:
            return f"{end}+{int((self.elapsed - self.regulation) // 60) + 1}'"
        return f"{self.minute}'"


def _mmss(seconds: float) -> str:
    whole = int(seconds)
    return f"{whole // 60:02d}:{whole % 60:02d}"


def event_label(period: int, second: int) -> str:
    """``23'`` or ``45+2'`` for an event ``second`` seconds into ``period``."""
    regulation = PERIOD_SECONDS[period]
    end = PERIOD_START_MINUTE[period] + regulation // 60
    if second >= regulation:
        return f"{end}+{(second - regulation) // 60 + 1}'"
    return f"{PERIOD_START_MINUTE[period] + second // 60 + 1}'"

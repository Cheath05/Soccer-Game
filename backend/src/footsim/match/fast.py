"""Fast results: one draw per match, for the leagues the user has switched off full simulation
(world/fast_sim.py; Settings → Simulation).

Each side's goals are Poisson from the fast engine's own expected goals (QuickEngine
.expected_goals: the same starters' strengths, home advantage and instructions), so the leagues
keep their balance of strength. Then the goals get scorers and assists (the fast engine's
weights), a few starters are rested and a few substitutes come on, and every player who took part
gets his minutes and a rating, so tables, player pages and development carry on as before. There
are no cards, injuries or fatigue. Parameters in data/config/match/fast_results.yaml.
"""

import numpy as np

from footsim.defs.loader import GameDefinitions
from footsim.defs.positions import PositionGroup
from footsim.match.penalties import shootout
from footsim.match.quick import QuickEngine
from footsim.match.report import Decider, MatchEvent, MatchReport, PlayerLine, TeamStats
from footsim.match.teams import SheetPlayer, SquadPlayer, TeamSheet

DEFENSIVE = (PositionGroup.GK, PositionGroup.CB, PositionGroup.FB)


class FastResults:
    def __init__(self, defs: GameDefinitions, quick: QuickEngine) -> None:
        self.p = defs.fast_results
        self.q = defs.quick_engine
        self.quick = quick

    def play(self, home: TeamSheet, away: TeamSheet, rng: np.random.Generator,
             neutral: bool = False, decider: Decider | None = None) -> MatchReport:
        p = self.p
        lam_h, lam_a = self.quick.expected_goals(home, away, neutral)
        lam_h, lam_a = lam_h * p.goals_scale, lam_a * p.goals_scale
        report = MatchReport(home.club_id, away.club_id)
        sides = [_Side.build(home, rng, p.rest_chance), _Side.build(away, rng, p.rest_chance)]
        report.bench = [sp.player_id for side in sides for sp in side.bench]
        low, high = p.sub_minutes
        for side in sides:
            side.substitute(rng, p.subs_per_team, low, high)
        lam = (lam_h, lam_a)
        goals = [0, 0]
        prior = decider.first_leg if decider and decider.first_leg else (0, 0)
        for minute, i in self._goal_times(lam, prior, 0.0, 90.0, rng):
            self._goal(report, sides[i], sides[1 - i], minute, rng)
            goals[i] += 1
        end = 90
        if decider and decider.level(goals[0], goals[1]):
            if decider.extra_time:
                report.extra_time, end = True, 120
                totals = (goals[0] + prior[0], goals[1] + prior[1])
                for minute, i in self._goal_times(lam, totals, 90.0, 120.0, rng):
                    self._goal(report, sides[i], sides[1 - i], minute, rng)
                    goals[i] += 1
            if decider.level(goals[0], goals[1]) and decider.penalties:
                report.home_pens, report.away_pens = shootout(
                    [sp.player for sp in sides[0].on_pitch(end)], sides[0].keeper(),
                    [sp.player for sp in sides[1].on_pitch(end)], sides[1].keeper(), rng)
        report.home_goals, report.away_goals = goals
        report.events.sort(key=lambda e: e.minute)
        for i, side in enumerate(sides):
            self._lines(report, side, goals[i], goals[1 - i], end, rng)
        report.home_stats = TeamStats(goals=goals[0], xg=round(lam_h, 2))
        report.away_stats = TeamStats(goals=goals[1], xg=round(lam_a, 2))
        return report

    def _goal_times(self, lam: tuple[float, float], score: tuple[int, int], start: float,
                    end: float, rng: np.random.Generator) -> list[tuple[int, int]]:
        """When each side scores between ``start`` and ``end`` minutes, as (minute, side), from
        ``score`` (with any first leg's goals). The goals come as a Poisson process whose rates
        follow the fast engine's: its share of the expected goals in each half (extra time at
        extra_time_share of a match), a side well ahead easing off, and late on the trailing side
        pushing and the leading side catching it on the break. Rates only change at a goal or at
        a boundary (half time, the chasing minute), so only those are stepped through."""
        q, p = self.q, self.p
        inside = (m for m in (45.0, float(q.chasing_minute)) if start < m < end)
        cuts = sorted({start, end, *inside})
        totals = list(score)
        found: list[tuple[int, int]] = []
        t = start
        for stop in cuts[1:]:
            while True:
                if t >= 90.0:
                    share = p.extra_time_share / 30
                else:
                    share = (q.second_half_share if t >= 45.0 else 1 - q.second_half_share) / 45
                rates = []
                for i in (0, 1):
                    rate = lam[i] * share
                    lead = totals[i] - totals[1 - i]
                    if lead >= q.easing_lead:
                        rate *= q.easing_own_goals ** (lead - q.easing_lead + 1)
                    if t >= q.chasing_minute and lead != 0:
                        rate *= q.chasing_own_goals if lead < 0 else q.chasing_opponent_goals
                    rates.append(rate)
                total = rates[0] + rates[1]
                wait = float(rng.exponential(1 / total)) if total > 0 else float("inf")
                if t + wait >= stop:
                    t = stop
                    break
                t += wait
                side = 0 if rng.random() * total < rates[0] else 1
                totals[side] += 1
                found.append((min(int(t) + 1, int(end)), side))
        return found

    def _goal(self, report: MatchReport, side: "_Side", other: "_Side", minute: int,
              rng: np.random.Generator) -> None:
        q = self.q
        club = side.sheet.club_id
        if rng.random() < q.own_goal_share:
            defenders = [sp for sp in other.on_pitch(minute) if sp.group is not PositionGroup.GK]
            victim = _pick(defenders, [q.defence_weights[sp.group] for sp in defenders], rng)
            report.events.append(MatchEvent(minute, "own_goal", club,
                                            victim.player_id if victim else None))
            return
        on = side.on_pitch(minute)
        if rng.random() < q.penalty_share:
            taker = max(on, key=lambda sp: sp.player.attr("penalties"))
            side.line(taker).goals += 1
            report.events.append(MatchEvent(minute, "penalty_goal", club, taker.player_id))
            return
        weights = [q.scorer_weights[sp.group] * (sp.player.attr("finishing") / 70) ** 2
                   * (sp.player.attr("off_ball") / 70) for sp in on]
        scorer = _pick(on, weights, rng)
        if scorer is None:
            return
        assister = None
        if rng.random() < q.assist_share:
            others = [sp for sp in on if sp is not scorer]
            creativity = [q.assist_weights[sp.group] * ((sp.player.attr("vision")
                          + sp.player.attr("short_passing") + sp.player.attr("crossing") / 2)
                          / 175) ** 2 for sp in others]
            assister = _pick(others, creativity, rng)
        side.line(scorer).goals += 1
        if assister:
            side.line(assister).assists += 1
        report.events.append(MatchEvent(minute, "goal", club, scorer.player_id,
                                        assister.player_id if assister else None))

    def _lines(self, report: MatchReport, side: "_Side", scored: int, conceded: int, end: int,
               rng: np.random.Generator) -> None:
        result = (scored > conceded) - (scored < conceded)
        for sp in side.played():
            line = side.line(sp)
            start, leave = side.entered.get(sp.player_id, 0), side.left.get(sp.player_id, end)
            line.minutes = max(1, min(leave, end) - start)
            rating = 6.3 + 0.3 * result + 1.0 * line.goals + 0.6 * line.assists
            if sp.group in DEFENSIVE:
                rating += 0.6 if conceded == 0 else -0.15 * conceded
            rating += 0.015 * (sp.rating - 70) + float(rng.normal(0, self.p.rating_noise))
            if line.minutes < 20:
                rating = 6.0 + (rating - 6.0) * 0.4
            line.rating = round(float(np.clip(rating, 3.5, 10.0)), 1)
            report.players[sp.player_id] = line
        for sp_out, sp_in, minute in side.subs:
            report.events.append(MatchEvent(minute, "sub", side.sheet.club_id, sp_out.player_id,
                                            sp_in.player_id))


def _pick(players: list[SheetPlayer], weights: list[float],
          rng: np.random.Generator) -> SheetPlayer | None:
    total = sum(weights)
    if not players or total <= 0:
        return None
    return players[int(rng.choice(len(players), p=np.array(weights) / total))]


class _Side:
    """One side's players through the match: who started (after rotation), who came on when."""

    def __init__(self, sheet: TeamSheet, starters: list[SheetPlayer],
                 bench: list[SheetPlayer]) -> None:
        self.sheet = sheet
        self.starters = starters
        self.bench = bench
        self.entered: dict[int, int] = {}
        self.left: dict[int, int] = {}
        self.subs: list[tuple[SheetPlayer, SheetPlayer, int]] = []
        self.lines: dict[int, PlayerLine] = {}
        self._starter_ids = {sp.player_id for sp in starters}

    @classmethod
    def build(cls, sheet: TeamSheet, rng: np.random.Generator, rest_chance: float) -> "_Side":
        """The sheet's XI, with each outfield starter rested for the best substitute of his
        position group with ``rest_chance`` (that substitute takes his place and role)."""
        starters, bench = list(sheet.starters), list(sheet.bench)
        for k, sp in enumerate(starters):
            if sp.group is PositionGroup.GK or rng.random() >= rest_chance:
                continue
            same = [b for b in bench if b.group is sp.group]
            if not same:
                continue
            incoming = max(same, key=lambda b: b.rating)
            bench.remove(incoming)
            starters[k] = _in_place_of(incoming, sp)
            bench.append(sp)
        return cls(sheet, starters, bench)

    def substitute(self, rng: np.random.Generator, count: int, low: int, high: int) -> None:
        minutes = sorted(int(m) for m in rng.integers(low, high + 1, size=count))
        on = [sp for sp in self.starters if sp.group is not PositionGroup.GK]
        on.sort(key=lambda sp: sp.rating)
        for minute in minutes:
            if not on or not self.bench:
                return
            out = on.pop(0)
            outfield = [b for b in self.bench if b.group is not PositionGroup.GK]
            same = [b for b in outfield if b.group is out.group]
            pool = same or outfield
            if not pool:
                return
            incoming = max(pool, key=lambda b: b.rating)
            self.bench.remove(incoming)
            entering = _in_place_of(incoming, out)
            self.left[out.player_id] = minute
            self.entered[entering.player_id] = minute
            self.subs.append((out, entering, minute))

    def on_pitch(self, minute: int) -> list[SheetPlayer]:
        here = [sp for sp in self.starters if self.left.get(sp.player_id, 999) > minute]
        here += [sp_in for _, sp_in, m in self.subs if m <= minute]
        return here

    def keeper(self) -> SquadPlayer | None:
        gk = next((sp for sp in self.starters if sp.group is PositionGroup.GK), None)
        return gk.player if gk else None

    def played(self) -> list[SheetPlayer]:
        return [*self.starters, *(sp_in for _, sp_in, _ in self.subs)]

    def line(self, sp: SheetPlayer) -> PlayerLine:
        line = self.lines.get(sp.player_id)
        if line is None:
            line = PlayerLine(sp.player_id, self.sheet.club_id,
                              started=sp.player_id in self._starter_ids)
            self.lines[sp.player_id] = line
        return line


def _in_place_of(incoming: SheetPlayer, out: SheetPlayer) -> SheetPlayer:
    """A substitute taking ``out``'s slot, position and role, rated by his own overall."""
    return SheetPlayer(incoming.player, incoming.number, out.slot, out.position, out.group,
                       out.role, incoming.rating)

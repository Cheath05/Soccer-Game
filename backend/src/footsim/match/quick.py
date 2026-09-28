"""Fast statistical match engine for matches nobody watches (Tier 1 in the design).

The match is played minute by minute: each side's scoring rate comes from its starters'
slot ratings (attack vs the opposing defence, midfield vs midfield), home advantage, team
instructions, red cards and the game state. Goals, cards, injuries and substitutions become
timed events with named players, so results feed stats, form, fitness and suspensions.
Parameters live in data/config/match/quick_engine.yaml.
"""

import math
from dataclasses import dataclass, field

import numpy as np

from footsim.defs.loader import GameDefinitions
from footsim.defs.positions import PositionGroup
from footsim.match.penalties import penalty_probability, shootout
from footsim.match.report import Decider, Injury, MatchEvent, MatchReport, PlayerLine, TeamStats
from footsim.match.teams import SheetPlayer, SquadPlayer, TeamSheet

YELLOW_WEIGHT = {PositionGroup.GK: 0.2, PositionGroup.CB: 1.3, PositionGroup.FB: 1.1,
                 PositionGroup.DM: 1.4, PositionGroup.CM: 1.0, PositionGroup.AM: 0.7,
                 PositionGroup.W: 0.7, PositionGroup.ST: 0.8}
INJURIES = [  # (name, median days, spread)
    ("Knock", 4, 0.5), ("Hamstring strain", 21, 0.5), ("Calf strain", 14, 0.5),
    ("Ankle sprain", 18, 0.6), ("Groin strain", 16, 0.5), ("Thigh bruise", 7, 0.5),
    ("Knee ligament damage", 60, 0.6), ("Concussion", 10, 0.3), ("Broken metatarsal", 75, 0.3),
]
INJURY_WEIGHTS = [0.30, 0.18, 0.12, 0.12, 0.08, 0.10, 0.04, 0.04, 0.02]
FATIGUE_PER_MINUTE = 0.30
SUB_BELOW_STAMINA = 88.0


@dataclass
class _Side:
    sheet: TeamSheet
    on_pitch: list[SheetPlayer]
    bench: list[SheetPlayer]
    lines: dict[int, PlayerLine]
    stamina: dict[int, float]
    entered: dict[int, int] = field(default_factory=dict)
    left: dict[int, int] = field(default_factory=dict)
    goals: int = 0
    reds: int = 0
    yellows: dict[int, int] = field(default_factory=dict)
    subs_used: int = 0
    xg: float = 0.0


def _weighted_average(players: list[SheetPlayer], weights: dict[PositionGroup, float]) -> float:
    total = sum(weights[p.group] for p in players)
    if total <= 0:
        return 60.0
    return sum(weights[p.group] * p.rating for p in players) / total


class QuickEngine:
    def __init__(self, defs: GameDefinitions) -> None:
        self.p = defs.quick_engine

    def strengths(self, players: list[SheetPlayer]) -> tuple[float, float, float]:
        p = self.p
        return (_weighted_average(players, p.attack_weights),
                _weighted_average(players, p.defence_weights),
                _weighted_average(players, p.midfield_weights))

    def _effects(self, sheet: TeamSheet) -> tuple[float, float, float]:
        own = opp = fatigue = 1.0
        for key, levels in self.p.instructions.items():
            effect = levels.get(sheet.instruction(key, ""))
            if effect:
                own *= effect.own_goals
                opp *= effect.opponent_goals
                fatigue *= effect.fatigue
        return own, opp, fatigue

    def expected_goals(self, home: TeamSheet, away: TeamSheet, neutral: bool = False
                       ) -> tuple[float, float]:
        p = self.p
        att_h, def_h, mid_h = self.strengths(home.starters)
        att_a, def_a, mid_a = self.strengths(away.starters)
        adv = 1.0 if neutral else p.home_advantage
        own_h, opp_h, _ = self._effects(home)
        own_a, opp_a, _ = self._effects(away)
        lam_h = p.base_goals * adv * math.exp(
            p.attack_beta * (att_h - def_a) + p.midfield_beta * (mid_h - mid_a)) * own_h * opp_a
        lam_a = p.base_goals / adv * math.exp(
            p.attack_beta * (att_a - def_h) + p.midfield_beta * (mid_a - mid_h)) * own_a * opp_h
        return lam_h, lam_a

    def play(self, home: TeamSheet, away: TeamSheet, rng: np.random.Generator,
             neutral: bool = False, decider: Decider | None = None) -> MatchReport:
        p = self.p
        report = MatchReport(home.club_id, away.club_id)
        sides = [self._side(home), self._side(away)]
        lam = self.expected_goals(home, away, neutral)
        fatigue = [self._effects(home)[2], self._effects(away)[2]]
        mid = [self.strengths(home.starters)[2], self.strengths(away.starters)[2]]

        halves = [(1, 45 + int(rng.integers(1, 4)), 1 - p.second_half_share),
                  (46, 90 + int(rng.integers(2, 7)), p.second_half_share)]
        sub_minutes = sorted(int(m) for m in rng.integers(58, 86, size=3))
        for start, end, share in halves:
            for minute in range(start, end + 1):
                self._minute(report, sides, lam, share / 45, min(minute, 90), rng, decider)
                self._tire(sides, fatigue)
                if minute in sub_minutes:
                    for side in sides:
                        self._substitute(report, side, minute, rng)

        if decider and decider.level(sides[0].goals, sides[1].goals):
            if decider.extra_time:
                report.extra_time = True
                for minute in range(91, 121):
                    self._minute(report, sides, lam, 0.9 / 90, minute, rng, decider)
                    self._tire(sides, fatigue)
            if decider.level(sides[0].goals, sides[1].goals) and decider.penalties:
                report.home_pens, report.away_pens = shootout(
                    [sp.player for sp in sides[0].on_pitch], self._keeper(sides[0]),
                    [sp.player for sp in sides[1].on_pitch], self._keeper(sides[1]), rng)

        end_minute = 120 if report.extra_time else 90
        report.home_goals, report.away_goals = sides[0].goals, sides[1].goals
        self._finish(report, sides, mid, neutral, end_minute, rng)
        return report

    # --- match flow -------------------------------------------------------------------

    def _side(self, sheet: TeamSheet) -> _Side:
        lines = {sp.player_id: PlayerLine(sp.player_id, sheet.club_id, started=True)
                 for sp in sheet.starters}
        stamina = {sp.player_id: sp.player.condition for sp in [*sheet.starters, *sheet.bench]}
        side = _Side(sheet, list(sheet.starters), list(sheet.bench), lines, stamina)
        for sp in sheet.starters:
            side.entered[sp.player_id] = 0
        return side

    def _minute(self, report: MatchReport, sides: list[_Side], lam: tuple[float, float],
                per_minute_share: float, minute: int, rng: np.random.Generator,
                decider: Decider | None) -> None:
        p = self.p
        prior = decider.first_leg if decider and decider.first_leg else (0, 0)
        totals = [sides[0].goals + prior[0], sides[1].goals + prior[1]]
        for i, side in enumerate(sides):
            other = sides[1 - i]
            rate = lam[i] * per_minute_share
            rate *= p.red_card_own_goals ** side.reds * p.red_card_opponent_goals ** other.reds
            lead = totals[i] - totals[1 - i]
            if lead >= p.easing_lead:
                rate *= p.easing_own_goals ** (lead - p.easing_lead + 1)
            if minute >= p.chasing_minute and lead != 0:
                rate *= p.chasing_own_goals if lead < 0 else p.chasing_opponent_goals
            side.xg += rate
            if rng.random() < rate:
                self._goal(report, side, other, minute, rng)
            if rng.random() < p.yellows_per_team / 90:
                self._card(report, side, minute, rng, straight_red=False)
            if rng.random() < p.straight_reds_per_team / 90:
                self._card(report, side, minute, rng, straight_red=True)
            if rng.random() < p.injuries_per_team / 90:
                self._injury(report, side, minute, rng)

    def _tire(self, sides: list[_Side], fatigue: list[float]) -> None:
        for side, factor in zip(sides, fatigue, strict=True):
            for sp in side.on_pitch:
                stamina = sp.player.attr("stamina")
                drain = FATIGUE_PER_MINUTE * factor * (1.25 - stamina / 200)
                side.stamina[sp.player_id] = max(0.0, side.stamina[sp.player_id] - drain)

    def _pick(self, players: list[SheetPlayer], weights: list[float],
              rng: np.random.Generator) -> SheetPlayer | None:
        total = sum(weights)
        if not players or total <= 0:
            return None
        return players[int(rng.choice(len(players), p=np.array(weights) / total))]

    def _goal(self, report: MatchReport, side: _Side, other: _Side, minute: int,
              rng: np.random.Generator) -> None:
        p = self.p
        club = side.sheet.club_id
        if rng.random() < p.own_goal_share:
            defenders = [sp for sp in other.on_pitch if sp.group is not PositionGroup.GK]
            victim = self._pick(defenders, [p.defence_weights[sp.group] for sp in defenders], rng)
            side.goals += 1
            report.events.append(MatchEvent(minute, "own_goal", club,
                                            victim.player_id if victim else None))
            return
        if rng.random() < p.penalty_share:
            taker = max(side.on_pitch, key=lambda sp: sp.player.attr("penalties"))
            keeper = self._keeper(other)
            if rng.random() > penalty_probability(taker.player, keeper):
                report.events.append(MatchEvent(minute, "penalty_miss", club, taker.player_id))
                side.lines[taker.player_id].shots += 1
                return
            side.goals += 1
            side.lines[taker.player_id].goals += 1
            side.lines[taker.player_id].shots += 1
            side.lines[taker.player_id].shots_on_target += 1
            report.events.append(MatchEvent(minute, "penalty_goal", club, taker.player_id))
            return
        weights = [p.scorer_weights[sp.group]
                   * (sp.player.attr("finishing") / 70) ** 2 * (sp.player.attr("off_ball") / 70)
                   for sp in side.on_pitch]
        scorer = self._pick(side.on_pitch, weights, rng)
        if scorer is None:
            return
        assister = None
        if rng.random() < p.assist_share:
            others = [sp for sp in side.on_pitch if sp is not scorer]
            creativity = [p.assist_weights[sp.group] * ((sp.player.attr("vision")
                          + sp.player.attr("short_passing") + sp.player.attr("crossing") / 2)
                          / 175) ** 2 for sp in others]
            assister = self._pick(others, creativity, rng)
        side.goals += 1
        line = side.lines[scorer.player_id]
        line.goals += 1
        line.shots += 1
        line.shots_on_target += 1
        if assister:
            side.lines[assister.player_id].assists += 1
        report.events.append(MatchEvent(minute, "goal", club, scorer.player_id,
                                        assister.player_id if assister else None))

    def _card(self, report: MatchReport, side: _Side, minute: int, rng: np.random.Generator,
              straight_red: bool) -> None:
        weights = [YELLOW_WEIGHT[sp.group] * sp.player.attr("aggression") / 60
                   for sp in side.on_pitch]
        player = self._pick(side.on_pitch, weights, rng)
        if player is None:
            return
        club = side.sheet.club_id
        line = side.lines[player.player_id]
        if not straight_red:
            side.yellows[player.player_id] = side.yellows.get(player.player_id, 0) + 1
            line.yellow += 1
            report.events.append(MatchEvent(minute, "yellow", club, player.player_id))
            if side.yellows[player.player_id] < 2:
                return
            detail = "second yellow"
        else:
            detail = "straight red"
        line.red += 1
        side.reds += 1
        report.events.append(MatchEvent(minute, "red", club, player.player_id, detail=detail))
        side.on_pitch.remove(player)
        side.left[player.player_id] = minute

    def _injury(self, report: MatchReport, side: _Side, minute: int,
                rng: np.random.Generator) -> None:
        outfield = [sp for sp in side.on_pitch if sp.group is not PositionGroup.GK]
        weights = [1.0 + (100 - side.stamina[sp.player_id]) / 50 for sp in outfield]
        player = self._pick(outfield, weights, rng)
        if player is None:
            return
        kind = int(rng.choice(len(INJURIES), p=np.array(INJURY_WEIGHTS) / sum(INJURY_WEIGHTS)))
        name, median, spread = INJURIES[kind]
        days = max(1, int(round(median * math.exp(rng.normal(0, spread)))))
        report.injuries.append(Injury(player.player_id, side.sheet.club_id, days, name))
        report.events.append(MatchEvent(minute, "injury", side.sheet.club_id, player.player_id,
                                        detail=name))
        self._replace(report, side, player, minute, rng)

    def _substitute(self, report: MatchReport, side: _Side, minute: int,
                    rng: np.random.Generator) -> None:
        if side.subs_used >= self.p.subs_per_team or not side.bench:
            return
        tired = sorted((sp for sp in side.on_pitch if sp.group is not PositionGroup.GK),
                       key=lambda sp: side.stamina[sp.player_id] + sp.rating / 4)
        count = min(len(tired), int(rng.integers(1, 3)), self.p.subs_per_team - side.subs_used)
        for sp in tired[:count]:
            if side.stamina[sp.player_id] < SUB_BELOW_STAMINA:
                self._replace(report, side, sp, minute, rng)

    def _replace(self, report: MatchReport, side: _Side, out: SheetPlayer, minute: int,
                 rng: np.random.Generator) -> None:
        if side.subs_used >= self.p.subs_per_team or not side.bench:
            return
        same = [sp for sp in side.bench if sp.group is out.group]
        pool = same or [sp for sp in side.bench if sp.group is not PositionGroup.GK] or side.bench
        incoming = max(pool, key=lambda sp: sp.rating)
        side.bench.remove(incoming)
        entering = SheetPlayer(incoming.player, incoming.number, out.slot, out.position,
                               out.group, out.role, incoming.rating)
        side.on_pitch[side.on_pitch.index(out)] = entering
        side.left[out.player_id] = minute
        side.entered[incoming.player_id] = minute
        side.lines[incoming.player_id] = PlayerLine(incoming.player_id, side.sheet.club_id,
                                                    started=False)
        side.subs_used += 1
        report.events.append(MatchEvent(minute, "sub", side.sheet.club_id, out.player_id,
                                        incoming.player_id))

    @staticmethod
    def _keeper(side: _Side) -> SquadPlayer | None:
        keeper = next((sp for sp in side.on_pitch if sp.group is PositionGroup.GK), None)
        return keeper.player if keeper else None

    # --- stats and ratings ------------------------------------------------------------

    def _finish(self, report: MatchReport, sides: list[_Side], mid: list[float], neutral: bool,
                end_minute: int, rng: np.random.Generator) -> None:
        p = self.p
        possession = 50 + 2.0 * (mid[0] - mid[1]) + (0 if neutral else 2) + rng.normal(0, 3)
        possession = float(np.clip(possession, 28, 72))
        stats = [report.home_stats, report.away_stats]
        for i, side in enumerate(sides):
            st = stats[i]
            st.goals = side.goals
            st.xg = round(side.xg, 2)
            st.possession = round(possession if i == 0 else 100 - possession, 1)
            logged_shots = sum(line.shots for line in side.lines.values())
            logged_on = sum(line.shots_on_target for line in side.lines.values())
            # Own goals count for the side but aren't its shots, so floor shots at goals.
            st.shots = max(logged_shots, side.goals, int(rng.poisson(side.xg / p.xg_per_shot)))
            on_rate = max(0.0, p.on_target_share - side.goals / max(st.shots, 1))
            st.shots_on_target = min(st.shots, max(
                logged_on, side.goals + int(rng.binomial(st.shots - side.goals, on_rate))))
            st.passes = int(rng.normal(9.0 * st.possession, 40))
            st.passes_completed = int(st.passes * np.clip(
                0.72 + (st.possession - 50) / 250 + (mid[i] - 65) / 400, 0.6, 0.92))
            st.corners = int(rng.poisson(5.0 * side.xg / 1.4 + 1))
            st.fouls = int(rng.poisson(11))
            st.offsides = int(rng.poisson(1.8))
            st.yellow = sum(line.yellow for line in side.lines.values())
            st.red = side.reds

        for i, side in enumerate(sides):
            other = sides[1 - i]
            st, opp = stats[i], stats[1 - i]
            participants = list(side.lines.values())
            minutes = {}
            for line in participants:
                start = side.entered.get(line.player_id, 0)
                end = side.left.get(line.player_id, end_minute)
                minutes[line.player_id] = max(1, min(end, end_minute) - start)
                line.minutes = minutes[line.player_id]
            by_id = {sp.player_id: sp for sp in [*side.sheet.starters, *side.sheet.bench]}
            self._spread_stats(side, st, opp, minutes, by_id, rng)
            result = (side.goals > other.goals) - (side.goals < other.goals)
            conceded = other.goals
            for line in participants:
                sp = by_id[line.player_id]
                rating = 6.3 + 0.3 * result + 1.0 * line.goals + 0.6 * line.assists
                rating += 0.1 * line.shots_on_target + 0.04 * (line.tackles + line.interceptions)
                if sp.group in (PositionGroup.GK, PositionGroup.CB, PositionGroup.FB):
                    rating += 0.6 if conceded == 0 else -0.15 * conceded
                if sp.group is PositionGroup.GK:
                    rating += 0.15 * line.saves
                rating += 0.015 * (sp.rating - 70) + float(rng.normal(0, 0.35))
                rating -= 0.2 * line.yellow + 1.5 * line.red
                if line.minutes < 20:
                    rating = 6.0 + (rating - 6.0) * 0.4
                line.rating = round(float(np.clip(rating, 3.5, 10.0)), 1)
            report.players.update(side.lines)
            report.fitness.update({pid: round(side.stamina[pid], 1) for pid in side.lines})

    def _spread_stats(self, side: _Side, st: TeamStats, opp: TeamStats, minutes: dict[int, int],
                      by_id: dict[int, SheetPlayer], rng: np.random.Generator) -> None:
        p = self.p
        ids = list(minutes)
        share = np.array([minutes[i] for i in ids], dtype=float)
        groups = [by_id[i].group for i in ids]

        def allocate(total: int, weights: list[float]) -> np.ndarray:
            w = np.array(weights) * share
            if total <= 0 or w.sum() <= 0:
                return np.zeros(len(ids), dtype=int)
            return rng.multinomial(total, w / w.sum())

        extra_shots = st.shots - sum(side.lines[i].shots for i in ids)
        extra_on = st.shots_on_target - sum(side.lines[i].shots_on_target for i in ids)
        shot_w = [p.scorer_weights[g] + 0.02 for g in groups]
        more_on = allocate(max(0, extra_on), shot_w)
        more_off = allocate(max(0, extra_shots - max(0, extra_on)), shot_w)
        pass_w = [{PositionGroup.GK: 0.5, PositionGroup.CB: 1.3, PositionGroup.FB: 1.1,
                   PositionGroup.DM: 1.4, PositionGroup.CM: 1.4, PositionGroup.AM: 1.0,
                   PositionGroup.W: 0.8, PositionGroup.ST: 0.6}[g] for g in groups]
        passes = allocate(st.passes, pass_w)
        completed = allocate(st.passes_completed, pass_w)
        def_w = [{PositionGroup.GK: 0.0, PositionGroup.CB: 1.2, PositionGroup.FB: 1.1,
                  PositionGroup.DM: 1.4, PositionGroup.CM: 1.0, PositionGroup.AM: 0.5,
                  PositionGroup.W: 0.5, PositionGroup.ST: 0.3}[g] for g in groups]
        tackles = allocate(int(rng.poisson(16)), def_w)
        interceptions = allocate(int(rng.poisson(9)), def_w)
        keeper_minutes = {pid: minutes[pid] for pid, g in zip(ids, groups, strict=True)
                          if g is PositionGroup.GK}
        main_keeper = max(keeper_minutes, key=lambda k: keeper_minutes[k], default=None)
        for k, pid in enumerate(ids):
            line = side.lines[pid]
            line.shots += int(more_on[k] + more_off[k])
            line.shots_on_target += int(more_on[k])
            line.passes = int(passes[k])
            line.passes_completed = int(min(passes[k], completed[k]))
            line.tackles = int(tackles[k])
            line.interceptions = int(interceptions[k])
            if pid == main_keeper:
                line.saves = max(0, opp.shots_on_target - opp.goals)

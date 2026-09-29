"""Duels for the ball: tackles, take-ons, fouls and cards.

Only the defender closest to the ball carrier challenges him. He first sizes the carrier up
(quicker with better anticipation), then either commits to a tackle, at a rate per second
set by his instructions, aggression, booking and fatigue, or keeps jockeying, which is
pressure without a tackle. A carrier who runs straight at a defender tries to take him on,
once. A beaten defender may stop a counter-attack with a tactical foul. A foul's severity
decides the card. Parameters: data/config/match/duels.yaml.
"""

import math
from typing import TYPE_CHECKING

import numpy as np

from footsim.defs.positions import PositionGroup
from footsim.match.engine import actions
from footsim.match.engine.pitch import LENGTH, MID_Y, PENALTY_SPOT, WIDTH, in_box, in_own_box
from footsim.match.quick import INJURIES, INJURY_WEIGHTS
from footsim.match.report import Injury

if TYPE_CHECKING:
    from footsim.match.engine.engine import MatchEngine

INJURY_IN_FOUL = 0.012  # chance a foul injures the player fouled
DT = 0.1  # seconds per engine tick


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def contest(eng: "MatchEngine", i: int) -> bool:
    """The ball carrier ``i`` under challenge this tick. True if he lost the ball (or was
    fouled), so play has moved on."""
    p = eng.defs.duels
    team = int(eng.team_of[i])
    opps = [int(k) for k in eng.team_indices(1 - team) if eng.group[k] is not PositionGroup.GK]
    if not opps:
        return False
    gaps = np.linalg.norm(eng.pos[opps] - eng.pos[i], axis=1)
    nearest = int(np.argmin(gaps))
    k, gap = opps[nearest], float(gaps[nearest])
    if gap > p.engage_radius or eng.t < eng.tackle_ready[k]:
        eng.engaged.pop(k, None)
        return False
    carrier, since = eng.engaged.get(k, (-1, 0.0))
    if carrier != i:
        eng.engaged[k] = (i, eng.t)
        since = eng.t

    # A carrier running with the ball into a defender who blocks his path either tries to
    # take him on or checks back and looks for a pass.
    speed = float(np.linalg.norm(eng.vel[i]))
    if (eng.carry_target is not None and speed > p.take_on_speed and gap < p.contact_radius
            and eng.t >= eng.take_on_ready.get((i, k), 0.0)):
        heading = eng.vel[i] / speed
        if float((eng.pos[k] - eng.pos[i]) @ heading) > 0.6 * gap:
            eng.take_on_ready[(i, k)] = eng.t + p.take_on_cooldown
            appetite = (p.take_on_appetite * (eng.a(i, "dribbling") + eng.a(i, "flair")) / 160
                        * (1 + eng.role[i].on_ball.dribble_bias))
            if eng.rng.random() < appetite:
                return _duel(eng, k, i, gap, take_on=True)
            eng.carry_target = None  # checks back: slows and re-decides
            eng.vel[i] *= 0.3
            eng.decide_at = min(eng.decide_at, eng.t + 0.3)
            return False

    low, high = p.reaction
    reaction = high - (high - low) * eng.a(k, "anticipation") / 100
    if eng.t - since < reaction:
        return False
    if eng.rng.random() >= _tackle_rate(eng, k, i) * DT:
        return False
    return _duel(eng, k, i, gap, take_on=False)


def _tackle_rate(eng: "MatchEngine", k: int, i: int) -> float:
    """Tackle attempts per second by defender ``k`` engaged with carrier ``i``."""
    p = eng.defs.duels
    team = int(eng.team_of[k])
    pressing = eng.instructions[team].get("pressing", "normal")
    rate = p.tackle_rate * p.pressing_commitment.get(pressing, 1.0)
    rate *= 0.6 + eng.a(k, "aggression") / 250
    rate *= 0.7 + 0.3 * float(eng.stamina[k])
    if eng.yellows[k]:
        rate *= p.booked_caution
    if in_own_box(*eng.to_att(team, float(eng.pos[i, 0]), float(eng.pos[i, 1]))):
        rate *= p.careful_in_own_box
    return rate


def _duel(eng: "MatchEngine", k: int, i: int, gap: float, take_on: bool) -> bool:
    p = eng.defs.duels
    team = int(eng.team_of[i])
    defending = 1 - team
    sliding = gap > 1.2
    tackler_x, _ = eng.to_att(defending, float(eng.pos[k, 0]), float(eng.pos[k, 1]))
    carrier_x, carrier_y = eng.to_att(defending, float(eng.pos[i, 0]), float(eng.pos[i, 1]))
    from_behind = tackler_x > carrier_x + 0.5  # he's chasing, not goal-side
    foul = p.foul_chance * eng.a(k, "aggression") / 65
    foul *= (1.3 if sliding else 1.0) * (1.25 if from_behind else 1.0)
    if in_own_box(carrier_x, carrier_y):
        foul *= p.box_foul_scale
    if eng.yellows[k]:
        foul *= p.booked_caution
    kind = "take_on" if take_on else "tackle"
    if eng.rng.random() < foul:
        eng.emit("duel", defending, k, outcome="foul", carrier=i, xa=round(tackler_x, 1),
                 sliding=sliding, kind=kind)
        commit_foul(eng, k, i, sliding=sliding, from_behind=from_behind)
        return True
    tackle = (0.55 * eng.a(k, "sliding_tackle" if sliding else "standing_tackle")
              + 0.25 * eng.a(k, "def_positioning") + 0.2 * eng.a(k, "strength"))
    if carrier_x < 35:
        tackle += 6.0  # near their own goal defenders commit, with cover behind them
    dribble = (0.45 * eng.a(i, "dribbling") + 0.2 * eng.a(i, "agility")
               + 0.15 * eng.a(i, "balance") + 0.2 * eng.a(i, "strength"))
    edge = p.take_on_edge if take_on else p.tackle_edge
    if eng.rng.random() < _sigmoid((tackle - dribble) / 12 + edge):
        eng.emit("duel", defending, k, outcome="won", carrier=i, xa=round(tackler_x, 1),
                 sliding=sliding, kind=kind)
        eng.tackle_ready[k] = eng.t + p.tackle_cooldown
        eng.lines[eng.players[k].player_id].tackles += 1
        eng.commentate(defending, f"{eng.players[k].player.short_name} wins it with a tackle "
                                  f"on {eng.players[i].player.short_name}")
        midfield, deep = p.keep_after_tackle
        if eng.rng.random() < (deep if carrier_x < 35 else midfield):
            actions.gain_possession(eng, k, how="tackle")
        else:  # poked away: out of play if he's near the touchline, else up the pitch
            eng.owner = -1
            eng.state = "loose"
            y = float(eng.ball[1])
            near_line = min(y, WIDTH - y) < 12
            if near_line and eng.rng.random() < p.touchline_knock_out:
                direction = np.array([float(eng.rng.normal(0, 0.3)), -1.0 if y < MID_Y else 1.0])
                direction /= float(np.linalg.norm(direction))
            else:
                angle = float(eng.rng.normal(0, 1.0))
                direction = np.array([math.cos(angle) * eng.attack_dir[defending],
                                      math.sin(angle)])
            eng.ball_v = direction * float(eng.rng.uniform(4, 10))
            eng.last_touch = k
        return True
    eng.tackle_ready[k] = eng.t + p.beaten_recovery  # wrong-footed: needs a moment
    eng.emit("duel", defending, k, outcome="beaten", carrier=i, xa=round(tackler_x, 1),
             sliding=sliding, kind=kind)
    eng.vel[k] *= 0.2
    eng.commentate(team, f"{eng.players[i].player.short_name} skips past "
                         f"{eng.players[k].player.short_name}")
    if _counter_on(eng, i) and eng.rng.random() < p.tactical_foul_chance * (
            eng.a(k, "aggression") / 70) * (p.booked_caution if eng.yellows[k] else 1.0):
        commit_foul(eng, k, i, tactical=True)
        return True
    return False


def _counter_on(eng: "MatchEngine", i: int) -> bool:
    """Is carrier ``i`` running at a thin defence on a counter-attack?"""
    team = int(eng.team_of[i])
    poss = eng.possessions[-1] if eng.possessions else None
    if poss is None or poss.team != team or eng.t - poss.start_t > 12 or poss.start_x > LENGTH / 2:
        return False
    x, _ = eng.to_att(team, float(eng.pos[i, 0]), float(eng.pos[i, 1]))
    if not 35 < x < 80:
        return False
    keeper = eng.keeper(1 - team)
    goal_side = sum(1 for k in eng.team_indices(1 - team) if k != keeper
                    and eng.to_att(team, float(eng.pos[k, 0]), float(eng.pos[k, 1]))[0] > x)
    return goal_side <= 3


def commit_foul(eng: "MatchEngine", fouler: int, victim: int, *, sliding: bool = False,
                from_behind: bool = False, tactical: bool = False) -> None:
    p = eng.defs.duels
    team = int(eng.team_of[fouler])
    name = eng.players[fouler].player.name
    eng.stats[team].fouls += 1
    eng._announce("foul", team, f"Foul by {name}" + (", stopping the counter" if tactical else ""))
    pid = eng.players[fouler].player_id
    eng.player_fouls[pid] = eng.player_fouls.get(pid, 0) + 1
    aggressive = eng.a(fouler, "aggression") > 80
    if tactical:
        yellow, red = p.yellow.tactical, 0.0
    else:
        yellow = (p.yellow.base + p.yellow.sliding * sliding + p.yellow.aggressive * aggressive
                  + p.yellow.from_behind * from_behind)
        red = p.red.base + p.red.reckless * (sliding and aggressive)
    roll = eng.rng.random()
    card = "none"
    at = (float(eng.pos[victim, 0]), float(eng.pos[victim, 1]))
    if roll < red:
        card = "red"
        eng.send_off(fouler, "straight red")
    elif roll < red + yellow:
        card = "yellow"
        eng.yellows[fouler] += 1
        eng.lines[pid].yellow += 1
        eng.stats[team].yellow += 1
        eng.record_event("yellow", team, pid)
        eng.clock.ledger.add("card")
        eng._announce("yellow", team, f"Yellow card: {name}")
        if eng.yellows[fouler] >= 2:
            card = "second_yellow"
            eng.send_off(fouler, "second yellow")
    if eng.rng.random() < INJURY_IN_FOUL:
        injure(eng, victim)
    victim_team = 1 - team
    vx, vy = eng.to_att(victim_team, float(eng.pos[victim, 0]), float(eng.pos[victim, 1]))
    penalty = in_box(vx, vy)
    eng.emit("foul", team, fouler, at=at, victim=victim, card=card, penalty=penalty,
             tactical=tactical, xa=round(LENGTH - vx, 1))
    if penalty:
        spot = eng.to_pitch(victim_team, PENALTY_SPOT, MID_Y)
        eng._announce("penalty", victim_team, "PENALTY!")
        eng.clock.ledger.add("penalty")
        eng.award_restart("penalty", victim_team, spot)
    else:
        eng.award_restart("free_kick", victim_team, at)


def aerial_foul(eng: "MatchEngine", attacker: int, defender: int) -> None:
    """A contested header ends in a foul: usually the attacker pushing."""
    if eng.rng.random() < 0.7:
        commit_foul(eng, attacker, defender)
    else:
        commit_foul(eng, defender, attacker)


def injure(eng: "MatchEngine", i: int) -> None:
    kind = int(eng.rng.choice(len(INJURIES), p=np.array(INJURY_WEIGHTS) / sum(INJURY_WEIGHTS)))
    name, median, spread = INJURIES[kind]
    days = max(1, int(round(median * math.exp(eng.rng.normal(0, spread)))))
    team = int(eng.team_of[i])
    sp = eng.players[i]
    eng.injuries.append(Injury(sp.player_id, eng.sheets[team].club_id, days, name))
    eng.record_event("injury", team, sp.player_id, detail=name)
    eng.clock.ledger.add("injury")
    eng.emit("injury", team, i, days=days, name=name)
    eng._announce("injury", team, f"{sp.player.name} is injured ({name})")
    eng.stamina[i] = min(float(eng.stamina[i]), 0.2)  # the AI will take him off

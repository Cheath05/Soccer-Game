"""Match metrics for calibration and validation, read from the engine's event log.

``summarize`` turns one finished (or partly played) match into plain numbers: the usual
team statistics plus what explains them. That covers the possession funnel (won → final
third → box → shot → goal), duels, restarts and how long they took, where shots and goals
came from (open play, set pieces, fast breaks, rebounds), PPDA, distance run and time with
the ball in play. ``aggregate`` summarises many matches. Nothing here affects a match.
"""

import math
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING, Any

import numpy as np

from footsim.defs.positions import PositionGroup
from footsim.match.engine.log import EngineEvent, Possession
from footsim.match.engine.pitch import BOX_DEPTH, BOX_HALF, LENGTH, MID_Y

if TYPE_CHECKING:
    from footsim.match.engine.engine import MatchEngine

DT = 0.1
OPEN_PLAY_SOURCES = {"tackle", "interception", "loose", "save", "claim", "pass"}
SET_PIECE_WINDOW = 10.0  # s after a restart that a shot still counts as coming from it
FAST_BREAK_WINDOW = 15.0  # s from winning the ball in our own half to the shot
REBOUND_WINDOW = 5.0


def _zone(xa: float) -> str:
    return "def" if xa < 35 else "mid" if xa < 70 else "att"


def _in_box(xa: float, ya: float) -> bool:
    return xa >= LENGTH - BOX_DEPTH and abs(ya - MID_Y) <= BOX_HALF


def _possession_at(possessions: Sequence[Possession], t: float, team: int) -> Possession | None:
    for poss in reversed(possessions):
        if poss.start_t <= t + 1e-6:
            return poss if poss.team == team else None
    return None


def summarize(eng: "MatchEngine") -> dict[str, Any]:
    """Metrics for one match. Team-level values are lists indexed [home, away]."""
    log: list[EngineEvent] = eng.log
    possessions = eng.possessions
    teams: list[dict[str, Any]] = []
    for t in (0, 1):
        s = eng.stats[t]
        outfield = [float(eng.stamina[i]) for i in eng.team_indices(t)
                    if eng.group[i] is not PositionGroup.GK]
        teams.append({
            "goals": eng.score[t], "shots": s.shots, "shots_on_target": s.shots_on_target,
            "xg": float(s.xg), "passes": s.passes, "passes_completed": s.passes_completed,
            "corners": s.corners, "fouls": s.fouls, "offsides": s.offsides,
            "yellows": s.yellow, "reds": s.red,
            "distance_km": float(eng.distance[eng.team_of == t].sum()) / 1000,
            "end_stamina": float(np.mean(outfield)) if outfield else 0.0,
        })
    total_ticks = sum(eng.possession_ticks) or 1
    for t in (0, 1):
        teams[t]["possession"] = eng.possession_ticks[t] / total_ticks

    counts: dict[str, Counter[int]] = defaultdict(Counter)
    restarts: Counter[str] = Counter()
    waits: dict[str, list[float]] = defaultdict(list)
    corner_box: list[tuple[int, int]] = []
    pass_att: Counter[str] = Counter()
    pass_cmp: Counter[str] = Counter()
    zone_att: Counter[str] = Counter()
    zone_cmp: Counter[str] = Counter()
    defensive_actions_high: Counter[int] = Counter()  # PPDA denominator, per defending team
    passes_allowed_deep: Counter[int] = Counter()  # PPDA numerator, per passing team
    teleports = 0
    last_restart: dict[int, tuple[float, str]] = {}
    shots: list[dict[str, Any]] = []
    last_shot_t: dict[int, float] = {}
    pass_zone: dict[int, str] = {}  # passer index -> zone of his last pass

    for ev in log:
        team = ev.team
        d = ev.data
        if ev.kind == "pass":
            assert team is not None
            if d["kind"] != "clearance":
                pass_att[d["kind"]] += 1
                zone = _zone(d["xa"])
                zone_att[zone] += 1
                if ev.player is not None:
                    pass_zone[ev.player] = zone
                if d["xa"] < 63:
                    passes_allowed_deep[team] += 1
        elif ev.kind == "pass_result":
            assert team is not None
            if d["result"] == "complete":
                pass_cmp[d["kind"]] += 1
                if ev.player is not None and ev.player in pass_zone:
                    zone_cmp[pass_zone[ev.player]] += 1
            else:
                counts["interceptions"][1 - team] += 1
                if d.get("by_xa", 0.0) > 42:
                    defensive_actions_high[1 - team] += 1
        elif ev.kind == "duel":
            assert team is not None
            counts["duel_" + d["outcome"]][team] += 1
            if d["xa"] > 42:
                defensive_actions_high[team] += 1
        elif ev.kind == "foul":
            assert team is not None
            if d["xa"] > 42:
                defensive_actions_high[team] += 1
            if d["penalty"]:
                counts["penalties_conceded"][team] += 1
        elif ev.kind == "clearance":
            assert team is not None
            counts["clearances"][team] += 1
        elif ev.kind == "aerial":
            assert team is not None
            counts["aerials_won"][team] += 1
        elif ev.kind == "save":
            assert team is not None
            counts["saves"][team] += 1
            if d.get("teleported", 0.0) > 1.5:
                teleports += 1
        elif ev.kind == "block":
            assert team is not None
            counts["blocks"][team] += 1
        elif ev.kind == "restart":
            restarts[d["kind"]] += 1
        elif ev.kind == "restart_taken":
            assert team is not None
            waits[d["kind"]].append(d["wait"])
            teleports += int(d["teleported"])
            if d["kind"] == "corner":
                corner_box.append((d["box_attackers"], d["box_defenders"]))
            last_restart[team] = (ev.t, d["kind"])
        elif ev.kind == "shot":
            assert team is not None
            poss = _possession_at(possessions, ev.t, team)
            origin = "open_play"
            if d["penalty"]:
                origin = "penalty"
            elif d["free_kick"]:
                origin = "direct_free_kick"
            else:
                restart = last_restart.get(team)
                if restart is not None and ev.t - restart[0] <= SET_PIECE_WINDOW and (
                        poss is None or restart[0] >= poss.start_t - 0.5):
                    origin = "set_piece_" + restart[1]
                elif (poss is not None and poss.source in OPEN_PLAY_SOURCES
                      and poss.start_x < LENGTH / 2
                      and ev.t - poss.start_t <= FAST_BREAK_WINDOW):
                    origin = "fast_break"
            previous = last_shot_t.get(team)
            rebound = (previous is not None and ev.t - previous <= REBOUND_WINDOW
                       and poss is not None and poss.start_t <= previous)
            last_shot_t[team] = ev.t
            shots.append({
                "team": team, "t": ev.t, "xg": d["xg"], "outcome": d["outcome"],
                "header": d["header"], "distance": d["distance"],
                "inside_box": _in_box(d["xa"], d["ya"]), "goal_side": d["goal_side"],
                "nearest": d["nearest"], "origin": origin, "rebound": bool(rebound),
            })

    goals: list[dict[str, Any]] = []
    for ev in log:
        if ev.kind != "goal":
            continue
        assert ev.team is not None
        if ev.data["own_goal"]:
            kind = "own_goal"
        else:
            before = [s for s in shots if s["team"] == ev.team and s["t"] <= ev.t]
            shot = before[-1] if before else None
            if shot is None:
                kind = "unknown"
            elif shot["rebound"] and shot["origin"] == "open_play":
                kind = "rebound"
            else:
                kind = shot["origin"]
        goals.append({"team": ev.team, "t": ev.t, "type": kind})

    for t in (0, 1):
        mine = [p for p in possessions if p.team == t]
        opp = 1 - t
        row = teams[t]
        row["saves"] = counts["saves"][t]
        row["tackles_won"] = counts["duel_won"][t]
        row["tackles_beaten"] = counts["duel_beaten"][t]
        row["tackle_fouls"] = counts["duel_foul"][t]
        row["take_ons_won"] = counts["duel_beaten"][opp]
        row["take_ons"] = counts["duel_beaten"][opp] + counts["duel_won"][opp]
        row["interceptions"] = counts["interceptions"][t]
        row["clearances"] = counts["clearances"][t]
        row["blocks"] = counts["blocks"][t]
        row["aerials_won"] = counts["aerials_won"][t]
        row["penalties"] = counts["penalties_conceded"][opp]
        row["possessions"] = len(mine)
        row["final_third_entries"] = sum(p.final_third for p in mine)
        row["box_entries"] = sum(p.box for p in mine)
        # Opta's high turnover: open-play regain within 40 m of the opponent's goal.
        row["high_regains"] = sum(1 for p in mine if p.source in OPEN_PLAY_SOURCES
                                  and p.start_x >= LENGTH - 40)
        actions = defensive_actions_high[t]
        row["ppda"] = passes_allowed_deep[opp] / actions if actions else float("nan")
        row["fast_break_shots"] = sum(1 for s in shots if s["team"] == t
                                      and s["origin"] == "fast_break")

    return {
        "score": list(eng.score),
        "duration_min": eng.t / 60,
        "ball_in_play_min": eng.live_ticks * DT / 60,
        "teams": teams,
        "possessions": [{"team": p.team, "duration": (p.end_t or eng.t) - p.start_t,
                         "start_x": p.start_x, "source": p.source, "final_third": p.final_third,
                         "box": p.box, "passes": p.passes, "shots": p.shots}
                        for p in possessions],
        "shots": shots,
        "goals": goals,
        "restarts": dict(restarts),
        "restart_waits": {k: list(v) for k, v in waits.items()},
        "corner_box": corner_box,
        "passes_by_kind": {k: [pass_att[k], pass_cmp[k]] for k in pass_att},
        "passes_by_zone": {z: [zone_att[z], zone_cmp[z]] for z in zone_att},
        "teleports": teleports,
    }


# --- many matches ------------------------------------------------------------------------


def _mean(values: Iterable[float]) -> float:
    items = [v for v in values if not math.isnan(v)]
    return float(np.mean(items)) if items else float("nan")


def aggregate(matches: Sequence[dict[str, Any]]) -> dict[str, float]:
    """Per-match averages (both teams combined unless the name says per team) and rates."""
    n = len(matches)
    if n == 0:
        return {}

    def both(key: str) -> float:
        return _mean(float(m["teams"][0][key] + m["teams"][1][key]) for m in matches)

    def per_team(key: str) -> float:
        return _mean(float(m["teams"][t][key]) for m in matches for t in (0, 1))

    goals = [sum(m["score"]) for m in matches]
    margins = [abs(m["score"][0] - m["score"][1]) for m in matches]
    shots = [s for m in matches for s in m["shots"]]
    open_play = [s for s in shots if s["origin"] not in ("penalty", "direct_free_kick")]
    all_goals = [g for m in matches for g in m["goals"]]
    corners = [c for m in matches for c in m["corner_box"]]
    possessions = [p for m in matches for p in m["possessions"]]
    passes = sum(m["teams"][t]["passes"] for m in matches for t in (0, 1))
    completed = sum(m["teams"][t]["passes_completed"] for m in matches for t in (0, 1))
    on_target = sum(m["teams"][t]["shots_on_target"] for m in matches for t in (0, 1))
    saves = sum(m["teams"][t]["saves"] for m in matches for t in (0, 1))
    duels_won = sum(m["teams"][t]["tackles_won"] for m in matches for t in (0, 1))
    duels_beaten = sum(m["teams"][t]["tackles_beaten"] for m in matches for t in (0, 1))
    xg = sum(s["xg"] for s in shots)
    home_poss = [m["teams"][0]["possession"] for m in matches]
    waits: dict[str, list[float]] = defaultdict(list)
    restarts: Counter[str] = Counter()
    for m in matches:
        restarts.update(m["restarts"])
        for kind, values in m["restart_waits"].items():
            waits[kind].extend(values)
    goal_types = Counter(g["type"] for g in all_goals)
    result: dict[str, float] = {
        "matches": n,
        "goals": float(np.mean(goals)),
        "goals_sd": float(np.std(goals)),
        "home_win": _mean(float(m["score"][0] > m["score"][1]) for m in matches),
        "draw": _mean(float(m["score"][0] == m["score"][1]) for m in matches),
        "away_win": _mean(float(m["score"][0] < m["score"][1]) for m in matches),
        "nil_nil": _mean(float(g == 0) for g in goals),
        "six_plus_goals": _mean(float(g >= 6) for g in goals),
        "margin_4_plus": _mean(float(mg >= 4) for mg in margins),
        "shots": both("shots"),
        "shots_on_target": both("shots_on_target"),
        "xg": both("xg"),
        "conversion": sum(goals) / max(1, len(shots)),
        "xg_per_shot": xg / max(1, len(shots)),
        "shots_outside_box": _mean(float(not s["inside_box"]) for s in open_play),
        "shot_distance": _mean(s["distance"] for s in open_play),
        "headers": _mean(float(s["header"]) for s in open_play),
        "passes": both("passes"),
        "pass_accuracy": completed / max(1, passes),
        "corners": both("corners"),
        "fouls": both("fouls"),
        "offsides": both("offsides"),
        "yellows": both("yellows"),
        "reds": both("reds"),
        "penalties": both("penalties"),
        "saves": both("saves"),
        "save_rate": saves / on_target if on_target else float("nan"),
        "tackles": (duels_won + duels_beaten) / n,
        "tackles_won": duels_won / n,
        "take_ons": both("take_ons"),
        "take_on_success": duels_beaten / max(1, duels_won + duels_beaten),
        "interceptions": both("interceptions"),
        "clearances": both("clearances"),
        "throw_ins": restarts["throw_in"] / n,
        "goal_kicks": restarts["goal_kick"] / n,
        "free_kicks": restarts["free_kick"] / n,
        "ball_in_play_min": _mean(m["ball_in_play_min"] for m in matches),
        "duration_min": _mean(m["duration_min"] for m in matches),
        "possession_spread": _mean(abs(p - 0.5) for p in home_poss),
        "distance_km_per_team": per_team("distance_km"),
        "end_stamina": per_team("end_stamina"),
        "possessions_per_team": per_team("possessions"),
        "possession_seconds": _mean(p["duration"] for p in possessions),
        "passes_per_possession": _mean(p["passes"] for p in possessions),
        "final_third_entries_per_team": per_team("final_third_entries"),
        "box_entries_per_team": per_team("box_entries"),
        "shots_per_box_entry": sum(p["shots"] for p in possessions if p["box"])
        / max(1, sum(1 for p in possessions if p["box"])),
        "high_regains": both("high_regains"),
        "ppda": per_team("ppda"),
        "fast_break_shot_share": _mean(float(s["origin"] == "fast_break") for s in shots),
        "set_piece_goal_share": sum(v for k, v in goal_types.items()
                                    if k.startswith("set_piece") or k in (
                                        "penalty", "direct_free_kick"))
        / max(1, len(all_goals)),
        "fast_break_goal_share": goal_types["fast_break"] / max(1, len(all_goals)),
        "own_goal_share": goal_types["own_goal"] / max(1, len(all_goals)),
        "rebound_shot_share": _mean(float(s["rebound"]) for s in shots),
        "corner_attackers_in_box": _mean(float(a) for a, _ in corners),
        "corner_defenders_in_box": _mean(float(d) for _, d in corners),
        "corners_with_4_plus_attackers": _mean(float(a >= 4) for a, _ in corners),
        "teleports": _mean(float(m["teleports"]) for m in matches),
    }
    for kind in ("throw_in", "goal_kick", "corner", "free_kick", "kickoff", "penalty"):
        result[f"wait_{kind}"] = _mean(waits.get(kind, []))
    return result

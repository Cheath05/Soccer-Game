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
OPEN_PLAY_SOURCES = {"tackle", "interception", "recovery", "loose", "save", "claim", "pass"}
SET_PIECE_WINDOW = 10.0  # s after a restart that a shot still counts as coming from it
FAST_BREAK_WINDOW = 15.0  # s from winning the ball in our own half to the shot
REBOUND_WINDOW = 5.0
# Pass length bands in metres: short, medium, and long (Opta's long ball is 32 m or more).
# Crosses and throw-ins get bands of their own.
PASS_BANDS = (("short", 14.0), ("medium", 32.0))
BANDS = ("short", "medium", "long", "cross", "throw")
# Where a failed pass went: its first decisive event.
FAILURES = ("intercepted", "recovered", "loose", "offside", "aerial_lost", "foul",
            "out_throw_in", "out_goal_kick", "out_corner", "out_other")
REGATHER_WINDOW = 3.0  # s: a completed pass may be gathered this long after it stopped
# Volume metrics also reported per minute of ball in play (the calibration principles).
PER_BIP_MINUTE = ("goals", "shots", "shots_on_target", "xg", "passes", "corners", "fouls",
                  "yellows", "reds", "offsides", "penalties", "tackles", "interceptions",
                  "throw_ins", "goal_kicks", "high_regains")


def _zone(xa: float) -> str:
    return "def" if xa < 35 else "mid" if xa < 70 else "att"


def _in_box(xa: float, ya: float) -> bool:
    return xa >= LENGTH - BOX_DEPTH and abs(ya - MID_Y) <= BOX_HALF


def _possession_at(possessions: Sequence[Possession], t: float, team: int) -> Possession | None:
    for poss in reversed(possessions):
        if poss.start_t <= t + 1e-6:
            return poss if poss.team == team else None
    return None


def _band(kind: str, length: float, restart: str | None = None) -> str:
    if restart == "throw_in":  # long throws are played as crosses, but they're throw-ins
        return "throw"
    if kind in ("cross", "throw"):
        return kind
    for name, upper in PASS_BANDS:
        if length < upper:
            return name
    return "long"


def _pass_outcomes(log: Sequence[EngineEvent]) -> dict[str, Any]:
    """Pair every pass with its outcome, walking the log in order (one ball, so one pass at a
    time). Returns per band ``[attempts, completed, sum of the passers' estimates]``, the cause
    of each failure, travel times of completed passes, estimate-decile counts for a
    reliability table, heavy touches and who gathered them, and the kind of each offside."""
    bands = {b: [0, 0, 0.0] for b in BANDS}
    failures: Counter[str] = Counter()
    travel: dict[str, list[float]] = {b: [] for b in BANDS}
    deciles = {b: [[0, 0, 0.0] for _ in range(10)] for b in BANDS}
    heavy = [0, 0]  # heavy touches, and those the receiver gathered again himself
    offsides: Counter[str] = Counter()
    pending: dict[str, Any] | None = None
    last_heavy: tuple[int, float] | None = None

    def fail(cause: str) -> None:
        nonlocal pending
        if pending is not None:
            failures[cause] += 1
            pending = None

    for ev in log:
        d = ev.data
        if ev.kind == "pass":
            # A new pass means the previous one ended with nobody on its side claiming it.
            fail("loose")
            last_heavy = None
            if d["kind"] == "clearance":
                continue
            band = _band(d["kind"], d["length"], d.get("restart"))
            estimate = float(d["estimate"])
            decile = min(int(estimate * 10), 9)
            bands[band][0] += 1
            bands[band][2] += estimate
            deciles[band][decile][0] += 1
            deciles[band][decile][2] += estimate
            pending = {"passer": ev.player, "band": band, "decile": decile, "t": ev.t,
                       "heavy": False}
        elif ev.kind == "pass_result":
            if d["result"] == "complete":
                if last_heavy is not None and d.get("by") == last_heavy[0] \
                        and ev.t - last_heavy[1] <= REGATHER_WINDOW:
                    heavy[1] += 1
                last_heavy = None
            if pending is None or ev.player != pending["passer"]:
                continue
            if d["result"] == "complete":
                band = pending["band"]
                bands[band][1] += 1
                deciles[band][pending["decile"]][1] += 1
                if not pending["heavy"]:
                    travel[band].append(ev.t - pending["t"])
                pending = None
            else:
                fail(d["result"])
        elif ev.kind == "heavy_touch":
            heavy[0] += 1
            last_heavy = (ev.player, ev.t) if ev.player is not None else None
            if pending is not None:
                pending["heavy"] = True
        elif ev.kind in ("carry", "duel", "shot", "clearance"):
            # Someone owns the ball again, and the pass never reached a teammate: it was lost
            # as a loose ball (a completion would have been logged before any of these).
            fail("loose")
        elif ev.kind == "aerial" and d.get("won") != "attack":
            fail("aerial_lost")
        elif ev.kind == "offside":
            fail("offside")
            restart = d.get("restart")
            offsides["free_kick" if restart else "open_play"] += 1
            if d.get("pass_kind") == "through":
                offsides["through"] += 1
            if d.get("running"):
                offsides["runner"] += 1
        elif ev.kind == "foul":
            fail("foul")
        elif ev.kind == "restart":
            kind = d["kind"]
            fail("out_" + kind if kind in ("throw_in", "goal_kick", "corner") else "out_other")
    fail("loose")
    return {"bands": bands, "failures": dict(failures), "deciles": deciles,
            "travel": {b: [round(x, 1) for x in v] for b, v in travel.items()},
            "heavy_touches": heavy, "offsides": dict(offsides)}


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
            elif d["result"] == "intercepted":
                counts["interceptions"][1 - team] += 1
                if d.get("by_xa", 0.0) > 42:  # PPDA counts interceptions, not recoveries
                    defensive_actions_high[1 - team] += 1
            else:
                counts["recoveries"][1 - team] += 1
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
        row["recoveries"] = counts["recoveries"][t]
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
        "pass_outcomes": _pass_outcomes(log),
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
        "home_goal_diff": _mean(float(m["score"][0] - m["score"][1]) for m in matches),
        "away_card_gap": _mean(float(m["teams"][1]["yellows"] - m["teams"][0]["yellows"])
                               for m in matches),
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
        "recoveries": both("recoveries"),
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
    result.update(_pass_metrics(matches))
    result["possession_shot_share"] = _mean(float(p["shots"] > 0) for p in possessions)
    bip = result["ball_in_play_min"]
    for key in PER_BIP_MINUTE:
        result[f"{key}_per_bip_min"] = result[key] / bip if bip else float("nan")
    return result


def _pass_metrics(matches: Sequence[dict[str, Any]]) -> dict[str, float]:
    """Pass completion, share and estimate honesty by band; where failed passes went; travel
    times; heavy touches; offsides by kind. Shares are of all passes except throw-ins."""
    n = len(matches)
    outcomes = [m["pass_outcomes"] for m in matches]
    totals = {b: [sum(o["bands"][b][k] for o in outcomes) for k in range(3)] for b in BANDS}
    played = sum(totals[b][0] for b in BANDS if b != "throw")
    result: dict[str, float] = {}
    for b in BANDS:
        att, cmp_, est = totals[b]
        result[f"pass_acc_{b}"] = cmp_ / att if att else float("nan")
        result[f"estimate_gap_{b}"] = (est - cmp_) / att if att else float("nan")
        times = [x for o in outcomes for x in o["travel"][b]]
        result[f"pass_time_{b}"] = _mean(times)
    result["long_ball_share"] = totals["long"][0] / played if played else float("nan")
    result["cross_share"] = totals["cross"][0] / played if played else float("nan")
    for cause in FAILURES:
        result[f"pass_fail_{cause}"] = sum(o["failures"].get(cause, 0) for o in outcomes) / n
    heavy = sum(o["heavy_touches"][0] for o in outcomes)
    result["heavy_touches"] = heavy / n
    result["heavy_touch_self_regather"] = (sum(o["heavy_touches"][1] for o in outcomes) / heavy
                                           if heavy else float("nan"))
    for kind in ("open_play", "free_kick", "through", "runner"):
        result[f"offsides_{kind}"] = sum(o["offsides"].get(kind, 0) for o in outcomes) / n
    return result


def reliability(matches: Sequence[dict[str, Any]], min_passes: int = 30) -> list[dict[str, Any]]:
    """Completion against the passer's own estimate, by band and estimate decile: the check
    that estimates are honest. Deciles with fewer than ``min_passes`` passes are left out."""
    rows: list[dict[str, Any]] = []
    for b in BANDS:
        for decile in range(10):
            att = sum(m["pass_outcomes"]["deciles"][b][decile][0] for m in matches)
            if att < min_passes:
                continue
            cmp_ = sum(m["pass_outcomes"]["deciles"][b][decile][1] for m in matches)
            est = sum(m["pass_outcomes"]["deciles"][b][decile][2] for m in matches)
            rows.append({"band": b, "estimate": f"{decile / 10:.1f}-{(decile + 1) / 10:.1f}",
                         "passes": att, "mean_estimate": est / att, "completed": cmp_ / att,
                         "gap": (est - cmp_) / att})
    return rows

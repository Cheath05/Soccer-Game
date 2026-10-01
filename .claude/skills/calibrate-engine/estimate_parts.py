"""Which part of the honest pass estimate is off? (Step 2.3c's diagnostic.)

Plays synthetic matches with the estimate on, and puts each part's predicted failure next to
what happened to the passes actually played: interceptions (path), balls that never reach the
receiver (reach x arrive), and balls lost at the control (secure). Then the reliability table by
estimate decile, and breakdowns of medium and short passes.

Usage, from backend/ (cfg-dev = data/config with passing.yaml estimate.honest: true):
    FOOTSIM_CONFIG_DIR=/private/tmp/claude-502/cfg-dev uv run python \
        ../.claude/skills/calibrate-engine/estimate_parts.py [matches per quality] [qualities...]
Six matches at each of 62 and 78 take about two minutes."""
import sys
from collections import defaultdict

import numpy as np

from footsim.core.rng import derive_rng
from footsim.match.engine import actions
from footsim.match.engine.engine import MatchEngine
from footsim.match.engine.probe import _band
from footsim.match.synthetic import synthetic_sheet
from footsim.world.context import get_world

world = get_world()
assert world.defs.passing.estimate.honest, "needs estimate.honest: true (FOOTSIM_CONFIG_DIR)"
per = int(sys.argv[1]) if len(sys.argv) > 1 else 3
qualities = [float(q) for q in sys.argv[2:]] or [62.0, 78.0]

last: dict[int, tuple] = {}
records: dict[int, list] = defaultdict(list)
orig_parts, orig_start = actions._estimate_parts, actions.start_pass


def parts(eng, i, team, receivers, kinds, target, *args, **kwargs):
    p = orig_parts(eng, i, team, receivers, kinds, target, *args, **kwargs)
    last[id(eng)] = (i, list(receivers), list(kinds), target.copy(), p)
    return p


def start(eng, i, j, target, lofted, kind, pressure=0.0, estimate=1.0):
    rec = None
    got = last.get(id(eng))
    if got is not None and got[0] == i and kind != "clearance":
        _, recv, kinds, tgt, p = got
        for k, r in enumerate(recv):
            if r == j and abs(tgt[k, 0] - target[0]) < 1e-9 and abs(tgt[k, 1] - target[1]) < 1e-9:
                rec = {"path": float(p.path[k]), "reach": float(p.reach[k]),
                       "arrive": float(p.arrive[k]), "secure": float(p.secure[k]),
                       "est": float(estimate), "kind": kinds[k]}
                break
    records[id(eng)].append(rec)
    ball = eng.ball.copy()
    orig_start(eng, i, j, target, lofted, kind, pressure, estimate)
    info = eng.pass_info
    if rec is not None and info is not None and info.intended is not None:
        aim, meant = np.array(info.target) - ball, np.array(info.intended) - ball
        d_meant = float(np.hypot(*meant))
        rec["factor"] = float(np.hypot(*aim)) / max(d_meant, 1e-6)
        cross_ = abs(float(aim[0] * meant[1] - aim[1] * meant[0])) / max(d_meant, 1e-6)
        rec["side"] = cross_  # how far off line the aim passes the intended point
        rec["lofted"] = bool(lofted)
        team = int(eng.team_of[i])
        tx, _ = target
        bx, _ = eng.to_att(team, float(ball[0]), float(ball[1]))
        pace = eng.defs.passing.pace
        rec["back"] = bool(tx < pace.back_zone and tx < bx)
        rec["to_keeper"] = eng.group[j].value == "GK" if j >= 0 else False
        rec["length"] = float(np.hypot(*meant))
        opps = eng.team_indices(1 - team)
        rec["marker"] = float(np.min(np.hypot(*(eng.pos[opps] - np.array(info.intended)).T)))
        rec["press"] = float(pressure)


actions._estimate_parts, actions.start_pass = parts, start


def outcomes(log):
    """Each pass event's outcome, in log order (None for clearances), as probe._pass_outcomes."""
    out: list = []
    pending = None
    state = {"heavy": False, "passer": None}

    def fail(cause):
        nonlocal pending
        if pending is not None:
            out[pending] = ("heavy_lost" if cause == "loose" and state["heavy"] else cause)
            pending = None

    for ev in log:
        d = ev.data
        if ev.kind == "pass":
            fail("loose")
            out.append(None)
            if d["kind"] == "clearance":
                continue
            pending = len(out) - 1
            state.update(heavy=False, passer=ev.player, info=d)
            out[pending] = "?"
        elif ev.kind == "pass_result" and pending is not None and ev.player == state["passer"]:
            if d["result"] == "complete":
                out[pending] = "complete"
                pending = None
            else:
                fail(d["result"])
        elif ev.kind == "heavy_touch":
            state["heavy"] = True
        elif ev.kind in ("carry", "duel", "shot", "clearance"):
            fail("loose")
        elif ev.kind == "aerial" and d.get("won") != "attack":
            fail("aerial_lost")
        elif ev.kind == "offside":
            fail("offside")
        elif ev.kind == "foul":
            fail("foul")
        elif ev.kind == "restart":
            fail("out")
    fail("loose")
    return out


rows = defaultdict(list)
for q in qualities:
    for m in range(per):
        home = synthetic_sheet(world.defs, world.picker, 1, q, seed=m)
        away = synthetic_sheet(world.defs, world.picker, 2, q, formation="4-4-2", seed=m)
        eng = MatchEngine(world.defs, home, away, derive_rng(1000 + m, f"parts-{q}"))
        eng.run()
        passes = [ev for ev in eng.log if ev.kind == "pass"]
        recs = records.pop(id(eng))
        assert len(passes) == len(recs), (len(passes), len(recs))
        for ev, rec, res in zip(passes, recs, outcomes(eng.log), strict=True):
            if rec is None or res is None:
                continue
            band = _band(ev.data["kind"], ev.data["length"], ev.data.get("restart"))
            rows[band].append((rec, res))

print(f"{per} matches at each of {qualities}")
print(f"{'band':7s} {'n':>5s} {'est':>5s} {'done':>5s} | {'P(int)':>6s} {'int':>5s} | "
      f"{'P(miss)':>7s} {'miss':>5s} | {'P(lose)':>7s} {'lose':>5s} | other")
for band in ("short", "medium", "long", "cross", "throw"):
    data = rows.get(band, [])
    if not data:
        continue
    n = len(data)
    est = np.mean([r["est"] for r, _ in data])
    done = np.mean([o == "complete" for _, o in data])
    p_int = np.mean([1 - r["path"] for r, _ in data])
    p_miss = np.mean([r["path"] * (1 - r["reach"] * r["arrive"]) for r, _ in data])
    p_lose = np.mean([r["path"] * r["reach"] * r["arrive"] * (1 - r["secure"]) for r, _ in data])
    res = [o for _, o in data]
    share = lambda *keys: np.mean([o in keys for o in res])
    lose_keys = ("heavy_lost", "aerial_lost")
    miss_keys = ("recovered", "out", "loose")
    other = {k: round(float(np.mean([o == k for o in res])), 3)
             for k in ("offside", "foul", "?") if any(o == k for o in res)}
    print(f"{band:7s} {n:5d} {est:5.3f} {done:5.3f} | {p_int:6.3f} {share('intercepted'):5.3f} | "
          f"{p_miss:7.3f} {share(*miss_keys):5.3f} | {p_lose:7.3f} {share(*lose_keys):5.3f} | {other}")
    detail = {k: round(float(np.mean([o == k for o in res])), 3)
              for k in ("recovered", "out", "loose", "heavy_lost", "aerial_lost")}
    print(f"{'':7s} realised failures: {detail}")

print("\nground medium passes: completion by length factor (aim / intended)")
data = [(r, o) for r, o in rows.get("medium", []) if "factor" in r and not r["lofted"]]
for lo, hi in ((0.5, 0.7), (0.7, 0.85), (0.85, 1.0), (1.0, 1.15), (1.15, 1.3), (1.3, 1.61)):
    sel = [(r, o) for r, o in data if lo <= r["factor"] < hi]
    if sel:
        print(f"  {lo:.2f}-{hi:.2f}: n={len(sel):4d} share={len(sel)/len(data):.3f} "
              f"done={np.mean([o == 'complete' for _, o in sel]):.3f} "
              f"est={np.mean([r['est'] for r, _ in sel]):.3f}")
print("ground medium passes: completion by sideways miss (m)")
for lo, hi in ((0, 1), (1, 2), (2, 3), (3, 5), (5, 99)):
    sel = [(r, o) for r, o in data if lo <= r["side"] < hi]
    if sel:
        print(f"  {lo}-{hi} m: n={len(sel):4d} done={np.mean([o == 'complete' for _, o in sel]):.3f} "
              f"est={np.mean([r['est'] for r, _ in sel]):.3f}")

print("\nshort ground passes, by kind")
data = [(r, o) for r, o in rows.get("short", []) if "factor" in r and not r["lofted"]]
groups = {"back pass (soft)": lambda r: r["back"], "to the keeper": lambda r: r["to_keeper"],
          "other": lambda r: not r["back"] and not r["to_keeper"]}
for name, f in groups.items():
    sel = [(r, o) for r, o in data if f(r)]
    if sel:
        res = [o for _, o in sel]
        print(f"  {name:16s} n={len(sel):4d} est={np.mean([r['est'] for r, _ in sel]):.3f} "
              f"done={np.mean([o == 'complete' for o in res]):.3f} "
              f"loose={np.mean([o == 'loose' for o in res]):.3f} "
              f"int={np.mean([o == 'intercepted' for o in res]):.3f}")
print("short ground 'other' passes: loose share by marker distance at the target (m)")
sel = [(r, o) for r, o in data if not r["back"] and not r["to_keeper"]]
for lo, hi in ((0, 2), (2, 4), (4, 7), (7, 99)):
    part = [(r, o) for r, o in sel if lo <= r["marker"] < hi]
    if part:
        res = [o for _, o in part]
        print(f"  {lo}-{hi} m: n={len(part):4d} est={np.mean([r['est'] for r, _ in part]):.3f} "
              f"done={np.mean([o == 'complete' for o in res]):.3f} "
              f"loose={np.mean([o == 'loose' for o in res]):.3f} "
              f"heavy={np.mean([o == 'heavy_lost' for o in res]):.3f} "
              f"int={np.mean([o == 'intercepted' for o in res]):.3f}")
print("short ground 'other' passes: by pressure on the passer")
for lo, hi in ((0, 0.01), (0.01, 0.5), (0.5, 1.01)):
    part = [(r, o) for r, o in sel if lo <= r["press"] < hi]
    if part:
        res = [o for _, o in part]
        print(f"  {lo}-{hi}: n={len(part):4d} est={np.mean([r['est'] for r, _ in part]):.3f} "
              f"done={np.mean([o == 'complete' for o in res]):.3f} "
              f"loose={np.mean([o == 'loose' for o in res]):.3f}")

print("\nreliability: completion by estimate decile (n, mean estimate, completed)")
for band in ("short", "medium", "long", "cross", "throw"):
    data = rows.get(band, [])
    cells = []
    for d in range(10):
        part = [(r, o) for r, o in data if min(int(r["est"] * 10), 9) == d]
        if len(part) >= 30:
            cells.append(f"{d/10:.1f}:{len(part)} {np.mean([r['est'] for r, _ in part]):.2f}/"
                         f"{np.mean([o == 'complete' for _, o in part]):.2f}")
    print(f"  {band:6s} " + "  ".join(cells))

print("\nmedium passes by estimate decile: mean parts, and what actually happened")
data = rows.get("medium", [])
for d in (5, 6, 7, 8, 9):
    part = [(r, o) for r, o in data if min(int(r["est"] * 10), 9) == d]
    if len(part) < 20:
        continue
    res = [o for _, o in part]
    mean = lambda k: np.mean([r[k] for r, _ in part])
    print(f"  {d/10:.1f}: n={len(part):4d} path={mean('path'):.3f} reach={mean('reach'):.3f} "
          f"arrive={mean('arrive'):.3f} secure={mean('secure'):.3f} | done="
          f"{np.mean([o == 'complete' for o in res]):.3f} int={np.mean([o == 'intercepted' for o in res]):.3f} "
          f"miss={np.mean([o in ('recovered', 'out', 'loose') for o in res]):.3f} "
          f"lose={np.mean([o in ('heavy_lost', 'aerial_lost') for o in res]):.3f} "
          f"kinds={dict(__import__('collections').Counter(r['kind'] for r, _ in part))}")

print("\nmedium passes estimated 0.9+: never reaching him, by sideways miss and by length factor")
top = [(r, o) for r, o in rows.get("medium", []) if r["est"] >= 0.9 and "factor" in r]
for lo, hi in ((0, 1), (1, 2), (2, 3), (3, 5), (5, 99)):
    part = [(r, o) for r, o in top if lo <= r["side"] < hi]
    if part:
        res = [o for _, o in part]
        print(f"  side {lo}-{hi} m: n={len(part):5d} miss={np.mean([o in ('recovered', 'out', 'loose') for o in res]):.3f} "
              f"done={np.mean([o == 'complete' for o in res]):.3f}")
for lo, hi in ((0.5, 0.7), (0.7, 0.9), (0.9, 1.1), (1.1, 1.3), (1.3, 1.61)):
    part = [(r, o) for r, o in top if lo <= r["factor"] < hi]
    if part:
        res = [o for _, o in part]
        print(f"  factor {lo:.1f}-{hi:.1f}: n={len(part):5d} miss={np.mean([o in ('recovered', 'out', 'loose') for o in res]):.3f} "
              f"out={np.mean([o == 'out' for o in res]):.3f} done={np.mean([o == 'complete' for o in res]):.3f}")

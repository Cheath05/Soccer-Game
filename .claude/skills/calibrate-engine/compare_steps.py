"""Compare two measurement steps: reference batches (ENG4, ENG1) and sweep levels.
Usage: python compare_steps.py OLD NEW   (e.g. 2.3a 2.3b1)"""
import glob
import json
import sys

R = "/Users/alexbenton/Developer/Soccer-Game/reports/engine/step2.3"
old, new = sys.argv[1], sys.argv[2]


def load(pattern: str) -> dict | None:
    files = sorted(glob.glob(pattern))
    return json.load(open(files[-1])) if files else None


def cell(d: dict | None, k: str) -> str:
    if d is None or k not in d["aggregate"]:
        return "-"
    v, ci = d["aggregate"][k], d["ci95"].get(k)
    fmt = (lambda x: f"{x:.3f}") if abs(v) < 10 else (lambda x: f"{x:.1f}")
    return fmt(v) + (f" ±{fmt(ci)}" if ci is not None else "")


KEYS = ["goals", "goals_per_bip_min", "shots", "shots_per_bip_min", "xg", "pass_accuracy",
        "passes_per_bip_min", "interceptions", "throw_ins", "goal_kicks", "corners",
        "ball_in_play_min", "offsides", "fouls", "high_regains", "fast_break_shot_share",
        "pass_acc_short", "pass_acc_medium", "pass_acc_long", "pass_acc_cross", "long_ball_share",
        "estimate_gap_short", "estimate_gap_medium", "estimate_gap_long", "estimate_gap_cross",
        "pass_time_short", "pass_time_medium", "pass_time_long", "heavy_touches",
        "heavy_touch_self_regather", "pass_fail_intercepted", "pass_fail_loose",
        "pass_fail_out_throw_in", "pass_fail_aerial_lost", "possession_shot_share"]
for div in ("ENG4", "ENG1"):
    a = load(f"{R}/ref-{old}/*-{div}-n200.json")
    b = load(f"{R}/ref-{new}/*-{div}-n200.json")
    print(f"\n## {div}: {old} → {new}\n| Metric | {old} | {new} |\n|---|---|---|")
    for k in KEYS:
        print(f"| {k} | {cell(a, k)} | {cell(b, k)} |")
SWEEP = ["pass_accuracy", "pass_acc_short", "pass_acc_medium", "pass_acc_long", "long_ball_share",
         "heavy_touch_self_regather", "pass_fail_loose", "interceptions", "goals", "shots", "fouls",
         "high_regains"]
print(f"\n## Sweep: {old} → {new}\n| Metric | q58 {old} | q58 {new} | q82 {old} | q82 {new} |")
print("|---|---|---|---|---|")
lv = {(s, q): load(f"{R}/sweep-{s}-q{q}/*.json") for s in (old, new) for q in (58, 82)}
for k in SWEEP:
    print(f"| {k} | {cell(lv[(old, 58)], k)} | {cell(lv[(new, 58)], k)} | {cell(lv[(old, 82)], k)} "
          f"| {cell(lv[(new, 82)], k)} |")

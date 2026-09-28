"""Command-line tools: `uv run footsim --help`."""

import argparse
import json
import sys
from pathlib import Path

from footsim.core.paths import config_dir, data_dir


def _default(path: str) -> Path:
    return data_dir() / path


def _calibrate_overall(args: argparse.Namespace) -> int:
    from footsim.calibration.overall import fit_overall_scaling, write_scaling
    from footsim.defs.loader import load_definitions
    from footsim.importers.csv_source import read_players
    from footsim.importers.derive import complete_attributes
    from footsim.importers.profile import load_profile

    defs = load_definitions()
    profile = load_profile(args.profile)
    players = read_players(args.ea_csv, profile)
    for p in players:
        p.attrs = complete_attributes(p, profile, args.seed)
    fits = fit_overall_scaling(defs, players)
    write_scaling(args.out, fits, reference=f"{profile.source} overall_rating")
    print(f"{'group':6} {'n':>6} {'scale':>7} {'offset':>8} {'r2':>6} {'mae':>5}")
    for f in fits:
        print(f"{f.group.value:6} {f.players:6d} {f.scale:7.3f} {f.offset:8.2f} {f.r2:6.3f} "
              f"{f.mae:5.2f}")
    print(f"wrote {args.out}")
    return 0


def _build_world(args: argparse.Namespace) -> int:
    from footsim.defs.loader import load_definitions
    from footsim.importers.build_world import build_world
    from footsim.importers.profile import load_profile
    from footsim.importers.transfermarkt import load_players
    from footsim.ratings.overall import load_overall_scaling

    if args.out.exists():
        if not args.force:
            print(f"{args.out} exists; pass --force to rebuild", file=sys.stderr)
            return 1
        args.out.unlink()
    defs = load_definitions()
    tm_players = None
    if not args.no_tm and args.tm_db.exists():
        tm_players = load_players(args.tm_db)
    elif not args.no_tm:
        print(f"note: {args.tm_db} not found, building without Transfermarkt data")
    report = build_world(
        ea_csv=args.ea_csv,
        profile=load_profile(args.profile),
        defs=defs,
        out_path=args.out,
        calendar_key=args.calendar,
        seed=args.seed,
        tm_players=tm_players,
        scaling=load_overall_scaling(config_dir() / "calibration" / "overall_scaling.yaml"),
    )
    report_path = _default("reports") / f"world-build-{report.season}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))

    print(f"{report.players} players, {report.clubs} clubs, {report.nations} nations")
    print(f"Transfermarkt: {report.tm_matched} matched, {report.tm_ambiguous} ambiguous, "
          f"{report.tm_unmatched} unmatched")
    print(f"{'league':40} {'clubs':>5} {'players':>7} {'TM%':>5} {'ovr':>6} {'src':>6}")
    for league, s in report.leagues.items():
        pct = 100 * s.tm_matched / s.players
        print(f"{league:40} {s.clubs:5d} {s.players:7d} {pct:5.0f} {s.mean_overall:6.1f} "
              f"{s.mean_source_overall:6.1f}")
    for warning in report.warnings:
        print(f"warning: {warning}")
    print(f"wrote {args.out} and {report_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="footsim")
    sub = parser.add_subparsers(dest="command", required=True)

    ea_csv = _default("raw/ea_fc27/players.csv")
    profile = _default("import_profiles/ea_fc_ratings_v1.yaml")

    cal = sub.add_parser("calibrate-overall", help="fit overall scaling to the ratings source")
    cal.add_argument("--ea-csv", type=Path, default=ea_csv)
    cal.add_argument("--profile", type=Path, default=profile)
    cal.add_argument("--seed", type=int, default=2026)
    cal.add_argument("--out", type=Path,
                     default=config_dir() / "calibration" / "overall_scaling.yaml")
    cal.set_defaults(func=_calibrate_overall)

    build = sub.add_parser("build-world", help="build the base-world database")
    build.add_argument("--ea-csv", type=Path, default=ea_csv)
    build.add_argument("--profile", type=Path, default=profile)
    build.add_argument("--tm-db", type=Path,
                       default=_default("raw/transfermarkt/transfermarkt-datasets.duckdb"))
    build.add_argument("--no-tm", action="store_true", help="skip Transfermarkt enrichment")
    build.add_argument("--calendar", default="ENG-2026-27")
    build.add_argument("--seed", type=int, default=2026)
    build.add_argument("--out", type=Path, default=_default("worlds/base-2026-27.sqlite"))
    build.add_argument("--force", action="store_true", help="overwrite an existing world")
    build.set_defaults(func=_build_world)

    args = parser.parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())

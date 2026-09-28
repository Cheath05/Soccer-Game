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


def _sim_season(args: argparse.Namespace) -> int:
    import shutil
    import tempfile
    import time

    from sqlalchemy import select, text

    from footsim.persistence.database import open_database
    from footsim.persistence.schema import competition, league_final
    from footsim.world.career import advance, initialize_career
    from footsim.world.context import get_world
    from footsim.world.squads import club_name

    world = get_world()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "sim.sqlite"
        shutil.copy(args.world, path)
        engine = open_database(path)
        with engine.begin() as conn:
            initialize_career(conn, world, None, None)
        for number in range(1, args.seasons + 1):
            started = time.perf_counter()
            with engine.begin() as conn:
                result = advance(conn, world, max_days=400)
            elapsed = time.perf_counter() - started
            with engine.connect() as conn:
                season_id = number
                stats = conn.execute(text("""
                    SELECT COUNT(*) n, AVG(home_goals + away_goals) goals,
                           AVG(home_goals > away_goals) home, AVG(home_goals = away_goals) draw,
                           AVG(home_goals + away_goals = 0) nil, MAX(home_goals + away_goals) most
                    FROM fixture WHERE season_id = :s AND stage = 'league'
                """), {"s": season_id}).one()
                print(f"\n=== Season {season_id}: {stats.n} league matches in {elapsed:.1f}s "
                      f"({result.stop}) ===")
                print(f"goals/match {stats.goals:.2f}  home {100 * stats.home:.0f}%  "
                      f"draw {100 * stats.draw:.0f}%  0-0 {100 * stats.nil:.1f}%  "
                      f"max goals {stats.most}")
                for comp in conn.execute(select(competition).order_by(competition.c.tier)):
                    rows = conn.execute(select(league_final).where(
                        league_final.c.season_id == season_id,
                        league_final.c.competition_id == comp.id,
                    ).order_by(league_final.c.position)).all()
                    if not rows:
                        continue
                    print(f"-- {comp.name}")
                    for r in rows:
                        if r.position <= 3 or r.position >= len(rows) - 2 or r.outcome:
                            print(f"  {r.position:2d}. {club_name(conn, r.club_id):28} "
                                  f"{r.points:3d} pts  {r.goals_for:3d}-{r.goals_against:<3d} "
                                  f"{r.outcome or ''}")
                for message in result.messages:
                    print(f"  * {message}")
        engine.dispose()
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

    sim = sub.add_parser("sim-season", help="simulate whole seasons without a user club")
    sim.add_argument("--world", type=Path, default=_default("worlds/base-2026-27.sqlite"))
    sim.add_argument("--seasons", type=int, default=1)
    sim.set_defaults(func=_sim_season)

    args = parser.parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())

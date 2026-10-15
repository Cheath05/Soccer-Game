"""`footsim europe-report`: the European competitions measured (W6 E8).

It runs a watch-only career from a copy of the base world, with the European competitions on,
through whole seasons, and reports for each competition and season:
- who won, and how strong the last four were (reputation, league-phase place, coefficient rank);
- goals per match and home / draw / away in the league phase and the knockouts;
- how often the strongest clubs went deep;
- the prize money paid;
- the room around European matches (gaps of one clear day, never fewer);
- the top club coefficients at the end.

Read against real football approximately (these are context, not targets: one engine for every
competition): Champions League league-phase matches have had a little over 3 goals a game, and
its last four are usually clubs from the top few of the pre-season coefficient ranking.
"""

import shutil
import statistics
import tempfile
import time
from collections import Counter, defaultdict
from dataclasses import replace
from datetime import date
from pathlib import Path

from sqlalchemy import Connection, text

from footsim.persistence.database import open_database
from footsim.persistence.migrations import migrate
from footsim.world.career import advance, initialize_career
from footsim.world.context import World
from footsim.world.cups import REST_DAYS
from footsim.world.europe.common import KNOCKOUT, competitions_by_rank
from footsim.world.finance import ledger_mismatches
from footsim.world.meta import read_meta


def _pct(part: float, whole: float) -> str:
    return f"{100 * part / whole:.0f}%" if whole else "-"


def _season_report(conn: Connection, world: World, season_id: int) -> list[str]:
    lines: list[str] = []
    names: dict[int, str] = {r.id: r.name for r in conn.execute(text("SELECT id, name FROM club"))}
    reputation: dict[int, int] = {r.id: r.reputation for r in conn.execute(
        text("SELECT id, reputation FROM club"))}
    for comp in competitions_by_rank(world):
        comp_id = conn.execute(text("SELECT id FROM competition WHERE key = :k"),
                               {"k": comp.key}).scalar()
        if comp_id is None:
            continue
        entries = conn.execute(text(
            "SELECT club_id, position, route FROM continental_entry "
            "WHERE season_id = :s AND competition_id = :c"), {"s": season_id, "c": comp_id}).all()
        if not entries:
            continue
        by_rep = sorted((e.club_id for e in entries), key=lambda c: -reputation[c])
        rep_rank = {c: k + 1 for k, c in enumerate(by_rep)}
        games = conn.execute(text(
            "SELECT round, home_goals, away_goals, home_pens FROM fixture "
            "WHERE season_id = :s AND stage = :k AND status = 'played'"),
            {"s": season_id, "k": comp.key}).all()
        lines.append(f"\n## {comp.name}, season {season_id}")
        for label, rows in (("league phase", [g for g in games if 1 <= g.round < KNOCKOUT]),
                            ("knockouts", [g for g in games if g.round >= KNOCKOUT])):
            if not rows:
                continue
            goals = [g.home_goals + g.away_goals for g in rows]
            home = sum(g.home_goals > g.away_goals for g in rows)
            draw = sum(g.home_goals == g.away_goals for g in rows)
            lines.append(f"- {label}: {len(rows)} matches, {statistics.mean(goals):.2f} goals a "
                         f"match; home {_pct(home, len(rows))}, draw {_pct(draw, len(rows))}, "
                         f"away {_pct(len(rows) - home - draw, len(rows))}")
        ties = conn.execute(text(
            "SELECT round, club_a_id, club_b_id, winner_club_id FROM cup_tie "
            "WHERE season_id = :s AND competition_id = :c AND round >= :k ORDER BY round"),
            {"s": season_id, "c": comp_id, "k": KNOCKOUT}).all()
        final_round = KNOCKOUT + len(comp.knockout) - 1
        semis = [c for t in ties if t.round == final_round - 1 for c in (t.club_a_id, t.club_b_id)]
        final = [t for t in ties if t.round == final_round and t.winner_club_id]
        position = {e.club_id: e.position for e in entries}
        if final:
            w = final[0].winner_club_id
            lines.append(f"- winner: {names[w]} (reputation {reputation[w]}, "
                         f"#{rep_rank[w]} of {len(entries)} by reputation, "
                         f"{position.get(w)} in the league phase)")
        if semis:
            lines.append("- last four: " + ", ".join(
                f"{names[c]} (rep #{rep_rank[c]}, LP {position.get(c)})" for c in semis))
            top8 = set(by_rep[:8])
            last16 = {c for t in ties if t.round == KNOCKOUT + 1
                      for c in (t.club_a_id, t.club_b_id)}
            lines.append(f"- of the 8 strongest by reputation, {len(top8 & set(semis))} in the "
                         f"last four, {len(top8 & last16)} in the last 16")
        prize = conn.execute(text(
            "SELECT SUM(amount_cents), MAX(total) FROM (SELECT club_id, SUM(amount_cents) "
            "AS amount_cents, SUM(amount_cents) AS total FROM finance_ledger WHERE kind = "
            "'prize' AND ref_id = :c AND season_id = :s GROUP BY club_id)"),
            {"c": comp_id, "s": season_id}).one()
        if prize[0]:
            lines.append(f"- prize money: €{prize[0] / 1e8:.0f}M in all, "
                         f"at most €{prize[1] / 1e8:.1f}M to one club")
    return lines


def _room(conn: Connection, world: World, season_id: int) -> str:
    rows = conn.execute(text(
        "SELECT date, stage, home_club_id, away_club_id FROM fixture WHERE season_id = :s"),
        {"s": season_id}).all()
    days: dict[int, list[tuple[date, bool]]] = defaultdict(list)
    for r in rows:
        for c in (r.home_club_id, r.away_club_id):
            days[c].append((date.fromisoformat(r.date), r.stage in world.defs.continental))
    gaps: Counter[int] = Counter()
    for games in days.values():
        games.sort()
        for (d1, e1), (d2, e2) in zip(games, games[1:], strict=False):
            if e1 or e2:
                gaps[min((d2 - d1).days - 1, REST_DAYS + 1)] += 1
    total = sum(gaps.values())
    return ("- room around European matches (clear days): "
            + ", ".join(f"{k if k <= REST_DAYS else f'{REST_DAYS + 1}+'}: {gaps[k]} "
                        f"({_pct(gaps[k], total)})" for k in sorted(gaps)))


def europe_report(world_path: Path, world: World, seed: int, seasons: int) -> str:
    world = replace(world, defs=replace(world.defs, europe=world.defs.europe.model_copy(
        update={"enabled": True})))
    started = time.perf_counter()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "career.sqlite"
        shutil.copy(world_path, path)
        engine = open_database(path)
        migrate(engine)
        with engine.begin() as conn:
            initialize_career(conn, world, None, None, seed=seed)
        lines = [f"# European competitions: {seasons} season(s), seed {seed}"]
        for _ in range(seasons):
            with engine.connect() as conn:
                season_id = read_meta(conn).season_id
            while True:
                with engine.begin() as conn:
                    advance(conn, world, max_days=60)
                    if read_meta(conn).season_id != season_id:
                        break
            with engine.connect() as conn:
                lines += _season_report(conn, world, season_id)
                lines.append(_room(conn, world, season_id))
        with engine.connect() as conn:
            top = conn.execute(text(
                "SELECT c.name, SUM(k.points) AS p FROM club_coefficient k JOIN club c "
                "ON c.id = k.club_id GROUP BY k.club_id ORDER BY p DESC LIMIT 10")).all()
            lines.append("\n## Coefficient points earned in the game, top 10")
            lines += [f"- {r.name}: {r.p:.0f}" for r in top]
            mismatches = ledger_mismatches(conn)
            lines.append(f"\nLedger: {'balances match' if not mismatches else mismatches[:5]}")
        engine.dispose()
    lines.append(f"\n({time.perf_counter() - started:.0f} s)")
    return "\n".join(lines)

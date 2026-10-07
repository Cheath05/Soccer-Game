"""`footsim market-report`: the AI transfer market measured (W4-5).

It runs a watch-only career from a copy of the base world, by default through the first summer
window, and reports:
- what moved, by league;
- the top deals;
- who moved (age, overall);
- whether any squad ran short;
- budgets and balances, free agents, and the market's total value.

The approximate real targets it's read against are in docs/plans/w3-w4-finances-transfers.md
("The AI market").
"""

import shutil
import statistics
import tempfile
import time
from collections import defaultdict
from datetime import date
from pathlib import Path

from sqlalchemy import Connection, text

from footsim.persistence.database import open_database
from footsim.persistence.migrations import migrate
from footsim.world.career import advance, initialize_career
from footsim.world.context import World
from footsim.world.finance import club_leagues, ledger_mismatches
from footsim.world.meta import read_meta
from footsim.world.transfers import fee_text, player_values

CHUNK_DAYS = 7  # days simulated per transaction


def _eur(cents: float) -> str:
    return fee_text(int(cents)) if cents >= 0 else "-" + fee_text(int(-cents))


def _squads(conn: Connection, season: int) -> dict[str, list[tuple[int, int, int]]]:
    """Each league's clubs: (club, seniors, keepers)."""
    leagues = club_leagues(conn, season)
    rows = conn.execute(text(
        "SELECT k.club_id, COUNT(*) AS seniors, SUM((SELECT position FROM player_position pp "
        "  WHERE pp.player_id = k.person_id ORDER BY familiarity DESC, position LIMIT 1) = 'GK') "
        "  AS keepers FROM contract k WHERE k.is_active = 1 AND k.kind = 'player' "
        "GROUP BY k.club_id")).all()
    result: dict[str, list[tuple[int, int, int]]] = defaultdict(list)
    for r in rows:
        key = leagues[r.club_id][0] if r.club_id in leagues else "(outside)"
        result[key].append((int(r.club_id), int(r.seniors), int(r.keepers or 0)))
    return result


def _money(conn: Connection, season: int) -> dict[str, tuple[float, float]]:
    """Each league's mean balance and budget (euros)."""
    leagues = club_leagues(conn, season)
    by: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for r in conn.execute(text(
            "SELECT club_id, balance_cents, transfer_budget_cents FROM club_finance")):
        key = leagues[r.club_id][0] if r.club_id in leagues else "(outside)"
        by[key].append((int(r.balance_cents), int(r.transfer_budget_cents)))
    return {k: (statistics.mean(b for b, _ in v) / 100, statistics.mean(t for _, t in v) / 100)
            for k, v in by.items()}


def market_report(base_world: Path, world: World, seed: int, until: date) -> str:
    lines: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "career.sqlite"
        shutil.copy(base_world, path)
        engine = open_database(path)
        migrate(engine)
        with engine.begin() as conn:
            initialize_career(conn, world, None, None, seed=seed)
        with engine.connect() as conn:
            start = read_meta(conn)
            free_before: int = conn.execute(text(
                "SELECT COUNT(*) FROM player p WHERE retired_on IS NULL AND NOT EXISTS ("
                "SELECT 1 FROM contract k WHERE k.person_id = p.person_id AND k.is_active = 1)"
            )).scalar_one()
            value_before = sum(player_values(conn, world, start.current_date).values())
            money_before = _money(conn, start.season_id)
            squads_before = _squads(conn, start.season_id)
        began = time.perf_counter()
        while True:
            with engine.begin() as conn:
                day = read_meta(conn).current_date
                if day >= until:
                    break
                result = advance(conn, world, max_days=min(CHUNK_DAYS, (until - day).days))
            if result.stop == "season_end":
                break
        elapsed = time.perf_counter() - began
        with engine.connect() as conn:
            meta = read_meta(conn)
            lines += _report(conn, world, start.current_date, meta.current_date, start.season_id,
                             free_before, value_before, money_before, squads_before, elapsed)
        engine.dispose()
    return "\n".join(lines)


def _report(conn: Connection, world: World, first: date, last: date, season: int,
            free_before: int, value_before: int,
            money_before: dict[str, tuple[float, float]],
            squads_before: dict[str, list[tuple[int, int, int]]], elapsed: float) -> list[str]:
    leagues = club_leagues(conn, season)
    tiers = {k: (world.defs.leagues[k].nation, world.defs.leagues[k].tier)
             for k in world.defs.leagues}

    def league(club: int | None) -> str:
        if club is None:
            return "(free)"
        return leagues[club][0] if club in leagues else "(outside)"

    deals = conn.execute(text(
        "SELECT t.*, pe.first_name, pe.last_name, pe.known_as, pe.birth_date, "
        "b.name AS buyer, s.name AS seller FROM transfer t JOIN person pe ON pe.id = t.player_id "
        "LEFT JOIN club b ON b.id = t.to_club_id LEFT JOIN club s ON s.id = t.from_club_id "
        "ORDER BY t.id")).all()
    moves = [d for d in deals if d.kind in ("transfer", "free")]
    lines = [f"Market report: {first} to {last}, simulated in {elapsed:.0f} s.",
             f"Deals: {len(moves)} ({sum(d.kind == 'transfer' for d in moves)} transfers, "
             f"{sum(d.kind == 'free' for d in moves)} free agents), "
             f"{sum(d.kind == 'release' for d in deals)} releases; "
             f"fees {_eur(sum(d.fee_cents for d in moves))}."]
    by_league: dict[str, list[object]] = defaultdict(list)
    spent: dict[str, int] = defaultdict(int)
    received: dict[str, int] = defaultdict(int)
    signings: dict[int, int] = defaultdict(int)
    for d in moves:
        by_league[league(d.to_club_id)].append(d)
        spent[league(d.to_club_id)] += d.fee_cents
        received[league(d.from_club_id)] += d.fee_cents
        signings[d.to_club_id] += 1
    squads = _squads(conn, season)
    lines.append("\nBy buying league: deals, fees, net spend, clubs signing anyone, signings per "
                 "club (mean / max):")
    order = sorted(by_league | {k: [] for k in squads},
                   key=lambda k: tiers.get(k, ("ZZZ", 9)))
    for key in order:
        clubs = [c for c, _, _ in squads.get(key, [])]
        counts = [signings.get(c, 0) for c in clubs]
        busy = sum(1 for n in counts if n) / len(counts) if counts else 0.0
        lines.append(
            f"  {key:10s} {len(by_league.get(key, [])):4d} deals, fees {_eur(spent[key]):>8s}, "
            f"net {_eur(spent[key] - received[key]):>8s}, {busy:4.0%} signing, "
            f"{statistics.mean(counts) if counts else 0:.1f} / {max(counts) if counts else 0}")
    lines.append("\nTop deals:")
    from footsim.world.squads import display_name

    for d in sorted(moves, key=lambda d: -d.fee_cents)[:15]:
        age = (date.fromisoformat(d.date) - date.fromisoformat(d.birth_date)).days // 365
        lines.append(f"  {display_name(d.first_name, d.last_name, d.known_as):24s} {age:2d} "
                     f"{d.seller or '(free)':>24s} -> {d.buyer:24s} {_eur(d.fee_cents):>8s} "
                     f"{_eur(d.wage_weekly_cents)}/wk")
    ages = [(date.fromisoformat(d.date) - date.fromisoformat(d.birth_date)).days / 365.25
            for d in moves]
    if ages:
        q = statistics.quantiles(ages, n=4)
        lines.append(f"\nMovers' ages: quartiles {q[0]:.1f} / {q[1]:.1f} / {q[2]:.1f}")
    fee_bands = [(0, "free"), (1, "<1M"), (100_000_000, "1-10M"), (1_000_000_000, "10-50M"),
                 (5_000_000_000, "50M+")]
    band_counts: dict[str, int] = defaultdict(int)
    for d in moves:
        name = "free"
        for floor, label in fee_bands:
            if d.fee_cents >= floor:
                name = label
        band_counts[name] += 1
    lines.append("Fees: " + ", ".join(f"{label} {band_counts[label]}" for _, label in fee_bands))
    lines.append("\nSquads before -> after (seniors min / median / max; clubs under 16 "
                 "seniors; clubs under 2 keepers):")
    for key in order:
        rows = squads.get(key, [])
        if not rows:
            continue
        sizes = [s for _, s, _ in rows]
        short = sum(1 for s in sizes if s < 16)
        few_keepers = sum(1 for _, _, g in rows if g < 2)
        old = squads_before.get(key, [])
        old_sizes = [s for _, s, _ in old] or [0]
        lines.append(f"  {key:10s} {min(old_sizes):3d} / {statistics.median(old_sizes):5.1f} / "
                     f"{max(old_sizes):3d} -> {min(sizes):3d} / {statistics.median(sizes):5.1f} / "
                     f"{max(sizes):3d}   {sum(1 for s in old_sizes if s < 16)} -> {short} short, "
                     f"{sum(1 for _, _, g in old if g < 2)} -> {few_keepers} without 2 keepers")
    money_after = _money(conn, season)
    lines.append("\nMean balance and budget, before -> after:")
    for key in order:
        if key in money_before and key in money_after:
            (b0, t0), (b1, t1) = money_before[key], money_after[key]
            lines.append(f"  {key:10s} balance {_eur(b0 * 100):>8s} -> {_eur(b1 * 100):>8s}; "
                         f"budget {_eur(t0 * 100):>8s} -> {_eur(t1 * 100):>8s}")
    free_after: int = conn.execute(text(
        "SELECT COUNT(*) FROM player p WHERE retired_on IS NULL AND NOT EXISTS ("
        "SELECT 1 FROM contract k WHERE k.person_id = p.person_id AND k.is_active = 1)"
    )).scalar_one()
    value_after = sum(player_values(conn, world, last).values())
    lines.append(f"\nFree agents {free_before} -> {free_after}; the market's total value "
                 f"{_eur(value_before * 100)} -> {_eur(value_after * 100)}.")
    owners: int = conn.execute(text(
        "SELECT COUNT(*) FROM (SELECT person_id FROM contract WHERE is_active = 1 "
        "AND kind != 'loan' GROUP BY person_id HAVING COUNT(*) > 1)")).scalar_one()
    lines.append(f"Checks: players with two owners {owners}; "
                 f"clubs whose balance isn't their ledger {len(ledger_mismatches(conn))}.")
    return lines

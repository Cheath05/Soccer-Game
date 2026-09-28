"""Builds a base-world database from a ratings source plus optional Transfermarkt enrichment.

Ratings source (EA FC CSV): squads, attributes, positions, PlayStyles. Covers every tier we
simulate, as of the ratings snapshot.
Transfermarkt (CC0 snapshot): heights, birthplaces, contract expiries, market values, for
players it can be matched to (mostly top-division players).
world_build.yaml: potential, personality, contracts and wages nobody publishes.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import Any

import numpy as np
from sqlalchemy import Engine

from footsim.defs.loader import GameDefinitions
from footsim.domain.attributes import ATTRIBUTES
from footsim.importers.csv_source import read_players
from footsim.importers.derive import complete_attributes, traits_for
from footsim.importers.generate import (
    age_on,
    club_reputation,
    draw_personality,
    draw_potential,
    estimate_height,
    estimate_weight,
    generated_contract_end,
    player_reputation,
    weekly_wage_cents,
)
from footsim.importers.profile import ImportProfile
from footsim.importers.records import SourcePlayer, TmPlayer
from footsim.importers.resolve import MatchResult, match_players
from footsim.importers.rng import entity_rng
from footsim.persistence import schema as t
from footsim.persistence.database import create_database, write_meta
from footsim.ratings.overall import OverallScaling, RatingModel

NATURAL = 20
ALTERNATE = 15
TM_SOURCE = "transfermarkt"


class BuildError(Exception):
    pass


@dataclass
class LeagueStats:
    clubs: int = 0
    players: int = 0
    tm_matched: int = 0
    mean_overall: float = 0.0
    mean_source_overall: float = 0.0


@dataclass
class BuildReport:
    season: str
    seed: int
    players: int = 0
    clubs: int = 0
    nations: int = 0
    tm_matched: int = 0
    tm_ambiguous: int = 0
    tm_unmatched: int = 0
    leagues: dict[str, LeagueStats] = field(default_factory=dict)
    unmatched_examples: dict[str, list[str]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = dict(self.__dict__)
        data["leagues"] = {k: v.__dict__ for k, v in self.leagues.items()}
        return data


def build_world(
    *,
    ea_csv: Path,
    profile: ImportProfile,
    defs: GameDefinitions,
    out_path: Path,
    calendar_key: str,
    seed: int,
    tm_players: list[TmPlayer] | None = None,
    scaling: OverallScaling | None = None,
    strict: bool = True,
) -> BuildReport:
    calendar = defs.calendars[calendar_key]
    season_start = calendar.season_start
    report = BuildReport(season=calendar.season, seed=seed)

    players = read_players(ea_csv, profile)
    if not players:
        raise BuildError(f"{ea_csv} produced no players")
    for p in players:
        p.attrs = complete_attributes(p, profile, seed)

    model = RatingModel.build(defs, scaling)
    matrix = np.array([[p.attrs[a] for a in ATTRIBUTES] for p in players], dtype=np.float64)
    group_overalls = model.group_overalls(matrix)
    overall = {
        p.source_id: float(group_overalls[defs.positions[p.position].group][i])
        for i, p in enumerate(players)
    }

    aliases = {n.name: set(n.aliases) for n in defs.nations.values()}
    match = match_players(players, tm_players or [], aliases) if tm_players else MatchResult()
    report.tm_matched = len(match.matches)
    report.tm_ambiguous = len(match.ambiguous)
    report.tm_unmatched = len(match.unmatched)

    engine = create_database(out_path)
    try:
        _write_world(engine, defs, profile, players, overall, match, calendar_key, seed, report,
                     strict)
    except Exception:
        engine.dispose()
        out_path.unlink(missing_ok=True)
        raise
    write_meta(
        engine,
        {
            "world_seed": seed,
            "season": calendar.season,
            "calendar": calendar_key,
            "game_date": season_start.isoformat(),
            "sources": {
                "ratings": {"file": ea_csv.name, "profile": profile.key, "players": len(players)},
                "transfermarkt": {"players": len(tm_players or []), "matched": report.tm_matched},
            },
            "overall_scaling_applied": bool(scaling and scaling.groups),
        },
    )
    engine.dispose()
    return report


def _write_world(
    engine: Engine,
    defs: GameDefinitions,
    profile: ImportProfile,
    players: list[SourcePlayer],
    overall: dict[str, float],
    match: MatchResult,
    calendar_key: str,
    seed: int,
    report: BuildReport,
    strict: bool,
) -> None:
    calendar = defs.calendars[calendar_key]
    season_start = calendar.season_start
    rules = defs.world_build
    by_name = {n.name: n for n in defs.nations.values()}

    # Nations: every nationality and club country we saw, plus nations leagues refer to.
    nation_names = sorted(
        {p.nationality for p in players}
        | set(profile.league_nations.values())
        | {defs.nations[lg.nation].name for lg in defs.leagues.values()}
    )
    nation_id = {name: i for i, name in enumerate(nation_names, start=1)}
    nation_rows = [
        {"id": i, "name": name, "code": by_name[name].code if name in by_name else None}
        for name, i in nation_id.items()
    ]
    report.nations = len(nation_rows)

    # Clubs, keyed by (league, club) as a club name can repeat across leagues.
    club_keys = sorted({(p.league, p.club) for p in players})
    club_id = {key: i for i, key in enumerate(club_keys, start=1)}
    squad: dict[tuple[str, str], list[SourcePlayer]] = defaultdict(list)
    for p in players:
        squad[(p.league, p.club)].append(p)
    club_rep = {
        key: club_reputation([overall[p.source_id] for p in squad[key]], rules.reputation)
        for key in club_keys
    }
    club_rows = [
        {
            "id": club_id[key],
            "name": key[1],
            "nation_id": nation_id.get(profile.league_nations.get(key[0], "")),
            "source_league": key[0],
            "reputation": club_rep[key],
            "stadium_name": None,
            "stadium_capacity": None,
        }
        for key in club_keys
    ]
    report.clubs = len(club_rows)

    competition_id = {key: i for i, key in enumerate(sorted(defs.leagues), start=1)}
    competition_rows = [
        {
            "id": competition_id[key],
            "key": key,
            "name": lg.name,
            "short_name": lg.short_name,
            "nation_id": nation_id[defs.nations[lg.nation].name],
            "type": "league",
            "tier": lg.tier,
            "sim_level": lg.sim_level.value,
        }
        for key, lg in sorted(defs.leagues.items())
    ]
    season_row = {
        "id": 1,
        "label": calendar.season,
        "start_date": calendar.season_start.isoformat(),
        "end_date": calendar.season_end.isoformat(),
    }
    membership_rows = []
    league_clubs: dict[str, int] = defaultdict(int)
    for league, club in club_keys:
        comp = profile.leagues.get(league)
        if comp in competition_id:
            membership_rows.append(
                {"club_id": club_id[(league, club)], "season_id": 1,
                 "competition_id": competition_id[comp]}
            )
            league_clubs[comp] += 1
    for key, lg in defs.leagues.items():
        if league_clubs[key] != lg.clubs:
            message = f"{key} expects {lg.clubs} clubs, source has {league_clubs[key]}"
            if strict:
                raise BuildError(message)
            report.warnings.append(message)

    Rows = list[dict[str, Any]]
    person_rows: Rows = []
    player_rows: Rows = []
    attr_rows: Rows = []
    position_rows: Rows = []
    personality_rows: Rows = []
    trait_rows: Rows = []
    contract_rows: Rows = []
    external_rows: Rows = []
    stats: dict[str, LeagueStats] = defaultdict(LeagueStats)
    unmatched = set(match.unmatched) | set(match.ambiguous)

    for pid, p in enumerate(players, start=1):
        tm = match.matches.get(p.source_id)
        ovr = overall[p.source_id]
        age = age_on(p.birth_date, season_start)
        home = (p.league, p.club)

        rng = partial(entity_rng, seed, p.source, p.source_id)

        height = p.height_cm or (tm.height_cm if tm else None)
        if height is None:
            height = estimate_height(p.position, p.attrs, rules.physique, rng("height"))
        weight = p.weight_kg or estimate_weight(height, p.attrs, rules.physique, rng("weight"))

        person_rows.append({
            "id": pid,
            "first_name": p.first_name,
            "last_name": p.last_name,
            "known_as": p.known_as,
            "birth_date": p.birth_date.isoformat(),
            "nation_id": nation_id[p.nationality],
            "birth_city": tm.city_of_birth if tm else None,
        })
        player_rows.append({
            "person_id": pid,
            "height_cm": height,
            "weight_kg": weight,
            "preferred_foot": p.preferred_foot,
            "weak_foot": p.weak_foot,
            "skill_moves": p.skill_moves,
            "pa_hidden": draw_potential(ovr, age, rules.potential, rng("potential")),
            "reputation": player_reputation(ovr, club_rep[home], rules.reputation),
            "value_eur_cents": tm.market_value_eur * 100 if tm and tm.market_value_eur else None,
        })
        attr_rows.append({"player_id": pid, **p.attrs})

        familiarity = {p.position: NATURAL}
        for alt in p.alt_positions:
            familiarity.setdefault(alt, ALTERNATE)
        for adj in defs.adjacency:
            if adj.from_ == p.position and familiarity.get(adj.to, 0) < adj.familiarity:
                familiarity[adj.to] = adj.familiarity
        position_rows.extend(
            {"player_id": pid, "position": pos, "familiarity": fam}
            for pos, fam in sorted(familiarity.items())
        )

        personality_rows.append(
            {"player_id": pid, **draw_personality(ovr, rules.personality, rng("personality"))}
        )
        trait_rows.extend({"player_id": pid, "trait": tr} for tr in traits_for(p, profile))

        if tm and tm.contract_expiry and tm.contract_expiry > season_start:
            end = tm.contract_expiry
        else:
            end = generated_contract_end(age, season_start, rules.contracts, rng("contract"))
        wage_level = defs.wage_levels.for_league(p.league)
        contract_rows.append({
            "id": pid,
            "person_id": pid,
            "club_id": club_id[home],
            "kind": "player",
            "start_date": season_start.isoformat(),  # real join dates aren't in the sources
            "end_date": end.isoformat(),
            "wage_weekly_cents": weekly_wage_cents(
                ovr, wage_level, defs.wage_levels.minimum_weekly_wage, rng("wage")
            ),
            "release_clause_cents": None,
            "is_active": 1,
        })

        external_rows.append({"entity_type": "player", "entity_id": pid, "source": p.source,
                              "source_id": p.source_id})
        if tm:
            external_rows.append({"entity_type": "player", "entity_id": pid,
                                  "source": TM_SOURCE, "source_id": str(tm.tm_id)})

        league_stats = stats[p.league]
        league_stats.players += 1
        league_stats.tm_matched += tm is not None
        league_stats.mean_overall += ovr
        league_stats.mean_source_overall += p.source_overall or 0
        if p.source_id in unmatched:
            examples = report.unmatched_examples.setdefault(p.league, [])
            if len(examples) < 10:
                examples.append(f"{p.display_name} ({p.club}, {p.birth_date})")

    for league, league_stats in stats.items():
        league_stats.clubs = sum(1 for lg, _ in club_keys if lg == league)
        league_stats.mean_overall = round(league_stats.mean_overall / league_stats.players, 2)
        league_stats.mean_source_overall = round(
            league_stats.mean_source_overall / league_stats.players, 2
        )
    report.leagues = dict(sorted(stats.items(), key=lambda kv: -kv[1].mean_source_overall))
    report.players = len(player_rows)

    external_rows.extend(
        {"entity_type": "club", "entity_id": club_id[key], "source": profile.source,
         "source_id": f"{key[0]}|{key[1]}"}
        for key in club_keys
    )

    with engine.begin() as conn:
        for table, rows in (
            (t.nation, nation_rows),
            (t.season, [season_row]),
            (t.competition, competition_rows),
            (t.club, club_rows),
            (t.club_league_membership, membership_rows),
            (t.person, person_rows),
            (t.player, player_rows),
            (t.player_attr, attr_rows),
            (t.player_position, position_rows),
            (t.player_personality, personality_rows),
            (t.player_trait, trait_rows),
            (t.contract, contract_rows),
            (t.external_id, external_rows),
        ):
            if rows:
                conn.execute(table.insert(), rows)

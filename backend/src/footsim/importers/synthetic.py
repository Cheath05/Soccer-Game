"""Squads for the top divisions FC 27 doesn't cover (W7 A6, docs/plans/w7-all-of-uefa.md).

The clubs are in data/config/world/new_clubs.yaml. Each club's squad comes from the best source
that has it:
- FC 27 itself, for the few clubs it has in these countries (`ea_league`): left as they are.
- Transfermarkt's whole 2025-26 squads, for the leagues it covers (`tm_league`): real names, birth
  dates, positions, heights, feet and contracts. A player's overall comes from his market value,
  age and position, by a model fitted on the thousands of players in both FC 27 and Transfermarkt.
- The real players Transfermarkt has for a small country's club that played in Europe in 2025-26
  (its qualifying lineups), topped up with generated players.
- Generated players for the rest: names drawn from the country's real first names and surnames,
  ages from a typical squad's, and attributes copied from an FC 27 player of the same position and
  a similar level, shifted to the level wanted.

A league's level (the mean of its clubs' best-sixteen overalls) comes from its country's UEFA
coefficient: a line in log(coefficient) fitted on the leagues FC 27 covers whole. Within a league,
clubs differ by their Elo ratings, worked out from every game Transfermarkt has since 2012 (31
leagues and all UEFA rounds), at FC 27's own slope of level per Elo point; a club with too few
games is put below the league's clubs that have played in Europe, by last season's table. Real
players keep the order their market values give them, the club's level setting how high they
are. Everything is deterministic for the world seed."""

import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from footsim.core.paths import config_dir
from footsim.defs.loader import GameDefinitions
from footsim.defs.world_build import EloRules, GeneratedAgeRules, NewLeagueRules
from footsim.importers.records import SourcePlayer, TmPlayer
from footsim.importers.resolve import MatchResult
from footsim.importers.rng import entity_rng

SOURCE = "footsim"  # generated players
TM_SQUAD = "transfermarkt-squad"  # players taken from Transfermarkt's squads
TM_POSITIONS = {
    "Goalkeeper": "GK", "Centre-Back": "CB", "Left-Back": "LB", "Right-Back": "RB",
    "Defensive Midfield": "DM", "Central Midfield": "CM", "Attacking Midfield": "AM",
    "Left Midfield": "LM", "Right Midfield": "RM", "Left Winger": "LW", "Right Winger": "RW",
    "Centre-Forward": "ST", "Second Striker": "ST"}
TM_BROAD = {"Goalkeeper": "GK", "Defender": "CB", "Midfield": "CM", "Attack": "ST"}


@dataclass(frozen=True)
class NewLeague:
    key: str  # its competition (GRE1)
    nation: str  # its nation code
    clubs: list[str]  # in last season's order, the promoted last
    ea_league: str | None = None
    tm_league: str | None = None
    ea_names: dict[str, str] = field(default_factory=dict)  # our name -> FC 27's
    # our name -> Transfermarkt's (its formal name, say), or None: no Transfermarkt club is it
    tm_names: dict[str, str | None] = field(default_factory=dict)


@dataclass
class SyntheticReport:
    clubs: int = 0
    from_ea: int = 0
    tm_players: int = 0
    generated: int = 0
    league_levels: dict[str, float] = field(default_factory=dict)
    clubs_by_source: Counter[str] = field(default_factory=Counter)
    value_model: list[float] = field(default_factory=list)
    elo_model: list[float] = field(default_factory=list)  # league a, b (ln coefficient); slope
    unmatched_ea: list[str] = field(default_factory=list)


def load_new_leagues(root: Path | None = None) -> list[NewLeague]:
    path = (root or config_dir()) / "world" / "new_clubs.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [NewLeague(key=k, nation=v["nation"], clubs=list(v["clubs"]),
                      ea_league=v.get("ea_league"), tm_league=v.get("tm_league"),
                      ea_names=dict(v.get("ea_names") or {}),
                      tm_names=dict(v.get("tm_names") or {}))
            for k, v in raw["leagues"].items()]


def ea_pairs(league: NewLeague, ea_clubs: list[str]) -> dict[str, str]:
    """Our clubs that FC 27 has, one to one (our name -> FC 27's): by `ea_names`, then the same
    name, then a name contained in only one of ours."""
    pairs = {ours: theirs for ours, theirs in league.ea_names.items() if theirs in ea_clubs}
    for theirs in ea_clubs:
        if theirs in pairs.values():
            continue
        exact = [c for c in league.clubs if c not in pairs and norm(c) == norm(theirs)]
        loose = [c for c in league.clubs if c not in pairs and same_club(c, theirs)]
        found = exact if len(exact) == 1 else loose if len(loose) == 1 else []
        if found:
            pairs[found[0]] = theirs
    return pairs


def norm(name: str) -> str:
    """A club name for matching across sources: no accents, case, punctuation or the usual
    prefixes (FC, FK, NK...)."""
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    words = re.sub(r"[^a-z0-9 ]", " ", text).split()
    stop = {"fc", "fk", "nk", "sk", "sc", "cf", "ac", "afc", "kf", "fcm", "pfc", "hnk", "gnk",
            "rnk", "mfk", "ofk", "bk", "if", "ks", "club", "the", "football", "futbol"}
    kept = [w for w in words if w not in stop]
    return " ".join(kept or words)


def same_club(a: str, b: str) -> bool:
    """The same club by name: the same words, or one name the start of the other ("Valur" and
    "Valur Reykjavik"; not "Gorica" and "Mladost Donja Gorica")."""
    x, y = norm(a), norm(b)
    return bool(x and y) and (x == y or f"{y} ".startswith(f"{x} ")
                              or f"{x} ".startswith(f"{y} "))


# --- models fitted on FC 27 -----------------------------------------------------------------------

def fit_value_model(players: list[SourcePlayer], match: MatchResult, season: date) -> np.ndarray:
    """Overall from a Transfermarkt market value: overall = b0 + b1 * log10(value) + b2 * (age -
    26) + b3 * (age - 26)^2 + b4 * goalkeeper, fitted on the players in both sources."""
    rows, ys = [], []
    for p in players:
        tm = match.matches.get(p.source_id)
        if tm is None or not tm.market_value_eur or p.source_overall is None:
            continue
        age = (season - p.birth_date).days / 365.25 - 26
        rows.append([1.0, np.log10(tm.market_value_eur), age, age * age,
                     1.0 if p.position == "GK" else 0.0])
        ys.append(float(p.source_overall))
    coef, *_ = np.linalg.lstsq(np.array(rows), np.array(ys), rcond=None)
    return np.asarray(coef, dtype=float)


def value_overall(coef: np.ndarray, value: int | None, birth: date, gk: bool,
                  season: date) -> float | None:
    if not value:
        return None
    age = (season - birth).days / 365.25 - 26
    return float(coef @ np.array([1.0, np.log10(value), age, age * age, 1.0 if gk else 0.0]))


@dataclass
class EloTable:
    rating: dict[int, float]
    games: dict[int, int]
    names: dict[int, str]  # each Transfermarkt club's latest name
    # the countries whose domestic games each club has played (none for a club seen only in
    # UEFA's rounds, as most small countries' clubs are)
    countries: dict[int, set[str]] = field(default_factory=dict)

    def find(self, name: str, country: str | None = None) -> int | None:
        """The Transfermarkt club of that name, if exactly one matches; given a country, never a
        club known to play somewhere else (Arsenal Dzerzhinsk is not Arsenal)."""
        hits = [cid for cid, n in self.names.items() if same_club(n, name)
                and (country is None or not self.countries.get(cid)
                     or country in self.countries[cid])]
        return hits[0] if len(hits) == 1 else None

    def named(self, name: str) -> int | None:
        """The Transfermarkt club of exactly that name, if only one has it."""
        hits = [cid for cid, n in self.names.items() if n == name]
        return hits[0] if len(hits) == 1 else None


def club_elo(tm_db: Path, rules: EloRules) -> EloTable:
    """An Elo rating for every club in Transfermarkt's games since ``rules.since``, in date
    order, World Football Elo's way: a bigger step for a bigger win."""
    import duckdb

    con = duckdb.connect(str(tm_db), read_only=True)
    try:
        games = con.execute(
            "SELECT home_club_id, away_club_id, home_club_name, away_club_name, "
            "home_club_goals, away_club_goals FROM games WHERE home_club_goals IS NOT NULL "
            "AND date >= ? ORDER BY date, game_id", [rules.since]).fetchall()
        domestic = con.execute(
            "SELECT DISTINCT club_id, country_name FROM (SELECT g.home_club_id AS club_id, "
            "c.country_name FROM games g JOIN competitions c ON c.competition_id = "
            "g.competition_id WHERE c.type IN ('domestic_league', 'domestic_cup') UNION ALL "
            "SELECT g.away_club_id, c.country_name FROM games g JOIN competitions c ON "
            "c.competition_id = g.competition_id WHERE c.type IN ('domestic_league', "
            "'domestic_cup')) WHERE club_id IS NOT NULL AND country_name IS NOT NULL "
            "ORDER BY club_id, country_name").fetchall()
    finally:
        con.close()
    countries: dict[int, set[str]] = defaultdict(set)
    for club_id, country in domestic:
        countries[int(club_id)].add(str(country))
    rating: dict[int, float] = defaultdict(lambda: rules.start)
    count: dict[int, int] = defaultdict(int)
    names: dict[int, str] = {}
    for h, a, hn, an, hg, ag in games:
        if h is None or a is None:
            continue
        names[h], names[a] = hn or names.get(h, ""), an or names.get(a, "")
        expected = 1 / (1 + 10 ** ((rating[a] - rating[h] - rules.home) / rules.scale))
        score = 1.0 if hg > ag else 0.5 if hg == ag else 0.0
        margin = abs(hg - ag)
        step = 1.0 if margin <= 1 else 1.5 if margin == 2 else (11 + margin) / 8
        delta = rules.k * step * (score - expected)
        rating[h] += delta
        rating[a] -= delta
        count[h] += 1
        count[a] += 1
    return EloTable(dict(rating), dict(count), names, dict(countries))


def _club_tm_ids(players: list[SourcePlayer], match: MatchResult, elo: EloTable,
                 rules: NewLeagueRules) -> dict[tuple[str, str], tuple[int, float]]:
    """Each FC 27 club's Transfermarkt club (through its players' current club, with enough
    games for an Elo) and its level (the mean of its best ``level_players``)."""
    top = rules.level_players
    by_club: dict[tuple[str, str], list[SourcePlayer]] = defaultdict(list)
    for p in players:
        by_club[(p.league, p.club)].append(p)
    out = {}
    for key, squad in by_club.items():
        clubs = Counter(match.matches[p.source_id].club_name for p in squad
                        if p.source_id in match.matches and match.matches[p.source_id].club_name)
        overalls = sorted((p.source_overall or 0 for p in squad), reverse=True)[:top]
        if not clubs or len(overalls) < top:
            continue
        tm_id = elo.find(str(clubs.most_common(1)[0][0]))
        if tm_id is not None and elo.games.get(tm_id, 0) >= rules.elo.fc27_min_games:
            out[key] = (tm_id, float(np.mean(overalls)))
    return out


def fit_league_model(players: list[SourcePlayer], defs: GameDefinitions) -> np.ndarray:
    """A league's level from its country's five-season UEFA coefficient: level = a + b *
    ln(coefficient), fitted on the top leagues FC 27 covers whole (ten clubs or more)."""
    seasons = sorted(defs.association_coefficients.seasons)[-defs.europe.coefficient.seasons:]
    total = {code: sum(defs.association_coefficients.seasons[s].get(code, 0.0) for s in seasons)
             for code in defs.association_coefficients.seasons[seasons[-1]]}
    nation_of = {source: lg.nation for lg in defs.leagues.values() if lg.tier == 1
                 for source in lg.source_leagues}
    levels: dict[str, list[float]] = defaultdict(list)
    by_club: dict[tuple[str, str], list[int]] = defaultdict(list)
    for p in players:
        if p.league in nation_of and p.source_overall:
            by_club[(p.league, p.club)].append(p.source_overall)
    for (league, _), overalls in by_club.items():
        top = defs.world_build.new_leagues.level_players
        if len(overalls) >= top:
            levels[league].append(float(np.mean(sorted(overalls, reverse=True)[:top])))
    xs, ys = [], []
    for league, values in levels.items():
        code = nation_of[league]
        if len(values) >= 10 and total.get(code):
            xs.append(np.log(total[code]))
            ys.append(float(np.mean(values)))
    b, a = np.polyfit(np.array(xs), np.array(ys), 1)
    return np.array([a, b])


def fit_elo_slope(players: list[SourcePlayer], match: MatchResult, elo: EloTable,
                  rules: NewLeagueRules) -> float:
    """Level per Elo point within a league, fitted on FC 27's clubs (each league's clubs taken
    from their league's mean)."""
    rows: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for (league, _), (tm_id, level) in _club_tm_ids(players, match, elo, rules).items():
        rows[league].append((elo.rating[tm_id], level))
    xs, ys = [], []
    for values in rows.values():
        if len(values) < 3:
            continue
        mean_elo = np.mean([v[0] for v in values])
        mean_level = np.mean([v[1] for v in values])
        xs += [v[0] - mean_elo for v in values]
        ys += [v[1] - mean_level for v in values]
    return float(np.polyfit(np.array(xs), np.array(ys), 1)[0])


# --- generating players ---------------------------------------------------------------------------

class Templates:
    """FC 27 players by position, to copy attributes from."""

    def __init__(self, players: list[SourcePlayer], pool: int) -> None:
        self.pool = pool  # a player's template: one of the this many nearest his overall
        self.by_position: dict[str, list[SourcePlayer]] = defaultdict(list)
        for p in players:
            if p.source_overall:
                self.by_position[p.position].append(p)
        for group in self.by_position.values():
            group.sort(key=lambda p: p.source_overall or 0)

    def pick(self, position: str, overall: float, rng: np.random.Generator) -> SourcePlayer:
        group = self.by_position.get(position) or self.by_position["CM"]
        keys = np.array([p.source_overall or 0 for p in group], dtype=float)
        nearest = np.argsort(np.abs(keys - overall), kind="stable")[:self.pool]
        return group[int(nearest[rng.integers(len(nearest))])]


class Names:
    """Real first names and surnames by nationality, from FC 27 and Transfermarkt."""

    def __init__(self, players: list[SourcePlayer], tm_players: list[TmPlayer],
                 aliases: dict[str, str]) -> None:
        self.first: dict[str, list[str]] = defaultdict(list)
        self.last: dict[str, list[str]] = defaultdict(list)
        for p in players:
            if p.first_name and p.last_name:
                self.first[p.nationality].append(p.first_name)
                self.last[p.nationality].append(p.last_name)
        for t in tm_players:
            nation = aliases.get(t.citizenship or "", t.citizenship or "")
            if t.first_name and t.last_name:
                self.first[nation].append(t.first_name)
                self.last[nation].append(t.last_name)

    def draw(self, nation: str, rng: np.random.Generator) -> tuple[str, str]:
        first = self.first.get(nation) or self.first["England"]
        last = self.last.get(nation) or self.last["England"]
        return first[rng.integers(len(first))], last[rng.integers(len(last))]


def _shifted(template: SourcePlayer, overall: float) -> dict[str, int]:
    shift = overall - (template.source_overall or overall)
    return {a: int(min(99, max(1, round(v + shift)))) for a, v in template.attrs.items()}


def _generated_player(source_id: str, league: str, club: str, position: str, overall: float,
                      nation: str, templates: Templates, names: Names,
                      season: date, age_rules: GeneratedAgeRules,
                      rng: np.random.Generator) -> SourcePlayer:
    template = templates.pick(position, overall, rng)
    first, last = names.draw(nation, rng)
    age = float(np.clip(rng.normal(age_rules.mean, age_rules.sd), age_rules.min, age_rules.max))
    birth = season - timedelta(days=int(age * 365.25) + int(rng.integers(0, 365)))
    return SourcePlayer(
        source=SOURCE, source_id=source_id, first_name=first, last_name=last, known_as=None,
        birth_date=birth, nationality=nation, club=club, league=league, position=position,
        alt_positions=list(template.alt_positions), preferred_foot=template.preferred_foot,
        weak_foot=template.weak_foot, skill_moves=template.skill_moves, height_cm=None,
        weight_kg=None, source_overall=round(overall), playstyles=[],
        attrs=_shifted(template, overall))


def _tm_player(t: TmPlayer, league: str, club: str, overall: float, nation: str,
               templates: Templates, rng: np.random.Generator) -> SourcePlayer:
    position = TM_POSITIONS.get(t.sub_position or "") or TM_BROAD.get(t.position or "", "CM")
    template = templates.pick(position, overall, rng)
    first = t.first_name or (t.name.split(" ")[0] if " " in t.name else "")
    last = t.last_name or t.name
    foot = {"left": "left", "right": "right", "both": "right"}.get((t.foot or "").lower(),
                                                                   template.preferred_foot)
    return SourcePlayer(
        source=TM_SQUAD, source_id=f"tm:{t.tm_id}", first_name=first, last_name=last,
        known_as=None if t.first_name else t.name, birth_date=t.birth_date, nationality=nation,
        club=club, league=league, position=position, alt_positions=list(template.alt_positions),
        preferred_foot=foot, weak_foot=template.weak_foot, skill_moves=template.skill_moves,
        height_cm=t.height_cm, weight_kg=None, source_overall=round(overall), playstyles=[],
        attrs=_shifted(template, overall))


@dataclass
class TmSquads:
    """Transfermarkt's current squads: each club's players, its league's clubs."""

    players_by_club: dict[int, list[int]]  # club id -> player ids (last season 2025 or later)
    league_clubs: dict[str, dict[int, str]]  # domestic league -> club id -> name


def tm_squads(tm_db: Path) -> TmSquads:
    import duckdb

    con = duckdb.connect(str(tm_db), read_only=True)
    try:
        rows = con.execute("SELECT player_id, current_club_id FROM players "
                           "WHERE last_season >= '2025' AND current_club_id IS NOT NULL "
                           "ORDER BY player_id").fetchall()
        clubs = con.execute("SELECT club_id, name, domestic_competition_id FROM clubs "
                            "ORDER BY club_id").fetchall()
    finally:
        con.close()
    by_club: dict[int, list[int]] = defaultdict(list)
    for pid, cid in rows:
        by_club[int(cid)].append(int(pid))
    league_clubs: dict[str, dict[int, str]] = defaultdict(dict)
    for cid, name, comp in clubs:
        if comp:
            league_clubs[comp][int(cid)] = name or ""
    return TmSquads(dict(by_club), dict(league_clubs))


def synthesize(players: list[SourcePlayer], match: MatchResult, tm_players: list[TmPlayer],
               tm_db: Path, defs: GameDefinitions, season: date, seed: int,
               leagues: list[NewLeague] | None = None
               ) -> tuple[list[SourcePlayer], dict[str, TmPlayer], dict[str, str],
                          SyntheticReport]:
    """The new leagues' players (not FC 27's own), the Transfermarkt records behind the real
    ones (by source id, for heights, values and contracts), each new source league's country
    (for the import profile), and a report."""
    leagues = leagues if leagues is not None else load_new_leagues()
    rules = defs.world_build.new_leagues
    top = rules.level_players
    report = SyntheticReport()
    aliases = {alias: n.name for n in defs.nations.values() for alias in n.aliases}
    names = Names(players, tm_players, aliases)
    templates = Templates(players, rules.template_pool)
    value_coef = fit_value_model(players, match, season)
    elo = club_elo(tm_db, rules.elo)
    league_coef = fit_league_model(players, defs)
    slope = fit_elo_slope(players, match, elo, rules)
    report.value_model = [round(float(c), 3) for c in value_coef]
    report.elo_model = [round(float(c), 3) for c in league_coef] + [round(slope, 4)]
    seasons = sorted(defs.association_coefficients.seasons)[-defs.europe.coefficient.seasons:]
    coefficient = {code: sum(defs.association_coefficients.seasons[x].get(code, 0.0)
                             for x in seasons)
                   for code in defs.association_coefficients.seasons[seasons[-1]]}
    squads = tm_squads(tm_db)
    taken = {t.tm_id for t in match.matches.values()}  # in FC 27 already (perhaps elsewhere)
    claimed: set[int] = set()  # Transfermarkt clubs already given to one of ours
    tm_by_id = {t.tm_id: t for t in tm_players if t.tm_id not in taken}
    out: list[SourcePlayer] = []
    extra: dict[str, TmPlayer] = {}
    league_nations: dict[str, str] = {}

    for lg in leagues:
        nation_name = defs.nations[lg.nation].name
        source_league = f"{SOURCE}:{lg.key}"
        league_nations[source_league] = nation_name
        ea_clubs = sorted({p.club for p in players if lg.ea_league and p.league == lg.ea_league})
        paired = ea_pairs(lg, ea_clubs)
        report.unmatched_ea += [f"{lg.key}: {c}" for c in ea_clubs if c not in paired.values()]
        league_level = float(league_coef[0] + league_coef[1]
                             * np.log(max(coefficient.get(lg.nation, 1.0), 1.0)))
        # Each club's Elo: its own where it has played enough, else below the league's clubs
        # that have (by last season's table), the league's level spread around their mean.
        tm_ids: dict[str, int | None] = {}
        country = defs.nations[lg.nation].name
        for club in lg.clubs:
            found = None
            in_league = squads.league_clubs.get(lg.tm_league or "", {})
            if club in lg.tm_names:  # by hand: Transfermarkt's own name, or none
                tm_name = lg.tm_names[club]
                if tm_name is not None:
                    hits = [cid for cid, n in in_league.items() if n == tm_name]
                    found = hits[0] if len(hits) == 1 else elo.named(tm_name)
            else:
                hits = [cid for cid, n in in_league.items() if same_club(n, club)]
                found = hits[0] if len(hits) == 1 else elo.find(club, country)
            tm_ids[club] = found if found is not None and found not in claimed else None
            if tm_ids[club] is not None:
                claimed.add(tm_ids[club])  # type: ignore[arg-type]
        rated = {c: elo.rating[i] for c, i in tm_ids.items()
                 if i is not None and elo.games.get(i, 0) >= rules.elo.min_games}
        floor = min(rated.values()) - rules.unrated_gap if rated else rules.elo.start
        club_elos = {}
        for k, club in enumerate(lg.clubs):
            club_elos[club] = rated.get(
                club, floor - rules.unrated_span * k / max(1, len(lg.clubs) - 1))
        mean_elo = float(np.mean(list(club_elos.values())))
        levels = {c: league_level + slope * (e - mean_elo) for c, e in club_elos.items()}
        for k, club in enumerate(lg.clubs):
            rng = entity_rng(seed, SOURCE, lg.key, club)
            if club in paired:
                report.from_ea += 1
                report.clubs_by_source["ea"] += 1
                continue
            report.clubs += 1
            level = levels[club]
            squad: list[SourcePlayer] = []
            tm_id = tm_ids.get(club)
            members = [tm_by_id[i] for i in squads.players_by_club.get(tm_id or -1, [])
                       if i in tm_by_id] if tm_id is not None else []
            real = []
            for t in members:
                rating = value_overall(value_coef, t.market_value_eur, t.birth_date,
                                       (t.position or "") == "Goalkeeper", season)
                real.append((t, rating))
            real.sort(key=lambda r: -(r[1] or 0))
            real = real[:rules.max_real_players]
            # Real players keep the order their values give them; the club's level sets how
            # high (their values' own level is shifted onto it).
            known = sorted((r for _, r in real if r is not None), reverse=True)
            shift = (level - float(np.mean(known[:top])) if len(known) >= rules.min_valued
                     else 0.0)
            for t, rating in real:
                overall = (rating + shift if rating is not None
                           else level - rules.unvalued_below)
                nation = aliases.get(t.citizenship or "", t.citizenship or nation_name)
                squad.append(_tm_player(t, source_league, club, overall, nation, templates,
                                        rng))
                extra[f"tm:{t.tm_id}"] = t
            report.tm_players += len(real)
            kind = "tm" if len(real) >= rules.min_real_for_tm else "mixed" if real else "generated"
            report.clubs_by_source[kind] += 1
            # Fill the squad to its size, by the positions it lacks.
            have = Counter(p.position for p in squad)
            wanted = []
            # by depth: the positions the real players leave open first
            for pos in rules.squad_shape:
                if have[pos] > 0:
                    have[pos] -= 1
                else:
                    wanted.append(pos)
            wanted = wanted[:max(0, rules.squad_size - len(squad))]
            centre = float(np.mean(rules.spread[:top]))
            offsets = [x - centre for x in rules.spread]
            spread = offsets[-len(wanted):] if squad else offsets[:len(wanted)]
            foreign = rules.foreign.share.get(lg.nation, rules.foreign.default_share)
            pool = rules.foreign.neighbours.get(lg.nation, []) + rules.foreign.travellers
            for j, (pos, offset) in enumerate(zip(wanted, spread, strict=False)):
                nation = (nation_name if rng.random() >= foreign
                          else pool[int(rng.integers(len(pool)))])
                if nation == nation_name or nation not in names.first:
                    nation = nation if nation in names.first else nation_name
                overall = level + offset + float(rng.normal(0.0, rules.noise_sd))
                squad.append(_generated_player(f"gen:{lg.key}:{k}:{j}", source_league, club,
                                               pos, overall, nation, templates, names, season,
                                               rules.age, rng))
                report.generated += 1
            out += squad
        built: dict[str, list[int]] = defaultdict(list)
        for p in out:
            if p.league == source_league:
                built[p.club].append(p.source_overall or 0)
        club_levels = [float(np.mean(sorted(v, reverse=True)[:top])) for v in built.values()]
        report.league_levels[lg.key] = (round(float(np.mean(club_levels)), 1)
                                        if club_levels else 0.0)
    return out, extra, league_nations, report


def with_new_leagues(profile: Any, league_nations: dict[str, str],
                     leagues: list[NewLeague] | None = None) -> Any:
    """The import profile with the new leagues added: each source league's country, and its
    competition (ours, and FC 27's few clubs' league)."""
    mapped = {}
    for lg in leagues if leagues is not None else load_new_leagues():
        mapped[f"{SOURCE}:{lg.key}"] = lg.key
        if lg.ea_league:
            mapped[lg.ea_league] = lg.key
    return profile.model_copy(update={
        "league_nations": {**profile.league_nations, **league_nations},
        "leagues": {**profile.leagues, **mapped}})

"""Entity resolution: which Transfermarkt player is this ratings-source player?

Pass 1 blocks candidates on exact birth date and scores name similarity (accents and
punctuation removed; any name variant may match), with small bonuses for matching club and
nationality. Pass 2 retries the leftovers against players whose birth date is within a week
(sources sometimes disagree by a day), demanding a near-exact full name.

A surname alone only counts when the first names are compatible, so twins (same birthday,
same surname) aren't confused. A match needs a clear margin over the runner-up, and when
several source players claim the same Transfermarkt player the clearly best one wins.
"""

import re
import unicodedata
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date

from rapidfuzz import fuzz

from footsim.importers.records import SourcePlayer, TmPlayer

NAME_THRESHOLD = 85.0
MIN_MARGIN = 4.0
SURNAME_ONLY_PENALTY = 10.0
FIRST_NAME_COMPATIBLE = 70.0
CLUB_BONUS = 3.0
NATION_BONUS = 2.0
NEAR_BIRTH_DAYS = 7
NEAR_BIRTH_THRESHOLD = 95.0

_FOLD = str.maketrans(
    {"ø": "o", "Ø": "O", "æ": "ae", "Æ": "AE", "ß": "ss", "ł": "l", "Ł": "L", "đ": "d",
     "Đ": "D", "ı": "i", "œ": "oe", "Œ": "OE", "þ": "th", "ð": "d"}
)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.translate(_FOLD))
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _source_full_names(p: SourcePlayer) -> set[str]:
    first, last = normalize(p.first_name), normalize(p.last_name)
    names = {f"{first} {last}".strip()}
    if last:
        # "Rodrigo Hernández Cascante" is often listed as "Rodrigo Hernández".
        names.add(f"{first} {last.split()[0]}".strip())
    if p.known_as:
        names.add(normalize(p.known_as))
    return {n for n in names if n}


def _tm_full_names(t: TmPlayer) -> set[str]:
    names = {normalize(t.name), normalize(f"{t.first_name} {t.last_name}")}
    return {n for n in names if n}


def _first_names_compatible(p: SourcePlayer, t: TmPlayer) -> bool:
    a, b = normalize(p.first_name), normalize(t.first_name)
    if not a or not b or a in b or b in a:
        return True
    return fuzz.ratio(a, b) >= FIRST_NAME_COMPATIBLE


def full_name_score(p: SourcePlayer, t: TmPlayer) -> float:
    return max(
        (fuzz.token_set_ratio(a, b) for a in _source_full_names(p) for b in _tm_full_names(t)),
        default=0.0,
    )


def name_score(p: SourcePlayer, t: TmPlayer) -> float:
    score = full_name_score(p, t)
    last_a, last_b = normalize(p.last_name), normalize(t.last_name)
    if last_a and last_b and _first_names_compatible(p, t):
        score = max(score, fuzz.ratio(last_a, last_b) - SURNAME_ONLY_PENALTY)
    return score


@dataclass
class MatchResult:
    matches: dict[str, TmPlayer] = field(default_factory=dict)
    scores: dict[str, float] = field(default_factory=dict)
    ambiguous: list[str] = field(default_factory=list)
    unmatched: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _Proposal:
    tm: TmPlayer
    score: float  # name score
    total: float  # with bonuses


Scorer = Callable[[SourcePlayer, TmPlayer], float]


def _best(
    p: SourcePlayer,
    candidates: Sequence[TmPlayer],
    aliases: dict[str, set[str]],
    scorer: Scorer,
    threshold: float,
) -> tuple[_Proposal | None, bool]:
    """Best candidate, and whether the choice was ambiguous."""
    scored = []
    for t in candidates:
        score = scorer(p, t)
        if score < threshold:
            continue
        total = score
        if t.club_name and fuzz.token_set_ratio(normalize(p.club), normalize(t.club_name)) >= 80:
            total += CLUB_BONUS
        if t.citizenship and (
            t.citizenship == p.nationality or t.citizenship in aliases.get(p.nationality, ())
        ):
            total += NATION_BONUS
        scored.append(_Proposal(t, score, total))
    if not scored:
        return None, False
    scored.sort(key=lambda s: s.total, reverse=True)
    if len(scored) > 1 and scored[0].total - scored[1].total < MIN_MARGIN:
        return None, True
    return scored[0], False


def _resolve_claims(proposals: dict[str, _Proposal], result: MatchResult) -> None:
    """Award each Transfermarkt player to at most one source player."""
    claimants: dict[int, list[str]] = defaultdict(list)
    for source_id, proposal in proposals.items():
        claimants[proposal.tm.tm_id].append(source_id)
    for source_ids in claimants.values():
        ranked = sorted(source_ids, key=lambda s: proposals[s].score, reverse=True)
        winner = ranked[0]
        if len(ranked) > 1 and proposals[winner].score - proposals[ranked[1]].score < MIN_MARGIN:
            result.ambiguous.extend(ranked)
            continue
        result.matches[winner] = proposals[winner].tm
        result.scores[winner] = proposals[winner].score
        result.unmatched.extend(ranked[1:])


def match_players(
    players: Iterable[SourcePlayer],
    tm_players: Iterable[TmPlayer],
    nation_aliases: dict[str, set[str]] | None = None,
) -> MatchResult:
    """``nation_aliases`` maps a source nationality to other spellings of it."""
    aliases = nation_aliases or {}
    players = list(players)
    tm_list = list(tm_players)
    by_birth: dict[date, list[TmPlayer]] = defaultdict(list)
    for t in tm_list:
        by_birth[t.birth_date].append(t)

    result = MatchResult()
    proposals: dict[str, _Proposal] = {}
    leftovers: list[SourcePlayer] = []
    for p in players:
        proposal, ambiguous = _best(
            p, by_birth.get(p.birth_date, []), aliases, name_score, NAME_THRESHOLD
        )
        if proposal:
            proposals[p.source_id] = proposal
        elif ambiguous:
            result.ambiguous.append(p.source_id)
        else:
            leftovers.append(p)
    _resolve_claims(proposals, result)

    taken = {t.tm_id for t in result.matches.values()}
    by_surname: dict[str, list[TmPlayer]] = defaultdict(list)
    for t in tm_list:
        if t.tm_id not in taken:
            for token in normalize(t.last_name or t.name).split():
                by_surname[token].append(t)
    second: dict[str, _Proposal] = {}
    for p in leftovers:
        tokens = normalize(p.last_name).split() + normalize(p.known_as or "").split()
        candidates = {
            t.tm_id: t
            for token in tokens
            for t in by_surname.get(token, [])
            if abs((t.birth_date - p.birth_date).days) <= NEAR_BIRTH_DAYS
        }
        proposal, ambiguous = _best(
            p, list(candidates.values()), aliases, full_name_score, NEAR_BIRTH_THRESHOLD
        )
        if proposal:
            second[p.source_id] = proposal
        elif ambiguous:
            result.ambiguous.append(p.source_id)
        else:
            result.unmatched.append(p.source_id)
    _resolve_claims(second, result)
    return result

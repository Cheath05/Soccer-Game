"""The news after a Continue or a sim, in sections (college fixes, 20 Nov): the user's own team
first, then the college season's champions together (one line a conference), the rest of college
soccer, recruiting, and the world beyond. The messages stay as the simulation wrote them; this
only sorts them, and merges each conference's two champions' lines into one."""

import re

from pydantic import BaseModel

CONFERENCE = re.compile(
    r"^(?P<club>.+) win the (?P<conf>.+) (?P<what>regular season|Tournament)\.$")
NATIONAL = re.compile(r"^(?P<club>.+) win the College Cup: they are the NCAA champions\.$")

YOURS = "Your team"
CHAMPIONS = "Conference champions"
COLLEGE = "College soccer"
RECRUITING = "Recruiting"
WORLD = "Around the world"
ORDER = (YOURS, CHAMPIONS, COLLEGE, RECRUITING, WORLD)


class NewsSectionOut(BaseModel):
    title: str
    items: list[str]


def _section(message: str, club: str | None) -> str:
    lower = message.lower()
    if (club and club in message) or message.startswith(("Your ", "You ", "Player development")):
        return YOURS
    if "recruit" in lower or "signing day" in lower or "visits campus" in lower \
            or "high-school" in lower:
        return RECRUITING
    if "college" in lower or "ncaa" in lower or "draft" in lower:
        return COLLEGE
    return WORLD


def news_sections(messages: list[str], club: str | None) -> list[NewsSectionOut]:
    """``messages`` in sections, in ``ORDER``, leaving out the empty ones. ``club`` is the user's
    club's name: its news comes first (a conference title of its own too)."""
    found: dict[str, list[str]] = {k: [] for k in ORDER}
    conferences: dict[str, dict[str, str]] = {}
    for m in dict.fromkeys(messages):  # once each, in order
        hit = CONFERENCE.match(m)
        if hit is not None:
            what = "regular season" if hit["what"] == "regular season" else "tournament"
            conferences.setdefault(hit["conf"], {})[what] = hit["club"]
            if club and hit["club"] == club:
                found[YOURS].append(m)
            continue
        if NATIONAL.match(m) and not (club and club in m):
            found[COLLEGE].insert(0, m)
            continue
        found[_section(m, club)].append(m)
    for conf, won in sorted(conferences.items()):
        regular, tournament = won.get("regular season"), won.get("tournament")
        if regular and tournament and regular == tournament:
            line = f"{conf}: {regular} (regular season and tournament)"
        else:
            line = f"{conf}: " + ", ".join(f"{c} ({w})" for w, c in (
                ("regular season", regular), ("tournament", tournament)) if c)
        found[CHAMPIONS].append(line)
    return [NewsSectionOut(title=k, items=found[k]) for k in ORDER if found[k]]

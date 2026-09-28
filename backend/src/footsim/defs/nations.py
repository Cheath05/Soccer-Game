"""Nations (data/config/nations.yaml). ``name`` uses the ratings source's spelling;
``aliases`` hold other spellings (e.g. Transfermarkt) for cross-source matching."""

from footsim.defs.common import DefModel


class NationDef(DefModel):
    code: str
    name: str
    confederation: str
    eu: bool = False
    aliases: list[str] = []


class NationsFile(DefModel):
    nations: list[NationDef]

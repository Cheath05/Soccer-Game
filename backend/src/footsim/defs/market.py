"""The transfer market's rules (W4): data/config/transfers/market.yaml."""

from footsim.defs.common import DefModel


class MarketDef(DefModel):
    default_window_nation: str  # whose windows a club from a country without a calendar follows

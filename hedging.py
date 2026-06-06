"""Delta hedging engine - calculates required hedge adjustments."""

from dataclasses import dataclass
from config import SHARES_PER_CONTRACT, DELTA_REBALANCE_THRESHOLD


@dataclass
class HedgeState:
    position_delta: float       # total delta exposure from options
    shares_needed: int          # shares needed to hedge (+ = buy, - = sell)
    current_shares: int         # shares currently held
    portfolio_delta: float      # net delta after hedge
    rebalance_needed: bool
    signal: str                 # "BUY", "SELL", "HOLD"
    signal_detail: str


def calculate_hedge(
    portfolio_position_delta: float,
    current_hedge_shares: int = 0,
    ticker: str = "",
) -> HedgeState:
    """
    Calculates the hedge based on the total delta of all option positions.
    """
    # Target shares to hold = -portfolio_position_delta (to neutralize)
    target_shares = round(-portfolio_position_delta)
    shares_needed = target_shares - current_hedge_shares

    portfolio_delta = portfolio_position_delta + current_hedge_shares

    rebalance_needed = abs(portfolio_delta) > DELTA_REBALANCE_THRESHOLD

    label = f" {ticker}" if ticker else ""

    if not rebalance_needed:
        signal = "HOLD"
        signal_detail = "Delta 中性，維持現有部位"
    elif shares_needed > 0:
        signal = "BUY"
        signal_detail = f"買入 {shares_needed} 股{label} 對沖"
    else:
        signal = "SELL"
        signal_detail = f"賣出 {abs(shares_needed)} 股{label} 對沖"

    return HedgeState(
        position_delta=portfolio_position_delta,
        shares_needed=shares_needed,
        current_shares=current_hedge_shares,
        portfolio_delta=portfolio_delta,
        rebalance_needed=rebalance_needed,
        signal=signal,
        signal_detail=signal_detail,
    )

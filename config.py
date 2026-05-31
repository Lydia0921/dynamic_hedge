"""Global constants for the hedging dashboard."""

from datetime import date

SHARES_PER_CONTRACT = 100

# Delta hedging thresholds
DELTA_REBALANCE_THRESHOLD = 30   # rebalance when net delta exceeds this (shares)
GAMMA_WARNING_THRESHOLD = 0.05

# Refresh interval (seconds)
REFRESH_INTERVAL = 60

# Volatility model
HV_WINDOWS = [20, 30, 60]              # historical volatility lookback windows (trading days)
IV_RESIDUAL_THRESHOLD = 0.03            # ±3% residual triggers SELL/BUY signal
IV_RANK_SELL_THRESHOLD = 50             # IV Rank > 50% = favorable for sellers

"""Volatility model engine — HV estimation, IV ranking, and residual-based signals."""

import numpy as np
import pandas as pd

from config import HV_WINDOWS, IV_RESIDUAL_THRESHOLD
from data import get_historical_closes, get_spot_price, get_risk_free_rate, get_full_option_chain
from greeks import implied_volatility


# ── Historical Volatility ──────────────────────────────────────────


def calc_historical_volatility(ticker: str, windows: list[int] | None = None) -> dict[int, float]:
    """Close-to-close annualized HV for multiple lookback windows.

    Returns {window: hv} e.g. {20: 0.45, 30: 0.42, 60: 0.40}.
    """
    if windows is None:
        windows = HV_WINDOWS

    closes = get_historical_closes(ticker, period="1y")
    if closes.empty or len(closes) < max(windows) + 1:
        return {w: 0.0 for w in windows}

    log_returns = np.log(closes / closes.shift(1)).dropna()

    result = {}
    for w in windows:
        if len(log_returns) < w:
            result[w] = 0.0
        else:
            result[w] = float(log_returns.iloc[-w:].std() * np.sqrt(252))
    return result


def calc_hv_series(ticker: str, window: int = 30) -> pd.Series:
    """Rolling HV series over the past year for charting."""
    closes = get_historical_closes(ticker, period="1y")
    if closes.empty or len(closes) < window + 1:
        return pd.Series(dtype=float)

    log_returns = np.log(closes / closes.shift(1)).dropna()
    return log_returns.rolling(window).std() * np.sqrt(252)


# ── IV Rank / Percentile ──────────────────────────────────────────


def calc_iv_rank(current_iv: float, iv_high_52w: float, iv_low_52w: float) -> float:
    """IV Rank = (current - 52wk low) / (52wk high - 52wk low) × 100.

    Returns 0–100.
    """
    if iv_high_52w <= iv_low_52w:
        return 0.0
    rank = (current_iv - iv_low_52w) / (iv_high_52w - iv_low_52w) * 100
    return max(0.0, min(100.0, rank))


def calc_iv_percentile(current_iv: float, iv_history: pd.Series) -> float:
    """IV Percentile = % of days in history where IV was below current.

    Returns 0–100.
    """
    if iv_history.empty:
        return 0.0
    return float((iv_history < current_iv).sum() / len(iv_history) * 100)


def estimate_current_atm_iv(ticker: str, expiry_str: str) -> float:
    """Estimate current ATM IV from the option chain for a given expiry."""
    spot = get_spot_price(ticker)
    rfr = get_risk_free_rate()
    chain = get_full_option_chain(ticker, expiry_str)
    calls = chain["calls"]
    if calls.empty:
        return 0.0

    # Find the strike closest to spot
    calls = calls.copy()
    calls["dist"] = (calls["strike"] - spot).abs()
    atm_row = calls.loc[calls["dist"].idxmin()]

    bid = float(atm_row.get("bid", 0))
    ask = float(atm_row.get("ask", 0))
    if bid > 0 and ask > 0:
        market_price = (bid + ask) / 2
    else:
        market_price = float(atm_row.get("lastPrice", 0))

    if market_price <= 0:
        return 0.0

    from datetime import date
    expiry_date = date.fromisoformat(expiry_str)
    dte = (expiry_date - date.today()).days
    T = max(dte, 0) / 365.0
    if T <= 0:
        return 0.0

    return implied_volatility(market_price, spot, float(atm_row["strike"]), T, rfr, "call")


# ── Model IV & Residuals ─────────────────────────────────────────


def calc_model_iv(ticker: str, window: int = 30) -> float:
    """Model IV = HV as baseline (simple, effective first pass).

    Uses EWMA-weighted HV for slight recency bias.
    """
    closes = get_historical_closes(ticker, period="1y")
    if closes.empty or len(closes) < window + 1:
        return 0.0

    log_returns = np.log(closes / closes.shift(1)).dropna()
    recent = log_returns.iloc[-window:]

    # EWMA weighting — more recent days have more influence
    weights = np.exp(np.linspace(-1, 0, len(recent)))
    weights /= weights.sum()
    weighted_var = np.sum(weights * (recent.values - np.average(recent.values, weights=weights)) ** 2)
    return float(np.sqrt(weighted_var * 252))


def calc_iv_residual(market_iv: float, model_iv: float) -> float:
    """Residual = market IV - model IV.

    Positive = overpriced (SELL opportunity).
    Negative = underpriced.
    """
    return market_iv - model_iv


def generate_signal(residual: float, threshold: float | None = None) -> str:
    """Generate SELL/BUY/NEUTRAL signal from IV residual.

    SELL when market overprices (positive residual > threshold).
    BUY when market underprices (negative residual beyond threshold).
    """
    if threshold is None:
        threshold = IV_RESIDUAL_THRESHOLD

    if residual > threshold:
        return "SELL"
    elif residual < -threshold:
        return "BUY"
    return "NEUTRAL"


# ── Full Chain Analysis ──────────────────────────────────────────


def analyze_chain_iv(ticker: str, expiry_str: str) -> pd.DataFrame:
    """Compute market IV, model IV, residual, and signal for every strike in a chain.

    Returns DataFrame with columns:
        strike, type, market_price, market_iv, model_iv, residual, signal
    """
    spot = get_spot_price(ticker)
    rfr = get_risk_free_rate()
    model_iv = calc_model_iv(ticker)
    chain = get_full_option_chain(ticker, expiry_str)

    from datetime import date
    expiry_date = date.fromisoformat(expiry_str)
    dte = (expiry_date - date.today()).days
    T = max(dte, 0) / 365.0

    rows = []
    for opt_type, df in [("call", chain["calls"]), ("put", chain["puts"])]:
        if df.empty:
            continue
        for _, row in df.iterrows():
            strike = float(row["strike"])
            bid = float(row.get("bid", 0))
            ask = float(row.get("ask", 0))
            if bid > 0 and ask > 0:
                mp = (bid + ask) / 2
            else:
                mp = float(row.get("lastPrice", 0))

            if mp <= 0 or T <= 0:
                continue

            mkt_iv = implied_volatility(mp, spot, strike, T, rfr, opt_type)
            residual = calc_iv_residual(mkt_iv, model_iv)
            signal = generate_signal(residual)

            rows.append({
                "strike": strike,
                "type": opt_type.upper(),
                "market_price": round(mp, 2),
                "market_iv": round(mkt_iv * 100, 1),
                "model_iv": round(model_iv * 100, 1),
                "residual": round(residual * 100, 1),
                "signal": signal,
                "volume": int(row.get("volume", 0)) if pd.notna(row.get("volume")) else 0,
                "open_interest": int(row.get("openInterest", 0)) if pd.notna(row.get("openInterest")) else 0,
            })

    return pd.DataFrame(rows)


def calc_overpriced_ratio(chain_df: pd.DataFrame) -> float:
    """% of options in the chain where market IV > model IV (signal = SELL).

    Returns 0–100.
    """
    if chain_df.empty:
        return 0.0
    sell_count = (chain_df["signal"] == "SELL").sum()
    return float(sell_count / len(chain_df) * 100)

"""Market data fetching via yfinance (free)."""

import yfinance as yf
import pandas as pd
from datetime import date, datetime


def validate_ticker(ticker: str) -> bool:
    """Check if a ticker is valid and has options data."""
    try:
        stock = yf.Ticker(ticker)
        info = stock.fast_info
        if info.get("lastPrice") or info.get("previousClose"):
            return True
        # fallback: try history
        data = stock.history(period="1d")
        return not data.empty
    except Exception:
        return False


def get_spot_price(ticker: str) -> float:
    stock = yf.Ticker(ticker)
    data = stock.history(period="1d")
    if data.empty:
        fast = stock.fast_info
        return fast.get("lastPrice", fast.get("previousClose", 0.0))
    return float(data["Close"].iloc[-1])


def get_risk_free_rate() -> float:
    """Fetch 13-week T-bill rate as risk-free rate proxy."""
    try:
        irx = yf.Ticker("^IRX")
        data = irx.history(period="5d")
        if not data.empty:
            return float(data["Close"].iloc[-1]) / 100
    except Exception:
        pass
    return 0.045  # fallback


def get_available_expiries(ticker: str) -> list[str]:
    """Return all available option expiry dates for a ticker."""
    try:
        stock = yf.Ticker(ticker)
        return list(stock.options)
    except Exception:
        return []


def get_available_strikes(ticker: str, expiry_str: str, option_type: str = "call") -> list[float]:
    """Return all available strikes for a given ticker, expiry, and type."""
    try:
        stock = yf.Ticker(ticker)
        chain = stock.option_chain(expiry_str)
        options = chain.calls if option_type == "call" else chain.puts
        return sorted(options["strike"].tolist())
    except Exception:
        return []


def get_option_chain(ticker: str, expiry: date, option_type: str = "call") -> pd.DataFrame | None:
    """Fetch option chain for a specific expiry and type."""
    stock = yf.Ticker(ticker)
    try:
        expiry_str = expiry.strftime("%Y-%m-%d")
        chain = stock.option_chain(expiry_str)
        return chain.calls if option_type == "call" else chain.puts
    except Exception:
        return None


def get_option_market_price(ticker: str, expiry: date, strike: float, option_type: str = "call") -> float | None:
    """Get the last/mid price for a specific option contract."""
    stock = yf.Ticker(ticker)
    try:
        expiry_str = expiry.strftime("%Y-%m-%d")
        chain = stock.option_chain(expiry_str)
        options = chain.calls if option_type == "call" else chain.puts
        row = options[options["strike"] == strike]
        if row.empty:
            return None
        bid = float(row["bid"].iloc[0])
        ask = float(row["ask"].iloc[0])
        if bid > 0 and ask > 0:
            return (bid + ask) / 2
        last = float(row["lastPrice"].iloc[0])
        return last if last > 0 else None
    except Exception:
        return None


def get_historical_prices(ticker: str, period: str = "1mo") -> pd.DataFrame:
    stock = yf.Ticker(ticker)
    return stock.history(period=period)


def days_to_expiry(expiry: date) -> int:
    return (expiry - date.today()).days


def time_to_expiry(expiry: date) -> float:
    """Time to expiry in years."""
    return max(days_to_expiry(expiry), 0) / 365.0


def get_historical_closes(ticker: str, period: str = "1y") -> pd.Series:
    """Return daily close prices for HV calculation."""
    stock = yf.Ticker(ticker)
    hist = stock.history(period=period)
    if hist.empty:
        return pd.Series(dtype=float)
    return hist["Close"]


def get_full_option_chain(ticker: str, expiry_str: str) -> dict[str, pd.DataFrame]:
    """Return both calls and puts DataFrames for a given expiry.

    Returns dict with keys 'calls' and 'puts'.
    """
    stock = yf.Ticker(ticker)
    try:
        chain = stock.option_chain(expiry_str)
        return {"calls": chain.calls, "puts": chain.puts}
    except Exception:
        return {"calls": pd.DataFrame(), "puts": pd.DataFrame()}


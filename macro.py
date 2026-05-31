"""Macro indicators as supplementary reference for hedging decisions."""

import yfinance as yf


def get_vix() -> float:
    """CBOE Volatility Index - market fear gauge."""
    try:
        data = yf.Ticker("^VIX").history(period="5d")
        if not data.empty:
            return float(data["Close"].iloc[-1])
    except Exception:
        pass
    return 0.0


def get_us10y() -> float:
    """US 10-Year Treasury yield."""
    try:
        data = yf.Ticker("^TNX").history(period="5d")
        if not data.empty:
            return float(data["Close"].iloc[-1])
    except Exception:
        pass
    return 0.0


def get_sp500_change() -> float:
    """S&P 500 daily change %."""
    try:
        data = yf.Ticker("^GSPC").history(period="5d")
        if len(data) >= 2:
            return (data["Close"].iloc[-1] / data["Close"].iloc[-2] - 1) * 100
    except Exception:
        pass
    return 0.0


def get_macro_summary() -> dict:
    return {
        "vix": get_vix(),
        "us10y": get_us10y(),
        "sp500_chg": get_sp500_change(),
    }

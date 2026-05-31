"""Trade logging system - records trades with reasoning and indicators to CSV."""

import csv
import json
import os
from datetime import datetime
from dataclasses import dataclass, asdict
import pandas as pd

TRADES_DIR = os.path.join(os.path.dirname(__file__), "trades")

FIELDS = [
    "timestamp",
    "action",          # BUY / SELL / HOLD
    "instrument",      # ticker (stock) or option descriptor
    "quantity",
    "price",
    "strategy",        # delta_hedge, roll, spread, etc.
    "reason",
    "spot_price",
    "delta",
    "gamma",
    "theta",
    "vega",
    "iv",
    "dte",
    "portfolio_delta",
    "vix",
    "us10y",
    "cash_before",
    "cash_after",
    "notes",
]


def _log_file(ticker: str) -> str:
    os.makedirs(TRADES_DIR, exist_ok=True)
    return os.path.join(TRADES_DIR, f"{ticker.upper()}.csv")


def _ensure_file(ticker: str):
    path = _log_file(ticker)
    if not os.path.exists(path):
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writeheader()


def log_trade(
    ticker: str,
    action: str,
    instrument: str,
    quantity: int,
    price: float,
    strategy: str,
    reason: str,
    spot_price: float,
    delta: float,
    gamma: float,
    theta: float,
    vega: float,
    iv: float,
    dte: int,
    portfolio_delta: float,
    vix: float = 0.0,
    us10y: float = 0.0,
    cash_before: float = 0.0,
    cash_after: float = 0.0,
    notes: str = "",
):
    _ensure_file(ticker)
    row = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "action": action,
        "instrument": instrument,
        "quantity": quantity,
        "price": price,
        "strategy": strategy,
        "reason": reason,
        "spot_price": spot_price,
        "delta": round(delta, 4),
        "gamma": round(gamma, 4),
        "theta": round(theta, 4),
        "vega": round(vega, 4),
        "iv": round(iv, 4),
        "dte": dte,
        "portfolio_delta": round(portfolio_delta, 1),
        "vix": round(vix, 2),
        "us10y": round(us10y, 3),
        "cash_before": round(cash_before, 2),
        "cash_after": round(cash_after, 2),
        "notes": notes,
    }
    with open(_log_file(ticker), "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writerow(row)


def read_trades(ticker: str):
    _ensure_file(ticker)
    df = pd.read_csv(_log_file(ticker))
    return df


def get_current_state(ticker: str):
    """Calculate current share count and cash from trade history."""
    df = read_trades(ticker)
    if df.empty:
        return 0, 0.0

    shares = 0
    stock_trades = df[df['instrument'] == ticker.upper()]
    for _, row in stock_trades.iterrows():
        if row['action'] == 'BUY':
            shares += row['quantity']
        elif row['action'] == 'SELL':
            shares -= row['quantity']

    latest_cash = df.iloc[-1]['cash_after']
    if pd.isna(latest_cash) or latest_cash == 0:
        latest_cash = 0.0

    return max(0, int(shares)), float(latest_cash)


def _positions_file(ticker: str) -> str:
    os.makedirs(TRADES_DIR, exist_ok=True)
    return os.path.join(TRADES_DIR, f"{ticker.upper()}_positions.json")


def save_positions(ticker: str, positions: list[dict]):
    """Persist option positions to JSON."""
    with open(_positions_file(ticker), "w") as f:
        json.dump(positions, f, indent=2)


def load_positions(ticker: str) -> list[dict]:
    """Load saved option positions from JSON."""
    path = _positions_file(ticker)
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return []

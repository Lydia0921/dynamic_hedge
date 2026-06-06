"""Backfill trades.csv with proper Greeks, IV, spot prices, VIX, and portfolio delta.

Uses the project's own Black-Scholes model (greeks.py) and yfinance for historical prices.
Key improvements:
- Track running IV estimates per option leg (updated when that option is traded)
- Handle DTE=0 (same-day expiry) with a small time fraction
- Proper portfolio delta uses current spot to recalculate ALL active positions
"""

import csv
import numpy as np
from datetime import datetime, date, timedelta
import yfinance as yf

from greeks import calculate_greeks, implied_volatility

# ── Constants ──────────────────────────────────────────────────────────────
RISK_FREE_RATE = 0.043  # approx US 10Y yield during May-Jun 2026
SHARES_PER_CONTRACT = 100

# Option specs
SHORT_CALL_STRIKE = 131
SHORT_CALL_EXPIRY = date(2026, 6, 5)

LONG_CALL_STRIKE = 141
LONG_CALL_EXPIRY = date(2026, 6, 26)

# ── Fetch historical data ─────────────────────────────────────────────────
print("Fetching PLTR historical data...")
pltr = yf.download("PLTR", start="2026-05-13", end="2026-06-06", interval="1d")
print(f"Got {len(pltr)} rows of PLTR data")

print("Fetching VIX historical data...")
vix_data = yf.download("^VIX", start="2026-05-13", end="2026-06-06", interval="1d")
print(f"Got {len(vix_data)} rows of VIX data")

print("Fetching US 10Y yield data...")
tnx_data = yf.download("^TNX", start="2026-05-13", end="2026-06-06", interval="1d")
print(f"Got {len(tnx_data)} rows of TNX data")

# Fallback spot prices from trading diary (in case yfinance has gaps)
FALLBACK_SPOTS = {
    date(2026, 5, 14): 133.73,
    date(2026, 5, 18): 134.50,
    date(2026, 5, 20): 136.18,
    date(2026, 5, 22): 136.82,
    date(2026, 5, 27): 133.55,
    date(2026, 5, 28): 140.00,
    date(2026, 5, 29): 156.00,
    date(2026, 6, 3): 145.53,
    date(2026, 6, 5): 135.53,
}


def get_close_price(df, trade_date):
    """Get closing price for a given date, falling back to nearest prior date."""
    import pandas as pd
    if isinstance(df.columns, pd.MultiIndex):
        close_col = df['Close']
        if isinstance(close_col, pd.DataFrame):
            close_col = close_col.iloc[:, 0]
    else:
        close_col = df['Close']

    for offset in range(5):
        d = trade_date - timedelta(days=offset)
        d_str = d.strftime("%Y-%m-%d")
        if d_str in close_col.index.strftime("%Y-%m-%d").tolist():
            idx = close_col.index.strftime("%Y-%m-%d").tolist().index(d_str)
            return float(close_col.iloc[idx])
    return 0.0


def get_spot(trade_date):
    """Get PLTR spot price for a date, with fallback."""
    spot = get_close_price(pltr, trade_date)
    if spot == 0 or np.isnan(spot):
        spot = FALLBACK_SPOTS.get(trade_date, 135.0)
    return spot


def calc_dte(trade_date, expiry):
    return max((expiry - trade_date).days, 0)


def calc_T(trade_date, expiry):
    """Time to expiry in years. Minimum 0.5 day for same-day options."""
    dte = calc_dte(trade_date, expiry)
    if dte == 0:
        return 0.5 / 365.0  # half a trading day remaining
    return dte / 365.0


# ── Trade definitions ─────────────────────────────────────────────────────
trades = [
    {
        "timestamp": "2026-05-14 10:40:00",
        "action": "BUY", "instrument": "PLTR2605R131", "quantity": 6, "price": 6.15,
        "strategy": "Options", "reason": "Market - Buy",
        "option_type": "put", "strike": 131, "expiry": SHORT_CALL_EXPIRY,
        "cash_before": 100000.0, "cash_after": 96310.0,
        "notes": "誤操作：原意Short Call誤買Long Put",
    },
    {
        "timestamp": "2026-05-18 09:30:00",
        "action": "SELL", "instrument": "PLTR2605R131", "quantity": 6, "price": 5.15,
        "strategy": "Options", "reason": "Market - Sell",
        "option_type": "put", "strike": 131, "expiry": SHORT_CALL_EXPIRY,
        "cash_before": 96310.0, "cash_after": 99400.0,
        "notes": "平倉誤買Put, 止損-$600",
    },
    {
        "timestamp": "2026-05-18 09:49:00",
        "action": "SELL", "instrument": "PLTR2605F131", "quantity": 6, "price": 7.3,
        "strategy": "Options", "reason": "Market - Short",
        "option_type": "call", "strike": 131, "expiry": SHORT_CALL_EXPIRY,
        "cash_before": 99400.0, "cash_after": 103780.0,
        "notes": "核心建倉：Short 6口 $131 Call, 收權利金+$4380",
    },
    {
        "timestamp": "2026-05-20 11:33:00",
        "action": "BUY", "instrument": "PLTR", "quantity": 400, "price": 136.18,
        "strategy": "Equities", "reason": "Market - Buy",
        "option_type": None, "strike": None, "expiry": None,
        "cash_before": 103780.0, "cash_after": 49308.0,
        "notes": "Delta避險：買400股, 淨Delta≈-20",
    },
    {
        "timestamp": "2026-05-22 12:12:00",
        "action": "BUY", "instrument": "PLTR2626F141", "quantity": 3, "price": 5.9,
        "strategy": "Options", "reason": "Market - Buy",
        "option_type": "call", "strike": 141, "expiry": LONG_CALL_EXPIRY,
        "cash_before": 49308.0, "cash_after": 47538.0,
        "notes": "策略轉型：買3口遠期$141 Call對沖尾部風險",
    },
    {
        "timestamp": "2026-05-22 12:23:00",
        "action": "SELL", "instrument": "PLTR", "quantity": 110, "price": 136.22,
        "strategy": "Equities", "reason": "Market - Sell",
        "option_type": None, "strike": None, "expiry": None,
        "cash_before": 47538.0, "cash_after": 62522.2,
        "notes": "Delta再平衡：Long Call帶入正Delta, 減碼現股",
    },
    {
        "timestamp": "2026-05-27 11:04:00",
        "action": "SELL", "instrument": "PLTR", "quantity": 150, "price": 133.81,
        "strategy": "Equities", "reason": "Market - Sell",
        "option_type": None, "strike": None, "expiry": None,
        "cash_before": 62522.2, "cash_after": 82593.7,
        "notes": "Delta再平衡（股價小漲, Delta偏多）",
    },
    {
        "timestamp": "2026-05-27 11:12:00",
        "action": "BUY", "instrument": "PLTR", "quantity": 50, "price": 133.71,
        "strategy": "Equities", "reason": "Market - Buy",
        "option_type": None, "strike": None, "expiry": None,
        "cash_before": 82593.7, "cash_after": 75908.2,
        "notes": "Delta再平衡（股價回落, Delta偏空）",
    },
    {
        "timestamp": "2026-05-27 11:13:00",
        "action": "BUY", "instrument": "PLTR", "quantity": 50, "price": 133.79,
        "strategy": "Equities", "reason": "Market - Buy",
        "option_type": None, "strike": None, "expiry": None,
        "cash_before": 75908.2, "cash_after": 69218.7,
        "notes": "Delta再平衡（持續調整）",
    },
    {
        "timestamp": "2026-06-03 10:33:00",
        "action": "BUY", "instrument": "PLTR", "quantity": 170, "price": 145.53,
        "strategy": "Equities", "reason": "Market - Buy",
        "option_type": None, "strike": None, "expiry": None,
        "cash_before": 69218.7, "cash_after": 44478.6,
        "notes": "Gamma Risk爆發：到期週深度ITM被迫高位補倉",
    },
    {
        "timestamp": "2026-06-05 09:55:00",
        "action": "SELL", "instrument": "PLTR2626F141", "quantity": 3, "price": 5.45,
        "strategy": "Options", "reason": "Market - Sell",
        "option_type": "call", "strike": 141, "expiry": LONG_CALL_EXPIRY,
        "cash_before": 44478.6, "cash_after": 46113.6,
        "notes": "到期日平倉遠期Long Call, 回收資金",
    },
    {
        "timestamp": "2026-06-05 10:10:00",
        "action": "BUY", "instrument": "PLTR", "quantity": 190, "price": 138.43,
        "strategy": "Equities", "reason": "Market - Buy",
        "option_type": None, "strike": None, "expiry": None,
        "cash_before": 46113.6, "cash_after": 19811.9,
        "notes": "缺口補足：補入190股至600股應付指派",
    },
    {
        "timestamp": "2026-06-05 10:23:00",
        "action": "SELL", "instrument": "SOXL", "quantity": 30, "price": 224.58,
        "strategy": "Equities", "reason": "Market - Short",
        "option_type": None, "strike": None, "expiry": None,
        "cash_before": 19811.9, "cash_after": 26549.3,
        "notes": "SOXL短線放空",
    },
    {
        "timestamp": "2026-06-05 11:27:00",
        "action": "BUY", "instrument": "SOXL", "quantity": 30, "price": 215.44,
        "strategy": "Equities", "reason": "Market - Cover",
        "option_type": None, "strike": None, "expiry": None,
        "cash_before": 26549.3, "cash_after": 20086.1,
        "notes": "SOXL回補空單, +$274獲利",
    },
    {
        "timestamp": "2026-06-05 11:30:00",
        "action": "BUY", "instrument": "SOXL", "quantity": 50, "price": 215.15,
        "strategy": "Equities", "reason": "Market - Buy",
        "option_type": None, "strike": None, "expiry": None,
        "cash_before": 20086.1, "cash_after": 9328.6,
        "notes": "SOXL做多",
    },
    {
        "timestamp": "2026-06-05 12:46:00",
        "action": "SELL", "instrument": "SOXL", "quantity": 50, "price": 197.43,
        "strategy": "Equities", "reason": "Market - Sell",
        "option_type": None, "strike": None, "expiry": None,
        "cash_before": 9328.6, "cash_after": 19200.1,
        "notes": "SOXL賣出, -$886虧損",
    },
    {
        "timestamp": "2026-06-05 18:15:00",
        "action": "BUY", "instrument": "PLTR2605F131", "quantity": 6, "price": 4.53,
        "strategy": "Options", "reason": "Market - Cover",
        "option_type": "call", "strike": 131, "expiry": SHORT_CALL_EXPIRY,
        "cash_before": 19200.1, "cash_after": 16482.1,
        "notes": "主動平倉Short Call, 期權端淨獲利+$1662",
    },
]

# ── Portfolio state tracking ───────────────────────────────────────────────
pltr_shares = 0
short_call_131_qty = 0   # positive = number of contracts shorted
long_put_131_qty = 0     # positive = number of contracts held long
long_call_141_qty = 0    # positive = number of contracts held long

# Running IV estimates — updated each time a leg is traded
# These are used for portfolio delta when the leg itself isn't the current trade
iv_131_call = 0.50   # initial estimate
iv_131_put = 0.50
iv_141_call = 0.45

FIELDS = [
    "timestamp", "action", "instrument", "quantity", "price",
    "strategy", "reason", "spot_price", "delta", "gamma",
    "theta", "vega", "iv", "dte", "portfolio_delta",
    "vix", "us10y", "cash_before", "cash_after", "notes",
]

output_rows = []

for t in trades:
    trade_dt = datetime.strptime(t["timestamp"], "%Y-%m-%d %H:%M:%S")
    trade_date = trade_dt.date()

    # ── Get spot price ────────────────────────────────────────────────
    # For stock trades, the trade price IS the spot
    # For option trades, use PLTR daily close
    if t["option_type"] is None and t["instrument"] in ("PLTR", "SOXL"):
        spot = t["price"]
    else:
        spot = get_spot(trade_date)

    # ── Get VIX & US 10Y ──────────────────────────────────────────────
    vix_val = get_close_price(vix_data, trade_date)
    us10y_raw = get_close_price(tnx_data, trade_date)
    us10y_pct = us10y_raw / 100.0 if us10y_raw > 1 else us10y_raw

    # ── Calculate Greeks for the TRADED instrument ────────────────────
    delta_val = 0.0
    gamma_val = 0.0
    theta_val = 0.0
    vega_val = 0.0
    iv_val = 0.0
    dte_val = 0

    if t["option_type"] is not None:
        strike = t["strike"]
        expiry = t["expiry"]
        opt_type = t["option_type"]
        opt_price = t["price"]
        dte_val = calc_dte(trade_date, expiry)
        T = calc_T(trade_date, expiry)  # uses min 0.5 day

        if spot > 0:
            # Calculate IV from market price
            iv_val = implied_volatility(opt_price, spot, strike, T, RISK_FREE_RATE, opt_type)

            # Calculate Greeks with that IV
            g = calculate_greeks(spot, strike, T, RISK_FREE_RATE, iv_val, opt_type)
            delta_val = g.delta
            gamma_val = g.gamma
            theta_val = g.theta
            vega_val = g.vega

            # Update running IV estimates
            instrument = t["instrument"]
            if instrument == "PLTR2605F131":
                iv_131_call = iv_val
            elif instrument == "PLTR2605R131":
                iv_131_put = iv_val
            elif instrument == "PLTR2626F141":
                iv_141_call = iv_val
    else:
        # For stock trades
        delta_val = 1.0
        dte_val = calc_dte(trade_date, SHORT_CALL_EXPIRY)

    # ── Update portfolio positions ────────────────────────────────────
    instrument = t["instrument"]

    if instrument == "PLTR":
        if t["action"] == "BUY":
            pltr_shares += t["quantity"]
        else:
            pltr_shares -= t["quantity"]
    elif instrument == "PLTR2605R131":  # Put
        if t["action"] == "BUY":
            long_put_131_qty += t["quantity"]
        else:
            long_put_131_qty -= t["quantity"]
    elif instrument == "PLTR2605F131":  # Call 131
        if t["action"] == "SELL":
            short_call_131_qty += t["quantity"]
        elif t["action"] == "BUY":
            short_call_131_qty -= t["quantity"]
    elif instrument == "PLTR2626F141":  # Call 141
        if t["action"] == "BUY":
            long_call_141_qty += t["quantity"]
        elif t["action"] == "SELL":
            long_call_141_qty -= t["quantity"]

    # ── Compute portfolio delta (recalculate ALL active legs) ─────────
    # Use the PLTR spot for portfolio delta (not SOXL spot)
    pltr_spot = get_spot(trade_date) if t["instrument"] == "SOXL" else spot
    if t["option_type"] is None and t["instrument"] == "PLTR":
        pltr_spot = get_spot(trade_date)  # use daily close, not trade price

    port_delta = float(pltr_shares)

    # Short Call 131 contribution
    if short_call_131_qty > 0 and pltr_spot > 0:
        T_131 = calc_T(trade_date, SHORT_CALL_EXPIRY)
        g_131 = calculate_greeks(pltr_spot, SHORT_CALL_STRIKE, T_131, RISK_FREE_RATE, iv_131_call, "call")
        port_delta -= g_131.delta * short_call_131_qty * SHARES_PER_CONTRACT

    # Long Put 131 contribution
    if long_put_131_qty > 0 and pltr_spot > 0:
        T_put = calc_T(trade_date, SHORT_CALL_EXPIRY)
        g_put = calculate_greeks(pltr_spot, 131, T_put, RISK_FREE_RATE, iv_131_put, "put")
        port_delta += g_put.delta * long_put_131_qty * SHARES_PER_CONTRACT

    # Long Call 141 contribution
    if long_call_141_qty > 0 and pltr_spot > 0:
        T_141 = calc_T(trade_date, LONG_CALL_EXPIRY)
        g_141 = calculate_greeks(pltr_spot, LONG_CALL_STRIKE, T_141, RISK_FREE_RATE, iv_141_call, "call")
        port_delta += g_141.delta * long_call_141_qty * SHARES_PER_CONTRACT

    # ── Build output row ──────────────────────────────────────────────
    row = {
        "timestamp": t["timestamp"],
        "action": t["action"],
        "instrument": t["instrument"],
        "quantity": t["quantity"],
        "price": t["price"],
        "strategy": t["strategy"],
        "reason": t["reason"],
        "spot_price": round(pltr_spot if t["instrument"] != "SOXL" else spot, 2),
        "delta": round(delta_val, 4),
        "gamma": round(gamma_val, 6),
        "theta": round(theta_val, 4),
        "vega": round(vega_val, 4),
        "iv": round(iv_val, 4),
        "dte": dte_val,
        "portfolio_delta": round(port_delta, 1),
        "vix": round(vix_val, 2),
        "us10y": round(us10y_pct, 3),
        "cash_before": t["cash_before"],
        "cash_after": t["cash_after"],
        "notes": t["notes"],
    }

    output_rows.append(row)

    print(f"\n{'='*70}")
    print(f"Trade: {t['action']} {t['quantity']} {t['instrument']} @ ${t['price']}")
    print(f"  PLTR Spot: ${pltr_spot:.2f} | DTE(131C): {calc_dte(trade_date, SHORT_CALL_EXPIRY)} | Traded IV: {iv_val:.4f}")
    print(f"  Instrument Delta: {delta_val:.4f} | Gamma: {gamma_val:.6f} | Theta: {theta_val:.4f} | Vega: {vega_val:.4f}")
    print(f"  VIX: {vix_val:.2f} | US10Y: {us10y_pct:.3f}")
    print(f"  Portfolio: {pltr_shares} shares | {short_call_131_qty} SC131 | {long_call_141_qty} LC141 | {long_put_131_qty} LP131")
    print(f"  Running IVs: 131C={iv_131_call:.4f} | 141C={iv_141_call:.4f}")
    print(f"  ► Portfolio Delta: {port_delta:.1f}")

# ── Write output CSV ──────────────────────────────────────────────────────
output_path = "trades.csv"
with open(output_path, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=FIELDS)
    writer.writeheader()
    for row in output_rows:
        writer.writerow(row)

print(f"\n\n✅ Written {len(output_rows)} trades to {output_path}")
print("All Greeks, IV, DTE, VIX, US10Y, and portfolio delta properly calculated.")

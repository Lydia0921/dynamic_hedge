"""Short-dated option research harness.

This module intentionally separates research/backtesting from the Streamlit UI.
It uses historical underlying prices plus Black-Scholes marks so short-dated
delta-hedge rules can be tested even when historical option chains are not
available from the free data source.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf
from scipy.stats import norm

from config import DELTA_REBALANCE_THRESHOLD, SHARES_PER_CONTRACT
from greeks import bs_price, calculate_greeks
from hedging import calculate_hedge


@dataclass(frozen=True)
class OptionLegSpec:
    option_type: str
    side: str
    contracts: int
    target_abs_delta: float


@dataclass(frozen=True)
class BacktestConfig:
    ticker: str = "PLTR"
    start: date = date(2026, 5, 1)
    end: date = date(2026, 5, 31)
    strategy: str = "short_strangle"
    target_dte: int = 30
    target_abs_delta: float = 0.30
    contracts: int = 1
    hv_window: int = 20
    iv_markup: float = 1.15
    min_iv: float = 0.20
    risk_free_rate: float = 0.045
    rebalance_threshold: float = DELTA_REBALANCE_THRESHOLD
    close_hedge_on_end: bool = True


def fetch_price_history(ticker: str, start: date, end: date) -> pd.DataFrame:
    """Fetch daily OHLC history. The end date is inclusive for callers."""
    yf_end = end + timedelta(days=1)
    hist = yf.Ticker(ticker).history(start=start.isoformat(), end=yf_end.isoformat())
    if hist.empty:
        raise ValueError(f"No price history returned for {ticker} from {start} to {end}.")
    return _normalize_history(hist)


def load_price_history(path: str | Path) -> pd.DataFrame:
    """Load OHLC history from CSV with Date and Close columns."""
    df = pd.read_csv(path)
    if "Date" not in df.columns or "Close" not in df.columns:
        raise ValueError("CSV must include at least Date and Close columns.")
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.set_index("Date").sort_index()
    return _normalize_history(df)


def _normalize_history(hist: pd.DataFrame) -> pd.DataFrame:
    hist = hist.copy()
    hist.index = pd.to_datetime(hist.index).tz_localize(None)
    hist = hist.sort_index()
    if "Close" not in hist.columns:
        raise ValueError("Price history must include a Close column.")
    return hist[["Close"]].dropna()


def _annualized_hv(closes: pd.Series, window: int, fallback: float) -> pd.Series:
    returns = np.log(closes / closes.shift(1))
    hv = returns.rolling(window).std() * np.sqrt(252)
    return hv.ffill().fillna(fallback)


def _strategy_legs(strategy: str, contracts: int, target_abs_delta: float) -> list[OptionLegSpec]:
    strategy = strategy.lower()
    if strategy == "short_call":
        return [OptionLegSpec("call", "short", contracts, target_abs_delta)]
    if strategy == "short_put":
        return [OptionLegSpec("put", "short", contracts, target_abs_delta)]
    if strategy == "short_strangle":
        return [
            OptionLegSpec("call", "short", contracts, target_abs_delta),
            OptionLegSpec("put", "short", contracts, target_abs_delta),
        ]
    raise ValueError("strategy must be one of: short_call, short_put, short_strangle")


def _strike_for_target_delta(
    spot: float,
    target_abs_delta: float,
    t_years: float,
    rfr: float,
    iv: float,
    option_type: str,
) -> float:
    if option_type == "call":
        d1 = norm.ppf(target_abs_delta)
    else:
        d1 = norm.ppf(1 - target_abs_delta)
    strike = spot * np.exp((rfr + 0.5 * iv**2) * t_years - d1 * iv * np.sqrt(t_years))
    return round(float(strike), 2)


def _signed_multiplier(leg: OptionLegSpec) -> int:
    direction = 1 if leg.side == "long" else -1
    return direction * leg.contracts * SHARES_PER_CONTRACT


def run_short_option_backtest(config: BacktestConfig, prices: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run one short-dated option cycle over the supplied price history."""
    prices = _normalize_history(prices)
    fallback_vol = max(config.min_iv / config.iv_markup, 0.01)
    prices["hv"] = _annualized_hv(prices["Close"], config.hv_window, fallback_vol)
    prices["model_iv"] = (prices["hv"] * config.iv_markup).clip(lower=config.min_iv)
    prices = prices.loc[
        (prices.index.date >= config.start) & (prices.index.date <= config.end)
    ].copy()
    if len(prices) < 2:
        raise ValueError("Backtest needs at least two trading days of price history.")

    entry_dt = prices.index[0]
    expiry_dt = min(entry_dt + timedelta(days=config.target_dte), prices.index[-1])
    entry_spot = float(prices["Close"].iloc[0])
    entry_iv = float(prices["model_iv"].iloc[0])
    entry_t = max((expiry_dt.date() - entry_dt.date()).days, 0) / 365

    legs = _strategy_legs(config.strategy, config.contracts, config.target_abs_delta)
    leg_rows = []
    cash = 0.0
    shares = 0

    for leg in legs:
        strike = _strike_for_target_delta(
            entry_spot,
            leg.target_abs_delta,
            entry_t,
            config.risk_free_rate,
            entry_iv,
            leg.option_type,
        )
        price = bs_price(entry_spot, strike, entry_t, config.risk_free_rate, entry_iv, leg.option_type)
        signed_mult = _signed_multiplier(leg)
        cash -= price * signed_mult
        leg_rows.append({
            "type": leg.option_type,
            "side": leg.side,
            "contracts": leg.contracts,
            "strike": strike,
            "entry_price": round(price, 4),
            "entry_iv": round(entry_iv, 4),
            "target_abs_delta": leg.target_abs_delta,
            "expiry": expiry_dt.date().isoformat(),
        })

    initial_equity = None
    rows = []

    for dt, row in prices.iterrows():
        spot = float(row["Close"])
        iv = float(row["model_iv"])
        dte = max((expiry_dt.date() - dt.date()).days, 0)
        t_years = dte / 365

        option_delta = 0.0
        option_gamma = 0.0
        option_theta = 0.0
        option_vega = 0.0
        option_value = 0.0

        for leg_row in leg_rows:
            signed_mult = (1 if leg_row["side"] == "long" else -1) * leg_row["contracts"] * SHARES_PER_CONTRACT
            greeks = calculate_greeks(
                spot,
                float(leg_row["strike"]),
                t_years,
                config.risk_free_rate,
                iv,
                str(leg_row["type"]),
            )
            option_delta += greeks.delta * signed_mult
            option_gamma += greeks.gamma * signed_mult
            option_theta += greeks.theta * signed_mult
            option_vega += greeks.vega * signed_mult
            option_value += greeks.option_price * signed_mult

        hedge = calculate_hedge(option_delta, shares, config.ticker)
        shares_traded = 0
        if dte > 0 and abs(hedge.portfolio_delta) > config.rebalance_threshold:
            shares_traded = hedge.shares_needed
            cash -= shares_traded * spot
            shares += shares_traded

        equity = cash + shares * spot + option_value
        if initial_equity is None:
            initial_equity = equity

        rows.append({
            "date": dt.date().isoformat(),
            "spot": round(spot, 4),
            "dte": dte,
            "model_iv": round(iv, 4),
            "option_value": round(option_value, 2),
            "option_delta": round(option_delta, 2),
            "option_gamma": round(option_gamma, 4),
            "option_theta": round(option_theta, 2),
            "option_vega": round(option_vega, 2),
            "hedge_shares": shares,
            "shares_traded": shares_traded,
            "cash": round(cash, 2),
            "equity": round(equity, 2),
            "pnl": round(equity - initial_equity, 2),
            "hedge_signal": hedge.signal if shares_traded else "HOLD",
        })

    results = pd.DataFrame(rows)

    if config.close_hedge_on_end and shares != 0:
        final_spot = float(prices["Close"].iloc[-1])
        close_trade = -shares
        cash += shares * final_spot
        shares = 0
        final_equity = cash + float(results.iloc[-1]["option_value"])
        results.loc[results.index[-1], "hedge_shares"] = 0
        results.loc[results.index[-1], "shares_traded"] = int(results.iloc[-1]["shares_traded"]) + close_trade
        results.loc[results.index[-1], "cash"] = round(cash, 2)
        results.loc[results.index[-1], "equity"] = round(final_equity, 2)
        results.loc[results.index[-1], "pnl"] = round(final_equity - initial_equity, 2)
        results.loc[results.index[-1], "hedge_signal"] = "CLOSE"

    return pd.DataFrame(leg_rows), results


def summarize_backtest(results: pd.DataFrame) -> dict[str, float]:
    equity = results["equity"].astype(float)
    pnl = results["pnl"].astype(float)
    peak = equity.cummax()
    drawdown = equity - peak
    trades = int((results["shares_traded"] != 0).sum())
    return {
        "final_pnl": float(pnl.iloc[-1]),
        "max_drawdown": float(drawdown.min()),
        "hedge_trades": trades,
        "avg_abs_option_delta": float(results["option_delta"].abs().mean()),
        "ending_equity": float(equity.iloc[-1]),
    }


def run_parameter_sweep(
    base_config: BacktestConfig,
    prices: pd.DataFrame,
    strategies: list[str],
    target_dtes: list[int],
    target_deltas: list[float],
    iv_markups: list[float],
) -> pd.DataFrame:
    """Run a grid search over short-option strategy parameters."""
    rows = []
    for strategy, target_dte, target_delta, iv_markup in product(
        strategies,
        target_dtes,
        target_deltas,
        iv_markups,
    ):
        config = BacktestConfig(
            ticker=base_config.ticker,
            start=base_config.start,
            end=base_config.end,
            strategy=strategy,
            target_dte=target_dte,
            target_abs_delta=target_delta,
            contracts=base_config.contracts,
            hv_window=base_config.hv_window,
            iv_markup=iv_markup,
            min_iv=base_config.min_iv,
            risk_free_rate=base_config.risk_free_rate,
            rebalance_threshold=base_config.rebalance_threshold,
            close_hedge_on_end=base_config.close_hedge_on_end,
        )
        legs, results = run_short_option_backtest(config, prices)
        summary = summarize_backtest(results)
        entry_credit = -float((legs["entry_price"] * legs["contracts"] * SHARES_PER_CONTRACT).sum())
        rows.append({
            "strategy": strategy,
            "target_dte": target_dte,
            "target_delta": target_delta,
            "iv_markup": iv_markup,
            "legs": len(legs),
            "entry_credit": round(abs(entry_credit), 2),
            "final_pnl": round(summary["final_pnl"], 2),
            "max_drawdown": round(summary["max_drawdown"], 2),
            "hedge_trades": int(summary["hedge_trades"]),
            "avg_abs_option_delta": round(summary["avg_abs_option_delta"], 2),
            "ending_equity": round(summary["ending_equity"], 2),
        })

    sweep = pd.DataFrame(rows)
    return sweep.sort_values(
        ["final_pnl", "max_drawdown", "hedge_trades"],
        ascending=[False, False, True],
    ).reset_index(drop=True)


def run_scenarios(results: pd.DataFrame, legs: pd.DataFrame, config: BacktestConfig) -> pd.DataFrame:
    """Shock the final marked option book across price and IV moves."""
    final = results.iloc[-1]
    spot = float(final["spot"])
    dte = int(final["dte"])
    base_iv = float(final["model_iv"])
    t_years = dte / 365
    rows = []

    for spot_move in [-0.10, -0.05, -0.03, 0.0, 0.03, 0.05, 0.10]:
        for iv_move in [-0.10, 0.0, 0.10, 0.25]:
            shocked_spot = spot * (1 + spot_move)
            shocked_iv = max(base_iv + iv_move, 0.01)
            option_value = 0.0
            option_delta = 0.0
            for _, leg in legs.iterrows():
                signed_mult = (1 if leg["side"] == "long" else -1) * int(leg["contracts"]) * SHARES_PER_CONTRACT
                greeks = calculate_greeks(
                    shocked_spot,
                    float(leg["strike"]),
                    t_years,
                    config.risk_free_rate,
                    shocked_iv,
                    str(leg["type"]),
                )
                option_value += greeks.option_price * signed_mult
                option_delta += greeks.delta * signed_mult
            rows.append({
                "spot_move": f"{spot_move:+.0%}",
                "iv_move": f"{iv_move:+.0%}",
                "spot": round(shocked_spot, 2),
                "iv": round(shocked_iv, 4),
                "option_value": round(option_value, 2),
                "option_delta": round(option_delta, 2),
            })

    return pd.DataFrame(rows)


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _parse_csv_values(value: str, cast):
    return [cast(item.strip()) for item in value.split(",") if item.strip()]


def _fetch_start_for_config(config: BacktestConfig) -> date:
    lookback_days = max(config.hv_window * 3, 90)
    return config.start - timedelta(days=lookback_days)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a short-dated option hedge harness.")
    parser.add_argument("--ticker", default="PLTR")
    parser.add_argument("--start", default="2026-05-01")
    parser.add_argument("--end", default="2026-05-31")
    parser.add_argument("--strategy", default="short_strangle", choices=["short_call", "short_put", "short_strangle"])
    parser.add_argument("--target-dte", type=int, default=30)
    parser.add_argument("--target-delta", type=float, default=0.30)
    parser.add_argument("--contracts", type=int, default=1)
    parser.add_argument("--hv-window", type=int, default=20)
    parser.add_argument("--iv-markup", type=float, default=1.15)
    parser.add_argument("--min-iv", type=float, default=0.20)
    parser.add_argument("--price-csv", help="Optional CSV with Date and Close columns.")
    parser.add_argument("--output-dir", default="reports")
    parser.add_argument("--sweep", action="store_true", help="Run a parameter sweep instead of a single backtest.")
    parser.add_argument("--strategies", default="short_call,short_put,short_strangle")
    parser.add_argument("--target-dtes", default="14,21,30")
    parser.add_argument("--target-deltas", default="0.20,0.25,0.30")
    parser.add_argument("--iv-markups", default="1.00,1.15,1.30")
    args = parser.parse_args()

    config = BacktestConfig(
        ticker=args.ticker.upper(),
        start=_parse_date(args.start),
        end=_parse_date(args.end),
        strategy=args.strategy,
        target_dte=args.target_dte,
        target_abs_delta=args.target_delta,
        contracts=args.contracts,
        hv_window=args.hv_window,
        iv_markup=args.iv_markup,
        min_iv=args.min_iv,
    )

    prices = (
        load_price_history(args.price_csv)
        if args.price_csv
        else fetch_price_history(config.ticker, _fetch_start_for_config(config), config.end)
    )
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.sweep:
        sweep = run_parameter_sweep(
            config,
            prices,
            _parse_csv_values(args.strategies, str),
            _parse_csv_values(args.target_dtes, int),
            _parse_csv_values(args.target_deltas, float),
            _parse_csv_values(args.iv_markups, float),
        )
        prefix = f"{config.ticker}_sweep_{config.start}_{config.end}"
        sweep_path = output_dir / f"{prefix}.csv"
        sweep.to_csv(sweep_path, index=False)
        print("Short option parameter sweep complete")
        print(f"Ticker: {config.ticker}")
        print(f"Window: {config.start} to {config.end}")
        print(f"Combinations: {len(sweep)}")
        print(f"Sweep: {sweep_path}")
        print("Top 10:")
        print(sweep.head(10).to_string(index=False))
        return

    legs, results = run_short_option_backtest(config, prices)
    scenarios = run_scenarios(results, legs, config)
    summary = summarize_backtest(results)

    prefix = f"{config.ticker}_{config.strategy}_{config.start}_{config.end}"
    legs_path = output_dir / f"{prefix}_legs.csv"
    results_path = output_dir / f"{prefix}_backtest.csv"
    scenarios_path = output_dir / f"{prefix}_scenarios.csv"
    legs.to_csv(legs_path, index=False)
    results.to_csv(results_path, index=False)
    scenarios.to_csv(scenarios_path, index=False)

    print("Short option hedge harness complete")
    print(f"Ticker: {config.ticker}")
    print(f"Strategy: {config.strategy}")
    print(f"Window: {config.start} to {config.end}")
    print(f"Legs: {legs_path}")
    print(f"Backtest: {results_path}")
    print(f"Scenarios: {scenarios_path}")
    print("Summary:")
    for key, value in summary.items():
        print(f"  {key}: {value:.2f}")


if __name__ == "__main__":
    main()

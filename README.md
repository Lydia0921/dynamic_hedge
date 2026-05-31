# 📊 Option Seller Dynamic Hedge Dashboard

A real-time **dynamic delta hedging & option seller analytics dashboard** for any US equity with listed options. Built with Streamlit and powered by free yfinance data — no API key required.

Enter any ticker (PLTR, AAPL, TSLA, etc.), build your option position leg by leg, and get live portfolio Greeks, hedge signals, IV analysis, seller timing assessment, and tail risk monitoring.

## ✨ Features

### 📊 Delta Hedge (Page 1)
- **Dynamic Position Builder** — add/remove option legs (calls & puts, long & short) on the fly
- **Real-Time Portfolio Greeks** — aggregated Delta, Gamma, Theta, Vega across all legs
- **Hedge Signal** — tells you exactly how many shares to buy/sell to stay delta neutral
- **Scenario Analysis** — see P/L impact for ±1% to ±5% price moves
- **Risk Alerts** — ITM assignment warnings, gamma risk, DTE countdown
- **Trade Log** — record and track your hedge adjustments (per-ticker CSV)
- **Macro Dashboard** — VIX, US 10Y yield, S&P 500 context
- **Candlestick Chart** — 1-month price history with strike lines overlaid

### 📈 IV Analysis (Page 2)
- **Market IV vs Model IV** — residual-based comparison for each position and full chain
- **SELL / BUY Signals** — positive residual (market IV > model IV) → SELL (overpriced option)
- **Full Chain IV Scan** — scan every strike for overpricing opportunities
- **Overpriced Ratio** — % of options where market IV exceeds model IV
- **Top 10 Overpriced** — ranked list of the most overpriced contracts

### 📉 IV Statistics (Page 3)
- **IV Rank & IV Percentile** — gauge charts showing current IV position within 52-week range
- **Seller Timing Assessment** — 3-condition scoring system (IV Rank, IV vs HV, IV Percentile)
- **HV vs IV Trend Chart** — rolling HV-20/HV-30 vs current ATM IV over the past year
- **IV Term Structure** — ATM IV across different expiry dates (contango vs backwardation)

### ⚠️ Tail Risk (Page 4)
- **IV Skew / Smile Curve** — call & put IV across strikes, visualizing market fear
- **Put-Call IV Differential** — quantified skew at each strike
- **OTM Overpricing Statistics** — market price vs Black-Scholes theoretical price for OTM options
- **Aggregate Chain Analysis** — SELL/BUY/NEUTRAL signal distribution with pie chart

## 🚀 Quick Start

```bash
# Clone the repo
git clone https://github.com/YOUR_USERNAME/DynamicHedging.git
cd DynamicHedging

# Install dependencies
pip install -r requirements.txt

# Run the dashboard
streamlit run app.py
```

Then open http://localhost:8501 in your browser.

## 📦 Requirements

- Python 3.10+
- See [requirements.txt](requirements.txt) for packages:
  - `streamlit` — dashboard framework
  - `yfinance` — free market data
  - `plotly` — interactive charts
  - `scipy` — Black-Scholes Greeks & IV solver
  - `pandas`, `numpy` — data processing

## 🎯 How to Use

1. **Enter a ticker** on the home page (e.g. `PLTR`) and click **載入標的**
2. **Navigate pages** using the left sidebar:
   - **📊 Delta Hedge** — build positions, monitor Greeks, get hedge signals
   - **📈 IV Analysis** — compare market IV vs model IV, find overpriced options
   - **📉 IV Statistics** — check IV Rank/Percentile, assess seller timing
   - **⚠️ Tail Risk** — analyze skew, OTM overpricing, tail risk levels
3. **Add option legs** on the Delta Hedge page using the Position Builder
4. **Monitor seller signals** — look for SELL signals (positive IV residuals) on IV Analysis
5. **Record trades** using the Trade Log to maintain position memory across sessions

## 🏗️ Architecture

```
app.py                          — Multi-page entry point, shared state & home page
pages/
├── 1_📊_Delta_Hedge.py         — Position builder, Greeks, hedge signals, scenarios
├── 2_📈_IV_Analysis.py         — Market IV vs Model IV, residual signals, chain scan
├── 3_📉_IV_Statistics.py       — IV Rank/Percentile, HV trends, seller timing
└── 4_⚠️_Tail_Risk.py          — Skew, OTM overpricing, tail risk stats

volatility_model.py             — HV engine, IV ranking, residual signals, chain analysis
greeks.py                       — Black-Scholes pricer, Greeks calculator, IV solver
hedging.py                      — Delta hedge engine (signal generation)
data.py                         — Market data layer (yfinance wrappers)
config.py                       — Global constants (thresholds, HV windows, IV params)
trade_log.py                    — CSV-based trade recording system
macro.py                        — VIX, yields, S&P 500 macro indicators
```

### Seller Signal Logic

```
Model IV = EWMA-weighted Historical Volatility (30-day)
Residual = Market IV − Model IV
  → Residual > +3%  → SELL signal (option overpriced)
  → Residual < −3%  → BUY signal (option underpriced)
  → Otherwise       → NEUTRAL
```

## ⚠️ Disclaimer

This tool is for **educational and paper trading purposes only**. It uses the European Black-Scholes model which may not perfectly reflect American-style option pricing. Always verify with your broker's data before making real trades.

## 📄 License

MIT


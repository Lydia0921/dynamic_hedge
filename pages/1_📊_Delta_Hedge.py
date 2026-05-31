"""Page 1: Delta Hedge Dashboard — position builder, Greeks, hedge signal, scenarios."""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date, datetime

from config import SHARES_PER_CONTRACT, REFRESH_INTERVAL, GAMMA_WARNING_THRESHOLD
from data import (
    get_spot_price, get_risk_free_rate, get_option_market_price,
    get_historical_prices, get_available_expiries, get_available_strikes,
    days_to_expiry, time_to_expiry,
)
from greeks import calculate_greeks, implied_volatility
from hedging import calculate_hedge
from trade_log import log_trade, read_trades, save_positions
from macro import get_macro_summary

# ── Guard ──
if "ticker" not in st.session_state:
    st.warning("請先從首頁載入標的。")
    st.stop()

ticker = st.session_state.ticker
positions = st.session_state.positions

# ──────────────────────────────────────────────
# Sidebar — Position Builder (page-specific)
# ──────────────────────────────────────────────
if st.session_state.ticker_valid and ticker:
    st.sidebar.divider()
    st.sidebar.subheader("📐 建立期權部位")

    expiries = get_available_expiries(ticker)
    if expiries:
        selected_expiry = st.sidebar.selectbox("到期日 (Expiry Date)", expiries)

        opt_type = st.sidebar.selectbox("選擇權類型", ["call", "put"])

        strikes = get_available_strikes(ticker, selected_expiry, opt_type)
        if strikes:
            selected_strike = st.sidebar.selectbox("履約價 (Strike Price)", strikes)
        else:
            selected_strike = st.sidebar.number_input("履約價 (Strike Price)", min_value=0.01, value=100.0, step=1.0)

        opt_side = st.sidebar.selectbox("買賣方向 (Side)", ["long", "short"])
        opt_contracts = st.sidebar.number_input("口數 (Contracts)", min_value=1, value=1, step=1)

        if st.sidebar.button("➕ 新增部位"):
            new_leg = {
                "strike": float(selected_strike),
                "expiry": selected_expiry,
                "type": opt_type,
                "contracts": int(opt_contracts),
                "side": opt_side,
            }
            st.session_state.positions.append(new_leg)
            save_positions(ticker, st.session_state.positions)
            st.sidebar.success(f"已新增: {opt_side} {opt_contracts}口 ${selected_strike} {opt_type}")
    else:
        st.sidebar.warning("此標的目前沒有可用的選擇權資料。")

    # ── Display current legs ──
    if st.session_state.positions:
        st.sidebar.divider()
        st.sidebar.subheader("📋 目前部位")
        for i, pos in enumerate(st.session_state.positions):
            label = f"{pos['side'].capitalize()} {pos['contracts']}口 ${pos['strike']} {pos['type'].upper()} ({pos['expiry']})"
            col_label, col_del = st.sidebar.columns([4, 1])
            col_label.write(label)
            if col_del.button("🗑️", key=f"del_{i}"):
                st.session_state.positions.pop(i)
                save_positions(ticker, st.session_state.positions)
                st.rerun()

    # ── Hedge shares & cash ──
    st.sidebar.divider()
    st.sidebar.subheader("💰 帳戶資金")
    st.session_state.hedge_shares = st.sidebar.number_input(
        "目前持有避險股數", min_value=0, max_value=50000,
        value=st.session_state.hedge_shares, step=10,
        help="你目前為了對沖而持有的現股數量"
    )
    st.session_state.cash_balance = st.sidebar.number_input(
        "可用現金餘額", min_value=0.0,
        value=st.session_state.cash_balance, step=100.0, format="%.2f",
    )

    # ── Auto refresh ──
    st.sidebar.divider()
    auto_refresh = st.sidebar.checkbox("自動更新 (Auto-refresh)", value=False)

# ══════════════════════════════════════════════
# MAIN AREA
# ══════════════════════════════════════════════

st.title(f"📊 {ticker} 動態 Delta 避險監控")

col_refresh, col_time = st.columns([1, 5])
with col_refresh:
    if st.button("🔄 刷新數據"):
        st.cache_data.clear()
with col_time:
    st.write(f"**最後更新時間：** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# ── Fetch spot & risk-free rate ──
with st.spinner("正在獲取市場數據..."):
    spot = get_spot_price(ticker)
    rfr = get_risk_free_rate()

current_shares = st.session_state.hedge_shares
cash_balance = st.session_state.cash_balance
positions = st.session_state.positions

# ── Check if there are positions ──
if not positions:
    col1, col2 = st.columns(2)
    col1.metric(f"{ticker} 現價", f"${spot:.2f}")
    col2.metric("部位狀態", "無 — 請從側邊欄新增")
    st.info("👈 請使用側邊欄的 **建立期權部位** 來新增你的部位。")

    st.subheader("歷史走勢圖 (1個月)")
    hist = get_historical_prices(ticker, period="1mo")
    if not hist.empty:
        fig = go.Figure()
        fig.add_trace(go.Candlestick(
            x=hist.index, open=hist["Open"], high=hist["High"],
            low=hist["Low"], close=hist["Close"], name=ticker,
        ))
        fig.update_layout(height=400, xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)
    st.stop()

# ══════════════════════════════════════════════
# PORTFOLIO GREEKS CALCULATION
# ══════════════════════════════════════════════

portfolio_position_delta = 0.0
portfolio_gamma = 0.0
portfolio_theta = 0.0
portfolio_vega = 0.0

positions_data = []
nearest_dte = 999

for pos in positions:
    expiry_date = date.fromisoformat(pos['expiry'])
    T = time_to_expiry(expiry_date)
    dte = days_to_expiry(expiry_date)
    nearest_dte = min(nearest_dte, dte)

    market_price = get_option_market_price(ticker, expiry_date, pos['strike'], pos['type'])

    if market_price and market_price > 0:
        iv = implied_volatility(market_price, spot, pos['strike'], T, rfr, pos['type'])
    else:
        iv = 0.50
        market_price = None

    greeks = calculate_greeks(spot, pos['strike'], T, rfr, iv, pos['type'])

    multiplier = pos['contracts'] * SHARES_PER_CONTRACT
    direction = 1 if pos['side'] == 'long' else -1

    pos_delta = greeks.delta * multiplier * direction
    pos_gamma = greeks.gamma * multiplier * direction
    pos_theta = greeks.theta * multiplier * direction
    pos_vega = greeks.vega * multiplier * direction

    portfolio_position_delta += pos_delta
    portfolio_gamma += pos_gamma
    portfolio_theta += pos_theta
    portfolio_vega += pos_vega

    positions_data.append({
        "Strike": pos['strike'],
        "Expiry": pos['expiry'],
        "Side": pos['side'],
        "Contracts": pos['contracts'],
        "Type": pos['type'].upper(),
        "DTE": dte,
        "IV": f"{iv*100:.1f}%",
        "Market Price": f"${market_price:.2f}" if market_price else "N/A",
        "Delta": f"{pos_delta:.1f}",
        "Gamma": f"{pos_gamma:.1f}",
        "Theta": f"${pos_theta:.1f}",
        "Vega": f"${pos_vega:.1f}",
    })

# ── Hedge Calculation ──
hedge = calculate_hedge(portfolio_position_delta, current_shares, ticker)

# ── Top Row: Key Metrics ──
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric(f"{ticker} 現價", f"${spot:.2f}")
col2.metric("最近到期天數 (DTE)", f"{nearest_dte} 天")
col3.metric("總 Theta (每日)", f"${portfolio_theta:.2f}")
col4.metric("總 Vega", f"${portfolio_vega:.2f}")
col5.metric("總 Gamma", f"{portfolio_gamma:.2f}")

st.divider()

# ── Portfolio Details ──
st.subheader("投資組合明細")
st.dataframe(pd.DataFrame(positions_data), use_container_width=True, hide_index=True)

st.divider()

# ── Hedge Signal ──
st.subheader("避險信號")

signal_color = {"BUY": "🟢", "SELL": "🔴", "HOLD": "⚪"}
st.markdown(f"### {signal_color.get(hedge.signal, '')} {hedge.signal_detail}")

hcol1, hcol2, hcol3 = st.columns(3)
hcol1.metric("期權總 Delta", f"{hedge.position_delta:.1f}")
hcol2.metric("目前避險股數", f"{hedge.current_shares}")
hcol3.metric("組合淨 Delta", f"{hedge.portfolio_delta:.1f}",
             delta="需要再平衡" if hedge.rebalance_needed else "Delta 中立",
             delta_color="inverse" if hedge.rebalance_needed else "normal")

if hedge.rebalance_needed:
    cost = hedge.shares_needed * spot if hedge.shares_needed > 0 else 0
    st.warning(f"⚠️ 淨 Delta 已超過門檻！建議 {'買入' if hedge.shares_needed > 0 else '賣出'} "
               f"{abs(hedge.shares_needed)} 股現貨")
    if cost > 0:
        affordable = "✅ 現金充足" if cash_balance >= cost else "❌ 現金不足"
        st.info(f"預估花費: ${cost:,.0f} | 帳戶可用餘額: ${cash_balance:,.2f} | {affordable}")

st.divider()

# ── Risk Scenarios (percentage-based) ──
st.subheader("情境分析")

scenarios = []
for pct_move in [-5, -3, -1, 0, 1, 3, 5]:
    price_move = spot * pct_move / 100
    new_spot = spot + price_move

    new_port_delta = 0.0
    for pos in positions:
        expiry_date = date.fromisoformat(pos['expiry'])
        T = time_to_expiry(expiry_date)
        greeks = calculate_greeks(new_spot, pos['strike'], T, rfr, 0.50, pos['type'])
        multiplier = pos['contracts'] * SHARES_PER_CONTRACT
        direction = 1 if pos['side'] == 'long' else -1
        new_port_delta += greeks.delta * multiplier * direction

    new_hedge = calculate_hedge(new_port_delta, current_shares, ticker)

    pnl_options = portfolio_position_delta * price_move
    pnl_shares = price_move * current_shares
    scenarios.append({
        "漲跌幅": f"{pct_move:+d}%",
        "模擬股價": f"${new_spot:.2f}",
        "新期權 Delta": f"{new_port_delta:.1f}",
        "期權 P/L": f"${pnl_options:.0f}",
        "現貨 P/L": f"${pnl_shares:.0f}",
        "總淨 P/L": f"${pnl_options + pnl_shares:.0f}",
        "後續動作": new_hedge.signal_detail,
    })

st.dataframe(pd.DataFrame(scenarios), use_container_width=True, hide_index=True)

# ── Price Chart ──
st.subheader("歷史走勢圖 (1個月)")
hist = get_historical_prices(ticker, period="1mo")
if not hist.empty:
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=hist.index, open=hist["Open"], high=hist["High"],
        low=hist["Low"], close=hist["Close"], name=ticker,
    ))
    for pos in positions:
        color = "green" if pos['side'] == 'long' else "red"
        fig.add_hline(y=pos['strike'], line_dash="dash", line_color=color,
                      annotation_text=f"{pos['side'].capitalize()} ${pos['strike']}")
    fig.update_layout(height=400, xaxis_rangeslider_visible=False)
    st.plotly_chart(fig, use_container_width=True)

# ── Alerts ──
st.subheader("風險警示")
alerts = []
if nearest_dte <= 7:
    alerts.append("🔴 距離到期不足 7 天 — Gamma 風險正在加劇，注意 Pin Risk (釘住風險)")
if abs(portfolio_gamma) > GAMMA_WARNING_THRESHOLD * SHARES_PER_CONTRACT:
    alerts.append(f"🟡 淨 Gamma 偏高 ({portfolio_gamma:.1f}) — Delta 的跳動速度會很快")
for pos in positions:
    if pos['side'] == 'short' and spot > pos['strike'] and pos['type'] == 'call':
        alerts.append(f"🔴 ${pos['strike']} Short Call 已進入價內 (ITM) — 有被履約指派的風險")
    if pos['side'] == 'short' and spot < pos['strike'] and pos['type'] == 'put':
        alerts.append(f"🔴 ${pos['strike']} Short Put 已進入價內 (ITM) — 有被履約指派的風險")

if alerts:
    for a in alerts:
        st.markdown(a)
else:
    st.success("✅ 目前無重大風險警示")

# ── Macro Indicators ──
st.divider()
st.subheader("總經指標")
macro = get_macro_summary()
mcol1, mcol2, mcol3 = st.columns(3)
mcol1.metric("VIX (恐慌指數)", f"{macro['vix']:.2f}")
mcol2.metric("美債 10 年期殖利率", f"{macro['us10y']:.2f}%")
mcol3.metric("S&P 500 單日漲跌", f"{macro['sp500_chg']:+.2f}%")

# ── Trade Log ──
st.divider()
st.subheader("交易紀錄")

with st.expander("📝 記錄新交易", expanded=False):
    with st.form("trade_form"):
        tcol1, tcol2, tcol3 = st.columns(3)
        with tcol1:
            t_action = st.selectbox("動作 (Action)", ["BUY", "SELL", "HOLD"])
            t_quantity = st.number_input("數量 (股)", min_value=0, value=abs(hedge.shares_needed), step=10)
        with tcol2:
            t_strategy = st.selectbox("策略 (Strategy)", ["delta_hedge", "roll", "spread", "close", "other"])
            t_price = st.number_input("成交價", min_value=0.0, value=float(spot), step=0.01, format="%.2f")
        with tcol3:
            t_reason = st.text_input("原因 (Reason)", value=hedge.signal_detail)
            t_notes = st.text_input("備註 (Notes)", value="")

        submitted = st.form_submit_button("💾 儲存紀錄")
        if submitted:
            cost = t_quantity * t_price if t_action == "BUY" else -(t_quantity * t_price)
            log_trade(
                ticker=ticker,
                action=t_action,
                instrument=ticker,
                quantity=t_quantity,
                price=t_price,
                strategy=t_strategy,
                reason=t_reason,
                spot_price=spot,
                delta=portfolio_position_delta,
                gamma=portfolio_gamma,
                theta=portfolio_theta,
                vega=portfolio_vega,
                iv=0.0,
                dte=nearest_dte,
                portfolio_delta=hedge.portfolio_delta,
                vix=macro["vix"],
                us10y=macro["us10y"],
                cash_before=cash_balance,
                cash_after=cash_balance - cost,
                notes=t_notes,
            )
            if t_action == "BUY":
                st.session_state.hedge_shares += t_quantity
            elif t_action == "SELL":
                st.session_state.hedge_shares = max(0, st.session_state.hedge_shares - t_quantity)
            st.session_state.cash_balance -= cost
            st.success(f"✅ 紀錄成功: {t_action} {t_quantity} 股 @ ${t_price:.2f}")
            st.rerun()

trades_df = read_trades(ticker)
if not trades_df.empty:
    st.dataframe(
        trades_df.sort_values("timestamp", ascending=False).head(20),
        use_container_width=True,
        hide_index=True,
    )

# ── Auto Refresh ──
if st.session_state.get("ticker_valid") and auto_refresh:
    import time
    time.sleep(REFRESH_INTERVAL)
    st.rerun()

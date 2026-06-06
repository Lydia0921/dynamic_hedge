"""Page 3: IV Statistics — IV Rank, IV Percentile, HV vs IV trends, seller timing."""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from config import IV_RANK_SELL_THRESHOLD
from data import get_spot_price, get_available_expiries, get_historical_closes
from volatility_model import (
    calc_historical_volatility,
    calc_hv_series,
    calc_iv_rank,
    calc_iv_percentile,
    calc_model_iv,
    estimate_current_atm_iv,
)

# ── Guard: auto-init if navigated directly ──
if "ticker" not in st.session_state:
    from trade_log import get_current_state, load_positions
    st.session_state.ticker = "PLTR"
    st.session_state.ticker_valid = True
    st.session_state.positions = load_positions("PLTR")
    saved_shares, saved_cash = get_current_state("PLTR")
    st.session_state.hedge_shares = saved_shares
    st.session_state.cash_balance = saved_cash

ticker = st.session_state.ticker

st.title(f"📉 {ticker} IV 統計 — 賣方時機判斷")

# ── Fetch data ──
with st.spinner("正在計算 IV 統計..."):
    spot = get_spot_price(ticker)
    hv_dict = calc_historical_volatility(ticker)
    hv_30_series = calc_hv_series(ticker, window=30)
    hv_20_series = calc_hv_series(ticker, window=20)
    model_iv = calc_model_iv(ticker, window=30)

    # Estimate current ATM IV from nearest expiry
    expiries = get_available_expiries(ticker)
    if expiries:
        current_atm_iv = estimate_current_atm_iv(ticker, expiries[0])
        atm_expiry_label = expiries[0]
    else:
        current_atm_iv = 0.0
        atm_expiry_label = "N/A"

# ══════════════════════════════════════════════
# Section 1: IV Rank & Percentile
# ══════════════════════════════════════════════
st.subheader("📊 IV Rank & IV Percentile")

# Estimate 52-week IV range from HV series as proxy
if not hv_30_series.empty:
    hv_clean = hv_30_series.dropna()
    if not hv_clean.empty:
        iv_high_52w = float(hv_clean.max())
        iv_low_52w = float(hv_clean.min())
    else:
        iv_high_52w = current_atm_iv
        iv_low_52w = current_atm_iv
else:
    iv_high_52w = current_atm_iv
    iv_low_52w = current_atm_iv

iv_rank = calc_iv_rank(current_atm_iv, iv_high_52w, iv_low_52w)
iv_percentile = calc_iv_percentile(current_atm_iv, hv_30_series.dropna()) if not hv_30_series.empty else 0.0

# ── Gauge Charts ──
gauge_col1, gauge_col2 = st.columns(2)

with gauge_col1:
    fig_rank = go.Figure(go.Indicator(
        mode="gauge+number",
        value=iv_rank,
        number={"suffix": "%"},
        title={"text": "IV Rank (52 週)"},
        gauge={
            "axis": {"range": [0, 100]},
            "bar": {"color": "#3b82f6"},
            "steps": [
                {"range": [0, 30], "color": "#dcfce7"},
                {"range": [30, 50], "color": "#fef9c3"},
                {"range": [50, 75], "color": "#fed7aa"},
                {"range": [75, 100], "color": "#fecaca"},
            ],
            "threshold": {
                "line": {"color": "red", "width": 3},
                "thickness": 0.75,
                "value": IV_RANK_SELL_THRESHOLD,
            },
        },
    ))
    fig_rank.update_layout(height=280)
    st.plotly_chart(fig_rank, use_container_width=True)

with gauge_col2:
    fig_pct = go.Figure(go.Indicator(
        mode="gauge+number",
        value=iv_percentile,
        number={"suffix": "%"},
        title={"text": "IV Percentile (52 週)"},
        gauge={
            "axis": {"range": [0, 100]},
            "bar": {"color": "#8b5cf6"},
            "steps": [
                {"range": [0, 30], "color": "#dcfce7"},
                {"range": [30, 50], "color": "#fef9c3"},
                {"range": [50, 75], "color": "#fed7aa"},
                {"range": [75, 100], "color": "#fecaca"},
            ],
            "threshold": {
                "line": {"color": "red", "width": 3},
                "thickness": 0.75,
                "value": IV_RANK_SELL_THRESHOLD,
            },
        },
    ))
    fig_pct.update_layout(height=280)
    st.plotly_chart(fig_pct, use_container_width=True)

# ── Key Metrics ──
kcol1, kcol2, kcol3, kcol4 = st.columns(4)
kcol1.metric("當前 ATM IV", f"{current_atm_iv*100:.1f}%", help=f"來源: {atm_expiry_label} 最接近 ATM 的 Call")
kcol2.metric("52 週 IV 高點", f"{iv_high_52w*100:.1f}%")
kcol3.metric("52 週 IV 低點", f"{iv_low_52w*100:.1f}%")
kcol4.metric("模型 IV (EWMA HV-30)", f"{model_iv*100:.1f}%")

st.divider()

# ══════════════════════════════════════════════
# Section 2: Seller Timing Assessment
# ══════════════════════════════════════════════
st.subheader("🎯 賣方時機評估")

conditions = []
score = 0

# Condition 1: IV Rank
if iv_rank > IV_RANK_SELL_THRESHOLD:
    conditions.append(("✅", f"IV Rank = {iv_rank:.0f}% > {IV_RANK_SELL_THRESHOLD}%", "IV 處於歷史高位，有利賣方"))
    score += 1
else:
    conditions.append(("❌", f"IV Rank = {iv_rank:.0f}% ≤ {IV_RANK_SELL_THRESHOLD}%", "IV 偏低，賣方優勢不明顯"))

# Condition 2: Market IV > HV
hv_30 = hv_dict.get(30, 0)
if current_atm_iv > hv_30 and hv_30 > 0:
    premium_pct = (current_atm_iv / hv_30 - 1) * 100
    conditions.append(("✅", f"ATM IV ({current_atm_iv*100:.1f}%) > HV-30 ({hv_30*100:.1f}%)", f"IV 溢價 {premium_pct:.0f}%，選擇權被市場高估"))
    score += 1
else:
    conditions.append(("❌", f"ATM IV ({current_atm_iv*100:.1f}%) ≤ HV-30 ({hv_30*100:.1f}%)", "IV 未高於 HV，高估程度不足"))

# Condition 3: IV Percentile
if iv_percentile > 60:
    conditions.append(("✅", f"IV Percentile = {iv_percentile:.0f}%", "多數時間 IV 低於當前水準"))
    score += 1
else:
    conditions.append(("❌", f"IV Percentile = {iv_percentile:.0f}%", "IV 並非處於多數歷史日的高位"))

# Display assessment
for emoji, condition, explanation in conditions:
    st.markdown(f"{emoji} **{condition}** — {explanation}")

st.markdown("---")

if score == 3:
    st.success("🟢 **賣方時機評估：極佳** — 所有條件都滿足，IV 高位 + 市場高估 + 歷史分位高")
elif score == 2:
    st.info("🟡 **賣方時機評估：尚可** — 多數條件滿足，可選擇性進場")
elif score == 1:
    st.warning("🟠 **賣方時機評估：謹慎** — 條件不足，建議等待更佳時機")
else:
    st.error("🔴 **賣方時機評估：不利** — 目前不適合賣方策略")

st.divider()

# ══════════════════════════════════════════════
# Section 3: HV vs IV Trend Chart
# ══════════════════════════════════════════════
st.subheader("📈 HV vs IV 歷史走勢")

if not hv_30_series.empty:
    fig_trend = go.Figure()

    # HV-20
    if not hv_20_series.empty:
        fig_trend.add_trace(go.Scatter(
            x=hv_20_series.index,
            y=hv_20_series.values * 100,
            mode="lines",
            name="HV-20",
            line=dict(color="#22c55e", width=1.5),
            opacity=0.7,
        ))

    # HV-30
    fig_trend.add_trace(go.Scatter(
        x=hv_30_series.index,
        y=hv_30_series.values * 100,
        mode="lines",
        name="HV-30",
        line=dict(color="#3b82f6", width=2),
    ))

    # Current ATM IV as horizontal reference
    if current_atm_iv > 0:
        fig_trend.add_hline(
            y=current_atm_iv * 100,
            line_dash="dash",
            line_color="#f59e0b",
            annotation_text=f"當前 ATM IV: {current_atm_iv*100:.1f}%",
        )

    fig_trend.update_layout(
        title="滾動歷史波動率 vs 當前隱含波動率",
        xaxis_title="日期",
        yaxis_title="波動率 (%)",
        height=450,
        template="plotly_dark",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    st.plotly_chart(fig_trend, use_container_width=True)

    st.caption("💡 **判讀**：當 ATM IV 線在 HV 線上方 → 市場 IV 溢價（賣方有利）。差距越大，賣方 edge 越明顯。")
else:
    st.warning("歷史數據不足，無法繪製 HV 走勢。")

st.divider()

# ══════════════════════════════════════════════
# Section 4: IV Term Structure
# ══════════════════════════════════════════════
st.subheader("📐 IV 期限結構 (Term Structure)")

if expiries and len(expiries) >= 2:
    with st.spinner("正在計算各到期日 ATM IV..."):
        term_data = []
        for exp in expiries[:10]:  # limit to 10 expiries for performance
            atm_iv = estimate_current_atm_iv(ticker, exp)
            if atm_iv > 0:
                from datetime import date as dt_date
                dte = (dt_date.fromisoformat(exp) - dt_date.today()).days
                term_data.append({
                    "expiry": exp,
                    "dte": dte,
                    "atm_iv": atm_iv * 100,
                })

    if term_data:
        term_df = pd.DataFrame(term_data)

        fig_term = go.Figure()
        fig_term.add_trace(go.Scatter(
            x=term_df["dte"],
            y=term_df["atm_iv"],
            mode="markers+lines",
            marker=dict(size=10, color="#8b5cf6"),
            line=dict(color="#8b5cf6", width=2),
            text=term_df["expiry"],
            hovertemplate="到期日: %{text}<br>DTE: %{x}<br>ATM IV: %{y:.1f}%",
        ))
        fig_term.update_layout(
            title="ATM IV vs DTE — 期限結構",
            xaxis_title="DTE (天)",
            yaxis_title="ATM IV (%)",
            height=400,
            template="plotly_dark",
        )
        st.plotly_chart(fig_term, use_container_width=True)

        st.caption("💡 **正常形態**：遠月 IV > 近月 IV（正斜率）。反轉代表近期事件風險被高度定價。")
    else:
        st.warning("無法計算 ATM IV。")
else:
    st.info("可用到期日不足，無法繪製期限結構。")

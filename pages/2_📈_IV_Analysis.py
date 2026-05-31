"""Page 2: IV Analysis — Market IV vs Model IV comparison with SELL/BUY signals."""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from config import IV_RESIDUAL_THRESHOLD
from data import get_spot_price, get_available_expiries
from volatility_model import (
    calc_model_iv,
    calc_historical_volatility,
    analyze_chain_iv,
    calc_overpriced_ratio,
    generate_signal,
    calc_iv_residual,
)
from greeks import implied_volatility
from data import get_option_market_price, get_risk_free_rate, time_to_expiry, days_to_expiry
from config import SHARES_PER_CONTRACT
from datetime import date

# ── Guard ──
if "ticker" not in st.session_state:
    st.warning("請先從首頁載入標的。")
    st.stop()

ticker = st.session_state.ticker

st.title(f"📈 {ticker} IV 分析 — 市場 IV vs 模型 IV")

# ── Fetch baseline data ──
with st.spinner("正在計算波動率模型..."):
    spot = get_spot_price(ticker)
    rfr = get_risk_free_rate()
    model_iv = calc_model_iv(ticker, window=30)
    hv_dict = calc_historical_volatility(ticker)

# ── Model Summary ──
st.subheader("📐 波動率模型基準")

mcol1, mcol2, mcol3, mcol4 = st.columns(4)
mcol1.metric(f"{ticker} 現價", f"${spot:.2f}")
mcol2.metric("模型 IV (EWMA HV-30)", f"{model_iv*100:.1f}%")
mcol3.metric("HV-20", f"{hv_dict.get(20, 0)*100:.1f}%")
mcol4.metric("HV-60", f"{hv_dict.get(60, 0)*100:.1f}%")

st.caption(f"殘差門檻: ±{IV_RESIDUAL_THRESHOLD*100:.0f}% — 超過此範圍才觸發 SELL/BUY 訊號")

st.divider()

# ══════════════════════════════════════════════
# Section 1: Current Position IV Residuals
# ══════════════════════════════════════════════
positions = st.session_state.positions

if positions:
    st.subheader("🔍 持倉 IV 殘差分析")

    residual_data = []
    for pos in positions:
        expiry_date = date.fromisoformat(pos['expiry'])
        T = time_to_expiry(expiry_date)
        dte = days_to_expiry(expiry_date)

        market_price = get_option_market_price(ticker, expiry_date, pos['strike'], pos['type'])

        if market_price and market_price > 0 and T > 0:
            mkt_iv = implied_volatility(market_price, spot, pos['strike'], T, rfr, pos['type'])
        else:
            mkt_iv = 0.0
            market_price = 0.0

        residual = calc_iv_residual(mkt_iv, model_iv)
        signal = generate_signal(residual)

        signal_emoji = {"SELL": "🔴", "BUY": "🟢", "NEUTRAL": "⚪"}.get(signal, "")

        residual_data.append({
            "部位": f"{pos['side'].upper()} {pos['contracts']}口 ${pos['strike']} {pos['type'].upper()}",
            "DTE": dte,
            "市場 IV": f"{mkt_iv*100:.1f}%",
            "模型 IV": f"{model_iv*100:.1f}%",
            "殘差": f"{residual*100:+.1f}%",
            "訊號": f"{signal_emoji} {signal}",
            "_residual_raw": residual,
        })

    df_residuals = pd.DataFrame(residual_data)

    # Display table (without internal column)
    st.dataframe(df_residuals.drop(columns=["_residual_raw"]), use_container_width=True, hide_index=True)

    # Residual bar chart
    fig_bar = go.Figure()
    colors = ["#ef4444" if r > 0 else "#22c55e" for r in df_residuals["_residual_raw"]]
    fig_bar.add_trace(go.Bar(
        x=df_residuals["部位"],
        y=[r * 100 for r in df_residuals["_residual_raw"]],
        marker_color=colors,
        text=[f"{r*100:+.1f}%" for r in df_residuals["_residual_raw"]],
        textposition="outside",
    ))
    fig_bar.add_hline(y=IV_RESIDUAL_THRESHOLD * 100, line_dash="dash", line_color="red",
                      annotation_text=f"SELL 門檻 (+{IV_RESIDUAL_THRESHOLD*100:.0f}%)")
    fig_bar.add_hline(y=-IV_RESIDUAL_THRESHOLD * 100, line_dash="dash", line_color="green",
                      annotation_text=f"BUY 門檻 (-{IV_RESIDUAL_THRESHOLD*100:.0f}%)")
    fig_bar.update_layout(
        title="持倉 IV 殘差（紅=高估 / 綠=低估）",
        yaxis_title="殘差 (%)",
        height=350,
        showlegend=False,
    )
    st.plotly_chart(fig_bar, use_container_width=True)

else:
    st.info("尚無持倉。殘差分析將在新增部位後顯示。")

st.divider()

# ══════════════════════════════════════════════
# Section 2: Full Chain IV Scan
# ══════════════════════════════════════════════
st.subheader("🔎 全鏈 IV 掃描")

expiries = get_available_expiries(ticker)
if not expiries:
    st.warning("無可用到期日。")
    st.stop()

selected_expiry = st.selectbox("選擇到期日", expiries, key="iv_scan_expiry")

with st.spinner("正在掃描整條 Option Chain..."):
    chain_df = analyze_chain_iv(ticker, selected_expiry)

if chain_df.empty:
    st.warning("無法取得該到期日的 Option Chain 資料。")
else:
    # ── Overpriced ratio headline ──
    overpriced_pct = calc_overpriced_ratio(chain_df)
    sell_count = (chain_df["signal"] == "SELL").sum()
    buy_count = (chain_df["signal"] == "BUY").sum()
    neutral_count = (chain_df["signal"] == "NEUTRAL").sum()

    scol1, scol2, scol3, scol4 = st.columns(4)
    scol1.metric("高估比例 (SELL)", f"{overpriced_pct:.1f}%")
    scol2.metric("🔴 SELL", f"{sell_count}")
    scol3.metric("🟢 BUY", f"{buy_count}")
    scol4.metric("⚪ NEUTRAL", f"{neutral_count}")

    if overpriced_pct > 50:
        st.success(f"📊 **{overpriced_pct:.0f}%** 的選擇權市場 IV > 模型 IV — 市場整體傾向過度定價，賣方機會偏多")
    elif overpriced_pct < 30:
        st.warning(f"📊 僅 **{overpriced_pct:.0f}%** 高估 — 目前賣方機會較少")

    # ── Filter controls ──
    filter_col1, filter_col2 = st.columns(2)
    with filter_col1:
        type_filter = st.multiselect("篩選類型", ["CALL", "PUT"], default=["CALL", "PUT"], key="chain_type_filter")
    with filter_col2:
        signal_filter = st.multiselect("篩選訊號", ["SELL", "BUY", "NEUTRAL"], default=["SELL", "BUY", "NEUTRAL"], key="chain_signal_filter")

    filtered = chain_df[
        (chain_df["type"].isin(type_filter)) &
        (chain_df["signal"].isin(signal_filter))
    ]

    # ── Display table ──
    display_df = filtered.rename(columns={
        "strike": "Strike",
        "type": "Type",
        "market_price": "市場價",
        "market_iv": "市場 IV (%)",
        "model_iv": "模型 IV (%)",
        "residual": "殘差 (%)",
        "signal": "訊號",
        "volume": "Volume",
        "open_interest": "OI",
    })
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    # ── Residual scatter plot ──
    fig_scatter = go.Figure()

    for opt_type, color in [("CALL", "#3b82f6"), ("PUT", "#f59e0b")]:
        subset = filtered[filtered["type"] == opt_type] if opt_type in type_filter else pd.DataFrame()
        if not subset.empty:
            marker_colors = ["#ef4444" if r > 0 else "#22c55e" for r in subset["residual"]]
            fig_scatter.add_trace(go.Scatter(
                x=subset["strike"],
                y=subset["residual"],
                mode="markers+lines",
                name=opt_type,
                marker=dict(color=marker_colors, size=8),
                line=dict(color=color, width=1, dash="dot"),
            ))

    fig_scatter.add_hline(y=IV_RESIDUAL_THRESHOLD * 100, line_dash="dash", line_color="red", opacity=0.5)
    fig_scatter.add_hline(y=-IV_RESIDUAL_THRESHOLD * 100, line_dash="dash", line_color="green", opacity=0.5)
    fig_scatter.add_hline(y=0, line_color="gray", opacity=0.3)
    fig_scatter.add_vline(x=spot, line_dash="dash", line_color="white", opacity=0.5,
                          annotation_text=f"Spot ${spot:.0f}")
    fig_scatter.update_layout(
        title=f"IV 殘差 vs Strike — {selected_expiry}",
        xaxis_title="Strike Price",
        yaxis_title="殘差 (%, 正=高估)",
        height=450,
        template="plotly_dark",
    )
    st.plotly_chart(fig_scatter, use_container_width=True)

    # ── Top overpriced options ──
    st.subheader("🏆 高估程度 Top 10")
    top_sell = chain_df[chain_df["signal"] == "SELL"].nlargest(10, "residual")
    if not top_sell.empty:
        st.dataframe(top_sell.rename(columns={
            "strike": "Strike", "type": "Type", "market_price": "市場價",
            "market_iv": "市場 IV (%)", "model_iv": "模型 IV (%)",
            "residual": "殘差 (%)", "signal": "訊號",
            "volume": "Volume", "open_interest": "OI",
        }), use_container_width=True, hide_index=True)
    else:
        st.info("目前沒有被高估的選擇權（殘差未超過門檻）。")

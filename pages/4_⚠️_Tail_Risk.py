"""Page 4: Tail Risk — IV skew, smile visualization, OTM overpricing statistics."""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

from data import get_spot_price, get_available_expiries, get_risk_free_rate, get_full_option_chain
from greeks import implied_volatility, bs_price
from volatility_model import calc_model_iv, analyze_chain_iv, calc_overpriced_ratio
from datetime import date

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

st.title(f"⚠️ {ticker} 尾部風險分析")

# ── Fetch baseline data ──
with st.spinner("正在獲取數據..."):
    spot = get_spot_price(ticker)
    rfr = get_risk_free_rate()
    model_iv = calc_model_iv(ticker)
    expiries = get_available_expiries(ticker)

if not expiries:
    st.warning("無可用到期日。")
    st.stop()

selected_expiry = st.selectbox("選擇到期日", expiries, key="tail_risk_expiry")

expiry_date = date.fromisoformat(selected_expiry)
dte = (expiry_date - date.today()).days
T = max(dte, 0) / 365.0

st.caption(f"現價: ${spot:.2f} | DTE: {dte} | 模型 IV: {model_iv*100:.1f}%")

st.divider()

# ══════════════════════════════════════════════
# Section 1: IV Skew / Smile Curve
# ══════════════════════════════════════════════
st.subheader("📐 IV Skew / Smile 曲線")

with st.spinner("正在計算各 Strike 的隱含波動率..."):
    chain = get_full_option_chain(ticker, selected_expiry)
    calls_df = chain["calls"]
    puts_df = chain["puts"]

    skew_data = {"calls": [], "puts": []}

    for label, df, opt_type in [("calls", calls_df, "call"), ("puts", puts_df, "put")]:
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

            iv = implied_volatility(mp, spot, strike, T, rfr, opt_type)
            if iv > 0.01:  # filter noise
                moneyness = strike / spot
                skew_data[label].append({
                    "strike": strike,
                    "iv": iv * 100,
                    "moneyness": moneyness,
                    "market_price": mp,
                })

calls_skew = pd.DataFrame(skew_data["calls"])
puts_skew = pd.DataFrame(skew_data["puts"])

if not calls_skew.empty or not puts_skew.empty:
    fig_skew = go.Figure()

    if not calls_skew.empty:
        fig_skew.add_trace(go.Scatter(
            x=calls_skew["strike"],
            y=calls_skew["iv"],
            mode="markers+lines",
            name="Call IV",
            marker=dict(color="#3b82f6", size=6),
            line=dict(color="#3b82f6", width=2),
        ))

    if not puts_skew.empty:
        fig_skew.add_trace(go.Scatter(
            x=puts_skew["strike"],
            y=puts_skew["iv"],
            mode="markers+lines",
            name="Put IV",
            marker=dict(color="#f59e0b", size=6),
            line=dict(color="#f59e0b", width=2),
        ))

    # Model IV reference
    fig_skew.add_hline(y=model_iv * 100, line_dash="dash", line_color="#22c55e",
                       annotation_text=f"模型 IV: {model_iv*100:.1f}%")

    # Spot price vertical line
    fig_skew.add_vline(x=spot, line_dash="dash", line_color="white", opacity=0.5,
                       annotation_text=f"Spot ${spot:.0f}")

    fig_skew.update_layout(
        title=f"IV Smile / Skew — {selected_expiry}",
        xaxis_title="Strike Price",
        yaxis_title="Implied Volatility (%)",
        height=500,
        template="plotly_dark",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    st.plotly_chart(fig_skew, use_container_width=True)

    st.caption("💡 **判讀**：典型 equity skew → OTM Put IV > ATM IV > OTM Call IV。偏離程度越大，市場對尾部風險定價越高。")
else:
    st.warning("無法計算 IV Skew。")

st.divider()

# ══════════════════════════════════════════════
# Section 2: Put-Call IV Differential
# ══════════════════════════════════════════════
st.subheader("📊 Put-Call IV 差異")

if not calls_skew.empty and not puts_skew.empty:
    # Merge on strike to compare put vs call IV
    merged = pd.merge(
        calls_skew[["strike", "iv"]].rename(columns={"iv": "call_iv"}),
        puts_skew[["strike", "iv"]].rename(columns={"iv": "put_iv"}),
        on="strike",
        how="inner",
    )
    merged["iv_diff"] = merged["put_iv"] - merged["call_iv"]
    merged["moneyness"] = merged["strike"] / spot

    if not merged.empty:
        fig_diff = go.Figure()

        colors = ["#ef4444" if d > 0 else "#22c55e" for d in merged["iv_diff"]]
        fig_diff.add_trace(go.Bar(
            x=merged["strike"],
            y=merged["iv_diff"],
            marker_color=colors,
            text=[f"{d:+.1f}%" for d in merged["iv_diff"]],
            textposition="outside",
            name="Put IV - Call IV",
        ))

        fig_diff.add_vline(x=spot, line_dash="dash", line_color="white", opacity=0.5,
                           annotation_text=f"Spot ${spot:.0f}")
        fig_diff.add_hline(y=0, line_color="gray", opacity=0.3)

        fig_diff.update_layout(
            title="Put IV - Call IV 差異（正值 = Put 溢價）",
            xaxis_title="Strike Price",
            yaxis_title="IV 差異 (%)",
            height=400,
            template="plotly_dark",
            showlegend=False,
        )
        st.plotly_chart(fig_diff, use_container_width=True)

        # Summary stats
        avg_diff = merged["iv_diff"].mean()
        max_diff_row = merged.loc[merged["iv_diff"].idxmax()]
        st.markdown(f"**平均 Put-Call IV 差異：** {avg_diff:+.1f}%")
        st.markdown(f"**最大 Put 溢價：** Strike ${max_diff_row['strike']:.0f}，差異 {max_diff_row['iv_diff']:+.1f}%")
else:
    st.info("需要同時有 Call 和 Put 數據才能計算差異。")

st.divider()

# ══════════════════════════════════════════════
# Section 3: OTM Overpricing Analysis
# ══════════════════════════════════════════════
st.subheader("💰 OTM 選擇權溢價統計")

with st.spinner("正在計算理論價格 vs 市場價格..."):
    overprice_data = []

    for label, df, opt_type in [("Call", calls_df, "call"), ("Put", puts_df, "put")]:
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

            # Determine OTM/ATM/ITM
            if opt_type == "call":
                moneyness_label = "OTM" if strike > spot * 1.02 else ("ITM" if strike < spot * 0.98 else "ATM")
            else:
                moneyness_label = "OTM" if strike < spot * 0.98 else ("ITM" if strike > spot * 1.02 else "ATM")

            # Theoretical price using model IV
            theo_price = bs_price(spot, strike, T, rfr, model_iv, opt_type)
            if theo_price > 0.01:
                overprice_pct = (mp / theo_price - 1) * 100
            else:
                overprice_pct = 0.0

            overprice_data.append({
                "strike": strike,
                "type": label,
                "moneyness": moneyness_label,
                "market_price": round(mp, 2),
                "theo_price": round(theo_price, 2),
                "overprice_pct": round(overprice_pct, 1),
            })

overprice_df = pd.DataFrame(overprice_data)

if not overprice_df.empty:
    # ── Summary metrics by moneyness ──
    summary = overprice_df.groupby("moneyness").agg(
        count=("overprice_pct", "count"),
        avg_overprice=("overprice_pct", "mean"),
        overpriced_count=("overprice_pct", lambda x: (x > 0).sum()),
    ).reset_index()
    summary["overpriced_ratio"] = (summary["overpriced_count"] / summary["count"] * 100).round(1)

    scol1, scol2, scol3 = st.columns(3)
    for i, (_, row) in enumerate(summary.iterrows()):
        col = [scol1, scol2, scol3][i % 3]
        col.metric(
            f"{row['moneyness']} 選擇權",
            f"溢價 {row['avg_overprice']:+.1f}%",
            f"{row['overpriced_ratio']:.0f}% 被高估 (n={row['count']})",
        )

    # ── OTM specific analysis ──
    otm_df = overprice_df[overprice_df["moneyness"] == "OTM"]
    if not otm_df.empty:
        otm_overpriced = (otm_df["overprice_pct"] > 0).sum()
        otm_total = len(otm_df)
        otm_ratio = otm_overpriced / otm_total * 100

        st.markdown("---")
        st.markdown(f"### 🎯 OTM 選擇權過度定價比例：**{otm_ratio:.1f}%** ({otm_overpriced}/{otm_total})")

        if otm_ratio > 50:
            st.success(f"📊 超過半數 OTM 選擇權市場價格 > 模型理論價格 — 市場對尾部風險可能過度定價，賣方可留意機會")
        else:
            st.info(f"📊 OTM 過度定價比例 {otm_ratio:.0f}% — 尾部風險定價相對合理")

    # ── Overprice scatter ──
    fig_op = go.Figure()

    for opt_type, color in [("Call", "#3b82f6"), ("Put", "#f59e0b")]:
        subset = overprice_df[overprice_df["type"] == opt_type]
        if subset.empty:
            continue

        marker_colors = ["#ef4444" if p > 0 else "#22c55e" for p in subset["overprice_pct"]]
        fig_op.add_trace(go.Scatter(
            x=subset["strike"],
            y=subset["overprice_pct"],
            mode="markers",
            name=opt_type,
            marker=dict(
                color=marker_colors,
                size=8,
                symbol="circle" if opt_type == "Call" else "diamond",
            ),
            hovertemplate=(
                f"{opt_type}<br>"
                "Strike: $%{x}<br>"
                "溢價: %{y:+.1f}%<br>"
                "<extra></extra>"
            ),
        ))

    fig_op.add_hline(y=0, line_color="gray", opacity=0.5)
    fig_op.add_vline(x=spot, line_dash="dash", line_color="white", opacity=0.5,
                     annotation_text=f"Spot ${spot:.0f}")
    fig_op.update_layout(
        title="市場價格 vs 理論價格 溢價率 (%)",
        xaxis_title="Strike Price",
        yaxis_title="溢價率 (%, 正=市場價>理論價)",
        height=450,
        template="plotly_dark",
    )
    st.plotly_chart(fig_op, use_container_width=True)

    # ── Full table ──
    with st.expander("📋 完整溢價明細表", expanded=False):
        display = overprice_df.rename(columns={
            "strike": "Strike",
            "type": "Type",
            "moneyness": "Moneyness",
            "market_price": "市場價",
            "theo_price": "理論價 (BS)",
            "overprice_pct": "溢價率 (%)",
        })
        st.dataframe(display, use_container_width=True, hide_index=True)

else:
    st.warning("無法計算溢價數據。")

st.divider()

# ══════════════════════════════════════════════
# Section 4: Aggregate Overpricing Stats
# ══════════════════════════════════════════════
st.subheader("📊 全鏈高估統計")

with st.spinner("正在分析整條 Chain..."):
    chain_analysis = analyze_chain_iv(ticker, selected_expiry)

if not chain_analysis.empty:
    overpriced_ratio = calc_overpriced_ratio(chain_analysis)
    sell_count = (chain_analysis["signal"] == "SELL").sum()
    buy_count = (chain_analysis["signal"] == "BUY").sum()
    total = len(chain_analysis)

    acol1, acol2, acol3 = st.columns(3)
    acol1.metric("SELL 訊號 (高估)", f"{sell_count}/{total}", f"{overpriced_ratio:.1f}%")
    acol2.metric("BUY 訊號 (低估)", f"{buy_count}/{total}", f"{buy_count/total*100:.1f}%")
    acol3.metric("市場定價偏差方向", "偏高估 🔴" if overpriced_ratio > 50 else "偏低估 🟢")

    # Pie chart
    fig_pie = go.Figure(data=[go.Pie(
        labels=["高估 (SELL)", "低估 (BUY)", "中性 (NEUTRAL)"],
        values=[sell_count, buy_count, total - sell_count - buy_count],
        marker_colors=["#ef4444", "#22c55e", "#6b7280"],
        hole=0.4,
    )])
    fig_pie.update_layout(
        title="全鏈訊號分布",
        height=350,
        template="plotly_dark",
    )
    st.plotly_chart(fig_pie, use_container_width=True)

    st.markdown(f"""
    > **結論**：在 {selected_expiry} 到期的 {total} 個選擇權合約中，
    > **{overpriced_ratio:.1f}%** 產生 SELL 訊號（市場 IV > 模型 IV + 門檻）。
    > 這{'表明市場傾向高估尾部風險，賣方可多留意。' if overpriced_ratio > 50 else '顯示市場定價相對合理。'}
    """)
else:
    st.warning("無法分析全鏈數據。")

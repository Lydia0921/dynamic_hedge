"""Dynamic Delta Hedging Dashboard — Multi-page entry point.

This is the home page. Sidebar ticker selection and shared session state live here.
Individual dashboard pages are in the pages/ directory.
"""

import streamlit as st
from trade_log import get_current_state, load_positions

st.set_page_config(page_title="動態 Delta 避險儀表板", layout="wide", page_icon="📊")

# ──────────────────────────────────────────────
# Shared session state initialization
# ──────────────────────────────────────────────
if "ticker" not in st.session_state:
    st.session_state.ticker = "PLTR"
    st.session_state.ticker_valid = True
    st.session_state.positions = load_positions("PLTR")
    saved_shares, saved_cash = get_current_state("PLTR")
    st.session_state.hedge_shares = saved_shares
    st.session_state.cash_balance = saved_cash
    st.session_state.hedge_shares_input = saved_shares
    st.session_state.cash_balance_input = saved_cash
    st.session_state.account_input_ticker = "PLTR"

# ──────────────────────────────────────────────
# Sidebar — Global Ticker Selector
# ──────────────────────────────────────────────
st.sidebar.header("⚙️ 設定 (Setup)")
ticker_input = st.sidebar.text_input("股票代碼 (Ticker)", value=st.session_state.ticker)

if st.sidebar.button("📡 載入標的"):
    from data import validate_ticker
    if validate_ticker(ticker_input.upper()):
        st.session_state.ticker = ticker_input.upper()
        st.session_state.ticker_valid = True
        st.session_state.positions = load_positions(ticker_input.upper())
        saved_shares, saved_cash = get_current_state(ticker_input.upper())
        st.session_state.hedge_shares = saved_shares
        st.session_state.cash_balance = saved_cash
        st.session_state.hedge_shares_input = saved_shares
        st.session_state.cash_balance_input = saved_cash
        st.session_state.account_input_ticker = ticker_input.upper()
        st.sidebar.success(f"✅ 已載入 {ticker_input.upper()}")
    else:
        st.session_state.ticker_valid = False
        st.sidebar.error(f"❌ 無法載入 {ticker_input.upper()}")

ticker = st.session_state.ticker

# ──────────────────────────────────────────────
# Home Page Content
# ──────────────────────────────────────────────
st.title("📊 選擇權賣方動態避險儀表板")
st.markdown(f"### 當前標的：**{ticker}**")

st.divider()

st.markdown("""
## 📑 頁面導覽

使用左側導航列切換頁面：

| 頁面 | 功能 |
|------|------|
| **📊 Delta Hedge** | 即時部位 Greeks、Delta 避險信號、情境分析、風險警示 |
| **📈 IV Analysis** | 市場 IV vs 模型 IV 比較、殘差分析、SELL/BUY 訊號 |
| **📉 IV Statistics** | IV Rank / Percentile、HV vs IV 走勢、賣方時機判斷 |
| **⚠️ Tail Risk** | IV Skew 曲線、OTM 溢價統計、尾部風險過度定價分析 |

---

### 賣方監控核心邏輯

1. **市場 IV > 模型 IV** → 正殘差 → **SELL 訊號**（選擇權被高估）
2. **IV Rank > 50%** → IV 處於歷史高位 → 賣方有利
3. **尾部風險過度定價** → OTM 選擇權溢價 → 賣方機會

> 💡 所有數據透過 yfinance 免費取得，無需 API Key。
""")

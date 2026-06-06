# 動態 Delta 避險儀表板

以 Streamlit 建構的選擇權賣方避險監控工具，整合即時 Delta 避險信號、IV 分析與尾部風險評估。資料來源為 yfinance，無需付費 API。

## 功能頁面

| 頁面 | 說明 |
|------|------|
| Delta 避險 | 即時投資組合希臘字母、Delta 中立避險信號、情境損益表、風險警示 |
| IV 分析 | 市場 IV 與模型 IV 比較、殘差型 SELL/BUY 訊號 |
| IV 統計 | IV Rank / Percentile、HV vs IV 走勢圖、賣方時機判斷 |
| 尾部風險 | IV Skew 曲線、OTM 溢價統計、尾部風險過度定價分析 |

## 啟動方式

```bash
pip install -r requirements.txt
streamlit run app.py
```

## 專案結構

```
├── app.py                  # 首頁與共用 session state
├── pages/
│   ├── 1_Delta_Hedge.py        # Delta 避險儀表板
│   ├── 2_IV_Analysis.py        # IV 模型 vs 市場
│   ├── 3_IV_Statistics.py      # IV Rank 與 HV 比較
│   └── 4_Tail_Risk.py          # Skew 與尾部風險分析
├── greeks.py               # Black-Scholes 定價與希臘字母計算
├── hedging.py              # Delta 避險信號引擎
├── volatility_model.py     # HV 估算、IV Rank、殘差信號
├── data.py                 # yfinance 資料擷取
├── trade_log.py            # 交易紀錄與部位持久化（CSV/JSON）
├── macro.py                # VIX、美債殖利率、S&P500 快照
├── config.py               # 全域常數（門檻值、時間視窗）
├── research_harness.py     # 短期選擇權策略回測 CLI
└── requirements.txt
```

## 核心邏輯

**Delta 避險信號**
- 以 Black-Scholes 計算所有期權部位的組合淨 Delta
- 當 |淨 Delta| 超過門檻值（預設 30），推薦應買入或賣出的股數
- 部位資料與交易紀錄儲存於本地 `trades/` 目錄

**IV 賣方訊號**
- 模型 IV = 歷史波動率 × 標記倍率（可設定）
- 殘差 = 市場 IV − 模型 IV；殘差 > +3% 觸發 SELL，< −3% 觸發 BUY
- IV Rank > 50% 代表 IV 處於歷史相對高位，對賣方有利

**回測工具**（`research_harness.py`）
```bash
python research_harness.py --ticker PLTR --strategy short_call --target-dte 30
python research_harness.py --sweep   # 網格搜尋 DTE / Delta / IV 標記倍率
```

## 參數設定

編輯 `config.py` 調整核心參數：

```python
DELTA_REBALANCE_THRESHOLD = 30   # 觸發再平衡的淨 Delta 門檻（股數）
GAMMA_WARNING_THRESHOLD   = 0.05
HV_WINDOWS                = [20, 30, 60]   # 歷史波動率回看視窗（交易日）
IV_RESIDUAL_THRESHOLD     = 0.03           # ±3% 殘差觸發訊號
IV_RANK_SELL_THRESHOLD    = 50             # IV Rank 百分位，高於此對賣方有利
```

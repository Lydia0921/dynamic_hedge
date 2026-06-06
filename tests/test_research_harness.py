from datetime import date
import unittest

import pandas as pd

from research_harness import (
    BacktestConfig,
    run_parameter_sweep,
    run_scenarios,
    run_short_option_backtest,
    summarize_backtest,
)


class ResearchHarnessTest(unittest.TestCase):
    def test_short_strangle_backtest_runs_on_synthetic_prices(self):
        dates = pd.bdate_range("2026-05-01", "2026-05-29")
        prices = pd.DataFrame(
            {"Close": [100 + i * 0.35 for i in range(len(dates))]},
            index=dates,
        )
        config = BacktestConfig(
            ticker="TEST",
            start=date(2026, 5, 1),
            end=date(2026, 5, 31),
            strategy="short_strangle",
            target_dte=30,
            contracts=1,
            hv_window=5,
        )

        legs, results = run_short_option_backtest(config, prices)
        scenarios = run_scenarios(results, legs, config)
        summary = summarize_backtest(results)

        self.assertEqual(len(legs), 2)
        self.assertEqual(len(results), len(dates))
        self.assertFalse(scenarios.empty)
        self.assertIn("final_pnl", summary)
        self.assertIn("hedge_trades", summary)

    def test_parameter_sweep_returns_ranked_summary(self):
        dates = pd.bdate_range("2026-05-01", "2026-05-29")
        prices = pd.DataFrame(
            {"Close": [100 + ((-1) ** i) * i * 0.2 for i in range(len(dates))]},
            index=dates,
        )
        config = BacktestConfig(
            ticker="TEST",
            start=date(2026, 5, 1),
            end=date(2026, 5, 31),
            contracts=1,
            hv_window=5,
        )

        sweep = run_parameter_sweep(
            config,
            prices,
            strategies=["short_call", "short_put"],
            target_dtes=[14, 21],
            target_deltas=[0.25],
            iv_markups=[1.0, 1.15],
        )

        self.assertEqual(len(sweep), 8)
        self.assertIn("strategy", sweep.columns)
        self.assertIn("final_pnl", sweep.columns)
        self.assertGreaterEqual(sweep["final_pnl"].iloc[0], sweep["final_pnl"].iloc[-1])


if __name__ == "__main__":
    unittest.main()

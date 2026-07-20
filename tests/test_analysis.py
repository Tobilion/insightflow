"""Unit tests for every function in services/analysis.py."""

import math
import unittest

import numpy as np
import pandas as pd

from insightflow.services import analysis
from insightflow.tests.fixtures import (
    ANOMALY_CLOSES,
    DRAWDOWN_CLOSES,
    SIMPLE_CLOSES,
    frame_from_closes,
)


class TestDailyReturns(unittest.TestCase):
    def test_known_returns(self):
        returns = analysis.daily_returns(frame_from_closes(SIMPLE_CLOSES))
        # 100 -> 110 -> 121 -> 133.1 is a clean +10% every day.
        self.assertTrue(math.isnan(returns.iloc[0]))
        for value in returns.iloc[1:]:
            self.assertAlmostEqual(value, 0.10, places=10)

    def test_first_value_is_nan_not_zero(self):
        returns = analysis.daily_returns(frame_from_closes([50.0, 55.0]))
        self.assertTrue(math.isnan(returns.iloc[0]))

    def test_accepts_bare_series(self):
        frame = frame_from_closes(SIMPLE_CLOSES)
        pd.testing.assert_series_equal(
            analysis.daily_returns(frame), analysis.daily_returns(frame["close"])
        )

    def test_sorts_unsorted_input(self):
        frame = frame_from_closes(SIMPLE_CLOSES).iloc[::-1]
        returns = analysis.daily_returns(frame).dropna()
        self.assertTrue((returns > 0).all())

    def test_missing_close_column_raises(self):
        with self.assertRaises(KeyError):
            analysis.daily_returns(pd.DataFrame({"price": [1.0, 2.0]}))


class TestLogReturns(unittest.TestCase):
    def test_log_of_ten_percent(self):
        returns = analysis.log_returns(frame_from_closes(SIMPLE_CLOSES))
        self.assertAlmostEqual(returns.iloc[1], math.log(1.1), places=10)

    def test_log_returns_are_additive(self):
        frame = frame_from_closes(SIMPLE_CLOSES)
        total = analysis.log_returns(frame).sum()
        self.assertAlmostEqual(total, math.log(133.1 / 100.0), places=10)


class TestRollingMean(unittest.TestCase):
    def test_partial_windows_are_nan(self):
        mean = analysis.rolling_mean(frame_from_closes([1, 2, 3, 4, 5]), window=3)
        self.assertEqual(mean.isna().sum(), 2)

    def test_known_average(self):
        mean = analysis.rolling_mean(frame_from_closes([1, 2, 3, 4, 5]), window=3)
        self.assertAlmostEqual(mean.iloc[2], 2.0)   # (1+2+3)/3
        self.assertAlmostEqual(mean.iloc[4], 4.0)   # (3+4+5)/3

    def test_window_of_one_is_the_price(self):
        frame = frame_from_closes(SIMPLE_CLOSES)
        mean = analysis.rolling_mean(frame, window=1)
        np.testing.assert_allclose(mean.to_numpy(), frame["close"].to_numpy())

    def test_invalid_window_raises(self):
        with self.assertRaises(ValueError):
            analysis.rolling_mean(frame_from_closes(SIMPLE_CLOSES), window=0)


class TestRollingVolatility(unittest.TestCase):
    def test_constant_returns_have_zero_volatility(self):
        # Constant +10% daily -> zero dispersion of returns.
        vol = analysis.rolling_volatility(frame_from_closes(SIMPLE_CLOSES), window=3)
        self.assertAlmostEqual(vol.dropna().iloc[-1], 0.0, places=12)

    def test_volatility_is_positive_when_returns_vary(self):
        vol = analysis.rolling_volatility(frame_from_closes([100, 110, 95, 130, 90]), window=3)
        self.assertGreater(vol.dropna().iloc[-1], 0)

    def test_annualization_scales_by_sqrt_252(self):
        frame = frame_from_closes([100, 110, 95, 130, 90, 140])
        plain = analysis.rolling_volatility(frame, window=4).dropna().iloc[-1]
        annual = analysis.rolling_volatility(frame, window=4, annualize=True).dropna().iloc[-1]
        self.assertAlmostEqual(annual, plain * math.sqrt(252), places=10)

    def test_window_below_two_raises(self):
        with self.assertRaises(ValueError):
            analysis.rolling_volatility(frame_from_closes(SIMPLE_CLOSES), window=1)


class TestMaxDrawdown(unittest.TestCase):
    def test_known_drawdown(self):
        # Peak 120 -> trough 60 is exactly -50%.
        self.assertAlmostEqual(
            analysis.max_drawdown(frame_from_closes(DRAWDOWN_CLOSES)), -0.5, places=10
        )

    def test_monotonic_rise_has_no_drawdown(self):
        self.assertAlmostEqual(
            analysis.max_drawdown(frame_from_closes(SIMPLE_CLOSES)), 0.0, places=12
        )

    def test_drawdown_is_never_positive(self):
        self.assertLessEqual(analysis.max_drawdown(frame_from_closes([5, 4, 9, 2, 8])), 0.0)

    def test_empty_input_is_nan(self):
        empty = frame_from_closes([]).astype(float)
        self.assertTrue(math.isnan(analysis.max_drawdown(empty)))

    def test_drawdown_series_matches_minimum(self):
        frame = frame_from_closes(DRAWDOWN_CLOSES)
        self.assertAlmostEqual(
            analysis.drawdown_series(frame).min(), analysis.max_drawdown(frame), places=12
        )


class TestFlagAnomalies(unittest.TestCase):
    def test_flags_the_single_planted_outlier(self):
        frame = frame_from_closes(ANOMALY_CLOSES)
        flags = analysis.flag_anomalies(frame, sigma=2.0)
        self.assertEqual(int(flags.sum()), 1)
        # Index 5 is the +30% jump from 104.06 to 135.00.
        self.assertTrue(bool(flags.iloc[5]))

    def test_result_is_boolean_with_no_nan(self):
        flags = analysis.flag_anomalies(frame_from_closes(ANOMALY_CLOSES))
        self.assertEqual(flags.dtype, bool)
        self.assertFalse(flags.isna().any())
        self.assertFalse(bool(flags.iloc[0]))  # first day has no return

    def test_constant_returns_flag_nothing(self):
        flags = analysis.flag_anomalies(frame_from_closes(SIMPLE_CLOSES))
        self.assertEqual(int(flags.sum()), 0)

    def test_flat_price_flags_nothing(self):
        flags = analysis.flag_anomalies(frame_from_closes([100.0] * 10))
        self.assertEqual(int(flags.sum()), 0)

    def test_higher_sigma_flags_fewer_days(self):
        frame = frame_from_closes([100, 104, 99, 130, 101, 98, 121, 99])
        loose = int(analysis.flag_anomalies(frame, sigma=1.0).sum())
        strict = int(analysis.flag_anomalies(frame, sigma=3.0).sum())
        self.assertGreaterEqual(loose, strict)

    def test_rolling_mode_is_usable_as_a_boolean_index(self):
        frame = frame_from_closes(ANOMALY_CLOSES)
        flags = analysis.flag_anomalies(frame, sigma=2.0, window=3)
        self.assertEqual(len(frame[flags]), int(flags.sum()))

    def test_non_positive_sigma_raises(self):
        with self.assertRaises(ValueError):
            analysis.flag_anomalies(frame_from_closes(SIMPLE_CLOSES), sigma=0)


class TestNormalizeAndCompare(unittest.TestCase):
    def test_normalize_starts_at_base(self):
        norm = analysis.normalize_to_base(frame_from_closes([250.0, 500.0]))
        self.assertAlmostEqual(norm.iloc[0], 100.0)
        self.assertAlmostEqual(norm.iloc[1], 200.0)

    def test_compare_rebases_every_column(self):
        frames = {
            "CHEAP": frame_from_closes([10.0, 11.0, 12.0]),
            "RICH": frame_from_closes([1000.0, 900.0, 1100.0]),
        }
        result = analysis.compare(frames)
        self.assertListEqual(list(result.columns), ["CHEAP", "RICH"])
        np.testing.assert_allclose(result.iloc[0].to_numpy(), [100.0, 100.0])
        self.assertAlmostEqual(result["CHEAP"].iloc[1], 110.0)
        self.assertAlmostEqual(result["RICH"].iloc[1], 90.0)

    def test_compare_aligns_on_shared_dates_only(self):
        frames = {
            "A": frame_from_closes([10, 11, 12], start="2026-01-05"),
            "B": frame_from_closes([20, 22, 24], start="2026-01-06"),
        }
        result = analysis.compare(frames)
        # A starts a day earlier; only the two overlapping days survive.
        self.assertEqual(len(result), 2)
        np.testing.assert_allclose(result.iloc[0].to_numpy(), [100.0, 100.0])

    def test_compare_of_nothing_is_empty(self):
        self.assertTrue(analysis.compare({}).empty)


class TestSummarizeAndEnrich(unittest.TestCase):
    def test_summary_numbers(self):
        stats = analysis.summarize(frame_from_closes(DRAWDOWN_CLOSES))
        self.assertEqual(stats["observations"], 5)
        self.assertAlmostEqual(stats["start_price"], 100.0)
        self.assertAlmostEqual(stats["end_price"], 80.0)
        self.assertAlmostEqual(stats["total_return"], -0.2, places=10)
        self.assertAlmostEqual(stats["max_drawdown"], -0.5, places=10)

    def test_summary_anomaly_count_matches_flags(self):
        frame = frame_from_closes(ANOMALY_CLOSES)
        stats = analysis.summarize(frame)
        self.assertEqual(stats["anomaly_count"], int(analysis.flag_anomalies(frame).sum()))
        self.assertEqual(len(stats["anomaly_dates"]), stats["anomaly_count"])

    def test_enrich_adds_columns_without_mutating_input(self):
        frame = frame_from_closes(ANOMALY_CLOSES)
        original_columns = list(frame.columns)
        enriched = analysis.enrich(frame, window=3)

        self.assertEqual(list(frame.columns), original_columns)
        for column in ("daily_return", "rolling_mean_3", "rolling_volatility_3", "drawdown", "anomaly"):
            self.assertIn(column, enriched.columns)
        self.assertEqual(len(enriched), len(frame))

    def test_enrich_columns_match_standalone_functions(self):
        frame = frame_from_closes(ANOMALY_CLOSES)
        enriched = analysis.enrich(frame, window=3)
        np.testing.assert_allclose(
            enriched["rolling_mean_3"].to_numpy(),
            analysis.rolling_mean(frame, 3).to_numpy(),
            equal_nan=True,
        )


if __name__ == "__main__":
    unittest.main()

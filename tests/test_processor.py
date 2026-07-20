"""Tests for the cleaning layer."""

import unittest

import pandas as pd

from insightflow.services.errors import DataFormatError
from insightflow.services.processor import DataProcessor
from insightflow.tests.fixtures import alpha_vantage_payload


class TestDataProcessor(unittest.TestCase):
    def test_process_stock_data_success(self):
        mock_json = {
            "Time Series (Daily)": {
                "2026-06-18": {
                    "1. open": "150.00",
                    "2. high": "155.00",
                    "3. low": "149.00",
                    "4. close": "154.00",
                    "5. volume": "1000000",
                }
            }
        }

        df = DataProcessor.process_stock_data(mock_json)

        self.assertIsInstance(df, pd.DataFrame)
        self.assertEqual(len(df), 1)
        self.assertIn("open", df.columns)
        self.assertEqual(df.loc["2026-06-18", "open"], 150.0)
        self.assertEqual(df.loc["2026-06-18", "close"], 154.0)

    def test_columns_are_named_by_key_not_position(self):
        # JSON objects carry no ordering guarantee, so positional naming is a bug
        # waiting to happen; the processor maps by key.
        payload = {
            "Time Series (Daily)": {
                "2026-06-18": {
                    "5. volume": "1000000",
                    "4. close": "154.00",
                    "1. open": "150.00",
                    "3. low": "149.00",
                    "2. high": "155.00",
                }
            }
        }
        df = DataProcessor.process_stock_data(payload)
        self.assertEqual(df.loc["2026-06-18", "close"], 154.0)
        self.assertEqual(df.loc["2026-06-18", "volume"], 1_000_000.0)

    def test_output_is_sorted_oldest_first(self):
        # The API returns newest-first; every rolling calculation needs ascending.
        payload = alpha_vantage_payload([100.0, 101.0, 102.0])
        df = DataProcessor.process_stock_data(payload)
        self.assertTrue(df.index.is_monotonic_increasing)
        self.assertEqual(df["close"].iloc[0], 100.0)
        self.assertEqual(df["close"].iloc[-1], 102.0)

    def test_all_columns_are_numeric(self):
        df = DataProcessor.process_stock_data(alpha_vantage_payload([100.0, 101.0]))
        for column in df.columns:
            self.assertTrue(pd.api.types.is_numeric_dtype(df[column]), column)

    def test_index_is_datetime(self):
        df = DataProcessor.process_stock_data(alpha_vantage_payload([100.0, 101.0]))
        self.assertIsInstance(df.index, pd.DatetimeIndex)

    def test_rows_with_unparseable_close_are_dropped(self):
        payload = alpha_vantage_payload([100.0, 101.0, 102.0])
        bad_date = sorted(payload["Time Series (Daily)"])[0]
        payload["Time Series (Daily)"][bad_date]["4. close"] = "n/a"
        df = DataProcessor.process_stock_data(payload)
        self.assertEqual(len(df), 2)

    def test_process_stock_data_invalid_format(self):
        with self.assertRaises(ValueError) as context:
            DataProcessor.process_stock_data({"Error Message": "Invalid API call"})
        self.assertIn("Invalid data format or API limit reached.", str(context.exception))

    def test_invalid_format_raises_typed_error(self):
        with self.assertRaises(DataFormatError):
            DataProcessor.process_stock_data({"Note": "rate limited"})

    def test_empty_series_raises(self):
        with self.assertRaises(DataFormatError):
            DataProcessor.process_stock_data({"Time Series (Daily)": {}})

    def test_non_dict_input_raises(self):
        with self.assertRaises(DataFormatError):
            DataProcessor.process_stock_data("not a payload")

    def test_symbol_from_payload(self):
        payload = alpha_vantage_payload([100.0], symbol="MSFT")
        self.assertEqual(DataProcessor.symbol_from_payload(payload), "MSFT")
        self.assertEqual(DataProcessor.symbol_from_payload({}, default="?"), "?")


if __name__ == "__main__":
    unittest.main()

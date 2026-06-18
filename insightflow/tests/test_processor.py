import unittest
import pandas as pd
from insightflow.services.processor import DataProcessor

class TestDataProcessor(unittest.TestCase):
    def test_process_stock_data_success(self):
        # Arrange
        mock_json = {
            "Time Series (Daily)": {
                "2026-06-18": {
                    "1. open": "150.00",
                    "2. high": "155.00",
                    "3. low": "149.00",
                    "4. close": "154.00",
                    "5. volume": "1000000"
                }
            }
        }

        # Act
        df = DataProcessor.process_stock_data(mock_json)

        # Assert
        self.assertIsInstance(df, pd.DataFrame)
        self.assertEqual(len(df), 1)
        self.assertIn("open", df.columns)
        self.assertEqual(df.loc["2026-06-18", "open"], 150.0)
        self.assertEqual(df.loc["2026-06-18", "close"], 154.0)

    def test_process_stock_data_invalid_format(self):
        # Arrange
        invalid_json = {"Error Message": "Invalid API call"}

        # Act & Assert
        with self.assertRaises(ValueError) as context:
            DataProcessor.process_stock_data(invalid_json)
        self.assertIn("Invalid data format or API limit reached.", str(context.exception))

if __name__ == "__main__":
    unittest.main()

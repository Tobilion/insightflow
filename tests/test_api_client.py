"""Tests for the data-source layer: demo mode and every API failure mode.

No test here touches the network. Live-mode tests patch ``requests.get``.
"""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import requests

from insightflow.services.api_client import (
    APIClient,
    DemoClient,
    available_sample_symbols,
    build_client,
)
from insightflow.services.errors import (
    DataFormatError,
    MissingAPIKeyError,
    NetworkError,
    RateLimitError,
    UnknownSymbolError,
)
from insightflow.services.processor import DataProcessor
from insightflow.tests.fixtures import (
    INFORMATION_RATE_LIMIT_PAYLOAD,
    RATE_LIMIT_PAYLOAD,
    UNKNOWN_SYMBOL_PAYLOAD,
    alpha_vantage_payload,
)


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"{self.status_code} error")

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class TestDemoMode(unittest.TestCase):
    """The claim: a fresh clone with no key and no network still works."""

    def test_samples_are_bundled_with_the_repo(self):
        symbols = available_sample_symbols()
        self.assertTrue(symbols, "No sample data found — demo mode would be broken.")
        self.assertIn("AAPL", symbols)

    def test_every_bundled_sample_survives_the_full_pipeline(self):
        for symbol in available_sample_symbols():
            with self.subTest(symbol=symbol):
                payload = DemoClient().fetch_stock_data(symbol)
                frame = DataProcessor.process_stock_data(payload)
                self.assertGreater(len(frame), 100)
                self.assertTrue(frame.index.is_monotonic_increasing)
                self.assertFalse(frame["close"].isna().any())

    def test_demo_client_makes_no_network_calls(self):
        with patch("requests.get", side_effect=AssertionError("network was used")) as mock_get:
            DemoClient().fetch_stock_data("AAPL")
        mock_get.assert_not_called()

    def test_demo_client_needs_no_api_key(self):
        with patch.dict("os.environ", {}, clear=True):
            payload = DemoClient().fetch_stock_data("MSFT")
        self.assertIn("Time Series (Daily)", payload)

    def test_symbol_is_case_insensitive(self):
        self.assertEqual(
            DemoClient().fetch_stock_data("aapl"), DemoClient().fetch_stock_data("AAPL")
        )

    def test_unknown_sample_lists_what_is_available(self):
        with self.assertRaises(UnknownSymbolError) as ctx:
            DemoClient().fetch_stock_data("NOPE")
        self.assertIn("AAPL", str(ctx.exception))

    def test_build_client_selects_demo(self):
        self.assertIsInstance(build_client(demo=True), DemoClient)
        self.assertIsInstance(build_client(demo=False, api_key="k"), APIClient)


class TestLiveClientFailureModes(unittest.TestCase):
    def setUp(self):
        self.client = APIClient(api_key="test-key")

    def test_missing_key_raises_before_any_request(self):
        with patch.dict("os.environ", {}, clear=True), patch("requests.get") as mock_get:
            with self.assertRaises(MissingAPIKeyError):
                APIClient().fetch_stock_data("AAPL")
        mock_get.assert_not_called()

    def test_rate_limit_note_is_detected(self):
        with patch("requests.get", return_value=FakeResponse(RATE_LIMIT_PAYLOAD)):
            with self.assertRaises(RateLimitError) as ctx:
                self.client.fetch_stock_data("AAPL")
        self.assertIn("5 calls per minute", str(ctx.exception))
        self.assertIn("5 calls/minute", ctx.exception.hint)

    def test_rate_limit_information_variant_is_detected(self):
        with patch("requests.get", return_value=FakeResponse(INFORMATION_RATE_LIMIT_PAYLOAD)):
            with self.assertRaises(RateLimitError):
                self.client.fetch_stock_data("AAPL")

    def test_unknown_symbol_is_detected(self):
        with patch("requests.get", return_value=FakeResponse(UNKNOWN_SYMBOL_PAYLOAD)):
            with self.assertRaises(UnknownSymbolError):
                self.client.fetch_stock_data("ZZZZ")

    def test_empty_series_is_treated_as_unknown_symbol(self):
        with patch("requests.get", return_value=FakeResponse({"Time Series (Daily)": {}})):
            with self.assertRaises(UnknownSymbolError):
                self.client.fetch_stock_data("ZZZZ")

    def test_no_network_raises_network_error(self):
        with patch("requests.get", side_effect=requests.exceptions.ConnectionError("no route")):
            with self.assertRaises(NetworkError):
                self.client.fetch_stock_data("AAPL")

    def test_timeout_raises_network_error(self):
        with patch("requests.get", side_effect=requests.exceptions.Timeout("timed out")):
            with self.assertRaises(NetworkError):
                self.client.fetch_stock_data("AAPL")

    def test_http_error_raises_network_error(self):
        with patch("requests.get", return_value=FakeResponse({}, status_code=503)):
            with self.assertRaises(NetworkError):
                self.client.fetch_stock_data("AAPL")

    def test_non_json_body_raises_data_format_error(self):
        with patch("requests.get", return_value=FakeResponse(ValueError("not json"))):
            with self.assertRaises(DataFormatError):
                self.client.fetch_stock_data("AAPL")

    def test_request_includes_a_timeout(self):
        payload = alpha_vantage_payload([100.0, 101.0])
        with patch("requests.get", return_value=FakeResponse(payload)) as mock_get:
            self.client.fetch_stock_data("TEST")
        self.assertIn("timeout", mock_get.call_args.kwargs)

    def test_successful_response_passes_through(self):
        payload = alpha_vantage_payload([100.0, 101.0], symbol="TEST")
        with patch("requests.get", return_value=FakeResponse(payload)):
            result = self.client.fetch_stock_data("TEST")
        self.assertEqual(len(result["Time Series (Daily)"]), 2)

    def test_every_error_carries_a_user_hint(self):
        for exc in (
            MissingAPIKeyError,
            RateLimitError,
            UnknownSymbolError,
            NetworkError,
            DataFormatError,
        ):
            with self.subTest(exc=exc.__name__):
                self.assertTrue(exc.hint)


class TestDemoClientDirectory(unittest.TestCase):
    def test_custom_samples_directory(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "XYZ.json"
            path.write_text(json.dumps(alpha_vantage_payload([1.0, 2.0], symbol="XYZ")))
            payload = DemoClient(samples_dir=tmp).fetch_stock_data("XYZ")
        self.assertEqual(len(payload["Time Series (Daily)"]), 2)


if __name__ == "__main__":
    unittest.main()

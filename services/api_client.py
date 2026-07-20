"""Data source for daily stock series.

Two implementations share one interface (``fetch_stock_data(symbol) -> dict``):

* :class:`APIClient` talks to Alpha Vantage.
* :class:`DemoClient` reads bundled JSON from ``data/samples``.

Both return the raw Alpha Vantage payload shape, so everything downstream --
the processor, the cache, the analysis layer -- is identical in demo and live
mode. Nothing above this module knows which one it is holding.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

from insightflow.services.errors import (
    DataFormatError,
    MissingAPIKeyError,
    NetworkError,
    RateLimitError,
    UnknownSymbolError,
)

load_dotenv()

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "data" / "samples"
TIME_SERIES_KEY = "Time Series (Daily)"


def available_sample_symbols() -> list[str]:
    """Tickers bundled with the repo, usable with no API key."""
    if not SAMPLES_DIR.is_dir():
        return []
    return sorted(p.stem for p in SAMPLES_DIR.glob("*.json") if not p.stem.startswith("_"))


def validate_payload(payload: dict, symbol: str) -> dict:
    """Turn Alpha Vantage's HTTP-200 error dialects into typed exceptions.

    Alpha Vantage does not use status codes for application errors. A throttled
    request, an unknown ticker, and a successful lookup all return 200; the
    difference is only in which top-level key is present.
    """
    if not isinstance(payload, dict):
        raise DataFormatError("Expected a JSON object from the API.")

    # Throttling has appeared under several different keys over the years.
    for key in ("Note", "Information", "Rate Limit"):
        message = payload.get(key)
        if message and ("frequency" in message.lower() or "rate limit" in message.lower()):
            raise RateLimitError(message)

    if "Error Message" in payload:
        raise UnknownSymbolError(
            f"'{symbol}' was rejected by the API: {payload['Error Message']}"
        )

    if TIME_SERIES_KEY not in payload:
        raise DataFormatError(f"Response did not contain '{TIME_SERIES_KEY}'.")

    if not payload[TIME_SERIES_KEY]:
        raise UnknownSymbolError(f"No price history returned for '{symbol}'.")

    return payload


class APIClient:
    """Live Alpha Vantage client."""

    def __init__(self, api_key: str | None = None, timeout: float = 10.0):
        self.base_url = "https://www.alphavantage.co/query"
        self._api_key = api_key
        self.timeout = timeout

    @property
    def api_key(self) -> str | None:
        return self._api_key or os.getenv("API_KEY")

    def fetch_stock_data(self, symbol: str) -> dict:
        key = self.api_key
        if not key:
            raise MissingAPIKeyError("No API key configured.")

        params = {"function": "TIME_SERIES_DAILY", "symbol": symbol, "apikey": key}
        try:
            response = requests.get(self.base_url, params=params, timeout=self.timeout)
            response.raise_for_status()
            payload = response.json()
        except requests.exceptions.RequestException as exc:
            raise NetworkError(f"Could not reach Alpha Vantage: {exc}") from exc
        except ValueError as exc:
            raise DataFormatError("API response was not valid JSON.") from exc

        return validate_payload(payload, symbol)


class DemoClient:
    """Offline client backed by JSON files committed to the repo.

    Makes ``git clone && python -m insightflow.main --demo`` a working app with
    no signup, no key, and no network.
    """

    def __init__(self, samples_dir: Path | str = SAMPLES_DIR):
        self.samples_dir = Path(samples_dir)

    def fetch_stock_data(self, symbol: str) -> dict:
        path = self.samples_dir / f"{symbol.strip().upper()}.json"
        if not path.is_file():
            available = ", ".join(available_sample_symbols()) or "none"
            raise UnknownSymbolError(
                f"No sample data for '{symbol}'. Bundled samples: {available}."
            )
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
        return validate_payload(payload, symbol)


def build_client(demo: bool = False, api_key: str | None = None):
    """Pick a client. The only place in the app that decides demo vs live."""
    return DemoClient() if demo else APIClient(api_key=api_key)

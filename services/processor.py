"""Turn a raw Alpha Vantage payload into a clean, analysis-ready DataFrame.

Cleaning only -- no statistics. Anything derived lives in ``analysis.py``.
"""

from __future__ import annotations

import pandas as pd

from insightflow.services.errors import DataFormatError

TIME_SERIES_KEY = "Time Series (Daily)"

COLUMN_MAP = {
    "1. open": "open",
    "2. high": "high",
    "3. low": "low",
    "4. close": "close",
    "5. volume": "volume",
}


class DataProcessor:
    @staticmethod
    def process_stock_data(json_data: dict) -> pd.DataFrame:
        """Parse the daily series into a float DataFrame indexed by date.

        The result is sorted oldest-first. Alpha Vantage returns newest-first,
        and every rolling/return calculation downstream assumes ascending order,
        so normalising it here means no other module has to remember to.
        """
        if not isinstance(json_data, dict) or TIME_SERIES_KEY not in json_data:
            raise DataFormatError("Invalid data format or API limit reached.")

        series = json_data[TIME_SERIES_KEY]
        if not series:
            raise DataFormatError("The daily time series was empty.")

        df = pd.DataFrame.from_dict(series, orient="index")
        df.index = pd.to_datetime(df.index)
        df.index.name = "date"

        # Prefer renaming by the API's own keys; fall back to positional naming
        # for payloads (or fixtures) that already use short column names.
        if set(COLUMN_MAP).issubset(df.columns):
            df = df.rename(columns=COLUMN_MAP)[list(COLUMN_MAP.values())]
        elif len(df.columns) == len(COLUMN_MAP):
            df.columns = list(COLUMN_MAP.values())
        else:
            raise DataFormatError(f"Unexpected columns in time series: {list(df.columns)}")

        df = df.apply(pd.to_numeric, errors="coerce")
        df = df.dropna(subset=["close"]).sort_index()

        if df.empty:
            raise DataFormatError("No usable rows after cleaning.")
        return df

    @staticmethod
    def symbol_from_payload(json_data: dict, default: str = "") -> str:
        """Read the ticker out of the payload's Meta Data block, if present."""
        meta = json_data.get("Meta Data", {}) if isinstance(json_data, dict) else {}
        return meta.get("2. Symbol", default)

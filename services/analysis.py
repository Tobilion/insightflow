"""Quantitative analysis over a cleaned OHLCV frame.

Every function here is pure: it takes a DataFrame (or Series) and returns a new
object without mutating its input and without touching the network, disk, or
Qt. That makes each one directly unit-testable against a fixture, which is why
this layer exists separately from the processor (cleaning) and the UI (display).

Input convention: a DataFrame indexed by ``DatetimeIndex`` ascending, with a
float ``close`` column -- exactly what ``DataProcessor.process_stock_data``
produces.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

DEFAULT_WINDOW = 20
DEFAULT_SIGMA = 2.0
TRADING_DAYS_PER_YEAR = 252


def _close(data: pd.DataFrame | pd.Series) -> pd.Series:
    """Accept either a full OHLCV frame or a bare close series."""
    if isinstance(data, pd.Series):
        series = data
    elif "close" in data.columns:
        series = data["close"]
    else:
        raise KeyError("Expected a 'close' column or a Series of closing prices.")
    return series.astype(float).sort_index()


def daily_returns(data: pd.DataFrame | pd.Series) -> pd.Series:
    """Simple day-over-day fractional return.

    The first observation has no prior day, so it is NaN rather than 0 -- an
    unknown return and a flat day are different facts and downstream std/mean
    calculations should not conflate them.
    """
    return _close(data).pct_change().rename("daily_return")


def log_returns(data: pd.DataFrame | pd.Series) -> pd.Series:
    """Log returns, which are additive over time and preferred for volatility."""
    close = _close(data)
    return np.log(close / close.shift(1)).rename("log_return")


def rolling_mean(data: pd.DataFrame | pd.Series, window: int = DEFAULT_WINDOW) -> pd.Series:
    """Trailing simple moving average of the close price.

    Uses ``min_periods=window`` so the first ``window - 1`` values are NaN
    instead of being averages of a partial, noisier window.
    """
    if window < 1:
        raise ValueError("window must be >= 1")
    return (
        _close(data)
        .rolling(window=window, min_periods=window)
        .mean()
        .rename(f"rolling_mean_{window}")
    )


def rolling_volatility(
    data: pd.DataFrame | pd.Series,
    window: int = DEFAULT_WINDOW,
    annualize: bool = False,
) -> pd.Series:
    """Rolling standard deviation of daily returns.

    Set ``annualize=True`` to scale by sqrt(252) for the conventional annual
    volatility figure.
    """
    if window < 2:
        raise ValueError("window must be >= 2 for a standard deviation")
    vol = daily_returns(data).rolling(window=window, min_periods=window).std()
    if annualize:
        vol = vol * np.sqrt(TRADING_DAYS_PER_YEAR)
    return vol.rename(f"rolling_volatility_{window}")


def max_drawdown(data: pd.DataFrame | pd.Series) -> float:
    """Largest peak-to-trough decline, as a negative fraction.

    -0.35 means the price fell 35% from its running high before recovering.
    Returns 0.0 for a series that never declined, and NaN for empty input.
    """
    close = _close(data).dropna()
    if close.empty:
        return float("nan")
    running_peak = close.cummax()
    return float((close / running_peak - 1.0).min())


def drawdown_series(data: pd.DataFrame | pd.Series) -> pd.Series:
    """Drawdown at every point in time, for plotting an underwater curve."""
    close = _close(data)
    return (close / close.cummax() - 1.0).rename("drawdown")


def flag_anomalies(
    data: pd.DataFrame | pd.Series,
    sigma: float = DEFAULT_SIGMA,
    window: int | None = None,
) -> pd.Series:
    """Boolean mask of days whose return is beyond +/- ``sigma`` deviations.

    ``window=None`` (default) measures each day against the standard deviation
    of the whole sample -- the right choice for "which days were unusual for
    this period?". Pass an integer ``window`` to measure each day against its
    own trailing window instead, which adapts to changing volatility regimes.

    Days with no computable return or deviation are False, never NaN, so the
    result is always safe to use as a boolean index.
    """
    if sigma <= 0:
        raise ValueError("sigma must be positive")

    returns = daily_returns(data)

    if window is None:
        std = returns.std()
        mean = returns.mean()
        if not np.isfinite(std) or std == 0:
            return pd.Series(False, index=returns.index, name="anomaly")
        deviation = (returns - mean).abs()
        flags = deviation > sigma * std
    else:
        rolling = returns.rolling(window=window, min_periods=window)
        std = rolling.std()
        mean = rolling.mean()
        flags = (returns - mean).abs() > sigma * std

    return flags.fillna(False).astype(bool).rename("anomaly")


def summarize(
    data: pd.DataFrame | pd.Series,
    window: int = DEFAULT_WINDOW,
    sigma: float = DEFAULT_SIGMA,
) -> dict:
    """Headline numbers for the results screen. Composed of the above only."""
    close = _close(data)
    returns = daily_returns(close)
    anomalies = flag_anomalies(close, sigma=sigma)
    vol = rolling_volatility(close, window=window)

    total_return = (
        float(close.iloc[-1] / close.iloc[0] - 1.0) if len(close) > 1 else float("nan")
    )

    return {
        "observations": int(len(close)),
        "start_date": close.index.min(),
        "end_date": close.index.max(),
        "start_price": float(close.iloc[0]) if len(close) else float("nan"),
        "end_price": float(close.iloc[-1]) if len(close) else float("nan"),
        "total_return": total_return,
        "mean_daily_return": float(returns.mean()),
        "annualized_volatility": float(returns.std() * np.sqrt(TRADING_DAYS_PER_YEAR)),
        "latest_rolling_volatility": (
            float(vol.dropna().iloc[-1]) if vol.notna().any() else float("nan")
        ),
        "max_drawdown": max_drawdown(close),
        "anomaly_count": int(anomalies.sum()),
        "anomaly_dates": list(anomalies[anomalies].index),
    }


def enrich(
    data: pd.DataFrame,
    window: int = DEFAULT_WINDOW,
    sigma: float = DEFAULT_SIGMA,
) -> pd.DataFrame:
    """Return a copy of the frame with all derived columns attached."""
    out = data.copy()
    out["daily_return"] = daily_returns(data)
    out[f"rolling_mean_{window}"] = rolling_mean(data, window)
    out[f"rolling_volatility_{window}"] = rolling_volatility(data, window)
    out["drawdown"] = drawdown_series(data)
    out["anomaly"] = flag_anomalies(data, sigma=sigma)
    return out


def normalize_to_base(data: pd.DataFrame | pd.Series, base: float = 100.0) -> pd.Series:
    """Rebase a price series so its first observation equals ``base``.

    This is what makes two tickers comparable on one axis: a $400 stock and a
    $40 stock both start at 100, so the chart shows relative performance rather
    than absolute price.
    """
    close = _close(data).dropna()
    if close.empty:
        return pd.Series(dtype=float, name="normalized")
    return (close / close.iloc[0] * base).rename("normalized")


def compare(
    series_by_symbol: dict[str, pd.DataFrame | pd.Series], base: float = 100.0
) -> pd.DataFrame:
    """Align several tickers on a shared date index, each rebased to ``base``.

    Rebasing happens *after* the join so every series starts at ``base`` on the
    same first common date -- rebasing first would misalign tickers whose
    histories begin on different days.
    """
    if not series_by_symbol:
        return pd.DataFrame()

    joined = pd.DataFrame({sym: _close(d) for sym, d in series_by_symbol.items()})
    joined = joined.dropna(how="any")
    if joined.empty:
        return joined
    return joined.divide(joined.iloc[0]).multiply(base)
